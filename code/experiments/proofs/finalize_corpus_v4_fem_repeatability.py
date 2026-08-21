#!/usr/bin/env python3
"""Finalize the fixed Corpus-v4 FEM repeatability panel under SLURM.

The finalizer is intentionally lightweight.  It authenticates the 15 source
array artifacts and terminal Slurm accounting, then applies the predeclared
finite-panel statistics.  It never imports or calls a field-solver entry point.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from experiments_corpus_v4_fem_repeatability import (  # noqa: E402
    ARM_SCHEMA,
    ATTEMPT_SCHEMA,
    MANIFEST_SCHEMA,
    _hardware_identity,
    _runtime_identity,
    arm_order,
    gmsh_thread_gate,
    parse_tres_exact,
    summarize_repeatability,
    task_mapping,
    validate_protocol,
)
from run_corpus_v4_cps_multifidelity_task import evaluate_result  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


FINAL_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-final.v1"
FINAL_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-final-manifest.v1"
EXPECTED_ARRAY_TASK_IDS = frozenset(range(15))
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
ACCOUNTING_PROVENANCE_SCHEMA = (
    "pcb-gnn.corpus-v4-fem-repeatability-accounting-provenance.v1"
)
TERMINAL_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "SPECIAL_EXIT",
    "TIMEOUT",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("protocols/corpus_v4_fem_repeatability_v1.json"),
    )
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("results/corpus_v4/fem_repeatability/v1"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/corpus_v4/fem_repeatability/v1/final"),
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _resolve_repo_path(path: Path | str, label: str) -> Path:
    value = Path(path)
    candidate = value.resolve() if value.is_absolute() else (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    return candidate


def _source_state() -> tuple[str, list[str], list[str]]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    tracked = subprocess.run(
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
    return head, tracked, untracked_source


def authenticate_source_and_bindings(
    *,
    protocol: Mapping[str, Any],
    protocol_path: Path,
    protocol_sha256: str,
    expected_source_git_head: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Authenticate every source/input byte and require a clean pinned commit."""
    head, dirty, untracked = _source_state()
    if head != expected_source_git_head or dirty or untracked:
        raise SystemExit("refusing repeatability finalization from changed source state")
    if sha256_file(protocol_path) != protocol_sha256:
        raise SystemExit("repeatability protocol changed during finalization")
    source_hashes = {
        name: sha256_file(_resolve_repo_path(name, "computational source"))
        for name in protocol["computational_sources"]
    }
    if source_hashes != protocol["computational_sources"]:
        raise SystemExit("finalizer computational source differs from protocol")
    bindings = {
        label: sha256_file(_resolve_repo_path(binding["path"], label))
        for label, binding in protocol["inputs"].items()
    }
    if bindings != {
        label: binding["sha256"] for label, binding in protocol["inputs"].items()
    }:
        raise SystemExit("finalizer input binding differs from protocol")
    return source_hashes, bindings


def _parse_scontrol(output: str) -> list[dict[str, str]]:
    return [
        {
            token.split("=", 1)[0]: token.split("=", 1)[1]
            for token in line.split()
            if "=" in token
        }
        for line in output.splitlines()
        if line.strip()
    ]


def validate_finalizer_slurm_allocation(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Authenticate the live non-array 2-CPU finalizer allocation."""
    required = (
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_ACCOUNT",
        "SLURM_JOB_ID",
        "SLURM_JOB_PARTITION",
        "SLURM_MEM_PER_NODE",
        "SLURMD_NODENAME",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"repeatability finalization is SLURM-only; missing {missing}")
    if any(os.environ.get(name) for name in ("SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")):
        raise SystemExit("repeatability finalizer must be a non-array Slurm job")
    resources = protocol["resources"]["finalizer"]
    requested_cpus = int(resources["cpus_per_task"])
    allocated_cpus = int(os.environ["SLURM_CPUS_PER_TASK"])
    observed = {
        "allocated_cpus_per_task": allocated_cpus,
        "job_account": os.environ["SLURM_JOB_ACCOUNT"],
        "job_id": os.environ["SLURM_JOB_ID"],
        "memory_mib": int(os.environ["SLURM_MEM_PER_NODE"]),
        "partition": os.environ["SLURM_JOB_PARTITION"],
        "requested_cpus_per_task": requested_cpus,
        "slurmd_nodename": os.environ["SLURMD_NODENAME"],
    }
    if (
        observed["job_account"] != resources["account"]
        or observed["partition"] != resources["partition"]
        or observed["memory_mib"] != int(resources["memory_gib"]) * 1024
        or allocated_cpus < requested_cpus
        or resources.get("allocated_cpus_may_exceed_request") is not True
    ):
        raise SystemExit("finalizer SLURM environment differs from protocol")
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", observed["job_id"]],
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0 or not query.stdout.strip():
        raise SystemExit("active finalizer job is not confirmed by Slurm")
    matches = [
        record
        for record in _parse_scontrol(query.stdout)
        if record.get("JobId") == observed["job_id"]
    ]
    if len(matches) != 1:
        raise SystemExit("active finalizer scheduler record is missing or ambiguous")
    record = matches[0]
    expected_fields = {
        "Account": resources["account"],
        "CPUs/Task": str(allocated_cpus),
        "JobState": "RUNNING",
        "MinMemoryNode": "8G",
        "NodeList": observed["slurmd_nodename"],
        "NumCPUs": str(allocated_cpus),
        "NumTasks": "1",
        "Partition": resources["partition"],
        "TimeLimit": resources["time_limit"],
        "TresPerTask": "cpu=2",
    }
    if any(
        (
            not _node_names_match(record.get(name, ""), expected)
            if name == "NodeList"
            else record.get(name) != expected
        )
        for name, expected in expected_fields.items()
    ):
        raise SystemExit("live finalizer scheduler record differs from protocol")
    try:
        requested_tres = parse_tres_exact(record.get("ReqTRES", ""))
        allocated_tres = parse_tres_exact(record.get("AllocTRES", ""))
    except ValueError as exc:
        raise SystemExit("finalizer TRES map is malformed") from exc
    if requested_tres != {
        "billing": str(requested_cpus),
        "cpu": str(requested_cpus),
        "mem": "8G",
        "node": "1",
    }:
        raise SystemExit("finalizer ReqTRES differs from protocol")
    if allocated_tres != {
        "billing": str(allocated_cpus),
        "cpu": str(allocated_cpus),
        "mem": "8G",
        "node": "1",
    }:
        raise SystemExit("finalizer AllocTRES differs from live allocation")
    retained_fields = set(expected_fields) | {"ReqTRES", "AllocTRES"}
    retained_record = {name: record[name] for name in sorted(retained_fields)}
    return {**observed, "scheduler_record": retained_record}


def parse_accounting(text: str) -> list[dict[str, str]]:
    """Parse the exact pipe-delimited accounting query or a test fixture."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        # ``sacct -P`` emits one terminal delimiter.  Accept exactly that one
        # empty field, while retaining strict field-count rejection otherwise.
        if values and values[-1] == "":
            values.pop()
        if tuple(values) == ACCOUNTING_FIELDS:
            continue
        if len(values) != len(ACCOUNTING_FIELDS):
            raise ValueError("sacct row field count differs from finalizer query")
        rows.append(dict(zip(ACCOUNTING_FIELDS, values)))
    return rows


def _canonical_accounting_rows(rows: Sequence[Mapping[str, str]]) -> bytes:
    normalized = [
        {field: row[field] for field in ACCOUNTING_FIELDS}
        for row in rows
    ]
    return canonical_json_bytes(normalized)


def build_accounting_provenance(
    *,
    rows: Sequence[Mapping[str, str]],
    raw_text: str,
    origin: str,
    command: Sequence[str],
    queried_utc: str,
) -> dict[str, Any]:
    """Bind parsed rows to the exact raw pipe and its acquisition path."""
    if origin not in {"live_sacct", "test_fixture"}:
        raise ValueError("accounting provenance origin is unsupported")
    return {
        "canonical_rows_sha256": sha256_bytes(_canonical_accounting_rows(rows)),
        "command": list(command),
        "origin": origin,
        "queried_utc": queried_utc,
        "raw_stdout_sha256": sha256_bytes(raw_text.encode("utf-8")),
        "row_count": len(rows),
        "schema": ACCOUNTING_PROVENANCE_SCHEMA,
    }


def query_live_accounting(
    source_array_job_id: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Query terminal accounting; production has no fixture-backed path."""
    command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        source_array_job_id,
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]
    query = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0:
        raise RuntimeError("terminal source-array accounting query failed")
    rows = parse_accounting(query.stdout)
    provenance = build_accounting_provenance(
        rows=rows,
        raw_text=query.stdout,
        origin="live_sacct",
        command=command,
        queried_utc=datetime.now(timezone.utc).isoformat(),
    )
    return rows, provenance


def validate_source_accounting(
    rows: Sequence[Mapping[str, str]],
    source_array_job_id: str,
    protocol: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Keep failed terminal diagnostics, but gate resume on COMPLETED/0:0."""
    if not source_array_job_id.isdigit():
        raise ValueError("source array logical job ID must be decimal")
    indexed: dict[int, dict[str, Any]] = {}
    raw_job_ids: set[str] = set()
    resources = protocol["resources"]["source_array"]
    expected_tres = {"billing": "25", "cpu": "25", "mem": "48G", "node": "1"}
    for raw_row in rows:
        row = dict(raw_row)
        if set(row) != set(ACCOUNTING_FIELDS):
            raise ValueError("accounting row fields differ from finalizer query")
        match = re.fullmatch(re.escape(source_array_job_id) + r"_(\d+)", row.get("JobID", ""))
        if match is None:
            raise ValueError("accounting JobID is outside the exact source array")
        task_id = int(match.group(1))
        if task_id not in range(15) or task_id in indexed:
            raise ValueError("accounting task is out of range or duplicated")
        raw_job_id = row.get("JobIDRaw", "")
        if not raw_job_id.isdigit():
            raise ValueError("accounting JobIDRaw is malformed")
        if raw_job_id in raw_job_ids:
            raise ValueError("accounting JobIDRaw values are not unique")
        raw_job_ids.add(raw_job_id)
        normalized_state = row.get("State", "").split(maxsplit=1)[0].rstrip("+")
        if normalized_state not in TERMINAL_STATES:
            raise ValueError("source-array accounting is not terminal")
        if re.fullmatch(r"\d+:\d+", row.get("ExitCode", "")) is None:
            raise ValueError("source-array accounting ExitCode is malformed")
        elapsed_raw = row.get("ElapsedRaw", "")
        if (
            row.get("Account") != resources["account"]
            or row.get("Partition") != resources["partition"]
            or row.get("Timelimit") != resources["time_limit"]
            or not row.get("NodeList")
            or row.get("NodeList") in {"(null)", "None", "Unknown"}
            or row.get("Restarts") != "0"
            or not elapsed_raw.isdigit()
            or not 1 <= int(elapsed_raw) <= 7200
        ):
            raise ValueError("source-array accounting identity is malformed")
        for field in ("ReqTRES", "AllocTRES"):
            try:
                tres = parse_tres_exact(row.get(field, ""))
            except ValueError as exc:
                raise ValueError(f"source-array accounting {field} is malformed") from exc
            if tres != expected_tres:
                raise ValueError(f"source-array accounting {field} differs from protocol")
        indexed[task_id] = {
            **row,
            "array_task_id": task_id,
            "normalized_state": normalized_state,
            "terminal_success": normalized_state == "COMPLETED"
            and row["ExitCode"] == "0:0",
        }
    if set(indexed) != EXPECTED_ARRAY_TASK_IDS:
        raise ValueError("source-array accounting does not contain exactly tasks 0..14")
    if len(raw_job_ids) != len(EXPECTED_ARRAY_TASK_IDS):
        raise ValueError("accounting JobIDRaw values are not unique")
    return [indexed[index] for index in range(15)]


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are not exact")


def _node_names_match(first: str, second: str) -> bool:
    """Accept only an exact name or the same short host/FQDN identity."""
    return first == second or first.split(".", 1)[0] == second.split(".", 1)[0]


def _validate_retained_execution_provenance(
    *,
    provenance: Mapping[str, Any],
    accounting_row: Mapping[str, Any],
    protocol: Mapping[str, Any],
    source_array_job_id: str,
    task_id: int,
) -> None:
    """Reapply the complete source resource/runtime/hardware contract."""
    _require_exact_keys(
        provenance,
        {
            "executed_batch_sha256",
            "hardware",
            "hostname",
            "input_bindings",
            "protocol_sha256",
            "runtime",
            "scheduler",
            "source_git_head",
            "source_sha256",
        },
        "task provenance",
    )
    if provenance.get("runtime") != protocol["runtime"]:
        raise ValueError("task runtime identity differs from protocol")

    resources = protocol["resources"]["source_array"]
    scheduler = provenance.get("scheduler")
    if not isinstance(scheduler, dict):
        raise ValueError("task scheduler provenance is missing")
    _require_exact_keys(
        scheduler,
        {
            "array_job_id",
            "array_task_count",
            "array_task_id",
            "array_task_max",
            "array_task_min",
            "cpus_per_task",
            "job_account",
            "job_id",
            "memory",
            "partition",
            "scheduler_record",
            "slurmd_nodename",
        },
        "task scheduler provenance",
    )
    scheduler_record = scheduler.get("scheduler_record")
    if not isinstance(scheduler_record, dict):
        raise ValueError("task live scheduler record is missing")
    _require_exact_keys(
        scheduler_record,
        {
            "Account",
            "AllocTRES",
            "ArrayJobId",
            "ArrayTaskId",
            "ArrayTaskThrottle",
            "CPUs/Task",
            "JobId",
            "JobState",
            "MinMemoryNode",
            "NodeList",
            "NumCPUs",
            "NumTasks",
            "Partition",
            "ReqTRES",
            "TimeLimit",
            "TresPerTask",
        },
        "task live scheduler record",
    )
    expected_scheduler = {
        "array_job_id": source_array_job_id,
        "array_task_count": 15,
        "array_task_id": task_id,
        "array_task_max": 14,
        "array_task_min": 0,
        "cpus_per_task": int(resources["cpus_per_task"]),
        "job_account": resources["account"],
        "job_id": accounting_row["JobIDRaw"],
        "partition": resources["partition"],
    }
    if any(scheduler.get(name) != value for name, value in expected_scheduler.items()):
        raise ValueError("task scheduler provenance differs from terminal accounting")
    if not _node_names_match(
        str(scheduler.get("slurmd_nodename", "")),
        str(accounting_row["NodeList"]),
    ):
        raise ValueError("task scheduler node differs from terminal accounting")
    if scheduler.get("memory") not in {"49152", "48G", "49152M", "50331648K"}:
        raise ValueError("task retained memory differs from protocol")

    required_record = {
        "Account": resources["account"],
        "AllocTRES": "cpu=25,mem=48G,node=1,billing=25",
        "ArrayJobId": source_array_job_id,
        "ArrayTaskId": str(task_id),
        "ArrayTaskThrottle": str(resources["array_throttle"]),
        "CPUs/Task": str(resources["cpus_per_task"]),
        "JobId": accounting_row["JobIDRaw"],
        "JobState": "RUNNING",
        "MinMemoryNode": "48G",
        "NumCPUs": str(resources["cpus_per_task"]),
        "NumTasks": str(resources["ntasks"]),
        "Partition": resources["partition"],
        "ReqTRES": "cpu=25,mem=48G,node=1,billing=25",
        "TimeLimit": resources["time_limit"],
        "TresPerTask": f"cpu={resources['cpus_per_task']}",
    }
    for name, expected in required_record.items():
        if name in {"ReqTRES", "AllocTRES"}:
            continue
        if scheduler_record.get(name) != expected:
            raise ValueError("task live scheduler record differs from protocol")
    if not _node_names_match(
        str(scheduler_record.get("NodeList", "")),
        str(accounting_row["NodeList"]),
    ):
        raise ValueError("task live scheduler node differs from terminal accounting")
    expected_tres = {"billing": "25", "cpu": "25", "mem": "48G", "node": "1"}
    for field in ("ReqTRES", "AllocTRES"):
        try:
            retained_tres = parse_tres_exact(scheduler_record.get(field, ""))
        except ValueError as exc:
            raise ValueError(f"task retained {field} is malformed") from exc
        if retained_tres != expected_tres:
            raise ValueError(f"task retained {field} differs from protocol")

    hostname = provenance.get("hostname")
    if (
        not isinstance(hostname, str)
        or not hostname
        or not _node_names_match(hostname, accounting_row["NodeList"])
    ):
        raise ValueError("task hostname differs from terminal accounting node")
    hardware = provenance.get("hardware")
    if not isinstance(hardware, dict):
        raise ValueError("task hardware identity is missing")
    _require_exact_keys(
        hardware,
        {
            "affinity_cpu_count",
            "anonymous_class_sha256",
            "architecture",
            "cpu_model",
            "kernel",
        },
        "task hardware identity",
    )
    identity = {
        name: hardware[name]
        for name in ("affinity_cpu_count", "architecture", "cpu_model", "kernel")
    }
    if (
        type(identity["affinity_cpu_count"]) is not int
        or identity["affinity_cpu_count"] != int(resources["cpus_per_task"])
        or any(
            not isinstance(identity[name], str) or not identity[name]
            for name in ("architecture", "cpu_model", "kernel")
        )
        or hardware.get("anonymous_class_sha256")
        != sha256_bytes(canonical_json_bytes(identity))
    ):
        raise ValueError("task hardware identity is malformed or unbound")


def _validate_arm(
    arm_record: Mapping[str, Any],
    *,
    expected_arm: Mapping[str, Any],
    panel: Mapping[str, Any],
    repeat_id: int,
    order_position: int,
    cps_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    expected_keys = {
        "arm",
        "claim_eligible",
        "completed_utc",
        "execution",
        "execution_sha256",
        "frozen_reference",
        "geometry",
        "gmsh_thread_gate",
        "numerical_resource_gate",
        "old_reference_relative_drift",
        "old_reference_signed_relative_drift",
        "order_position",
        "repeat_id",
        "schema",
        "speed_claim_eligible",
        "worker_result",
        "worker_result_sha256",
    }
    _require_exact_keys(arm_record, expected_keys, "arm observation")
    if (
        arm_record.get("schema") != ARM_SCHEMA
        or arm_record.get("claim_eligible") is not False
        or arm_record.get("speed_claim_eligible") is not False
        or arm_record.get("arm") != expected_arm
        or arm_record.get("repeat_id") != repeat_id
        or arm_record.get("order_position") != order_position
        or arm_record.get("geometry")
        != {
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "layout_id": panel["layout_id"],
        }
        or arm_record.get("frozen_reference")
        != {"cps_pf": panel["frozen_r3_cps_pf"], "units": "pF"}
    ):
        raise ValueError("arm observation identity differs from frozen mapping")
    worker_result = arm_record.get("worker_result")
    execution = arm_record.get("execution")
    if not isinstance(worker_result, dict) or not isinstance(execution, dict):
        raise ValueError("arm raw worker result or execution is missing")
    if execution.get("worker_result") != worker_result:
        raise ValueError("arm execution and retained raw worker result differ")
    if sha256_bytes(canonical_json_bytes(worker_result)) != arm_record.get("worker_result_sha256"):
        raise ValueError("arm raw worker-result SHA-256 differs")
    if sha256_bytes(canonical_json_bytes(execution)) != arm_record.get("execution_sha256"):
        raise ValueError("arm raw execution SHA-256 differs")
    cps_pf = worker_result.get("cps_pf")
    if type(cps_pf) not in {int, float} or not math.isfinite(float(cps_pf)):
        raise ValueError("arm Cps observation is not finite")
    reference = float(panel["frozen_r3_cps_pf"])
    signed = (float(cps_pf) - reference) / max(abs(reference), 1e-12)
    absolute = abs(signed)
    if (
        not math.isclose(
            float(arm_record.get("old_reference_signed_relative_drift")),
            signed,
            rel_tol=1e-12,
            abs_tol=1e-15,
        )
        or not math.isclose(
            float(arm_record.get("old_reference_relative_drift")),
            absolute,
            rel_tol=1e-12,
            abs_tol=1e-15,
        )
    ):
        raise ValueError("arm frozen-reference drift differs from raw Cps")
    gate = arm_record.get("numerical_resource_gate")
    if not isinstance(gate, dict) or type(gate.get("pass")) is not bool:
        raise ValueError("arm numerical/resource gate is malformed")
    recomputed_gate = evaluate_result(
        dict(execution), dict(cps_protocol), "cps_fem_r3_p16"
    )
    if gate != recomputed_gate:
        raise ValueError("arm numerical/resource gate differs from raw recomputation")
    recomputed_thread_gate = gmsh_thread_gate(
        execution, int(expected_arm["gmsh_threads"])
    )
    if arm_record.get("gmsh_thread_gate") != recomputed_thread_gate:
        raise ValueError("arm Gmsh thread gate differs from child telemetry")
    if recomputed_thread_gate["pass"] is not True:
        raise ValueError("arm child Gmsh thread observation did not pass")
    return dict(arm_record)


def load_authenticated_observations(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    input_root: Path,
    accounting: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Authenticate exactly 15 task directories and return all 30 arms."""
    source_dir = input_root / "attempts" / f"job_{source_array_job_id}"
    if not source_dir.is_dir():
        raise ValueError("source repeatability attempt directory is missing")
    expected_dirs = {f"task_{task_id:02d}" for task_id in range(15)}
    source_entries = list(source_dir.iterdir())
    observed_dirs = {path.name for path in source_entries if path.is_dir()}
    if (
        observed_dirs != expected_dirs
        or any(path.is_file() or path.is_symlink() for path in source_entries)
    ):
        raise ValueError("source repeatability task-directory set is not exact")

    accounting_by_task = {int(row["array_task_id"]): dict(row) for row in accounting}
    expected_bindings = {
        label: binding["sha256"] for label, binding in protocol["inputs"].items()
    }
    expected_sources = dict(protocol["computational_sources"])
    expected_batch_sha = expected_sources["code/jobs/submit_corpus_v4_fem_repeatability.sh"]
    cps_protocol = _load_json(
        _resolve_repo_path(protocol["inputs"]["cps_protocol"]["path"], "Cps protocol")
    )
    observations: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for task_id in range(15):
        task_dir = source_dir / f"task_{task_id:02d}"
        expected_files = {
            "TASK_MANIFEST.json",
            "arm_a_threads25.json",
            "arm_b_threads1.json",
            "result.json",
            "started.json",
        }
        task_entries = list(task_dir.iterdir())
        if {path.name for path in task_entries if path.is_file()} != expected_files:
            raise ValueError("repeatability task file set is not exact")
        if any(path.is_dir() or path.is_symlink() for path in task_entries):
            raise ValueError("repeatability task contains an unexpected entry")
        manifest = _load_json(task_dir / "TASK_MANIFEST.json")
        _require_exact_keys(
            manifest, {"files_sha256", "protocol_sha256", "schema"}, "task manifest"
        )
        expected_manifest_files = expected_files - {"TASK_MANIFEST.json"}
        files_sha256 = manifest.get("files_sha256")
        if (
            manifest.get("schema") != MANIFEST_SCHEMA
            or manifest.get("protocol_sha256") != protocol_sha256
            or not isinstance(files_sha256, dict)
            or set(files_sha256) != expected_manifest_files
        ):
            raise ValueError("repeatability task manifest differs from protocol")
        for name, expected_hash in files_sha256.items():
            if sha256_file(task_dir / name) != expected_hash:
                raise ValueError("repeatability task file hash differs from manifest")

        panel, repeat_id = task_mapping(task_id, protocol)
        expected_order = arm_order(repeat_id, protocol)
        started = _load_json(task_dir / "started.json")
        _require_exact_keys(
            started,
            {
                "array_task_id",
                "arm_order",
                "claim_eligible",
                "input_bindings",
                "panel",
                "protocol_sha256",
                "repeat_id",
                "schema",
                "source_git_head",
                "source_sha256",
                "speed_claim_eligible",
                "started_utc",
            },
            "task start receipt",
        )
        if (
            started.get("array_task_id") != task_id
            or started.get("repeat_id") != repeat_id
            or started.get("panel") != panel
            or started.get("arm_order") != [arm["arm_id"] for arm in expected_order]
            or started.get("claim_eligible") is not False
            or started.get("speed_claim_eligible") is not False
            or started.get("protocol_sha256") != protocol_sha256
            or started.get("source_git_head") != expected_source_git_head
            or started.get("source_sha256") != expected_sources
            or started.get("input_bindings") != expected_bindings
        ):
            raise ValueError("task start receipt differs from frozen execution")

        result = _load_json(task_dir / "result.json")
        _require_exact_keys(
            result,
            {
                "admission_eligible",
                "arms",
                "claim_eligible",
                "completed_utc",
                "integrity",
                "provenance",
                "schema",
                "speed_claim_eligible",
                "task",
            },
            "task result",
        )
        expected_task = {
            "array_task_id": task_id,
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "latency_task_id": panel["latency_task_id"],
            "layout_id": panel["layout_id"],
            "repeat_id": repeat_id,
        }
        if (
            result.get("schema") != ATTEMPT_SCHEMA
            or result.get("admission_eligible") is not False
            or result.get("claim_eligible") is not False
            or result.get("speed_claim_eligible") is not False
            or result.get("task") != expected_task
        ):
            raise ValueError("task result identity differs from frozen mapping")
        provenance = result.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("task provenance is missing")
        if (
            provenance.get("executed_batch_sha256") != expected_batch_sha
            or provenance.get("input_bindings") != expected_bindings
            or provenance.get("protocol_sha256") != protocol_sha256
            or provenance.get("source_git_head") != expected_source_git_head
            or provenance.get("source_sha256") != expected_sources
        ):
            raise ValueError("task source/protocol/input provenance differs")

        accounting_row = accounting_by_task[task_id]
        _validate_retained_execution_provenance(
            provenance=provenance,
            accounting_row=accounting_row,
            protocol=protocol,
            source_array_job_id=source_array_job_id,
            task_id=task_id,
        )

        result_arms = result.get("arms")
        if not isinstance(result_arms, list) or len(result_arms) != 2:
            raise ValueError("task must retain exactly two arm observations")
        validated_arms: list[dict[str, Any]] = []
        for position, expected_arm in enumerate(expected_order):
            standalone = _load_json(task_dir / f"{expected_arm['arm_id']}.json")
            if standalone != result_arms[position]:
                raise ValueError("standalone and embedded arm observations differ")
            validated_arms.append(
                _validate_arm(
                    standalone,
                    expected_arm=expected_arm,
                    panel=panel,
                    repeat_id=repeat_id,
                    order_position=position,
                    cps_protocol=cps_protocol,
                )
            )
        expected_integrity = all(
            arm["numerical_resource_gate"]["pass"] is True
            and arm["gmsh_thread_gate"]["pass"] is True
            for arm in validated_arms
        )
        if result.get("integrity") != {"passed": expected_integrity}:
            raise ValueError("task integrity flag differs from retained arm gates")
        observations.extend(validated_arms)
        receipts.append(
            {
                "array_task_id": task_id,
                "artifact_manifest_sha256": sha256_file(task_dir / "TASK_MANIFEST.json"),
                "job_id": accounting_row["JobID"],
                "job_id_raw": accounting_row["JobIDRaw"],
                "result_sha256": sha256_file(task_dir / "result.json"),
                "scheduler_exit_code": accounting_row["ExitCode"],
                "scheduler_state": accounting_row["State"],
                "terminal_success": accounting_row["terminal_success"],
            }
        )
    return observations, receipts


def build_final_payload(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    finalizer_job_id: str,
    input_root: Path,
    accounting_rows: Sequence[Mapping[str, str]],
    accounting_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a preterminal diagnostic even when source tasks exited nonzero."""
    if not finalizer_job_id.isdigit():
        raise ValueError("finalizer logical job ID must be decimal")
    _require_exact_keys(
        accounting_provenance,
        {
            "canonical_rows_sha256",
            "command",
            "origin",
            "queried_utc",
            "raw_stdout_sha256",
            "row_count",
            "schema",
        },
        "accounting provenance",
    )
    if (
        accounting_provenance.get("schema") != ACCOUNTING_PROVENANCE_SCHEMA
        or accounting_provenance.get("origin") not in {"live_sacct", "test_fixture"}
        or accounting_provenance.get("row_count") != len(accounting_rows)
        or accounting_provenance.get("canonical_rows_sha256")
        != sha256_bytes(_canonical_accounting_rows(accounting_rows))
        or re.fullmatch(
            r"[0-9a-f]{64}", str(accounting_provenance.get("raw_stdout_sha256", ""))
        )
        is None
        or not isinstance(accounting_provenance.get("queried_utc"), str)
        or not accounting_provenance.get("queried_utc")
        or not isinstance(accounting_provenance.get("command"), list)
    ):
        raise ValueError("accounting provenance is malformed or unbound")
    expected_live_command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        source_array_job_id,
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]
    if (
        accounting_provenance.get("origin") == "live_sacct"
        and accounting_provenance.get("command") != expected_live_command
    ):
        raise ValueError("live accounting command differs from frozen query")
    accounting = validate_source_accounting(
        accounting_rows, source_array_job_id, protocol
    )
    observations, receipts = load_authenticated_observations(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=expected_source_git_head,
        source_array_job_id=source_array_job_id,
        input_root=input_root,
        accounting=accounting,
    )
    summary = summarize_repeatability(observations, protocol)
    scheduler_gate = all(row["terminal_success"] is True for row in accounting)
    arm_a_gate = summary["decision"]["arm_a_all_gates_pass"] is True
    may_resume = scheduler_gate and arm_a_gate
    summary["decision"]["paired_latency_preflight_may_resume"] = False
    summary["decision"]["provisional_preterminal_gate_pass"] = may_resume
    summary["decision"]["terminal_accounting_gate_applied"] = True
    return {
        "admission_eligible": False,
        "artifact_stage": "preterminal_finalizer_output",
        "claim_eligible": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "all_15_scheduler_rows_completed_zero": scheduler_gate,
            "arm_a_all_gates_pass": arm_a_gate,
            "paired_latency_preflight_may_resume": False,
            "provisional_preterminal_gate_pass": may_resume,
        },
        "post_run_admission": {
            "finalizer_job_id": finalizer_job_id,
            "required": True,
            "required_exit_code": "0:0",
            "required_state": "COMPLETED",
            "terminal_accounting_verified": False,
        },
        "protocol_sha256": protocol_sha256,
        "repeatability_summary": summary,
        "schema": FINAL_SCHEMA,
        "source_array": {
            "accounting": accounting,
            "accounting_provenance": dict(accounting_provenance),
            "array_job_id": source_array_job_id,
            "completed_zero_count": sum(
                row["terminal_success"] is True for row in accounting
            ),
            "task_receipts": receipts,
        },
        "speed_claim_eligible": False,
    }


def validate_preterminal_payload(
    payload: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    source_array_job_id: str,
    finalizer_job_id: str,
    input_root: Path,
) -> None:
    """Recompute the complete solver-free preterminal result before admission."""
    _require_exact_keys(
        payload,
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
        "preterminal payload",
    )
    if (
        payload.get("schema") != FINAL_SCHEMA
        or payload.get("artifact_stage") != "preterminal_finalizer_output"
        or payload.get("admission_eligible") is not False
        or payload.get("claim_eligible") is not False
        or payload.get("speed_claim_eligible") is not False
        or payload.get("protocol_sha256") != protocol_sha256
        or not isinstance(payload.get("created_utc"), str)
        or not payload.get("created_utc")
    ):
        raise ValueError("preterminal payload identity or eligibility differs")
    if payload.get("post_run_admission") != {
        "finalizer_job_id": finalizer_job_id,
        "required": True,
        "required_exit_code": "0:0",
        "required_state": "COMPLETED",
        "terminal_accounting_verified": False,
    }:
        raise ValueError("preterminal post-run admission request differs")

    source_array = payload.get("source_array")
    if not isinstance(source_array, dict):
        raise ValueError("preterminal source-array payload is missing")
    _require_exact_keys(
        source_array,
        {
            "accounting",
            "accounting_provenance",
            "array_job_id",
            "completed_zero_count",
            "task_receipts",
        },
        "preterminal source-array payload",
    )
    if source_array.get("array_job_id") != source_array_job_id:
        raise ValueError("preterminal source-array identity differs")
    stored_accounting = source_array.get("accounting")
    if not isinstance(stored_accounting, list):
        raise ValueError("preterminal source-array accounting is missing")
    raw_accounting = [
        {field: row[field] for field in ACCOUNTING_FIELDS}
        for row in stored_accounting
        if isinstance(row, dict) and set(ACCOUNTING_FIELDS) <= set(row)
    ]
    if len(raw_accounting) != len(stored_accounting):
        raise ValueError("preterminal source-array accounting fields differ")
    accounting_provenance = source_array.get("accounting_provenance")
    if not isinstance(accounting_provenance, dict):
        raise ValueError("preterminal source accounting provenance is missing")
    _require_exact_keys(
        accounting_provenance,
        {
            "canonical_rows_sha256",
            "command",
            "origin",
            "queried_utc",
            "raw_stdout_sha256",
            "row_count",
            "schema",
        },
        "preterminal source accounting provenance",
    )
    expected_command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        source_array_job_id,
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]
    if (
        accounting_provenance.get("schema") != ACCOUNTING_PROVENANCE_SCHEMA
        or accounting_provenance.get("origin") != "live_sacct"
        or accounting_provenance.get("command") != expected_command
        or accounting_provenance.get("row_count") != len(raw_accounting)
        or accounting_provenance.get("canonical_rows_sha256")
        != sha256_bytes(_canonical_accounting_rows(raw_accounting))
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(accounting_provenance.get("raw_stdout_sha256", "")),
        )
        is None
    ):
        raise ValueError("preterminal source accounting provenance is unbound")
    accounting = validate_source_accounting(
        raw_accounting, source_array_job_id, protocol
    )
    if accounting != stored_accounting:
        raise ValueError("preterminal source accounting derivation differs")
    observations, receipts = load_authenticated_observations(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=expected_source_git_head,
        source_array_job_id=source_array_job_id,
        input_root=input_root,
        accounting=accounting,
    )
    if source_array.get("task_receipts") != receipts:
        raise ValueError("preterminal task receipts differ from source artifacts")
    completed_zero = sum(row["terminal_success"] is True for row in accounting)
    if source_array.get("completed_zero_count") != completed_zero:
        raise ValueError("preterminal completed-task count differs")

    recomputed_summary = summarize_repeatability(observations, protocol)
    scheduler_gate = completed_zero == len(EXPECTED_ARRAY_TASK_IDS)
    arm_a_gate = recomputed_summary["decision"]["arm_a_all_gates_pass"] is True
    provisional = scheduler_gate and arm_a_gate
    recomputed_summary["decision"]["paired_latency_preflight_may_resume"] = False
    recomputed_summary["decision"]["provisional_preterminal_gate_pass"] = provisional
    recomputed_summary["decision"]["terminal_accounting_gate_applied"] = True
    stored_summary = payload.get("repeatability_summary")
    if not isinstance(stored_summary, dict):
        raise ValueError("preterminal repeatability summary is missing")
    recomputed_summary.pop("created_utc", None)
    comparable_stored_summary = dict(stored_summary)
    if not isinstance(comparable_stored_summary.pop("created_utc", None), str):
        raise ValueError("preterminal summary timestamp is missing")
    if comparable_stored_summary != recomputed_summary:
        raise ValueError("preterminal repeatability summary differs from recomputation")
    expected_decision = {
        "all_15_scheduler_rows_completed_zero": scheduler_gate,
        "arm_a_all_gates_pass": arm_a_gate,
        "paired_latency_preflight_may_resume": False,
        "provisional_preterminal_gate_pass": provisional,
    }
    if payload.get("decision") != expected_decision:
        raise ValueError("preterminal decision differs from recomputation")

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("preterminal finalizer provenance is missing")
    _require_exact_keys(
        provenance,
        {
            "executed_batch_sha256",
            "finalizer_hardware",
            "finalizer_hostname",
            "finalizer_runtime",
            "finalizer_scheduler",
            "input_bindings",
            "source_git_head",
            "source_sha256",
        },
        "preterminal finalizer provenance",
    )
    expected_sources = dict(protocol["computational_sources"])
    expected_inputs = {
        label: binding["sha256"] for label, binding in protocol["inputs"].items()
    }
    if (
        provenance.get("executed_batch_sha256")
        != expected_sources["code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh"]
        or provenance.get("source_git_head") != expected_source_git_head
        or provenance.get("source_sha256") != expected_sources
        or provenance.get("input_bindings") != expected_inputs
        or provenance.get("finalizer_runtime") != protocol["runtime"]
    ):
        raise ValueError("preterminal finalizer source/runtime binding differs")
    scheduler = provenance.get("finalizer_scheduler")
    if not isinstance(scheduler, dict):
        raise ValueError("preterminal finalizer scheduler is missing")
    _require_exact_keys(
        scheduler,
        {
            "allocated_cpus_per_task",
            "job_account",
            "job_id",
            "memory_mib",
            "partition",
            "requested_cpus_per_task",
            "scheduler_record",
            "slurmd_nodename",
        },
        "preterminal finalizer scheduler",
    )
    resources = protocol["resources"]["finalizer"]
    allocated_cpus = scheduler.get("allocated_cpus_per_task")
    if (
        type(allocated_cpus) is not int
        or allocated_cpus < int(resources["cpus_per_task"])
        or scheduler.get("requested_cpus_per_task") != int(resources["cpus_per_task"])
        or scheduler.get("job_account") != resources["account"]
        or scheduler.get("job_id") != finalizer_job_id
        or scheduler.get("memory_mib") != int(resources["memory_gib"]) * 1024
        or scheduler.get("partition") != resources["partition"]
    ):
        raise ValueError("preterminal finalizer scheduler identity differs")
    scheduler_record = scheduler.get("scheduler_record")
    if not isinstance(scheduler_record, dict):
        raise ValueError("preterminal finalizer scheduler record is missing")
    expected_record = {
        "Account": resources["account"],
        "CPUs/Task": str(allocated_cpus),
        "JobState": "RUNNING",
        "MinMemoryNode": f"{resources['memory_gib']}G",
        "NodeList": scheduler["slurmd_nodename"],
        "NumCPUs": str(allocated_cpus),
        "NumTasks": str(resources["ntasks"]),
        "Partition": resources["partition"],
        "TimeLimit": resources["time_limit"],
        "TresPerTask": f"cpu={resources['cpus_per_task']}",
    }
    for name, expected in expected_record.items():
        if name == "NodeList":
            valid = _node_names_match(str(scheduler_record.get(name, "")), str(expected))
        else:
            valid = scheduler_record.get(name) == expected
        if not valid:
            raise ValueError("preterminal finalizer scheduler record differs")
    requested_tres = parse_tres_exact(scheduler_record.get("ReqTRES", ""))
    allocated_tres = parse_tres_exact(scheduler_record.get("AllocTRES", ""))
    if requested_tres != {
        "billing": str(resources["cpus_per_task"]),
        "cpu": str(resources["cpus_per_task"]),
        "mem": f"{resources['memory_gib']}G",
        "node": str(resources["nodes"]),
    } or allocated_tres != {
        "billing": str(allocated_cpus),
        "cpu": str(allocated_cpus),
        "mem": f"{resources['memory_gib']}G",
        "node": str(resources["nodes"]),
    }:
        raise ValueError("preterminal finalizer TRES differs")
    hardware = provenance.get("finalizer_hardware")
    if not isinstance(hardware, dict):
        raise ValueError("preterminal finalizer hardware is missing")
    identity = {
        name: hardware.get(name)
        for name in ("affinity_cpu_count", "architecture", "cpu_model", "kernel")
    }
    if (
        identity["affinity_cpu_count"] != allocated_cpus
        or hardware.get("anonymous_class_sha256")
        != sha256_bytes(canonical_json_bytes(identity))
        or not _node_names_match(
            str(provenance.get("finalizer_hostname", "")),
            str(scheduler["slurmd_nodename"]),
        )
    ):
        raise ValueError("preterminal finalizer hardware or node binding differs")


def _atomic_final_directory(target: Path, payload: Mapping[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise SystemExit("refusing to overwrite an immutable repeatability final")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=str(target.parent))
    )
    try:
        result_path = temporary / "result.json"
        atomic_write_json(result_path, payload)
        atomic_write_json(
            temporary / "FINAL_MANIFEST.json",
            {
                "files_sha256": {"result.json": sha256_file(result_path)},
                "finalizer_job_id": payload["post_run_admission"]["finalizer_job_id"],
                "protocol_sha256": payload["protocol_sha256"],
                "schema": FINAL_MANIFEST_SCHEMA,
                "source_array_job_id": payload["source_array"]["array_job_id"],
            },
        )
        temporary.replace(target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def main() -> None:
    args = parse_args()
    environment_pins = {
        "protocol_sha256": os.environ.get(
            "PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256"
        ),
        "source_array_job_id": os.environ.get(
            "PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID"
        ),
        "source_git_head": os.environ.get("PCB_GNN_V4_SOURCE_COMMIT"),
    }
    cli_pins = {
        "protocol_sha256": args.expected_protocol_sha256,
        "source_array_job_id": args.source_array_job_id,
        "source_git_head": args.expected_source_git_head,
    }
    if environment_pins != cli_pins:
        raise SystemExit("finalizer environment and CLI pins differ")
    protocol_path = _resolve_repo_path(args.protocol, "repeatability protocol")
    protocol_sha256 = sha256_file(protocol_path)
    if protocol_sha256 != args.expected_protocol_sha256:
        raise SystemExit("repeatability protocol SHA-256 differs from explicit pin")
    protocol = _load_json(protocol_path)
    validate_protocol(protocol)
    finalizer_scheduler = validate_finalizer_slurm_allocation(protocol)
    finalizer_runtime = _runtime_identity(protocol)
    finalizer_hardware = _hardware_identity()
    if (
        finalizer_hardware.get("affinity_cpu_count")
        != finalizer_scheduler["allocated_cpus_per_task"]
        or not _node_names_match(
            socket.gethostname(), finalizer_scheduler["slurmd_nodename"]
        )
    ):
        raise SystemExit("finalizer hardware or node identity differs from allocation")
    source_hashes, bindings = authenticate_source_and_bindings(
        protocol=protocol,
        protocol_path=protocol_path,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
    )
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch_sha = protocol["computational_sources"][
        "code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh"
    ]
    if not executed_batch.is_file() or sha256_file(executed_batch) != expected_batch_sha:
        raise SystemExit("executed finalizer batch script differs from frozen source")
    accounting_rows, accounting_provenance = query_live_accounting(
        args.source_array_job_id
    )
    if accounting_provenance.get("origin") != "live_sacct":
        raise SystemExit("production finalization requires live sacct accounting")
    input_root = _resolve_repo_path(args.input_root, "repeatability input root")
    payload = build_final_payload(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
        source_array_job_id=args.source_array_job_id,
        finalizer_job_id=finalizer_scheduler["job_id"],
        input_root=input_root,
        accounting_rows=accounting_rows,
        accounting_provenance=accounting_provenance,
    )
    final_sources, final_bindings = authenticate_source_and_bindings(
        protocol=protocol,
        protocol_path=protocol_path,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
    )
    if final_sources != source_hashes or final_bindings != bindings:
        raise SystemExit("source or bindings changed during repeatability finalization")
    payload["provenance"] = {
        "executed_batch_sha256": expected_batch_sha,
        "finalizer_hardware": finalizer_hardware,
        "finalizer_hostname": socket.gethostname(),
        "finalizer_runtime": finalizer_runtime,
        "finalizer_scheduler": finalizer_scheduler,
        "input_bindings": bindings,
        "source_git_head": args.expected_source_git_head,
        "source_sha256": source_hashes,
    }
    output_root = _resolve_repo_path(args.output_root, "repeatability final root")
    target = (
        output_root
        / f"source_job_{args.source_array_job_id}"
        / f"finalizer_job_{finalizer_scheduler['job_id']}"
    )
    _atomic_final_directory(target, payload)
    print(
        json.dumps(
            {
                "admission_eligible": False,
                "artifact": _repo_relative(target),
                "paired_latency_preflight_may_resume": payload["decision"][
                    "paired_latency_preflight_may_resume"
                ],
                "provisional_preterminal_gate_pass": payload["decision"][
                    "provisional_preterminal_gate_pass"
                ],
                "source_array_job_id": args.source_array_job_id,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
