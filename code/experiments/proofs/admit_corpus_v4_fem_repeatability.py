#!/usr/bin/env python3
"""Admit one completed Corpus-v4 FEM-repeatability finalizer.

This command is deliberately solver-free.  It authenticates the frozen
protocol, clean source tree, immutable preterminal finalizer artifacts, and
the finalizer's terminal Slurm allocation.  It is the only artifact builder
allowed to open the paired-latency preflight after a positive provisional
repeatability decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from finalize_corpus_v4_fem_repeatability import (  # noqa: E402
    validate_protocol,
    validate_preterminal_payload,
)

VALIDATOR_SOURCE = "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py"
PROTOCOL_RELATIVE = "protocols/corpus_v4_fem_repeatability_v1.json"
FINAL_ROOT_RELATIVE = "results/corpus_v4/fem_repeatability/v1/final"
ADMISSION_ROOT_RELATIVE = "results/corpus_v4/fem_repeatability/v1/admission"

PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-protocol.v1"
FINAL_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-final.v1"
FINAL_MANIFEST_SCHEMA = (
    "pcb-gnn.corpus-v4-fem-repeatability-final-manifest.v1"
)
ADMISSION_SCHEMA = (
    "pcb-gnn.corpus-v4-fem-repeatability-final-admission.v1"
)

ACCOUNTING_FIELDS = (
    "JobID",
    "JobIDRaw",
    "State",
    "ExitCode",
    "Account",
    "Partition",
    "Timelimit",
    "NodeList",
    "Restarts",
    "ElapsedRaw",
    "ReqTRES",
    "AllocTRES",
)
EXPECTED_FINALIZER_RESOURCES = {
    "account": "pgs0407",
    "allocated_cpus_may_exceed_request": True,
    "cpus_per_task": 2,
    "memory_gib": 8,
    "nodes": 1,
    "ntasks": 1,
    "partition": "nextgen",
    "time_limit": "00:30:00",
}
EXPECTED_FINALIZER_REQUEST_TRES = {
    "billing": "2",
    "cpu": "2",
    "mem": "8G",
    "node": "1",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_HEAD_RE = re.compile(r"[0-9a-f]{40}")
JOB_ID_RE = re.compile(r"[1-9][0-9]*")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(PROTOCOL_RELATIVE),
    )
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--finalizer-job-id", required=True)
    return parser.parse_args(argv)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")


def sha256_file(path: Path, label: str) -> str:
    _require_regular_file(path, label)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    _require_regular_file(path, label)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are not exact")


def _resolve_repo_relative(value: str, label: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} is not a bounded repository-relative path")
    candidate = ROOT / relative
    _reject_symlink_ancestors(candidate)
    return candidate


def _canonical_protocol_path(path: Path) -> Path:
    canonical = ROOT / PROTOCOL_RELATIVE
    candidate = Path(os.path.abspath(path if path.is_absolute() else ROOT / path))
    if candidate != canonical:
        raise ValueError("repeatability admission requires the canonical protocol path")
    _reject_symlink_ancestors(candidate)
    return candidate


def _canonical_final_paths(
    source_array_job_id: str, finalizer_job_id: str
) -> tuple[Path, Path]:
    _require_job_id(source_array_job_id, "source array job ID")
    _require_job_id(finalizer_job_id, "finalizer job ID")
    directory = (
        ROOT
        / FINAL_ROOT_RELATIVE
        / f"source_job_{source_array_job_id}"
        / f"finalizer_job_{finalizer_job_id}"
    )
    _reject_symlink_ancestors(directory / "result.json")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("canonical preterminal final directory is missing")
    return directory / "result.json", directory / "FINAL_MANIFEST.json"


def canonical_admission_path(
    source_array_job_id: str, finalizer_job_id: str
) -> Path:
    _require_job_id(source_array_job_id, "source array job ID")
    _require_job_id(finalizer_job_id, "finalizer job ID")
    return (
        ROOT
        / ADMISSION_ROOT_RELATIVE
        / f"source_job_{source_array_job_id}"
        / f"finalizer_job_{finalizer_job_id}"
        / "FINAL_ADMISSION.json"
    )


def _require_sha256(value: str, label: str) -> str:
    if SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_git_head(value: str) -> str:
    if GIT_HEAD_RE.fullmatch(value) is None:
        raise ValueError("source Git head must be a lowercase 40-character commit")
    return value


def _require_job_id(value: str, label: str) -> str:
    if JOB_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a positive decimal identifier")
    return value


def _git_output(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed")
    return result.stdout


def authenticate_clean_source(expected_source_git_head: str) -> dict[str, str]:
    """Require a clean pinned commit and a tracked admission validator."""
    expected = _require_git_head(expected_source_git_head)
    observed = _git_output(["rev-parse", "HEAD"]).strip()
    if observed != expected:
        raise ValueError("repeatability admission source commit differs")
    if _git_output(["status", "--short", "--untracked-files=no"]).splitlines():
        raise ValueError("repeatability admission requires a clean tracked tree")
    untracked_source = _git_output(
        [
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        ]
    ).splitlines()
    if untracked_source:
        raise ValueError("repeatability admission rejects untracked source files")
    tracked_validator = _git_output(
        ["ls-files", "--error-unmatch", VALIDATOR_SOURCE]
    ).strip()
    if tracked_validator != VALIDATOR_SOURCE:
        raise ValueError("repeatability admission validator is not Git-tracked")
    validator_path = ROOT / VALIDATOR_SOURCE
    return {
        "source_git_head": observed,
        "validator_source_sha256": sha256_file(
            validator_path, "repeatability admission validator"
        ),
    }


def authenticate_protocol(
    path: Path, expected_protocol_sha256: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authenticate the canonical protocol and every frozen source/input byte."""
    expected = _require_sha256(
        expected_protocol_sha256, "repeatability protocol SHA-256"
    )
    protocol_path = _canonical_protocol_path(path)
    observed = sha256_file(protocol_path, "repeatability protocol")
    if observed != expected:
        raise ValueError("repeatability protocol SHA-256 differs from explicit pin")
    protocol = load_json_object(protocol_path, "repeatability protocol")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unexpected repeatability protocol schema")
    validate_protocol(protocol)
    if protocol.get("resources", {}).get("finalizer") != EXPECTED_FINALIZER_RESOURCES:
        raise ValueError("repeatability finalizer resources differ from admission contract")
    artifact_contract = protocol.get("artifact_contract", {})
    if (
        artifact_contract.get("terminal_accounting_required") is not True
        or artifact_contract.get("post_finalizer_terminal_admission_required")
        is not True
    ):
        raise ValueError("repeatability protocol does not require terminal accounting")
    semantics = protocol.get("diagnostic_semantics", {})
    if (
        semantics.get("claim_eligible") is not False
        or semantics.get("speed_claim_eligible") is not False
    ):
        raise ValueError("repeatability diagnostic eligibility was weakened")

    source_map = protocol.get("computational_sources")
    if not isinstance(source_map, dict) or not source_map:
        raise ValueError("repeatability computational source closure is missing")
    if VALIDATOR_SOURCE not in source_map:
        raise ValueError("repeatability admission validator is absent from source closure")
    observed_sources: dict[str, str] = {}
    for name, digest in source_map.items():
        if not isinstance(name, str):
            raise ValueError("repeatability computational source name is malformed")
        expected_digest = _require_sha256(
            digest, f"computational source SHA-256: {name}"
        )
        source_path = _resolve_repo_relative(name, "computational source")
        observed_digest = sha256_file(source_path, f"computational source: {name}")
        if observed_digest != expected_digest:
            raise ValueError(f"computational source SHA-256 mismatch: {name}")
        observed_sources[name] = observed_digest

    inputs = protocol.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError("repeatability input closure is missing")
    observed_inputs: dict[str, str] = {}
    for label, binding in inputs.items():
        if not isinstance(label, str) or not isinstance(binding, dict):
            raise ValueError("repeatability input binding is malformed")
        relative = binding.get("path")
        digest = binding.get("sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError(f"repeatability input binding is incomplete: {label}")
        expected_digest = _require_sha256(digest, f"input SHA-256: {label}")
        input_path = _resolve_repo_relative(relative, f"input: {label}")
        observed_digest = sha256_file(input_path, f"input: {label}")
        if observed_digest != expected_digest:
            raise ValueError(f"repeatability input SHA-256 mismatch: {label}")
        observed_inputs[label] = observed_digest

    return protocol, {
        "input_sha256": observed_inputs,
        "protocol_sha256": observed,
        "source_sha256": observed_sources,
    }


def validate_preterminal_final(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    finalizer_job_id: str,
) -> dict[str, Any]:
    """Bind the exact immutable preterminal result and its manifest."""
    _require_sha256(protocol_sha256, "repeatability protocol SHA-256")
    _require_git_head(expected_source_git_head)
    _require_job_id(source_array_job_id, "source array job ID")
    _require_job_id(finalizer_job_id, "finalizer job ID")
    result_path, manifest_path = _canonical_final_paths(
        source_array_job_id, finalizer_job_id
    )
    result_sha = sha256_file(result_path, "preterminal final result")
    manifest_sha = sha256_file(manifest_path, "preterminal final manifest")
    manifest = load_json_object(manifest_path, "preterminal final manifest")
    _require_exact_keys(
        manifest,
        {
            "files_sha256",
            "finalizer_job_id",
            "protocol_sha256",
            "schema",
            "source_array_job_id",
        },
        "preterminal final manifest",
    )
    if (
        manifest.get("schema") != FINAL_MANIFEST_SCHEMA
        or manifest.get("finalizer_job_id") != finalizer_job_id
        or manifest.get("protocol_sha256") != protocol_sha256
        or manifest.get("source_array_job_id") != source_array_job_id
        or manifest.get("files_sha256") != {"result.json": result_sha}
    ):
        raise ValueError("preterminal final manifest bindings differ")

    result = load_json_object(result_path, "preterminal final result")
    validate_preterminal_payload(
        result,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=expected_source_git_head,
        source_array_job_id=source_array_job_id,
        finalizer_job_id=finalizer_job_id,
        input_root=ROOT / "results/corpus_v4/fem_repeatability/v1",
    )
    _require_exact_keys(
        result,
        {
            "admission_eligible",
            "artifact_stage",
            "claim_eligible",
            "created_utc",
            "decision",
            "post_run_admission",
            "protocol_sha256",
            "provenance",
            "repeatability_summary",
            "schema",
            "source_array",
            "speed_claim_eligible",
        },
        "preterminal final result",
    )
    if (
        result.get("schema") != FINAL_SCHEMA
        or result.get("artifact_stage") != "preterminal_finalizer_output"
        or result.get("admission_eligible") is not False
        or result.get("claim_eligible") is not False
        or result.get("speed_claim_eligible") is not False
        or result.get("protocol_sha256") != protocol_sha256
    ):
        raise ValueError("preterminal final result identity or eligibility differs")

    post_run = result.get("post_run_admission")
    if post_run != {
        "finalizer_job_id": finalizer_job_id,
        "required": True,
        "required_exit_code": "0:0",
        "required_state": "COMPLETED",
        "terminal_accounting_verified": False,
    }:
        raise ValueError("preterminal post-run admission request differs")
    source_array = result.get("source_array")
    if (
        not isinstance(source_array, dict)
        or source_array.get("array_job_id") != source_array_job_id
    ):
        raise ValueError("preterminal source-array identity differs")

    decision = result.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("preterminal decision is missing")
    _require_exact_keys(
        decision,
        {
            "all_15_scheduler_rows_completed_zero",
            "arm_a_all_gates_pass",
            "paired_latency_preflight_may_resume",
            "provisional_preterminal_gate_pass",
        },
        "preterminal decision",
    )
    all_completed = decision.get("all_15_scheduler_rows_completed_zero")
    arm_a_pass = decision.get("arm_a_all_gates_pass")
    provisional = decision.get("provisional_preterminal_gate_pass")
    if (
        type(all_completed) is not bool
        or type(arm_a_pass) is not bool
        or type(provisional) is not bool
        or decision.get("paired_latency_preflight_may_resume") is not False
        or provisional is not (all_completed and arm_a_pass)
    ):
        raise ValueError("preterminal provisional decision is inconsistent")

    summary = result.get("repeatability_summary")
    summary_decision = summary.get("decision") if isinstance(summary, dict) else None
    if (
        not isinstance(summary_decision, dict)
        or summary_decision.get("paired_latency_preflight_may_resume") is not False
        or summary_decision.get("provisional_preterminal_gate_pass") is not provisional
        or summary_decision.get("terminal_accounting_gate_applied") is not True
        or summary_decision.get("arm_a_all_gates_pass") is not arm_a_pass
    ):
        raise ValueError("preterminal repeatability summary decision differs")

    provenance = result.get("provenance")
    scheduler = provenance.get("finalizer_scheduler") if isinstance(provenance, dict) else None
    scheduler_record = scheduler.get("scheduler_record") if isinstance(scheduler, dict) else None
    if (
        not isinstance(provenance, dict)
        or provenance.get("source_git_head") != expected_source_git_head
        or not isinstance(scheduler, dict)
        or scheduler.get("job_id") != finalizer_job_id
        or not isinstance(scheduler_record, dict)
    ):
        raise ValueError("preterminal finalizer provenance differs")
    retained_req_tres = parse_tres_exact(scheduler_record.get("ReqTRES", ""))
    retained_alloc_tres = parse_tres_exact(scheduler_record.get("AllocTRES", ""))
    _validate_finalizer_tres(
        retained_req_tres,
        retained_alloc_tres,
        label="preterminal finalizer provenance",
    )

    return {
        "final_manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "final_manifest_sha256": manifest_sha,
        "final_result_path": result_path.relative_to(ROOT).as_posix(),
        "final_result_sha256": result_sha,
        "finalizer_job_id": finalizer_job_id,
        "finalizer_scheduler_tres": {
            "AllocTRES": dict(sorted(retained_alloc_tres.items())),
            "ReqTRES": dict(sorted(retained_req_tres.items())),
        },
        "provisional_preterminal_gate_pass": provisional,
        "source_array_job_id": source_array_job_id,
    }


def parse_tres_exact(value: str) -> dict[str, str]:
    if not isinstance(value, str) or not value:
        raise ValueError("TRES map is empty")
    parsed: dict[str, str] = {}
    for token in value.split(","):
        if token.count("=") != 1:
            raise ValueError("TRES token is malformed")
        name, amount = token.split("=", 1)
        if not name or not amount or name in parsed:
            raise ValueError("TRES token is empty or duplicated")
        parsed[name] = amount
    return parsed


def _validate_finalizer_tres(
    requested: Mapping[str, str],
    allocated: Mapping[str, str],
    *,
    label: str,
) -> None:
    if dict(requested) != EXPECTED_FINALIZER_REQUEST_TRES:
        raise ValueError(f"{label} ReqTRES differs from exact 2-CPU/8G request")
    if set(allocated) != {"billing", "cpu", "mem", "node"}:
        raise ValueError(f"{label} AllocTRES fields are not exact")
    allocated_cpu = allocated.get("cpu", "")
    allocated_billing = allocated.get("billing", "")
    if (
        not allocated_cpu.isdigit()
        or int(allocated_cpu) < 2
        or allocated_billing != allocated_cpu
        or allocated.get("mem") != "8G"
        or allocated.get("node") != "1"
    ):
        raise ValueError(f"{label} AllocTRES is inconsistent with the finalizer allocation")


def parse_accounting(text: str) -> list[dict[str, str]]:
    """Parse exact pipe-delimited finalizer rows for pure unit tests."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) != len(ACCOUNTING_FIELDS):
            raise ValueError("sacct row field count differs from admission query")
        rows.append(dict(zip(ACCOUNTING_FIELDS, values)))
    return rows


def accounting_command(finalizer_job_id: str) -> list[str]:
    _require_job_id(finalizer_job_id, "finalizer job ID")
    return [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        finalizer_job_id,
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]


def query_live_finalizer_accounting(
    finalizer_job_id: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Query only the finalizer allocation; production exposes no fixture path."""
    command = accounting_command(finalizer_job_id)
    query = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0:
        raise RuntimeError("terminal finalizer accounting query failed")
    rows = parse_accounting(query.stdout)
    return rows, {
        "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(rows)),
        "command": command,
        "queried_utc": datetime.now(timezone.utc).isoformat(),
        "raw_stdout_sha256": sha256_bytes(query.stdout.encode("utf-8")),
        "row_count": len(rows),
    }


def validate_finalizer_accounting(
    rows: Sequence[Mapping[str, str]],
    finalizer_job_id: str,
    protocol: Mapping[str, Any],
    retained_scheduler_tres: Mapping[str, Any],
) -> dict[str, Any]:
    """Require one exact COMPLETED/0:0 finalizer allocation receipt."""
    _require_job_id(finalizer_job_id, "finalizer job ID")
    if len(rows) != 1:
        raise ValueError("finalizer accounting must contain exactly one row")
    row = dict(rows[0])
    if set(row) != set(ACCOUNTING_FIELDS):
        raise ValueError("finalizer accounting row fields differ")
    resources = protocol.get("resources", {}).get("finalizer")
    if resources != EXPECTED_FINALIZER_RESOURCES:
        raise ValueError("repeatability finalizer resources differ from admission contract")
    if (
        row.get("JobID") != finalizer_job_id
        or row.get("JobIDRaw") != finalizer_job_id
    ):
        raise ValueError("finalizer logical/raw job identity differs")
    if row.get("State") != "COMPLETED" or row.get("ExitCode") != "0:0":
        raise ValueError("finalizer did not terminate as exact COMPLETED/0:0")
    elapsed = row.get("ElapsedRaw", "")
    if (
        row.get("Account") != "pgs0407"
        or row.get("Partition") != "nextgen"
        or row.get("Timelimit") != "00:30:00"
        or not row.get("NodeList")
        or row.get("NodeList") in {"(null)", "None", "Unknown"}
        or row.get("Restarts") != "0"
        or not elapsed.isdigit()
        or not 1 <= int(elapsed) <= 1800
    ):
        raise ValueError("finalizer terminal scheduler identity differs")
    if set(retained_scheduler_tres) != {"ReqTRES", "AllocTRES"}:
        raise ValueError("preterminal finalizer TRES binding fields are not exact")
    requested = parse_tres_exact(row.get("ReqTRES", ""))
    allocated = parse_tres_exact(row.get("AllocTRES", ""))
    _validate_finalizer_tres(requested, allocated, label="terminal finalizer")
    parsed_tres = {
        "AllocTRES": dict(sorted(allocated.items())),
        "ReqTRES": dict(sorted(requested.items())),
    }
    if parsed_tres != retained_scheduler_tres:
        raise ValueError("terminal finalizer TRES differs from preterminal provenance")
    return {
        "row": {field: row[field] for field in ACCOUNTING_FIELDS},
        "tres": parsed_tres,
    }


def build_admission_payload(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    finalizer_job_id: str,
    final_reference: Mapping[str, Any],
    accounting_rows: Sequence[Mapping[str, str]],
    accounting_provenance: Mapping[str, Any],
    validator_source_sha256: str,
    created_utc: str,
) -> dict[str, Any]:
    """Pure receipt builder; tests may supply parsed accounting fixtures."""
    _require_sha256(protocol_sha256, "repeatability protocol SHA-256")
    _require_git_head(expected_source_git_head)
    _require_sha256(validator_source_sha256, "admission validator SHA-256")
    _require_job_id(source_array_job_id, "source array job ID")
    if not isinstance(created_utc, str) or not created_utc:
        raise ValueError("admission creation time is missing")
    expected_reference_keys = {
        "final_manifest_path",
        "final_manifest_sha256",
        "final_result_path",
        "final_result_sha256",
        "finalizer_job_id",
        "finalizer_scheduler_tres",
        "provisional_preterminal_gate_pass",
        "source_array_job_id",
    }
    _require_exact_keys(final_reference, expected_reference_keys, "preterminal reference")
    if (
        final_reference.get("source_array_job_id") != source_array_job_id
        or final_reference.get("finalizer_job_id") != finalizer_job_id
        or type(final_reference.get("provisional_preterminal_gate_pass")) is not bool
    ):
        raise ValueError("preterminal reference identity differs")
    for name in ("final_manifest_sha256", "final_result_sha256"):
        _require_sha256(str(final_reference.get(name, "")), name)
    terminal = validate_finalizer_accounting(
        accounting_rows,
        finalizer_job_id,
        protocol,
        final_reference["finalizer_scheduler_tres"],
    )

    expected_command = accounting_command(finalizer_job_id)
    if (
        set(accounting_provenance)
        != {
            "canonical_rows_sha256",
            "command",
            "queried_utc",
            "raw_stdout_sha256",
            "row_count",
        }
        or accounting_provenance.get("command") != expected_command
        or accounting_provenance.get("row_count") != 1
        or accounting_provenance.get("canonical_rows_sha256")
        != sha256_bytes(canonical_json_bytes(list(accounting_rows)))
        or not isinstance(accounting_provenance.get("queried_utc"), str)
        or not accounting_provenance.get("queried_utc")
    ):
        raise ValueError("finalizer accounting provenance differs from live query")
    _require_sha256(
        str(accounting_provenance.get("canonical_rows_sha256", "")),
        "canonical finalizer accounting SHA-256",
    )
    _require_sha256(
        str(accounting_provenance.get("raw_stdout_sha256", "")),
        "raw finalizer accounting SHA-256",
    )

    provisional = bool(final_reference["provisional_preterminal_gate_pass"])
    return {
        "artifact_stage": "postterminal_finalizer_admission",
        "claim_eligible": False,
        "created_utc": created_utc,
        "decision": {
            "paired_latency_preflight_may_resume": provisional,
            "provisional_preterminal_gate_pass": provisional,
            "terminal_finalizer_completed_zero": True,
        },
        "finalizer": {
            "accounting": terminal,
            "accounting_provenance": dict(accounting_provenance),
            "job_id": finalizer_job_id,
            "job_id_raw": terminal["row"]["JobIDRaw"],
        },
        "preterminal_final": dict(final_reference),
        "protocol_sha256": protocol_sha256,
        "schema": ADMISSION_SCHEMA,
        "source_git_head": expected_source_git_head,
        "speed_claim_eligible": False,
        "validator": {
            "path": VALIDATOR_SOURCE,
            "sha256": validator_source_sha256,
        },
    }


def validate_admission_payload(
    payload: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    finalizer_job_id: str,
    expected_validator_source_sha256: str,
    live_accounting_rows: Sequence[Mapping[str, str]] | None,
) -> dict[str, Any]:
    """Replay every receipt input and compare it with fresh terminal accounting."""
    _require_exact_keys(
        payload,
        {
            "artifact_stage",
            "claim_eligible",
            "created_utc",
            "decision",
            "finalizer",
            "preterminal_final",
            "protocol_sha256",
            "schema",
            "source_git_head",
            "speed_claim_eligible",
            "validator",
        },
        "final admission receipt",
    )
    _require_sha256(
        expected_validator_source_sha256,
        "expected final-admission validator SHA-256",
    )
    final_reference = validate_preterminal_final(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=expected_source_git_head,
        source_array_job_id=source_array_job_id,
        finalizer_job_id=finalizer_job_id,
    )
    if payload.get("preterminal_final") != final_reference:
        raise ValueError("final admission preterminal reference differs from live bytes")
    if payload.get("validator") != {
        "path": VALIDATOR_SOURCE,
        "sha256": expected_validator_source_sha256,
    }:
        raise ValueError("final admission validator binding differs")
    finalizer = payload.get("finalizer")
    if not isinstance(finalizer, Mapping):
        raise ValueError("final admission finalizer receipt is missing")
    accounting = finalizer.get("accounting")
    stored_row = accounting.get("row") if isinstance(accounting, Mapping) else None
    provenance = finalizer.get("accounting_provenance")
    if not isinstance(stored_row, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("final admission accounting receipt is incomplete")
    rebuilt = build_admission_payload(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=expected_source_git_head,
        source_array_job_id=source_array_job_id,
        finalizer_job_id=finalizer_job_id,
        final_reference=final_reference,
        accounting_rows=[dict(stored_row)],
        accounting_provenance=provenance,
        validator_source_sha256=expected_validator_source_sha256,
        created_utc=str(payload.get("created_utc", "")),
    )
    if rebuilt != dict(payload):
        raise ValueError("final admission receipt differs from deterministic replay")
    if live_accounting_rows is not None:
        live_terminal = validate_finalizer_accounting(
            live_accounting_rows,
            finalizer_job_id,
            protocol,
            final_reference["finalizer_scheduler_tres"],
        )
        if live_terminal != accounting:
            raise ValueError("final admission accounting differs from live sacct")
    return final_reference


def _reject_symlink_ancestors(path: Path) -> None:
    current = path.parent
    root = ROOT.resolve()
    while current != root:
        if current.exists() and current.is_symlink():
            raise ValueError("admission output has a symlink ancestor")
        if current.parent == current:
            raise ValueError("admission output is outside the repository")
        current = current.parent


def write_immutable_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish canonical JSON atomically without any overwrite window."""
    reference = payload.get("preterminal_final", {})
    expected = canonical_admission_path(
        str(reference.get("source_array_job_id", "")),
        str(reference.get("finalizer_job_id", "")),
    )
    if path != expected:
        raise ValueError("final admission output path is not canonical")
    _reject_symlink_ancestors(path)
    if path.exists() or path.is_symlink() or path.parent.exists():
        raise FileExistsError("refusing to overwrite an immutable final admission")
    path.parent.mkdir(parents=True, exist_ok=False)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".FINAL_ADMISSION.tmp-", dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        data = canonical_json_bytes(payload) + b"\n"
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        temporary = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        if path.parent.exists() and not any(path.parent.iterdir()):
            path.parent.rmdir()
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _require_job_id(args.source_array_job_id, "source array job ID")
        _require_job_id(args.finalizer_job_id, "finalizer job ID")
        source_identity = authenticate_clean_source(args.expected_source_git_head)
        protocol, protocol_identity = authenticate_protocol(
            args.protocol, args.expected_protocol_sha256
        )
        final_reference = validate_preterminal_final(
            protocol=protocol,
            protocol_sha256=protocol_identity["protocol_sha256"],
            expected_source_git_head=source_identity["source_git_head"],
            source_array_job_id=args.source_array_job_id,
            finalizer_job_id=args.finalizer_job_id,
        )
        rows, accounting_provenance = query_live_finalizer_accounting(
            args.finalizer_job_id
        )
        # Reauthenticate every mutable trust root after the scheduler query.
        final_source_identity = authenticate_clean_source(args.expected_source_git_head)
        _, final_protocol_identity = authenticate_protocol(
            args.protocol, args.expected_protocol_sha256
        )
        final_reference_after_query = validate_preterminal_final(
            protocol=protocol,
            protocol_sha256=final_protocol_identity["protocol_sha256"],
            expected_source_git_head=final_source_identity["source_git_head"],
            source_array_job_id=args.source_array_job_id,
            finalizer_job_id=args.finalizer_job_id,
        )
        if (
            final_source_identity != source_identity
            or final_protocol_identity != protocol_identity
            or final_reference_after_query != final_reference
        ):
            raise ValueError("repeatability admission trust roots changed during query")
        payload = build_admission_payload(
            protocol=protocol,
            protocol_sha256=protocol_identity["protocol_sha256"],
            expected_source_git_head=source_identity["source_git_head"],
            source_array_job_id=args.source_array_job_id,
            finalizer_job_id=args.finalizer_job_id,
            final_reference=final_reference,
            accounting_rows=rows,
            accounting_provenance=accounting_provenance,
            validator_source_sha256=source_identity["validator_source_sha256"],
            created_utc=datetime.now(timezone.utc).isoformat(),
        )
        validate_admission_payload(
            payload,
            protocol=protocol,
            protocol_sha256=protocol_identity["protocol_sha256"],
            expected_source_git_head=source_identity["source_git_head"],
            source_array_job_id=args.source_array_job_id,
            finalizer_job_id=args.finalizer_job_id,
            expected_validator_source_sha256=source_identity[
                "validator_source_sha256"
            ],
            live_accounting_rows=rows,
        )
        output = canonical_admission_path(
            args.source_array_job_id, args.finalizer_job_id
        )
        write_immutable_json(output, payload)
    except (json.JSONDecodeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"FEM repeatability final admission: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "artifact": output.relative_to(ROOT).as_posix(),
                "finalizer_job_id": args.finalizer_job_id,
                "paired_latency_preflight_may_resume": payload["decision"][
                    "paired_latency_preflight_may_resume"
                ],
                "source_array_job_id": args.source_array_job_id,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
