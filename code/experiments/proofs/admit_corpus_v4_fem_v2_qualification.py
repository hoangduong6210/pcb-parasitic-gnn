#!/usr/bin/env python3
"""Create the solver-free postterminal admission for one FEM-v2 stage."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from run_corpus_v4_cps_multifidelity_task import parse_tres  # noqa: E402
from experiments_corpus_v4_fem_repeatability import (  # noqa: E402
    _assert_source_stable,
    _same_node_identity,
)
from finalize_corpus_v4_fem_v2_qualification import (  # noqa: E402
    ACCOUNTING_FIELDS,
    ACCOUNTING_PROVENANCE_SCHEMA,
    FINAL_MANIFEST_SCHEMA,
    FINAL_SCHEMA,
    FINALIZER_WRAPPERS,
    build_summary,
    classify_scientific_outcome,
    gate_a_result_from_prerequisite,
    load_tasks,
    parse_accounting,
    query_accounting,
    validate_terminal_accounting,
)
from run_corpus_v4_fem_v2_qualification import (  # noqa: E402
    ADMISSION_SCHEMA,
    NEXT_STAGE,
    OUTPUT_ROOT_RELATIVE,
    PROTOCOL_RELATIVE,
    STAGES,
    authenticate_protocol,
    canonical_output_root,
    is_sha256,
    repo_relative,
    stage_tasks,
    validate_inputs,
    validate_prerequisite,
)


JOB_ID_RE = re.compile(r"[1-9][0-9]*")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--finalizer-job-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path(OUTPUT_ROOT_RELATIVE))
    return parser.parse_args(argv)


def query_finalizer(
    job_id: str, *, attempts: int = 31, delay_s: float = 2.0
) -> tuple[dict[str, str], dict[str, Any]]:
    command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        job_id,
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]
    query: subprocess.CompletedProcess[str] | None = None
    rows: list[dict[str, str]] = []
    matches: list[dict[str, str]] = []
    for attempt in range(attempts):
        query = subprocess.run(command, capture_output=True, check=False, text=True)
        if query.returncode == 0:
            rows = parse_accounting(query.stdout)
            matches = [row for row in rows if row.get("JobID") == job_id]
            if len(rows) == 1 and len(matches) == 1:
                break
        if attempt + 1 < attempts:
            time.sleep(delay_s)
    if query is None or query.returncode != 0:
        raise RuntimeError("finalizer terminal accounting query failed")
    if len(rows) != 1 or len(matches) != 1:
        raise ValueError("finalizer accounting is not one exact main-job row")
    return matches[0], {
        "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(rows)),
        "command": command,
        "queried_utc": datetime.now(timezone.utc).isoformat(),
        "raw_stdout_sha256": sha256_bytes(query.stdout.encode("utf-8")),
        "row": matches[0],
    }


def validate_finalizer_terminal(
    row: Mapping[str, str],
    *,
    protocol: Mapping[str, Any],
    retained: Mapping[str, Any],
    finalizer_job_id: str,
) -> None:
    resource = protocol["resources"]["finalizer"]
    req = parse_tres(row.get("ReqTRES"))
    alloc = parse_tres(row.get("AllocTRES"))
    retained_record = retained.get("scheduler_record", {})
    allocated_cpus = alloc.get("cpu")
    if (
        row.get("JobID") != finalizer_job_id
        or row.get("JobIDRaw") != finalizer_job_id
        or row.get("State", "").split(maxsplit=1)[0].rstrip("+") != "COMPLETED"
        or row.get("ExitCode") != "0:0"
        or row.get("Account") != resource["account"]
        or row.get("Partition") != resource["partition"]
        or row.get("Timelimit") != resource["time_limit"]
        or row.get("Restarts") != "0"
        or not row.get("ElapsedRaw", "").isdigit()
        or req.get("cpu") != str(resource["requested_cpus_per_task"])
        or req.get("mem") != f"{resource['memory_gib']}G"
        or alloc.get("mem") != f"{resource['memory_gib']}G"
        or not str(alloc.get("cpu", "")).isdigit()
        or int(alloc["cpu"]) < int(resource["requested_cpus_per_task"])
        or retained.get("allocated_cpus_per_task") != int(allocated_cpus or 0)
        or retained.get("memory_mb") != int(resource["memory_gib"]) * 1024
        or retained.get("job_id") != finalizer_job_id
        or retained_record.get("JobId") != finalizer_job_id
        or retained_record.get("Account") != resource["account"]
        or retained_record.get("Partition") != resource["partition"]
        or retained_record.get("TimeLimit") != resource["time_limit"]
        or parse_tres(retained_record.get("ReqTRES")) != req
        or parse_tres(retained_record.get("AllocTRES")) != alloc
        or not _same_node_identity(retained_record.get("NodeList", ""), row.get("NodeList", ""))
    ):
        raise ValueError("finalizer did not satisfy the frozen postterminal contract")


def validate_preterminal_provenance(
    result: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    stage: str,
    source_git_head: str,
    input_bindings: Mapping[str, str],
    source_hashes: Mapping[str, str],
    live_accounting: Mapping[str, Any],
) -> None:
    provenance = result.get("provenance", {})
    if set(provenance) != {
        "accounting",
        "executed_batch_sha256",
        "finalizer_scheduler",
        "input_bindings",
        "source_git_head",
        "source_sha256",
    }:
        raise ValueError("preterminal provenance fields differ")
    if (
        provenance.get("executed_batch_sha256")
        != protocol["computational_sources"][FINALIZER_WRAPPERS[stage]]
        or provenance.get("input_bindings") != input_bindings
        or provenance.get("source_git_head") != source_git_head
        or provenance.get("source_sha256") != source_hashes
    ):
        raise ValueError("preterminal source provenance does not replay")

    retained = provenance.get("accounting", {})
    stable_fields = {
        "canonical_rows_sha256",
        "command",
        "origin",
        "raw_stdout_sha256",
        "row_count",
        "schema",
    }
    if (
        set(retained) != stable_fields | {"queried_utc"}
        or retained.get("schema") != ACCOUNTING_PROVENANCE_SCHEMA
        or any(retained.get(name) != live_accounting.get(name) for name in stable_fields)
        or not isinstance(retained.get("queried_utc"), str)
        or not retained["queried_utc"]
    ):
        raise ValueError("preterminal accounting provenance does not replay")


def load_preterminal(
    *,
    root: Path,
    stage: str,
    source_job_id: str,
    finalizer_job_id: str,
    protocol_sha256: str,
    source_git_head: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = (
        root
        / "final"
        / stage
        / f"source_job_{source_job_id}"
        / f"finalizer_job_{finalizer_job_id}"
    )
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("canonical preterminal directory is missing")
    result_path = directory / "result.json"
    manifest_path = directory / "FINAL_MANIFEST.json"
    if any(path.is_symlink() or not path.is_file() for path in (result_path, manifest_path)):
        raise ValueError("preterminal result or manifest is not a regular file")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if (
        set(manifest) != {
            "files_sha256",
            "finalizer_job_id",
            "protocol_sha256",
            "schema",
            "source_array_job_id",
            "stage",
        }
        or manifest.get("schema") != FINAL_MANIFEST_SCHEMA
        or manifest.get("files_sha256") != {"result.json": sha256_file(result_path)}
        or manifest.get("finalizer_job_id") != finalizer_job_id
        or manifest.get("source_array_job_id") != source_job_id
        or manifest.get("protocol_sha256") != protocol_sha256
        or manifest.get("stage") != stage
    ):
        raise ValueError("preterminal manifest does not bind the exact result")
    if (
        result.get("schema") != FINAL_SCHEMA
        or result.get("artifact_stage") != "preterminal_finalizer_output"
        or result.get("stage") != stage
        or result.get("protocol_sha256") != protocol_sha256
        or result.get("provenance", {}).get("source_git_head") != source_git_head
        or result.get("source_array", {}).get("array_job_id") != source_job_id
        or result.get("post_run_admission", {}).get("finalizer_job_id") != finalizer_job_id
        or result.get("admission_eligible") is not False
        or result.get("claim_eligible") is not False
        or result.get("speed_claim_eligible") is not False
    ):
        raise ValueError("preterminal result identity or eligibility differs")
    return result, {
        "manifest_path": repo_relative(manifest_path, "preterminal manifest"),
        "manifest_sha256": sha256_file(manifest_path),
        "result_path": repo_relative(result_path, "preterminal result"),
        "result_sha256": sha256_file(result_path),
    }


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if JOB_ID_RE.fullmatch(args.source_array_job_id) is None or JOB_ID_RE.fullmatch(args.finalizer_job_id) is None:
        raise SystemExit("source and finalizer job IDs must be positive decimals")
    root = canonical_output_root(args.output_root, "qualification admission root")
    protocol, protocol_sha256 = authenticate_protocol(
        args.protocol, args.expected_protocol_sha256
    )
    _, input_bindings = validate_inputs(protocol)
    source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=ROOT / PROTOCOL_RELATIVE,
        protocol_sha256=protocol_sha256,
    )
    result, binding = load_preterminal(
        root=root,
        stage=args.stage,
        source_job_id=args.source_array_job_id,
        finalizer_job_id=args.finalizer_job_id,
        protocol_sha256=protocol_sha256,
        source_git_head=args.expected_source_git_head,
    )
    accounting_row, accounting = query_finalizer(args.finalizer_job_id)
    validate_finalizer_terminal(
        accounting_row,
        protocol=protocol,
        retained=result["provenance"]["finalizer_scheduler"],
        finalizer_job_id=args.finalizer_job_id,
    )
    source_rows_raw, source_accounting = query_accounting(
        args.source_array_job_id,
        expected_rows=len(stage_tasks(protocol, args.stage)),
    )
    source_rows = validate_terminal_accounting(
        source_rows_raw,
        source_array_job_id=args.source_array_job_id,
        protocol=protocol,
        stage=args.stage,
    )
    if source_rows != result.get("source_array", {}).get("terminal_accounting"):
        raise ValueError("preterminal source accounting differs from live sacct")
    validate_preterminal_provenance(
        result,
        protocol=protocol,
        stage=args.stage,
        source_git_head=args.expected_source_git_head,
        input_bindings=input_bindings,
        source_hashes=source_hashes,
        live_accounting=source_accounting,
    )
    retained_prerequisite = result.get("prerequisite_admission")
    prerequisite = validate_prerequisite(
        stage=args.stage,
        path=(
            ROOT / retained_prerequisite["path"]
            if isinstance(retained_prerequisite, dict)
            else None
        ),
        expected_sha256=(
            retained_prerequisite.get("sha256")
            if isinstance(retained_prerequisite, dict)
            else None
        ),
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
        output_root=root,
    )
    all_source_success = all(row["terminal_success"] for row in source_rows)
    if all_source_success:
        try:
            payloads, artifacts = load_tasks(
                root=root,
                stage=args.stage,
                source_array_job_id=args.source_array_job_id,
                protocol=protocol,
                protocol_sha256=protocol_sha256,
                expected_source_git_head=args.expected_source_git_head,
                prerequisite=prerequisite,
                terminal_rows=source_rows,
                input_bindings=input_bindings,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError):
            replayed_pass = False
            replayed_outcome = "INDETERMINATE"
            if result.get("source_array", {}).get("artifacts") != []:
                raise ValueError("indeterminate preterminal output retained unexpected artifacts")
        else:
            if artifacts != result.get("source_array", {}).get("artifacts"):
                raise ValueError("preterminal artifact inventory does not replay")
            gate_a_result = None
            if prerequisite is not None:
                gate_a_result = gate_a_result_from_prerequisite(
                    args.stage,
                    ROOT / prerequisite["path"],
                    prerequisite["sha256"],
                    protocol_sha256,
                )
            replayed_summary = build_summary(args.stage, payloads, protocol, gate_a_result)
            if replayed_summary != result.get("qualification_summary"):
                raise ValueError("preterminal qualification summary does not replay")
            replayed_pass = replayed_summary.get("gate_pass") is True
            replayed_outcome = classify_scientific_outcome(
                args.stage, replayed_summary, replayed_pass
            )
    else:
        replayed_pass = False
        replayed_outcome = "INDETERMINATE"
        if result.get("source_array", {}).get("artifacts") != []:
            raise ValueError("indeterminate preterminal output retained unexpected artifacts")
    retained_decision = result.get("decision", {})
    if (
        retained_decision.get("all_source_tasks_completed_zero") is not all_source_success
        or retained_decision.get("provisional_qualification_stage_pass") is not replayed_pass
        or retained_decision.get("scientific_outcome") != replayed_outcome
        or retained_decision.get("provisional_multifidelity_v2_may_start")
        is not bool(args.stage == "gate_c" and replayed_pass)
        or retained_decision.get("provisional_r3_v2_generation_may_start")
        is not bool(args.stage == "gate_b" and replayed_pass)
    ):
        raise ValueError("preterminal decision does not replay")
    final_source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=ROOT / PROTOCOL_RELATIVE,
        protocol_sha256=protocol_sha256,
    )
    _, final_input_bindings = validate_inputs(protocol)
    if source_hashes != final_source_hashes or input_bindings != final_input_bindings:
        raise SystemExit("source or bound input changed during postterminal admission")

    provisional = retained_decision
    passed = provisional.get("provisional_qualification_stage_pass") is True
    scientific_outcome = provisional.get("scientific_outcome")
    if scientific_outcome not in {"POSITIVE", "SCIENTIFIC_NEGATIVE", "INDETERMINATE"}:
        raise ValueError("preterminal scientific outcome is malformed")
    next_stage = NEXT_STAGE[args.stage]
    admission = {
        "admission_eligible": passed,
        "artifact_stage": "postterminal_finalizer_admission",
        "claim_eligible": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "multifidelity_v2_may_start": bool(
                args.stage == "gate_c"
                and provisional.get("provisional_multifidelity_v2_may_start") is True
            ),
            "next_stage": next_stage,
            "next_stage_may_run": bool(passed and next_stage is not None),
            "qualification_stage_pass": passed,
            "r3_v2_generation_may_start": bool(
                args.stage == "gate_b"
                and provisional.get("provisional_r3_v2_generation_may_start") is True
            ),
            "scientific_outcome": scientific_outcome,
        },
        "finalizer_terminal_accounting": accounting,
        "preterminal_final": binding,
        "prerequisite_admission": result.get("prerequisite_admission"),
        "protocol_sha256": protocol_sha256,
        "schema": ADMISSION_SCHEMA,
        "source_git_head": args.expected_source_git_head,
        "speed_claim_eligible": False,
        "stage": args.stage,
    }
    target = (
        root
        / "admission"
        / args.stage
        / f"source_job_{args.source_array_job_id}"
        / f"finalizer_job_{args.finalizer_job_id}"
        / "FINAL_ADMISSION.json"
    )
    if target.exists():
        raise SystemExit("refusing to overwrite a qualification admission")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".FINAL_ADMISSION.", dir=target.parent)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        atomic_write_json(temporary_path, admission)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(json.dumps({"admission": repo_relative(target, "qualification admission"), "stage_pass": passed}, sort_keys=True))


if __name__ == "__main__":
    main()
