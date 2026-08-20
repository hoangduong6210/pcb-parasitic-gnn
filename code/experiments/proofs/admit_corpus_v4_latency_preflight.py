#!/usr/bin/env python3
"""Authenticate the exact three-task latency preflight and authorize full execution."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_latency_contract import (  # noqa: E402
    PREFLIGHT_ADMISSION_SCHEMA,
    PREFLIGHT_TASK_IDS,
    load_json,
    resolve_descendant_path,
    validate_execution_lock,
    validate_plan,
    validate_preflight_admission_payload,
    validate_protocol,
    validate_root_closure,
    validate_terminal_array_completion,
)
from finalize_corpus_v4_latency import validate_timing_record  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


SACCT_FIELDS = (
    "JobID",
    "JobIDRaw",
    "Account",
    "State",
    "ExitCode",
    "ElapsedRaw",
    "ReqTRES",
    "AllocTRES",
    "Partition",
    "Timelimit",
    "NodeList",
    "Restarts",
)


def _parse_sacct(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) != len(SACCT_FIELDS):
            raise ValueError("sacct row field count differs from the admission query")
        records.append(dict(zip(SACCT_FIELDS, values)))
    return records


def _query_sacct(array_job_id: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Query live scheduler state; production exposes no fixture path."""
    command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        array_job_id,
        f"--format={','.join(SACCT_FIELDS)}",
    ]
    query = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0:
        raise RuntimeError("sacct preflight admission query failed")
    rows = sorted(_parse_sacct(query.stdout), key=lambda row: row["JobID"])
    return rows, {
        "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(rows)),
        "command": command,
        "queried_utc": datetime.now(timezone.utc).isoformat(),
        "raw_stdout_sha256": sha256_bytes(query.stdout.encode("utf-8")),
        "row_count": len(rows),
    }


def _source_head() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_source = subprocess.run(
        [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    if dirty or untracked_source:
        raise ValueError("preflight admission requires clean tracked source bytes")
    return head


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--expected-task-manifest-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--array-job-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.array_job_id.isdigit():
        raise ValueError("preflight array job ID must be numeric")
    if args.out.exists() or args.out.is_symlink():
        raise FileExistsError(args.out)

    protocol, protocol_sha = validate_protocol(
        args.protocol, args.expected_protocol_sha256
    )
    panel_path = args.plan.parent / "panel_records.jsonl"
    plan, tasks, panel, plan_sha, task_sha, panel_sha = validate_plan(
        args.plan,
        args.task_manifest,
        panel_path,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_task_manifest_sha256=args.expected_task_manifest_sha256,
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=args.plan,
        tasks=tasks,
        panel_records=panel,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock,
        args.expected_execution_lock_sha256,
        protocol_sha256=protocol_sha,
        plan_sha256=plan_sha,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    if _source_head() != args.expected_source_git_head:
        raise ValueError("preflight admission source commit differs")
    bindings = {
        "execution_lock_sha256": lock_sha,
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_sha,
    }
    expected_output_label = (
        "results/corpus_v4/latency/preflight/admission/"
        f"job_{args.array_job_id}/PREFLIGHT_ADMISSION.json"
    )
    expected_output = resolve_descendant_path(
        ROOT, expected_output_label, "preflight admission output"
    )
    if args.out.resolve() != expected_output.resolve():
        raise ValueError("preflight admission output path is not canonical")

    accounting, accounting_provenance = _query_sacct(args.array_job_id)
    if len(accounting) != len(PREFLIGHT_TASK_IDS):
        raise ValueError("preflight accounting row inventory is not exact")
    entries: list[dict[str, Any]] = []
    repeatability_reference: dict[str, str] | None = None
    for task_id in PREFLIGHT_TASK_IDS:
        manifest_path = (
            ROOT
            / "results/corpus_v4/latency/preflight/attempts"
            / f"job_{args.array_job_id}"
            / f"task_{task_id:03d}"
            / "TASK_MANIFEST.json"
        )
        manifest = load_json(manifest_path)
        result_path = manifest_path.parent / "result.json"
        result = load_json(result_path)
        observed_repeatability_reference = result.get("bindings", {}).get(
            "fem_repeatability_admission"
        )
        if (
            not isinstance(observed_repeatability_reference, dict)
            or set(observed_repeatability_reference) != {"path", "sha256"}
        ):
            raise ValueError(
                f"preflight task {task_id} lacks exact FEM repeatability binding"
            )
        if repeatability_reference is None:
            repeatability_reference = dict(observed_repeatability_reference)
        elif observed_repeatability_reference != repeatability_reference:
            raise ValueError("preflight tasks bind different FEM repeatability receipts")
        validate_timing_record(
            result.get("record", {}),
            expected_repetitions=int(protocol["gnn_timing"]["measured_repetitions"]),
        )
        completion = validate_terminal_array_completion(
            result.get("provenance", {}).get("scheduler", {}), accounting
        )
        if completion is None:
            raise ValueError(
                f"preflight task {task_id} lacks exact COMPLETED/0:0 accounting"
            )
        entries.append(
            {
                "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256_file(manifest_path),
                "result_sha256": sha256_file(result_path),
                "scheduler_completion": completion,
                "task_id": task_id,
            }
        )

    if repeatability_reference is None:
        raise ValueError("preflight admission lacks FEM repeatability binding")
    payload = {
        "accounting_provenance": accounting_provenance,
        "bindings": bindings,
        "claim_eligible": False,
        "entries": entries,
        "expected_task_ids": list(PREFLIGHT_TASK_IDS),
        "fem_repeatability_admission": repeatability_reference,
        "full_array_authorized": True,
        "n_accepted": len(entries),
        "n_expected": len(PREFLIGHT_TASK_IDS),
        "preflight_array_job_id": args.array_job_id,
        "schema": PREFLIGHT_ADMISSION_SCHEMA,
        "source_git_head": args.expected_source_git_head,
        "status": "admitted-for-full-array",
        "validator_source_sha256": lock["source_sha256"][
            "code/experiments/proofs/admit_corpus_v4_latency_preflight.py"
        ],
    }
    validate_preflight_admission_payload(
        payload,
        bindings=bindings,
        expected_source_git_head=args.expected_source_git_head,
        tasks=tasks,
        lock=lock,
        checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
        require_live_fem_accounting=True,
    )
    args.out.parent.mkdir(parents=True, exist_ok=False)
    atomic_write_json(args.out, payload)
    print(args.out.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
