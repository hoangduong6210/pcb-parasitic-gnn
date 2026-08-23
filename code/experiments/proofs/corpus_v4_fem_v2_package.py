#!/usr/bin/env python3
"""Finalize and admit the one-thread Corpus-v4 FEM-v2 production package.

This module is intentionally solver-free.  Source arrays are handled by
``corpus_v4_fem_v2_production.py`` on compute nodes.  The commands here retain
exact component accounting, validate immutable task attempts, and build
cumulative accepted/pending receipts. Dataset admission authorizes freezing a
new accuracy protocol; it never starts training by itself.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
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
    atomic_write_jsonl,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    sha256_json,
)
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    parse_scontrol_records,
    parse_tres,
    scheduler_resource_contract_matches,
)
import corpus_v4_fem_v2_production as production  # noqa: E402


PACKAGE_SOURCE_RELATIVE = "code/experiments/proofs/corpus_v4_fem_v2_package.py"
WAVE_WRAPPER_RELATIVE = "code/jobs/submit_finalize_corpus_v4_fem_v2_wave.sh"
DATASET_WRAPPER_RELATIVE = "code/jobs/submit_finalize_corpus_v4_fem_v2_dataset.sh"

WAVE_RESULT_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-wave-final.v1"
WAVE_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-wave-final-manifest.v1"
WAVE_ADMISSION_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-wave-admission.v1"
ACCEPTED_SET_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-accepted-set.v1"
PENDING_SET_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-pending-set.v1"
NEGATIVE_SET_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-terminal-negative-set.v1"
DATASET_RESULT_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-dataset-final.v1"
DATASET_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-dataset-final-manifest.v1"
DATASET_ADMISSION_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-dataset-admission.v1"
ACCOUNTING_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-accounting.v1"

FINALIZER_RESOURCE = {
    "account": "pgs0407",
    "cpus_per_task": 2,
    "mem_gib": 16,
    "partition": "nextgen",
    "time_limit": "00:30:00",
}
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
TERMINAL_STATES = frozenset(
    {
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
)
SHA256_HEX = frozenset("0123456789abcdef")


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_HEX


def read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def safe_repo_path(relative: str, label: str) -> Path:
    return production.repo_path(relative, label)


def package_root() -> Path:
    return safe_repo_path(production.OUTPUT_ROOT_RELATIVE, "production root")


def fidelity_slug(fidelity_id: str) -> str:
    try:
        return production.FIDELITY_SLUG[fidelity_id]
    except KeyError as exc:
        raise ValueError("unsupported production fidelity") from exc


def parse_source_binding(value: str) -> dict[str, str]:
    """Parse ``JOBID|repository/path.json|sha256`` without shell evaluation."""
    parts = value.split("|")
    if len(parts) != 3:
        raise ValueError("source binding must be JOBID|PATH|SHA256")
    job_id, path, digest = parts
    if re.fullmatch(r"[1-9][0-9]*", job_id) is None:
        raise ValueError("source array JobID must be a positive integer")
    if not is_sha256(digest):
        raise ValueError("source dispatch SHA-256 is malformed")
    resolved = safe_repo_path(path, "source dispatch")
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("source dispatch is not a regular repository file")
    return {"dispatch_path": path, "dispatch_sha256": digest, "source_array_job_id": job_id}


def parse_accounting(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        if values and values[-1] == "":
            values.pop()
        if tuple(values) == ACCOUNTING_FIELDS:
            continue
        if len(values) != len(ACCOUNTING_FIELDS):
            raise ValueError("sacct row field count differs")
        rows.append(dict(zip(ACCOUNTING_FIELDS, values)))
    return rows


def query_accounting(
    job_ids: Sequence[str], *, expected_rows: int, attempts: int = 31, delay_s: float = 2.0
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not job_ids or len(set(job_ids)) != len(job_ids):
        raise ValueError("source JobIDs are empty or duplicate")
    if any(re.fullmatch(r"[1-9][0-9]*", job_id) is None for job_id in job_ids):
        raise ValueError("source JobID is malformed")
    command = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        ",".join(job_ids),
        "--format=" + ",".join(ACCOUNTING_FIELDS),
    ]
    query: subprocess.CompletedProcess[str] | None = None
    rows: list[dict[str, str]] = []
    for attempt in range(attempts):
        query = subprocess.run(command, capture_output=True, check=False, text=True)
        if query.returncode == 0:
            rows = parse_accounting(query.stdout)
            if len(rows) == expected_rows:
                break
        if attempt + 1 < attempts:
            time.sleep(delay_s)
    if query is None or query.returncode != 0 or len(rows) != expected_rows:
        raise RuntimeError("sacct did not return exact component coverage")
    canonical = sorted(
        ({field: row[field] for field in ACCOUNTING_FIELDS} for row in rows),
        key=lambda row: (row["JobID"], row["JobIDRaw"]),
    )
    return rows, {
        "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(canonical)),
        "command": command,
        "origin": "live_sacct",
        "queried_utc": datetime.now(timezone.utc).isoformat(),
        "raw_stdout_sha256": sha256_bytes(query.stdout.encode("utf-8")),
        "row_count": len(rows),
        "schema": ACCOUNTING_SCHEMA,
    }


def _time_limit(profile: Mapping[str, Any]) -> str:
    seconds = int(profile["time_s"])
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def validate_component_accounting(
    rows: Sequence[Mapping[str, str]],
    *,
    binding: Mapping[str, str],
    dispatch: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    fidelity_id = str(dispatch["fidelity_id"])
    profile = protocol["resource_profiles"][fidelity_id]["slurm"]
    expected_entries = list(dispatch["entries"])
    job_id = str(binding["source_array_job_id"])
    expected_by_local = {index: entry for index, entry in enumerate(expected_entries)}
    indexed: dict[int, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if set(row) != set(ACCOUNTING_FIELDS):
            raise ValueError("source component accounting fields differ")
        match = re.fullmatch(re.escape(job_id) + r"_(\d+)", row.get("JobID", ""))
        if match is None:
            raise ValueError("sacct row is outside its bound source array")
        local_id = int(match.group(1))
        if local_id not in expected_by_local or local_id in indexed:
            raise ValueError("sacct component is duplicate or outside dispatch")
        state = row.get("State", "").split(maxsplit=1)[0].rstrip("+")
        req = parse_tres(row.get("ReqTRES"))
        alloc = parse_tres(row.get("AllocTRES"))
        elapsed = row.get("ElapsedRaw", "")
        node_allocated = bool(
            row.get("NodeList")
            and row.get("NodeList") not in {"(null)", "None", "Unknown"}
        )
        allocation_matches = bool(
            alloc.get("mem") == f"{profile['mem_gib']}G"
            and str(alloc.get("cpu", "")).isdigit()
            and int(alloc["cpu"]) >= int(profile["cpus_per_task"])
        )
        execution_required = state in {"COMPLETED", "OUT_OF_MEMORY", "TIMEOUT"}
        elapsed_limit = int(profile["time_s"]) + (300 if state == "TIMEOUT" else 0)
        if (
            state not in TERMINAL_STATES
            or re.fullmatch(r"\d+:\d+", row.get("ExitCode", "")) is None
            or row.get("Account") != profile["account"]
            or row.get("Partition") != profile["partition"]
            or row.get("Timelimit") != _time_limit(profile)
            or row.get("Restarts") != "0"
            or not elapsed.isdigit()
            or int(elapsed) > elapsed_limit
            or req.get("cpu") != str(profile["cpus_per_task"])
            or req.get("mem") != f"{profile['mem_gib']}G"
            or (execution_required and (not node_allocated or not allocation_matches))
            or (not execution_required and node_allocated and not allocation_matches)
        ):
            raise ValueError("source component accounting differs from protocol")
        canonical = int(expected_by_local[local_id]["task_index"])
        indexed[canonical] = {
            **row,
            "array_task_id": local_id,
            "canonical_task_index": canonical,
            "normalized_state": state,
            "terminal_success": state == "COMPLETED" and row["ExitCode"] == "0:0",
        }
    expected_canonical = {int(entry["task_index"]) for entry in expected_entries}
    if set(indexed) != expected_canonical:
        raise ValueError("source accounting lacks exact dispatch coverage")
    return indexed


def validate_finalizer_terminal(
    row: Mapping[str, str], *, finalizer_job_id: str
) -> dict[str, Any]:
    req = parse_tres(row.get("ReqTRES"))
    alloc = parse_tres(row.get("AllocTRES"))
    state = row.get("State", "").split(maxsplit=1)[0].rstrip("+")
    elapsed = row.get("ElapsedRaw", "")
    if (
        row.get("JobID") != finalizer_job_id
        or row.get("JobIDRaw") != finalizer_job_id
        or state != "COMPLETED"
        or row.get("ExitCode") != "0:0"
        or row.get("Account") != FINALIZER_RESOURCE["account"]
        or row.get("Partition") != FINALIZER_RESOURCE["partition"]
        or row.get("Timelimit") != FINALIZER_RESOURCE["time_limit"]
        or row.get("Restarts") != "0"
        or not row.get("NodeList")
        or row.get("NodeList") in {"(null)", "None", "Unknown"}
        or not elapsed.isdigit()
        or not 1 <= int(elapsed) <= 1800
        or req.get("cpu") != str(FINALIZER_RESOURCE["cpus_per_task"])
        or req.get("mem") != f"{FINALIZER_RESOURCE['mem_gib']}G"
        or alloc.get("mem") != f"{FINALIZER_RESOURCE['mem_gib']}G"
        or not str(alloc.get("cpu", "")).isdigit()
        or int(alloc["cpu"]) < FINALIZER_RESOURCE["cpus_per_task"]
    ):
        raise ValueError("finalizer did not satisfy its postterminal contract")
    return {**dict(row), "normalized_state": state, "terminal_success": True}


def validate_finalizer_scheduler_link(
    live: Mapping[str, Any], terminal: Mapping[str, Any]
) -> None:
    record = live.get("scheduler_record", {})
    if (
        live.get("job_id") != terminal.get("JobID")
        or record.get("JobId") != terminal.get("JobIDRaw")
        or parse_tres(record.get("ReqTRES")) != parse_tres(terminal.get("ReqTRES"))
        or parse_tres(record.get("AllocTRES")) != parse_tres(terminal.get("AllocTRES"))
        or record.get("Account") != terminal.get("Account")
        or record.get("Partition") != terminal.get("Partition")
        or record.get("TimeLimit") != terminal.get("Timelimit")
    ):
        raise ValueError("live finalizer receipt differs from terminal accounting")


def validate_live_finalizer(wrapper_relative: str) -> dict[str, Any]:
    job_id = os.environ.get("SLURM_JOB_ID")
    required = (
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_ACCOUNT",
        "SLURM_JOB_PARTITION",
        "SLURM_MEM_PER_NODE",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if not job_id or missing:
        raise SystemExit("submit the package finalizer through Slurm")
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", job_id],
        capture_output=True,
        check=False,
        text=True,
    )
    matches = [row for row in parse_scontrol_records(query.stdout) if row.get("JobId") == job_id]
    allocated = int(os.environ["SLURM_CPUS_PER_TASK"])
    memory_mb = int(os.environ["SLURM_MEM_PER_NODE"])
    if query.returncode != 0 or len(matches) != 1:
        raise SystemExit("live finalizer is not confirmed by Slurm")
    row = matches[0]
    if (
        os.environ["SLURM_JOB_ACCOUNT"] != FINALIZER_RESOURCE["account"]
        or os.environ["SLURM_JOB_PARTITION"] != FINALIZER_RESOURCE["partition"]
        or memory_mb != FINALIZER_RESOURCE["mem_gib"] * 1024
        or row.get("Account") != FINALIZER_RESOURCE["account"]
        or row.get("Partition") != FINALIZER_RESOURCE["partition"]
        or row.get("TimeLimit") != FINALIZER_RESOURCE["time_limit"]
        or row.get("JobState") not in {"RUNNING", "COMPLETING"}
        or not scheduler_resource_contract_matches(
            row,
            allocated_cpus_per_task=allocated,
            mem_per_node_mb=memory_mb,
            profile={
                "cpus_per_task": FINALIZER_RESOURCE["cpus_per_task"],
                "mem_gib": FINALIZER_RESOURCE["mem_gib"],
            },
        )
    ):
        raise SystemExit("live finalizer allocation differs from package contract")
    executed = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected = safe_repo_path(wrapper_relative, "finalizer wrapper")
    if not executed.is_file() or sha256_file(executed) != sha256_file(expected):
        raise SystemExit("executed finalizer wrapper differs from frozen source")
    return {
        "allocated_cpus_per_task": allocated,
        "executed_batch_sha256": sha256_file(expected),
        "job_id": job_id,
        "memory_mb": memory_mb,
        "scheduler_record": row,
    }


def authenticate_roots(args: argparse.Namespace) -> dict[str, Any]:
    protocol, protocol_sha = production.authenticate_protocol(
        args.protocol, args.expected_protocol_sha256
    )
    plan, plan_sha = production.validate_plan(
        protocol, protocol_sha, args.plan, args.expected_plan_sha256
    )
    lock, lock_sha = production.validate_lock(
        protocol,
        protocol_sha,
        plan_sha,
        args.execution_lock,
        args.expected_execution_lock_sha256,
    )
    source_sha = production.assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_sha256=protocol_sha,
    )
    required_package_sources = {
        PACKAGE_SOURCE_RELATIVE,
        WAVE_WRAPPER_RELATIVE,
        DATASET_WRAPPER_RELATIVE,
    }
    if not required_package_sources <= set(source_sha) or source_sha != lock["source_sha256"]:
        raise ValueError("production lock does not include the package source closure")
    return {
        "execution_lock_sha256": lock_sha,
        "plan": plan,
        "plan_sha256": plan_sha,
        "protocol": protocol,
        "protocol_sha256": protocol_sha,
        "source_git_head": args.expected_source_git_head,
        "source_sha256": source_sha,
    }


def load_manifest(roots: Mapping[str, Any], fidelity_id: str) -> tuple[list[dict[str, Any]], str]:
    slug = fidelity_slug(fidelity_id)
    path = safe_repo_path(
        f"{production.PLAN_ROOT_RELATIVE}/{slug}_manifest.jsonl", "production manifest"
    )
    rows, digest, observed_fidelity = production.validate_manifest(
        roots["protocol"], roots["protocol_sha256"], roots["plan"], path
    )
    if observed_fidelity != fidelity_id:
        raise ValueError("manifest fidelity differs")
    return rows, digest


def validate_dispatch_binding(
    roots: Mapping[str, Any],
    binding: Mapping[str, str],
    *,
    fidelity_id: str,
    manifest: Sequence[Mapping[str, Any]],
    manifest_sha256: str,
    retry_authority: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    path = safe_repo_path(binding["dispatch_path"], "source dispatch")
    if sha256_file(path) != binding["dispatch_sha256"]:
        raise ValueError("source dispatch bytes differ from binding")
    payload = read_json(path, "source dispatch")
    if payload.get("schema") == production.DISPATCH_SCHEMA:
        dispatch, _ = production.validate_dispatch(
            roots["protocol_sha256"],
            roots["plan"],
            path,
            binding["dispatch_sha256"],
            manifest_sha256,
            fidelity_id,
            manifest,
        )
        return dispatch
    if payload.get("schema") != PENDING_SET_SCHEMA:
        raise ValueError("source dispatch has unsupported schema")
    if retry_authority is None:
        raise ValueError("retry dispatch lacks its prior admission authority")
    admission_path = safe_repo_path(
        retry_authority["path"], "retry prior admission"
    )
    if sha256_file(admission_path) != retry_authority["sha256"]:
        raise ValueError("retry prior admission hash differs")
    admission = read_json(admission_path, "retry prior admission")
    pending_binding = admission.get("preterminal_files", {})
    if (
        pending_binding.get("pending_set_path") != binding["dispatch_path"]
        or pending_binding.get("pending_set_sha256") != binding["dispatch_sha256"]
    ):
        raise ValueError("retry dispatch is not the pending set bound by its admission")
    if (
        payload.get("fidelity_id") != fidelity_id
        or payload.get("protocol_sha256") != roots["protocol_sha256"]
        or payload.get("plan_sha256") != roots["plan_sha256"]
        or payload.get("execution_lock_sha256") != roots["execution_lock_sha256"]
        or payload.get("manifest_sha256") != manifest_sha256
    ):
        raise ValueError("retry dispatch roots differ")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("retry dispatch is empty")
    seen: set[int] = set()
    for entry in entries:
        index = int(entry.get("task_index", -1))
        if index in seen or index not in range(len(manifest)):
            raise ValueError("retry dispatch index is duplicate or out of range")
        expected = manifest[index]
        if entry != {
            "geometry_sha256": expected["geometry_sha256"],
            "layout_id": expected["layout_id"],
            "task_index": index,
        }:
            raise ValueError("retry dispatch identity differs from manifest")
        seen.add(index)
    return payload


def _validate_scheduler_link(
    scheduler: Mapping[str, Any], terminal: Mapping[str, Any], profile: Mapping[str, Any]
) -> None:
    record = scheduler.get("scheduler_record", {})
    if (
        scheduler.get("array_job_id") != terminal["JobID"].split("_", 1)[0]
        or int(scheduler.get("array_task_id", -1)) != int(terminal["array_task_id"])
        or scheduler.get("job_id") != terminal.get("JobIDRaw")
        or record.get("JobId") != scheduler.get("job_id")
        or record.get("ArrayJobId") != scheduler.get("array_job_id")
        or int(record.get("ArrayTaskId", -1)) != int(scheduler.get("array_task_id", -2))
        or parse_tres(record.get("ReqTRES")) != parse_tres(terminal.get("ReqTRES"))
        or parse_tres(record.get("AllocTRES")) != parse_tres(terminal.get("AllocTRES"))
        or not scheduler_resource_contract_matches(
            dict(record),
            allocated_cpus_per_task=int(scheduler.get("allocated_cpus_per_task", 0)),
            mem_per_node_mb=int(scheduler.get("mem_per_node_mb", 0)),
            profile={"cpus_per_task": profile["cpus_per_task"], "mem_gib": profile["mem_gib"]},
        )
    ):
        raise ValueError("task scheduler receipt differs from terminal accounting")


def load_attempt(
    *,
    roots: Mapping[str, Any],
    fidelity_id: str,
    manifest_row: Mapping[str, Any],
    manifest_sha256: str,
    binding: Mapping[str, str],
    dispatch_sha256: str,
    terminal: Mapping[str, Any],
    retry_authority: Mapping[str, str] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    slug = fidelity_slug(fidelity_id)
    task_index = int(manifest_row["task_index"])
    task_dir = (
        package_root()
        / "attempts"
        / slug
        / f"job_{binding['source_array_job_id']}"
        / f"task_{task_index:04d}"
    )
    terminal_state = str(terminal.get("normalized_state", ""))
    resource_terminal = terminal_state in {"OUT_OF_MEMORY", "TIMEOUT"}
    terminal_success = terminal.get("terminal_success") is True
    base_artifact = {
        "array_task_id": int(terminal["array_task_id"]),
        "fidelity_id": fidelity_id,
        "geometry_sha256": manifest_row["geometry_sha256"],
        "layout_id": manifest_row["layout_id"],
        "source_array_job_id": binding["source_array_job_id"],
        "task_index": task_index,
    }
    if not task_dir.exists():
        if terminal_success:
            raise ValueError("successful scheduler component lacks a task attempt")
        if resource_terminal:
            return "terminal_negative", {
                **base_artifact,
                "artifact_stage": "scheduler_only_resource_failure",
                "failure_class": "genuine_numerical_or_resource_failure",
                "scheduler_state": terminal_state,
            }
        return "pending", None
    if task_dir.is_symlink() or not task_dir.is_dir():
        raise ValueError("task attempt is not an immutable directory")
    expected_names = {"TASK_MANIFEST.json", "result.json", "started.json"}
    observed_names = {path.name for path in task_dir.iterdir()}
    if observed_names != expected_names:
        if terminal_success:
            raise ValueError("successful scheduler component has an incomplete attempt")
        if not observed_names <= expected_names:
            raise ValueError("task attempt contains an unexpected file")
        partial = {
            **base_artifact,
            "artifact_stage": "incomplete_resource_failure",
            "failure_class": "genuine_numerical_or_resource_failure",
            "scheduler_state": terminal_state,
            "retained_files_sha256": {
                name: sha256_file(task_dir / name)
                for name in sorted(observed_names)
                if (task_dir / name).is_file() and not (task_dir / name).is_symlink()
            },
        }
        if "started.json" in observed_names:
            started = read_json(task_dir / "started.json", "partial task start")
            if (
                started.get("schema") != production.START_SCHEMA
                or started.get("task_index") != task_index
                or started.get("fidelity_id") != fidelity_id
                or started.get("layout_id") != manifest_row["layout_id"]
                or started.get("geometry_sha256") != manifest_row["geometry_sha256"]
                or started.get("protocol_sha256") != roots["protocol_sha256"]
                or started.get("plan_sha256") != roots["plan_sha256"]
                or started.get("manifest_sha256") != manifest_sha256
                or started.get("dispatch_sha256") != dispatch_sha256
                or started.get("source_git_head") != roots["source_git_head"]
                or started.get("retry_authorization") != retry_authority
            ):
                raise ValueError("partial task start identity differs")
        if resource_terminal:
            return "terminal_negative", partial
        return "pending", None
    files_manifest = read_json(task_dir / "TASK_MANIFEST.json", "task files manifest")
    if (
        files_manifest.get("schema")
        != "pcb-gnn.corpus-v4-fem-v2-production-task-files.v1"
        or set(files_manifest.get("files_sha256", {})) != {"result.json", "started.json"}
    ):
        raise ValueError("task files manifest differs")
    for name, digest in files_manifest["files_sha256"].items():
        if not is_sha256(digest) or sha256_file(task_dir / name) != digest:
            raise ValueError("task artifact hash differs")
    started = read_json(task_dir / "started.json", "task start")
    result = read_json(task_dir / "result.json", "task result")
    if (
        started.get("schema") != production.START_SCHEMA
        or started.get("task_index") != task_index
        or started.get("fidelity_id") != fidelity_id
        or started.get("layout_id") != manifest_row["layout_id"]
        or started.get("geometry_sha256") != manifest_row["geometry_sha256"]
        or started.get("protocol_sha256") != roots["protocol_sha256"]
        or started.get("plan_sha256") != roots["plan_sha256"]
        or started.get("manifest_sha256") != manifest_sha256
        or started.get("dispatch_sha256") != dispatch_sha256
        or started.get("source_git_head") != roots["source_git_head"]
        or started.get("retry_authorization") != retry_authority
        or result.get("schema") != production.TASK_SCHEMA
        or result.get("task_index") != task_index
        or result.get("fidelity", {}).get("fidelity_id") != fidelity_id
        or result.get("geometry", {}).get("layout_id") != manifest_row["layout_id"]
        or result.get("geometry", {}).get("geometry_sha256")
        != manifest_row["geometry_sha256"]
        or result.get("solver_contract_id") != manifest_row["solver_contract_id"]
    ):
        raise ValueError("task identity differs from production manifest")
    provenance = result.get("provenance", {})
    if (
        provenance.get("protocol_sha256") != roots["protocol_sha256"]
        or provenance.get("plan_sha256") != roots["plan_sha256"]
        or provenance.get("execution_lock_sha256") != roots["execution_lock_sha256"]
        or provenance.get("manifest_sha256") != manifest_sha256
        or provenance.get("dispatch_sha256") != dispatch_sha256
        or provenance.get("source_git_head") != roots["source_git_head"]
        or provenance.get("retry_authorization") != retry_authority
        or provenance.get("source_sha256") != roots["source_sha256"]
        or result.get("fresh_production_solve") is not True
        or result.get("claim_eligible") is not False
        or result.get("speed_claim_eligible") is not False
        or result.get("training_may_start") is not False
    ):
        raise ValueError("task provenance differs from production roots")
    scheduler = provenance.get("scheduler", {})
    _validate_scheduler_link(
        scheduler,
        terminal,
        roots["protocol"]["resource_profiles"][fidelity_id]["slurm"],
    )
    numerical = production.evaluate_result(result.get("execution", {}), roots["protocol"], fidelity_id)
    gmsh = production.gmsh_thread_gate(result.get("execution", {}), 1)
    stable = result.get("gates", {}).get("source_stable") is True
    expected_pass = bool(numerical.get("pass") is True and gmsh.get("pass") is True and stable)
    expected_failure = production.classify_failure(
        result.get("execution", {}), numerical, gmsh, stable
    )
    if (
        result.get("gates", {}).get("numerical_resource") != numerical
        or result.get("gates", {}).get("gmsh_thread") != gmsh
        or result.get("task_pass") is not expected_pass
        or result.get("failure_class") != expected_failure
    ):
        raise ValueError("task gates do not replay exactly")
    artifact = {
        **base_artifact,
        "artifact_manifest_path": production.repo_relative(
            task_dir / "TASK_MANIFEST.json", "task manifest"
        ),
        "artifact_manifest_sha256": sha256_file(task_dir / "TASK_MANIFEST.json"),
        "artifact_result_path": production.repo_relative(task_dir / "result.json", "task result"),
        "artifact_result_sha256": sha256_file(task_dir / "result.json"),
    }
    if resource_terminal:
        return "terminal_negative", {
            **artifact,
            "failure_class": "genuine_numerical_or_resource_failure",
            "scheduler_state": terminal_state,
        }
    if expected_pass and terminal_success:
        return "accepted", artifact
    if expected_failure == "genuine_numerical_or_resource_failure" and not terminal_success:
        return "terminal_negative", {**artifact, "failure_class": expected_failure}
    if expected_pass and not terminal_success:
        return "pending", None
    if not expected_pass and terminal_success:
        raise ValueError("failed task artifact came from a successful scheduler component")
    return "pending", None


def _load_bound_set(path: str, digest: str, schema: str, label: str) -> dict[str, Any]:
    resolved = safe_repo_path(path, label)
    if not is_sha256(digest) or sha256_file(resolved) != digest:
        raise ValueError(f"{label} hash differs")
    payload = read_json(resolved, label)
    if payload.get("schema") != schema:
        raise ValueError(f"{label} schema differs")
    return payload


def load_prior_admission(
    path: Path | None,
    expected_sha256: str | None,
    *,
    roots: Mapping[str, Any],
    fidelity_id: str,
    wave_id: int,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if (path is None) != (expected_sha256 is None):
        raise ValueError("prior admission path and SHA-256 are both required")
    if path is None:
        if wave_id != 0:
            raise ValueError("non-initial wave requires the preceding admission")
        return None, [], [], []
    if wave_id <= 0:
        raise ValueError("initial wave must not have a prior admission")
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    expected_parent = package_root() / "waves" / fidelity_slug(fidelity_id)
    if expected_parent.resolve() not in resolved.parents or resolved.name != "FINAL_ADMISSION.json":
        raise ValueError("prior admission is outside the canonical wave namespace")
    if not is_sha256(expected_sha256) or sha256_file(resolved) != expected_sha256:
        raise ValueError("prior admission SHA-256 differs")
    admission = read_json(resolved, "prior wave admission")
    root_values = admission.get("roots", {})
    if (
        admission.get("schema") != WAVE_ADMISSION_SCHEMA
        or admission.get("artifact_stage") != "postterminal_wave_admission"
        or admission.get("admission_eligible") is not True
        or admission.get("claim_eligible") is not False
        or admission.get("solver_executed") is not False
        or admission.get("speed_claim_eligible") is not False
        or admission.get("training_may_start") is not False
        or admission.get("fidelity_id") != fidelity_id
        or admission.get("wave_id") != wave_id - 1
        or admission.get("decision", {}).get("terminal_negative") is not False
        or admission.get("decision", {}).get("scientific_outcome") != "INDETERMINATE"
        or admission.get("decision", {}).get("retry_may_start") is not True
        or root_values.get("protocol_sha256") != roots["protocol_sha256"]
        or root_values.get("plan_sha256") != roots["plan_sha256"]
        or root_values.get("execution_lock_sha256") != roots["execution_lock_sha256"]
        or root_values.get("source_git_head") != roots["source_git_head"]
    ):
        raise ValueError("prior admission identity differs")
    bindings = admission.get("preterminal_files", {})
    accepted = _load_bound_set(
        bindings["accepted_set_path"], bindings["accepted_set_sha256"], ACCEPTED_SET_SCHEMA, "prior accepted set"
    )
    negative = _load_bound_set(
        bindings["terminal_negative_set_path"],
        bindings["terminal_negative_set_sha256"],
        NEGATIVE_SET_SCHEMA,
        "prior terminal-negative set",
    )
    source_inventory = admission.get("cumulative_source_inventory")
    if not isinstance(source_inventory, list):
        raise ValueError("prior admission lacks cumulative source inventory")
    normalized_inventory: list[dict[str, Any]] = []
    seen_inventory: set[tuple[str, int]] = set()
    for row in source_inventory:
        if not isinstance(row, dict):
            raise ValueError("prior source inventory row is malformed")
        job_id = row.get("source_array_job_id")
        task_index = row.get("task_index")
        if (
            not isinstance(job_id, str)
            or re.fullmatch(r"[1-9][0-9]*", job_id) is None
            or type(task_index) is not int
            or task_index not in range(int(roots["protocol"]["fidelities"][fidelity_id]["coverage"]))
            or (job_id, task_index) in seen_inventory
        ):
            raise ValueError("prior source inventory identity is invalid or duplicate")
        seen_inventory.add((job_id, task_index))
        normalized_inventory.append(
            {"source_array_job_id": job_id, "task_index": task_index}
        )
    if normalized_inventory != sorted(
        normalized_inventory,
        key=lambda row: (int(row["task_index"]), int(row["source_array_job_id"])),
    ):
        raise ValueError("prior source inventory is not canonical")
    terminal_attempts = {
        (str(row["source_array_job_id"]), int(row["task_index"]))
        for row in (*accepted.get("entries", []), *negative.get("entries", []))
    }
    if not terminal_attempts <= seen_inventory:
        raise ValueError("prior source inventory omits a terminal attempt")
    return (
        {"path": production.repo_relative(resolved, "prior admission"), "sha256": expected_sha256},
        list(accepted.get("entries", [])),
        list(negative.get("entries", [])),
        normalized_inventory,
    )


def classify_wave(
    *, expected_count: int, accepted_count: int, pending_count: int, negative_count: int
) -> dict[str, Any]:
    if accepted_count + pending_count + negative_count != expected_count:
        raise ValueError("wave state does not partition the manifest")
    coverage_complete = accepted_count == expected_count and pending_count == negative_count == 0
    if negative_count:
        outcome = "TERMINAL_NEGATIVE"
    elif coverage_complete:
        outcome = "POSITIVE"
    else:
        outcome = "INDETERMINATE"
    return {
        "coverage_complete": coverage_complete,
        "dataset_finalize_may_start": coverage_complete,
        "retry_may_start": bool(pending_count and not negative_count),
        "scientific_outcome": outcome,
        "terminal_negative": bool(negative_count),
    }


def build_wave_state(
    *,
    manifest: Sequence[Mapping[str, Any]],
    prior_accepted: Sequence[Mapping[str, Any]],
    prior_negative: Sequence[Mapping[str, Any]],
    current: Mapping[int, tuple[str, dict[str, Any] | None]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    accepted = {int(row["task_index"]): dict(row) for row in prior_accepted}
    negative = {int(row["task_index"]): dict(row) for row in prior_negative}
    if len(accepted) != len(prior_accepted) or len(negative) != len(prior_negative):
        raise ValueError("prior wave contains duplicate task identity")
    if set(accepted) & set(negative):
        raise ValueError("prior accepted and terminal-negative sets overlap")
    for index, (classification, artifact) in current.items():
        if index in accepted or index in negative:
            raise ValueError("current wave reruns a terminal prior task")
        if classification == "accepted":
            if artifact is None:
                raise ValueError("accepted task lacks artifact binding")
            accepted[index] = artifact
        elif classification == "terminal_negative":
            if artifact is None:
                raise ValueError("terminal-negative task lacks artifact binding")
            negative[index] = artifact
        elif classification != "pending":
            raise ValueError("unsupported task classification")
    expected_indices = set(range(len(manifest)))
    if not set(accepted) <= expected_indices or not set(negative) <= expected_indices:
        raise ValueError("wave task is outside the manifest")
    pending_indices = sorted(expected_indices - set(accepted) - set(negative))
    pending = [
        {
            "geometry_sha256": manifest[index]["geometry_sha256"],
            "layout_id": manifest[index]["layout_id"],
            "task_index": index,
        }
        for index in pending_indices
    ]
    accepted_rows = [accepted[index] for index in sorted(accepted)]
    negative_rows = [negative[index] for index in sorted(negative)]
    decision = classify_wave(
        expected_count=len(manifest),
        accepted_count=len(accepted_rows),
        pending_count=len(pending),
        negative_count=len(negative_rows),
    )
    return accepted_rows, pending, negative_rows, decision


def reject_unbound_valid_attempts(
    *,
    roots: Mapping[str, Any],
    fidelity_id: str,
    allowed_attempts: set[tuple[str, int]],
) -> None:
    """Reject a valid attempt omitted from the cumulative source inventory."""

    attempts_root = package_root() / "attempts" / fidelity_slug(fidelity_id)
    if not attempts_root.exists():
        return
    if attempts_root.is_symlink() or not attempts_root.is_dir():
        raise ValueError("fidelity attempt root is not a regular directory")
    for job_dir in attempts_root.iterdir():
        match = re.fullmatch(r"job_([1-9][0-9]*)", job_dir.name)
        if match is None or job_dir.is_symlink() or not job_dir.is_dir():
            raise ValueError("attempt job directory inventory differs")
        job_id = match.group(1)
        for task_dir in job_dir.iterdir():
            task_match = re.fullmatch(r"task_(\d{4})", task_dir.name)
            if task_match is None or task_dir.is_symlink() or not task_dir.is_dir():
                raise ValueError("attempt task directory inventory differs")
            result_path = task_dir / "result.json"
            manifest_path = task_dir / "TASK_MANIFEST.json"
            if not result_path.is_file() or not manifest_path.is_file():
                continue
            result = read_json(result_path, "candidate task result")
            provenance = result.get("provenance", {})
            same_roots = (
                result.get("schema") == production.TASK_SCHEMA
                and result.get("task_pass") is True
                and result.get("fidelity", {}).get("fidelity_id") == fidelity_id
                and provenance.get("protocol_sha256") == roots["protocol_sha256"]
                and provenance.get("plan_sha256") == roots["plan_sha256"]
                and provenance.get("execution_lock_sha256")
                == roots["execution_lock_sha256"]
                and provenance.get("source_git_head") == roots["source_git_head"]
            )
            if not same_roots:
                continue
            task_index = result.get("task_index")
            if type(task_index) is not int or (job_id, task_index) not in allowed_attempts:
                raise ValueError(
                    "valid production attempt is absent from the cumulative source inventory"
                )


def collect_wave(
    *,
    roots: Mapping[str, Any],
    fidelity_id: str,
    manifest: Sequence[Mapping[str, Any]],
    manifest_sha256: str,
    bindings: Sequence[Mapping[str, str]],
    accounting_rows: Sequence[Mapping[str, str]],
    prior_accepted: Sequence[Mapping[str, Any]],
    prior_negative: Sequence[Mapping[str, Any]],
    prior_source_inventory: Sequence[Mapping[str, Any]],
    retry_authority: Mapping[str, str] | None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    current: dict[int, tuple[str, dict[str, Any] | None]] = {}
    retained_accounting: list[dict[str, Any]] = []
    allowed_attempts = {
        (str(row["source_array_job_id"]), int(row["task_index"]))
        for row in (*prior_accepted, *prior_negative, *prior_source_inventory)
    }
    for binding in bindings:
        dispatch = validate_dispatch_binding(
            roots,
            binding,
            fidelity_id=fidelity_id,
            manifest=manifest,
            manifest_sha256=manifest_sha256,
            retry_authority=retry_authority,
        )
        job_id = binding["source_array_job_id"]
        job_rows = [row for row in accounting_rows if row.get("JobID", "").startswith(f"{job_id}_")]
        indexed = validate_component_accounting(
            job_rows, binding=binding, dispatch=dispatch, protocol=roots["protocol"]
        )
        for entry in dispatch["entries"]:
            index = int(entry["task_index"])
            if index in current:
                raise ValueError("current source dispatches overlap")
            terminal = indexed[index]
            allowed_attempts.add((binding["source_array_job_id"], index))
            current[index] = load_attempt(
                roots=roots,
                fidelity_id=fidelity_id,
                manifest_row=manifest[index],
                manifest_sha256=manifest_sha256,
                binding=binding,
                dispatch_sha256=binding["dispatch_sha256"],
                terminal=terminal,
                retry_authority=(
                    retry_authority
                    if dispatch.get("schema") == PENDING_SET_SCHEMA
                    else None
                ),
            )
            retained_accounting.append(terminal)
    reject_unbound_valid_attempts(
        roots=roots,
        fidelity_id=fidelity_id,
        allowed_attempts=allowed_attempts,
    )
    accepted, pending, negative, decision = build_wave_state(
        manifest=manifest,
        prior_accepted=prior_accepted,
        prior_negative=prior_negative,
        current=current,
    )
    source_inventory = [
        {"source_array_job_id": job_id, "task_index": task_index}
        for job_id, task_index in sorted(
            allowed_attempts, key=lambda row: (row[1], int(row[0]))
        )
    ]
    return (
        accepted,
        pending,
        negative,
        decision,
        sorted(
            retained_accounting,
            key=lambda row: (int(row["canonical_task_index"]), row["JobID"]),
        ),
        source_inventory,
    )


def roots_receipt(roots: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "execution_lock_sha256": roots["execution_lock_sha256"],
        "plan_sha256": roots["plan_sha256"],
        "protocol_sha256": roots["protocol_sha256"],
        "source_git_head": roots["source_git_head"],
        "source_sha256": roots["source_sha256"],
    }


def atomic_directory(target: Path, files: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if target.exists():
        raise SystemExit("refusing to overwrite an immutable package directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        for name, payload in files.items():
            if name.endswith(".jsonl"):
                atomic_write_jsonl(staging / name, payload)
            else:
                atomic_write_json(staging / name, payload)
        atomic_write_json(staging / "FINAL_MANIFEST.json", manifest | {
            "files_sha256": {name: sha256_file(staging / name) for name in sorted(files)}
        })
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def wave_final_dir(fidelity_id: str, wave_id: int, source_set_sha256: str, finalizer_job_id: str) -> Path:
    return (
        package_root()
        / "waves"
        / fidelity_slug(fidelity_id)
        / f"wave_{wave_id:03d}"
        / "final"
        / f"source_set_{source_set_sha256}"
        / f"finalizer_job_{finalizer_job_id}"
    )


def wave_admission_path(fidelity_id: str, wave_id: int, source_set_sha256: str, finalizer_job_id: str) -> Path:
    return (
        package_root()
        / "waves"
        / fidelity_slug(fidelity_id)
        / f"wave_{wave_id:03d}"
        / "admission"
        / f"source_set_{source_set_sha256}"
        / f"finalizer_job_{finalizer_job_id}"
        / "FINAL_ADMISSION.json"
    )


def finalize_wave(args: argparse.Namespace) -> dict[str, Any]:
    roots = authenticate_roots(args)
    finalizer = validate_live_finalizer(WAVE_WRAPPER_RELATIVE)
    manifest, manifest_sha = load_manifest(roots, args.fidelity_id)
    bindings = [parse_source_binding(value) for value in args.source_binding]
    if len({row["source_array_job_id"] for row in bindings}) != len(bindings):
        raise ValueError("source bindings contain duplicate arrays")
    if args.wave_id == 0:
        expected_dispatch = (
            f"{production.PLAN_ROOT_RELATIVE}/"
            f"{fidelity_slug(args.fidelity_id)}_dispatch_000.json"
        )
        if len(bindings) != 1 or bindings[0]["dispatch_path"] != expected_dispatch:
            raise ValueError("initial wave must bind the exact frozen first dispatch")
    prior, prior_accepted, prior_negative, prior_source_inventory = load_prior_admission(
        args.prior_admission,
        args.expected_prior_admission_sha256,
        roots=roots,
        fidelity_id=args.fidelity_id,
        wave_id=args.wave_id,
    )
    expected_rows = 0
    for binding in bindings:
        dispatch = validate_dispatch_binding(
            roots,
            binding,
            fidelity_id=args.fidelity_id,
            manifest=manifest,
            manifest_sha256=manifest_sha,
            retry_authority=prior,
        )
        expected_rows += len(dispatch["entries"])
    accounting_rows, accounting_provenance = query_accounting(
        [row["source_array_job_id"] for row in bindings], expected_rows=expected_rows
    )
    accepted, pending, negative, decision, retained, source_inventory = collect_wave(
        roots=roots,
        fidelity_id=args.fidelity_id,
        manifest=manifest,
        manifest_sha256=manifest_sha,
        bindings=bindings,
        accounting_rows=accounting_rows,
        prior_accepted=prior_accepted,
        prior_negative=prior_negative,
        prior_source_inventory=prior_source_inventory,
        retry_authority=prior,
    )
    source_set = {
        "bindings": bindings,
        "fidelity_id": args.fidelity_id,
        "prior_admission": prior,
        "roots": roots_receipt(roots),
        "wave_id": args.wave_id,
    }
    source_set_sha = sha256_json(source_set)
    common = {
        "execution_lock_sha256": roots["execution_lock_sha256"],
        "fidelity_id": args.fidelity_id,
        "manifest_sha256": manifest_sha,
        "plan_sha256": roots["plan_sha256"],
        "protocol_sha256": roots["protocol_sha256"],
        "source_set_sha256": source_set_sha,
        "wave_id": args.wave_id,
    }
    accepted_set = {**common, "entries": accepted, "schema": ACCEPTED_SET_SCHEMA}
    pending_set = {**common, "entries": pending, "schema": PENDING_SET_SCHEMA}
    negative_set = {**common, "entries": negative, "schema": NEGATIVE_SET_SCHEMA}
    result = {
        "admission_eligible": False,
        "artifact_stage": "preterminal_wave_finalizer",
        "claim_eligible": False,
        "counts": {
            "accepted": len(accepted),
            "expected": len(manifest),
            "pending": len(pending),
            "terminal_negative": len(negative),
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "fidelity_id": args.fidelity_id,
        "postterminal_admission_required": True,
        "prior_admission": prior,
        "provenance": {
            "accounting": accounting_provenance,
            "finalizer_scheduler": finalizer,
            "roots": roots_receipt(roots),
            "source_accounting": retained,
            "source_bindings": bindings,
            "cumulative_source_inventory": source_inventory,
        },
        "schema": WAVE_RESULT_SCHEMA,
        "solver_executed": False,
        "source_set_sha256": source_set_sha,
        "speed_claim_eligible": False,
        "training_may_start": False,
        "wave_id": args.wave_id,
    }
    target = wave_final_dir(
        args.fidelity_id, args.wave_id, source_set_sha, str(finalizer["job_id"])
    )
    files = {
        "accepted_artifact_set.json": accepted_set,
        "pending_task_set.json": pending_set,
        "result.json": result,
        "terminal_negative_set.json": negative_set,
    }
    manifest_payload = {
        "fidelity_id": args.fidelity_id,
        "finalizer_job_id": str(finalizer["job_id"]),
        "schema": WAVE_MANIFEST_SCHEMA,
        "source_set_sha256": source_set_sha,
        "wave_id": args.wave_id,
    }
    atomic_directory(target, files, manifest_payload)
    return {"artifact": production.repo_relative(target, "wave final"), **result}


def load_wave_final(
    *,
    fidelity_id: str,
    wave_id: int,
    source_set_sha256: str,
    finalizer_job_id: str,
    expected_manifest_sha256: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    if not is_sha256(source_set_sha256) or not is_sha256(expected_manifest_sha256):
        raise ValueError("wave source-set or manifest SHA-256 is malformed")
    if re.fullmatch(r"[1-9][0-9]*", finalizer_job_id) is None:
        raise ValueError("wave finalizer JobID is malformed")
    root = wave_final_dir(fidelity_id, wave_id, source_set_sha256, finalizer_job_id)
    manifest_path = root / "FINAL_MANIFEST.json"
    if sha256_file(manifest_path) != expected_manifest_sha256:
        raise ValueError("wave final manifest SHA-256 differs")
    manifest = read_json(manifest_path, "wave final manifest")
    expected_files = {
        "accepted_artifact_set.json",
        "pending_task_set.json",
        "result.json",
        "terminal_negative_set.json",
    }
    if (
        manifest.get("schema") != WAVE_MANIFEST_SCHEMA
        or manifest.get("fidelity_id") != fidelity_id
        or manifest.get("wave_id") != wave_id
        or manifest.get("source_set_sha256") != source_set_sha256
        or manifest.get("finalizer_job_id") != finalizer_job_id
        or set(manifest.get("files_sha256", {})) != expected_files
    ):
        raise ValueError("wave final manifest identity differs")
    payloads: dict[str, dict[str, Any]] = {}
    for name, digest in manifest["files_sha256"].items():
        path = root / name
        if not is_sha256(digest) or sha256_file(path) != digest:
            raise ValueError("wave final file hash differs")
        payloads[name] = read_json(path, name)
    return root, manifest, payloads["result.json"], payloads


def admit_wave(args: argparse.Namespace) -> dict[str, Any]:
    roots = authenticate_roots(args)
    final_root, manifest, preterminal, payloads = load_wave_final(
        fidelity_id=args.fidelity_id,
        wave_id=args.wave_id,
        source_set_sha256=args.source_set_sha256,
        finalizer_job_id=args.finalizer_job_id,
        expected_manifest_sha256=args.expected_final_manifest_sha256,
    )
    root_values = preterminal.get("provenance", {}).get("roots", {})
    if root_values != roots_receipt(roots):
        raise ValueError("wave preterminal roots differ")
    bindings = preterminal.get("provenance", {}).get("source_bindings", [])
    manifest_rows, manifest_sha = load_manifest(roots, args.fidelity_id)
    prior, prior_accepted, prior_negative, prior_source_inventory = load_prior_admission(
        None if preterminal.get("prior_admission") is None else safe_repo_path(preterminal["prior_admission"]["path"], "prior admission"),
        None if preterminal.get("prior_admission") is None else preterminal["prior_admission"]["sha256"],
        roots=roots,
        fidelity_id=args.fidelity_id,
        wave_id=args.wave_id,
    )
    replay_source_set = {
        "bindings": bindings,
        "fidelity_id": args.fidelity_id,
        "prior_admission": prior,
        "roots": roots_receipt(roots),
        "wave_id": args.wave_id,
    }
    if sha256_json(replay_source_set) != args.source_set_sha256:
        raise ValueError("wave source-set identity does not replay")
    common = {
        "execution_lock_sha256": roots["execution_lock_sha256"],
        "fidelity_id": args.fidelity_id,
        "manifest_sha256": manifest_sha,
        "plan_sha256": roots["plan_sha256"],
        "protocol_sha256": roots["protocol_sha256"],
        "source_set_sha256": args.source_set_sha256,
        "wave_id": args.wave_id,
    }
    for name, schema in (
        ("accepted_artifact_set.json", ACCEPTED_SET_SCHEMA),
        ("pending_task_set.json", PENDING_SET_SCHEMA),
        ("terminal_negative_set.json", NEGATIVE_SET_SCHEMA),
    ):
        payload = payloads[name]
        if payload.get("schema") != schema or any(payload.get(key) != value for key, value in common.items()):
            raise ValueError("wave set identity differs from production roots")
    if (
        preterminal.get("schema") != WAVE_RESULT_SCHEMA
        or preterminal.get("artifact_stage") != "preterminal_wave_finalizer"
        or preterminal.get("admission_eligible") is not False
        or preterminal.get("claim_eligible") is not False
        or preterminal.get("solver_executed") is not False
        or preterminal.get("training_may_start") is not False
        or preterminal.get("fidelity_id") != args.fidelity_id
        or preterminal.get("wave_id") != args.wave_id
        or preterminal.get("source_set_sha256") != args.source_set_sha256
    ):
        raise ValueError("wave preterminal identity differs")
    expected_rows = sum(
        len(
            validate_dispatch_binding(
                roots,
                binding,
                fidelity_id=args.fidelity_id,
                manifest=manifest_rows,
                manifest_sha256=manifest_sha,
                retry_authority=prior,
            )["entries"]
        )
        for binding in bindings
    )
    live_rows, live_accounting = query_accounting(
        [row["source_array_job_id"] for row in bindings], expected_rows=expected_rows
    )
    accepted, pending, negative, decision, retained, source_inventory = collect_wave(
        roots=roots,
        fidelity_id=args.fidelity_id,
        manifest=manifest_rows,
        manifest_sha256=manifest_sha,
        bindings=bindings,
        accounting_rows=live_rows,
        prior_accepted=prior_accepted,
        prior_negative=prior_negative,
        prior_source_inventory=prior_source_inventory,
        retry_authority=prior,
    )
    if (
        payloads["accepted_artifact_set.json"].get("entries") != accepted
        or payloads["pending_task_set.json"].get("entries") != pending
        or payloads["terminal_negative_set.json"].get("entries") != negative
        or preterminal.get("decision") != decision
        or preterminal.get("counts")
        != {
            "accepted": len(accepted),
            "expected": len(manifest_rows),
            "pending": len(pending),
            "terminal_negative": len(negative),
        }
        or preterminal.get("provenance", {}).get("source_accounting") != retained
        or preterminal.get("provenance", {}).get("cumulative_source_inventory")
        != source_inventory
        or preterminal.get("provenance", {}).get("accounting", {}).get("canonical_rows_sha256")
        != live_accounting["canonical_rows_sha256"]
        or prior != preterminal.get("prior_admission")
    ):
        raise ValueError("wave preterminal result does not replay exactly")
    final_rows, final_accounting = query_accounting(
        [args.finalizer_job_id], expected_rows=1
    )
    finalizer_terminal = validate_finalizer_terminal(
        final_rows[0], finalizer_job_id=args.finalizer_job_id
    )
    validate_finalizer_scheduler_link(
        preterminal.get("provenance", {}).get("finalizer_scheduler", {}),
        finalizer_terminal,
    )
    target = wave_admission_path(
        args.fidelity_id, args.wave_id, args.source_set_sha256, args.finalizer_job_id
    )
    if target.exists():
        raise SystemExit("refusing to overwrite a wave admission")
    target.parent.mkdir(parents=True, exist_ok=True)
    files = manifest["files_sha256"]
    admission = {
        "admission_eligible": True,
        "artifact_stage": "postterminal_wave_admission",
        "claim_eligible": False,
        "counts": preterminal["counts"],
        "cumulative_source_inventory": source_inventory,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "fidelity_id": args.fidelity_id,
        "finalizer_terminal_accounting": {
            "provenance": final_accounting,
            "row": finalizer_terminal,
        },
        "preterminal_files": {
            "accepted_set_path": production.repo_relative(final_root / "accepted_artifact_set.json", "accepted set"),
            "accepted_set_sha256": files["accepted_artifact_set.json"],
            "result_path": production.repo_relative(final_root / "result.json", "wave result"),
            "result_sha256": files["result.json"],
            "terminal_negative_set_path": production.repo_relative(final_root / "terminal_negative_set.json", "negative set"),
            "terminal_negative_set_sha256": files["terminal_negative_set.json"],
            "pending_set_path": production.repo_relative(final_root / "pending_task_set.json", "pending set"),
            "pending_set_sha256": files["pending_task_set.json"],
            "final_manifest_path": production.repo_relative(final_root / "FINAL_MANIFEST.json", "wave manifest"),
            "final_manifest_sha256": args.expected_final_manifest_sha256,
        },
        "roots": roots_receipt(roots),
        "schema": WAVE_ADMISSION_SCHEMA,
        "solver_executed": False,
        "source_set_sha256": args.source_set_sha256,
        "speed_claim_eligible": False,
        "training_may_start": False,
        "wave_id": args.wave_id,
    }
    atomic_write_json(target, admission)
    return {"artifact": production.repo_relative(target, "wave admission"), **admission}


def load_positive_wave_admission(
    path: Path,
    digest: str,
    *,
    roots: Mapping[str, Any],
    fidelity_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    expected_parent = package_root() / "waves" / fidelity_slug(fidelity_id)
    if expected_parent.resolve() not in resolved.parents or resolved.name != "FINAL_ADMISSION.json":
        raise ValueError("coverage admission is outside its canonical fidelity namespace")
    if not is_sha256(digest) or sha256_file(resolved) != digest:
        raise ValueError("coverage admission hash differs")
    admission = read_json(resolved, "coverage admission")
    if (
        admission.get("schema") != WAVE_ADMISSION_SCHEMA
        or admission.get("artifact_stage") != "postterminal_wave_admission"
        or admission.get("admission_eligible") is not True
        or admission.get("fidelity_id") != fidelity_id
        or admission.get("decision", {}).get("coverage_complete") is not True
        or admission.get("decision", {}).get("scientific_outcome") != "POSITIVE"
        or admission.get("roots") != roots_receipt(roots)
    ):
        raise ValueError("wave admission is not positive exact coverage")
    binding = admission["preterminal_files"]
    preterminal_path = safe_repo_path(binding["result_path"], "coverage wave result")
    if sha256_file(preterminal_path) != binding["result_sha256"]:
        raise ValueError("coverage wave result hash differs")
    preterminal = read_json(preterminal_path, "coverage wave result")
    if (
        preterminal.get("schema") != WAVE_RESULT_SCHEMA
        or preterminal.get("artifact_stage") != "preterminal_wave_finalizer"
        or preterminal.get("fidelity_id") != fidelity_id
        or preterminal.get("source_set_sha256") != admission.get("source_set_sha256")
        or preterminal.get("decision") != admission.get("decision")
        or preterminal.get("counts") != admission.get("counts")
        or preterminal.get("claim_eligible") is not False
        or preterminal.get("training_may_start") is not False
        or preterminal.get("provenance", {}).get("roots") != roots_receipt(roots)
        or preterminal.get("provenance", {}).get("cumulative_source_inventory")
        != admission.get("cumulative_source_inventory")
    ):
        raise ValueError("coverage wave preterminal receipt differs")
    terminal_receipt = admission.get("finalizer_terminal_accounting", {})
    terminal_row = terminal_receipt.get("row", {})
    finalizer_job_id = str(terminal_row.get("JobID", ""))
    validate_finalizer_terminal(terminal_row, finalizer_job_id=finalizer_job_id)
    validate_finalizer_scheduler_link(
        preterminal.get("provenance", {}).get("finalizer_scheduler", {}), terminal_row
    )
    accepted = _load_bound_set(
        binding["accepted_set_path"], binding["accepted_set_sha256"], ACCEPTED_SET_SCHEMA, "coverage accepted set"
    )
    entries = list(accepted.get("entries", []))
    expected = int(roots["protocol"]["fidelities"][fidelity_id]["coverage"])
    if len(entries) != expected or [int(row["task_index"]) for row in entries] != list(range(expected)):
        raise ValueError("coverage accepted set is not exact and dense")
    inventory = admission.get("cumulative_source_inventory", [])
    accepted_attempts = {
        (str(row["source_array_job_id"]), int(row["task_index"])) for row in entries
    }
    inventory_attempts = {
        (str(row.get("source_array_job_id")), row.get("task_index"))
        for row in inventory
        if isinstance(row, dict)
    }
    if len(inventory_attempts) != len(inventory) or not accepted_attempts <= inventory_attempts:
        raise ValueError("coverage source inventory omits an accepted attempt")
    return (
        {"path": production.repo_relative(resolved, "coverage admission"), "sha256": digest},
        entries,
    )


def build_dataset_observations(
    *, roots: Mapping[str, Any], accepted_by_fidelity: Mapping[str, Sequence[Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for fidelity_id in production.FIDELITIES:
        expected_count = int(roots["protocol"]["fidelities"][fidelity_id]["coverage"])
        entries = list(accepted_by_fidelity[fidelity_id])
        if len(entries) != expected_count:
            raise ValueError("dataset source coverage differs from protocol")
        for entry in entries:
            key = (fidelity_id, int(entry["task_index"]))
            if key in seen:
                raise ValueError("dataset contains duplicate accepted task")
            seen.add(key)
            result_path = safe_repo_path(entry["artifact_result_path"], "accepted task result")
            if sha256_file(result_path) != entry["artifact_result_sha256"]:
                raise ValueError("accepted task result hash differs")
            result = read_json(result_path, "accepted task result")
            worker = result.get("worker_result") or {}
            cps = worker.get("cps_pf")
            if (
                result.get("schema") != production.TASK_SCHEMA
                or result.get("task_pass") is not True
                or result.get("fidelity", {}).get("fidelity_id") != fidelity_id
                or result.get("task_index") != entry["task_index"]
                or result.get("geometry", {}).get("layout_id") != entry["layout_id"]
                or result.get("geometry", {}).get("geometry_sha256") != entry["geometry_sha256"]
                or not isinstance(cps, (int, float))
                or not math.isfinite(float(cps))
                or float(cps) <= 0.0
            ):
                raise ValueError("accepted production result is malformed")
            observations.append(
                {
                    "artifact_result_path": entry["artifact_result_path"],
                    "artifact_result_sha256": entry["artifact_result_sha256"],
                    "cps_pf": float(cps),
                    "fidelity_id": fidelity_id,
                    "geometry_sha256": entry["geometry_sha256"],
                    "layout_id": entry["layout_id"],
                    "mesh_nodes": worker.get("mesh_nodes"),
                    "mesh_tetrahedra": worker.get("mesh_tetrahedra"),
                    "relative_residual": worker.get("relative_residual"),
                    "system_sha256": worker.get("system_sha256"),
                    "units": "pF",
                }
            )
    observations.sort(key=lambda row: (int(row["layout_id"]), str(row["fidelity_id"])))
    if len(observations) != 1698:
        raise ValueError("joint dataset must contain exactly 1,698 observations")
    return observations


def dataset_source_set(r3: Mapping[str, str], r4: Mapping[str, str], roots: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    payload = {"r3_admission": dict(r3), "r4_admission": dict(r4), "roots": roots_receipt(roots)}
    return payload, sha256_json(payload)


def dataset_final_dir(source_set_sha256: str, finalizer_job_id: str) -> Path:
    return package_root() / "dataset" / "final" / f"source_set_{source_set_sha256}" / f"finalizer_job_{finalizer_job_id}"


def dataset_admission_path(source_set_sha256: str, finalizer_job_id: str) -> Path:
    return package_root() / "dataset" / "admission" / f"source_set_{source_set_sha256}" / f"finalizer_job_{finalizer_job_id}" / "FINAL_ADMISSION.json"


def finalize_dataset(args: argparse.Namespace) -> dict[str, Any]:
    roots = authenticate_roots(args)
    finalizer = validate_live_finalizer(DATASET_WRAPPER_RELATIVE)
    r3_binding, r3_entries = load_positive_wave_admission(
        args.r3_admission,
        args.expected_r3_admission_sha256,
        roots=roots,
        fidelity_id=production.FIDELITIES[0],
    )
    r4_binding, r4_entries = load_positive_wave_admission(
        args.r4_admission,
        args.expected_r4_admission_sha256,
        roots=roots,
        fidelity_id=production.FIDELITIES[1],
    )
    source_set, source_set_sha = dataset_source_set(r3_binding, r4_binding, roots)
    observations = build_dataset_observations(
        roots=roots,
        accepted_by_fidelity={
            production.FIDELITIES[0]: r3_entries,
            production.FIDELITIES[1]: r4_entries,
        },
    )
    summary = {
        "admission_eligible": False,
        "artifact_stage": "preterminal_dataset_finalizer",
        "claim_eligible": False,
        "counts": {"geometries": 1500, "r3_observations": 1500, "r4_observations": 198, "total_observations": 1698},
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {"dataset_generation_pass": True, "training_may_start": False},
        "fidelity_semantics": roots["protocol"]["scientific_semantics"],
        "provenance": {"finalizer_scheduler": finalizer, "roots": roots_receipt(roots), "source_set": source_set},
        "schema": DATASET_RESULT_SCHEMA,
        "solver_executed": False,
        "source_set_sha256": source_set_sha,
        "speed_claim_eligible": False,
        "training_may_start": False,
    }
    target = dataset_final_dir(source_set_sha, str(finalizer["job_id"]))
    files = {"label_observations.jsonl": observations, "summary.json": summary}
    atomic_directory(
        target,
        files,
        {
            "finalizer_job_id": str(finalizer["job_id"]),
            "schema": DATASET_MANIFEST_SCHEMA,
            "source_set_sha256": source_set_sha,
        },
    )
    return {"artifact": production.repo_relative(target, "dataset final"), **summary}


def load_dataset_final(
    source_set_sha256: str,
    finalizer_job_id: str,
    expected_manifest_sha256: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if not is_sha256(source_set_sha256) or not is_sha256(expected_manifest_sha256):
        raise ValueError("dataset source-set or manifest SHA-256 is malformed")
    if re.fullmatch(r"[1-9][0-9]*", finalizer_job_id) is None:
        raise ValueError("dataset finalizer JobID is malformed")
    root = dataset_final_dir(source_set_sha256, finalizer_job_id)
    manifest_path = root / "FINAL_MANIFEST.json"
    if sha256_file(manifest_path) != expected_manifest_sha256:
        raise ValueError("dataset final manifest SHA-256 differs")
    manifest = read_json(manifest_path, "dataset final manifest")
    if (
        manifest.get("schema") != DATASET_MANIFEST_SCHEMA
        or manifest.get("source_set_sha256") != source_set_sha256
        or manifest.get("finalizer_job_id") != finalizer_job_id
        or set(manifest.get("files_sha256", {})) != {"label_observations.jsonl", "summary.json"}
    ):
        raise ValueError("dataset final manifest identity differs")
    for name, digest in manifest["files_sha256"].items():
        if not is_sha256(digest) or sha256_file(root / name) != digest:
            raise ValueError("dataset final file hash differs")
    summary = read_json(root / "summary.json", "dataset summary")
    observations = production.load_jsonl(root / "label_observations.jsonl", "dataset observations")
    return root, manifest, summary, observations


def admit_dataset(args: argparse.Namespace) -> dict[str, Any]:
    roots = authenticate_roots(args)
    final_root, manifest, summary, observed = load_dataset_final(
        args.source_set_sha256, args.finalizer_job_id, args.expected_final_manifest_sha256
    )
    source_set = summary.get("provenance", {}).get("source_set", {})
    r3 = source_set.get("r3_admission", {})
    r4 = source_set.get("r4_admission", {})
    r3_binding, r3_entries = load_positive_wave_admission(
        safe_repo_path(r3.get("path", ""), "R3 coverage admission"),
        r3.get("sha256", ""),
        roots=roots,
        fidelity_id=production.FIDELITIES[0],
    )
    r4_binding, r4_entries = load_positive_wave_admission(
        safe_repo_path(r4.get("path", ""), "R4 coverage admission"),
        r4.get("sha256", ""),
        roots=roots,
        fidelity_id=production.FIDELITIES[1],
    )
    replay_source, replay_sha = dataset_source_set(r3_binding, r4_binding, roots)
    replay_observations = build_dataset_observations(
        roots=roots,
        accepted_by_fidelity={production.FIDELITIES[0]: r3_entries, production.FIDELITIES[1]: r4_entries},
    )
    if (
        replay_sha != args.source_set_sha256
        or replay_source != source_set
        or replay_observations != observed
        or summary.get("schema") != DATASET_RESULT_SCHEMA
        or summary.get("source_set_sha256") != replay_sha
        or summary.get("counts")
        != {"geometries": 1500, "r3_observations": 1500, "r4_observations": 198, "total_observations": 1698}
        or summary.get("decision") != {"dataset_generation_pass": True, "training_may_start": False}
        or summary.get("training_may_start") is not False
        or summary.get("provenance", {}).get("roots") != roots_receipt(roots)
    ):
        raise ValueError("dataset preterminal package does not replay exactly")
    final_rows, final_accounting = query_accounting([args.finalizer_job_id], expected_rows=1)
    terminal = validate_finalizer_terminal(final_rows[0], finalizer_job_id=args.finalizer_job_id)
    validate_finalizer_scheduler_link(
        summary.get("provenance", {}).get("finalizer_scheduler", {}), terminal
    )
    target = dataset_admission_path(args.source_set_sha256, args.finalizer_job_id)
    if target.exists():
        raise SystemExit("refusing to overwrite a dataset admission")
    target.parent.mkdir(parents=True, exist_ok=True)
    admission = {
        "admission_eligible": True,
        "artifact_stage": "postterminal_dataset_admission",
        "claim_eligible": False,
        "counts": summary["counts"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "accuracy_protocol_may_be_frozen": True,
            "dataset_generation_admitted": True,
            "training_may_start": False,
        },
        "finalizer_terminal_accounting": {"provenance": final_accounting, "row": terminal},
        "preterminal_files": {
            "final_manifest_path": production.repo_relative(final_root / "FINAL_MANIFEST.json", "dataset manifest"),
            "final_manifest_sha256": args.expected_final_manifest_sha256,
            "label_observations_path": production.repo_relative(final_root / "label_observations.jsonl", "dataset observations"),
            "label_observations_sha256": manifest["files_sha256"]["label_observations.jsonl"],
            "summary_path": production.repo_relative(final_root / "summary.json", "dataset summary"),
            "summary_sha256": manifest["files_sha256"]["summary.json"],
        },
        "roots": roots_receipt(roots),
        "schema": DATASET_ADMISSION_SCHEMA,
        "solver_executed": False,
        "source_set_sha256": args.source_set_sha256,
        "speed_claim_eligible": False,
        "training_may_start": False,
    }
    atomic_write_json(target, admission)
    return {"artifact": production.repo_relative(target, "dataset admission"), **admission}


def add_roots(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--protocol", type=Path, default=Path(production.PROTOCOL_RELATIVE))
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--plan", type=Path, default=Path(f"{production.PLAN_ROOT_RELATIVE}/plan.json"))
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, default=Path(production.LOCK_RELATIVE))
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    wave = commands.add_parser("finalize-wave", help="finalize one dynamic source wave under Slurm")
    add_roots(wave)
    wave.add_argument("--fidelity-id", choices=production.FIDELITIES, required=True)
    wave.add_argument("--wave-id", type=int, required=True)
    wave.add_argument("--source-binding", action="append", required=True)
    wave.add_argument("--prior-admission", type=Path)
    wave.add_argument("--expected-prior-admission-sha256")

    wave_admit = commands.add_parser("admit-wave", help="create a solver-free postterminal wave admission")
    add_roots(wave_admit)
    wave_admit.add_argument("--fidelity-id", choices=production.FIDELITIES, required=True)
    wave_admit.add_argument("--wave-id", type=int, required=True)
    wave_admit.add_argument("--source-set-sha256", required=True)
    wave_admit.add_argument("--finalizer-job-id", required=True)
    wave_admit.add_argument("--expected-final-manifest-sha256", required=True)

    dataset = commands.add_parser("finalize-dataset", help="finalize exact R3/R4 coverage under Slurm")
    add_roots(dataset)
    dataset.add_argument("--r3-admission", type=Path, required=True)
    dataset.add_argument("--expected-r3-admission-sha256", required=True)
    dataset.add_argument("--r4-admission", type=Path, required=True)
    dataset.add_argument("--expected-r4-admission-sha256", required=True)

    dataset_admit = commands.add_parser("admit-dataset", help="create the solver-free postterminal dataset admission")
    add_roots(dataset_admit)
    dataset_admit.add_argument("--source-set-sha256", required=True)
    dataset_admit.add_argument("--finalizer-job-id", required=True)
    dataset_admit.add_argument("--expected-final-manifest-sha256", required=True)
    return root


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if getattr(args, "wave_id", 0) < 0:
        raise SystemExit("wave ID must be nonnegative")
    if args.command == "finalize-wave":
        result = finalize_wave(args)
    elif args.command == "admit-wave":
        result = admit_wave(args)
    elif args.command == "finalize-dataset":
        result = finalize_dataset(args)
    elif args.command == "admit-dataset":
        result = admit_dataset(args)
    else:  # pragma: no cover
        raise AssertionError("unreachable command")
    print(json.dumps(result, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
