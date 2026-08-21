#!/usr/bin/env python3
"""Finalize one FEM-v2 qualification stage into a preterminal artifact."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from itertools import combinations
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
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    parse_scontrol_records,
    parse_tres,
    scheduler_resource_contract_matches,
)
from experiments_corpus_v4_fem_repeatability import (  # noqa: E402
    _assert_source_stable,
    _load_json,
    _resolve_repo_path,
    _same_node_identity,
    gmsh_thread_gate,
)
from run_corpus_v4_fem_v2_qualification import (  # noqa: E402
    ADMISSION_SCHEMA,
    NEXT_STAGE,
    OUTPUT_ROOT_RELATIVE,
    PROTOCOL_RELATIVE,
    SOURCE_WRAPPERS,
    START_SCHEMA,
    STAGES,
    TASK_MANIFEST_SCHEMA,
    TASK_SCHEMA,
    authenticate_protocol,
    canonical_output_root,
    is_sha256,
    numerical_gate,
    repo_relative,
    stage_tasks,
    validate_inputs,
    validate_prerequisite,
)


FINALIZER_WRAPPERS = {
    "gate_a": "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_a.sh",
    "gate_b": "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_b.sh",
    "gate_c": "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_c.sh",
}
FINAL_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-final.v1"
FINAL_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-final-manifest.v1"
ACCOUNTING_PROVENANCE_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-accounting.v1"
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--prerequisite-admission", type=Path)
    parser.add_argument("--expected-prerequisite-admission-sha256")
    parser.add_argument("--input-root", type=Path, default=Path(OUTPUT_ROOT_RELATIVE))
    return parser.parse_args(argv)


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
    job_id: str,
    *,
    expected_rows: int | None = None,
    attempts: int = 31,
    delay_s: float = 2.0,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
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
    for attempt in range(attempts):
        query = subprocess.run(command, capture_output=True, check=False, text=True)
        if query.returncode == 0:
            rows = parse_accounting(query.stdout)
            if rows and (expected_rows is None or len(rows) == expected_rows):
                break
        if attempt + 1 < attempts:
            time.sleep(delay_s)
    if query is None or query.returncode != 0:
        raise RuntimeError("terminal accounting query failed")
    if not rows or (expected_rows is not None and len(rows) != expected_rows):
        raise RuntimeError("terminal accounting did not reach exact coverage")
    normalized = [{field: row[field] for field in ACCOUNTING_FIELDS} for row in rows]
    return rows, {
        "canonical_rows_sha256": sha256_bytes(canonical_json_bytes(normalized)),
        "command": command,
        "origin": "live_sacct",
        "queried_utc": datetime.now(timezone.utc).isoformat(),
        "raw_stdout_sha256": sha256_bytes(query.stdout.encode("utf-8")),
        "row_count": len(rows),
        "schema": ACCOUNTING_PROVENANCE_SCHEMA,
    }


def validate_terminal_accounting(
    rows: Sequence[Mapping[str, str]],
    *,
    source_array_job_id: str,
    protocol: Mapping[str, Any],
    stage: str,
) -> list[dict[str, Any]]:
    tasks = stage_tasks(protocol, stage)
    resource = protocol["resources"][stage]
    indexed: dict[int, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        if set(row) != set(ACCOUNTING_FIELDS):
            raise ValueError("terminal accounting fields differ")
        match = re.fullmatch(re.escape(source_array_job_id) + r"_(\d+)", row.get("JobID", ""))
        if match is None:
            raise ValueError("terminal accounting row is outside the source array")
        task_id = int(match.group(1))
        if task_id not in range(len(tasks)) or task_id in indexed:
            raise ValueError("terminal accounting task is out of range or duplicate")
        state = row.get("State", "").split(maxsplit=1)[0].rstrip("+")
        if state not in TERMINAL_STATES or re.fullmatch(r"\d+:\d+", row.get("ExitCode", "")) is None:
            raise ValueError("source-array accounting is not terminal or has malformed exit code")
        req = parse_tres(row.get("ReqTRES"))
        alloc = parse_tres(row.get("AllocTRES"))
        elapsed = row.get("ElapsedRaw", "")
        if (
            row.get("Account") != resource["account"]
            or row.get("Partition") != resource["partition"]
            or row.get("Timelimit") != resource["time_limit"]
            or row.get("Restarts") != "0"
            or not row.get("NodeList")
            or row.get("NodeList") in {"(null)", "None", "Unknown"}
            or not elapsed.isdigit()
            or not 1 <= int(elapsed) <= 10800
            or req.get("cpu") != str(resource["requested_cpus_per_task"])
            or req.get("mem") != f"{resource['memory_gib']}G"
            or alloc.get("mem") != f"{resource['memory_gib']}G"
            or not str(alloc.get("cpu", "")).isdigit()
            or int(alloc["cpu"]) < int(resource["requested_cpus_per_task"])
        ):
            raise ValueError("terminal accounting resources differ from the protocol")
        indexed[task_id] = {
            **row,
            "array_task_id": task_id,
            "normalized_state": state,
            "terminal_success": state == "COMPLETED" and row["ExitCode"] == "0:0",
        }
    if set(indexed) != set(range(len(tasks))):
        raise ValueError("terminal accounting does not have exact dense coverage")
    return [indexed[index] for index in range(len(tasks))]


def validate_finalizer_allocation(protocol: Mapping[str, Any]) -> dict[str, Any]:
    job_id = os.environ.get("SLURM_JOB_ID")
    if not job_id:
        raise SystemExit("submit the FEM-v2 finalizer through Slurm")
    resource = protocol["resources"]["finalizer"]
    required = ("SLURM_CPUS_PER_TASK", "SLURM_JOB_ACCOUNT", "SLURM_JOB_PARTITION", "SLURM_MEM_PER_NODE", "SLURMD_NODENAME")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"finalizer Slurm environment is incomplete: {missing}")
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", job_id],
        capture_output=True,
        check=False,
        text=True,
    )
    matches = [row for row in parse_scontrol_records(query.stdout) if row.get("JobId") == job_id]
    allocated_cpus = int(os.environ["SLURM_CPUS_PER_TASK"])
    memory_mb = int(os.environ["SLURM_MEM_PER_NODE"])
    if (
        query.returncode != 0
        or len(matches) != 1
        or os.environ["SLURM_JOB_ACCOUNT"] != resource["account"]
        or os.environ["SLURM_JOB_PARTITION"] != resource["partition"]
        or memory_mb != int(resource["memory_gib"]) * 1024
    ):
        raise SystemExit("finalizer allocation differs from protocol")
    record = matches[0]
    profile = {
        "cpus_per_task": resource["requested_cpus_per_task"],
        "mem_gib": resource["memory_gib"],
    }
    if (
        record.get("Account") != resource["account"]
        or record.get("JobState") not in {"RUNNING", "COMPLETING"}
        or record.get("Partition") != resource["partition"]
        or record.get("TimeLimit") != resource["time_limit"]
        or not _same_node_identity(os.environ["SLURMD_NODENAME"], record.get("NodeList", ""))
        or not scheduler_resource_contract_matches(
            record,
            allocated_cpus_per_task=allocated_cpus,
            mem_per_node_mb=memory_mb,
            profile=profile,
        )
    ):
        raise SystemExit("live finalizer scheduler record differs from protocol")
    return {
        "allocated_cpus_per_task": allocated_cpus,
        "job_id": job_id,
        "memory_mb": memory_mb,
        "scheduler_record": {
            name: record[name]
            for name in (
                "Account",
                "AllocTRES",
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
            )
        },
    }


def load_admitted_result(
    path: Path, expected_sha256: str, protocol_sha256: str, expected_stage: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(path) != expected_sha256:
        raise ValueError("admission changed after prerequisite validation")
    admission = json.loads(path.read_text(encoding="utf-8"))
    if (
        admission.get("schema") != ADMISSION_SCHEMA
        or admission.get("stage") != expected_stage
        or admission.get("protocol_sha256") != protocol_sha256
        or admission.get("decision", {}).get("qualification_stage_pass") is not True
    ):
        raise ValueError("upstream stage is not positively admitted")
    binding = admission.get("preterminal_final", {})
    result_path = _resolve_repo_path(binding.get("result_path", ""), "admitted result")
    if sha256_file(result_path) != binding.get("result_sha256"):
        raise ValueError("admission does not bind its preterminal result")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("schema") != FINAL_SCHEMA or result.get("stage") != expected_stage:
        raise ValueError("admitted preterminal result identity differs")
    return admission, result


def gate_a_result_from_prerequisite(
    stage: str,
    prerequisite_path: Path,
    prerequisite_sha256: str,
    protocol_sha256: str,
) -> dict[str, Any]:
    predecessor = "gate_a" if stage == "gate_b" else "gate_b"
    _, result = load_admitted_result(
        prerequisite_path, prerequisite_sha256, protocol_sha256, predecessor
    )
    if stage == "gate_b":
        return result
    chain = result.get("prerequisite_admission", {})
    if chain.get("stage") != "gate_a" or not is_sha256(chain.get("sha256")):
        raise ValueError("Gate-B result does not bind Gate-A admission")
    path = _resolve_repo_path(chain["path"], "Gate-A admission")
    _, gate_a = load_admitted_result(path, chain["sha256"], protocol_sha256, "gate_a")
    return gate_a


def _validate_task_scheduler(
    scheduler: Mapping[str, Any], terminal: Mapping[str, Any], resource: Mapping[str, Any]
) -> None:
    record = scheduler.get("scheduler_record", {})
    req_terminal = parse_tres(terminal.get("ReqTRES"))
    alloc_terminal = parse_tres(terminal.get("AllocTRES"))
    if (
        scheduler.get("array_job_id") != terminal["JobID"].split("_", 1)[0]
        or int(scheduler.get("array_task_id", -1)) != int(terminal["array_task_id"])
        or scheduler.get("job_id") != terminal.get("JobIDRaw")
        or record.get("JobId") != scheduler.get("job_id")
        or record.get("ArrayJobId") != scheduler.get("array_job_id")
        or int(record.get("ArrayTaskId", -1)) != int(scheduler.get("array_task_id", -2))
        or not _same_node_identity(record.get("NodeList", ""), terminal.get("NodeList", ""))
        or parse_tres(record.get("ReqTRES")) != req_terminal
        or parse_tres(record.get("AllocTRES")) != alloc_terminal
        or not scheduler_resource_contract_matches(
            dict(record),
            allocated_cpus_per_task=int(scheduler.get("allocated_cpus_per_task", 0)),
            mem_per_node_mb=int(scheduler.get("mem_per_node_mb", 0)),
            profile={
                "cpus_per_task": resource["requested_cpus_per_task"],
                "mem_gib": resource["memory_gib"],
            },
        )
    ):
        raise ValueError("task scheduler receipt differs from terminal accounting")


def load_tasks(
    *,
    root: Path,
    stage: str,
    source_array_job_id: str,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    expected_source_git_head: str,
    prerequisite: Mapping[str, Any] | None,
    terminal_rows: Sequence[Mapping[str, Any]],
    input_bindings: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    task_specs = stage_tasks(protocol, stage)
    attempt_root = root / "attempts" / stage / f"job_{source_array_job_id}"
    expected_dirs = [attempt_root / f"task_{index:03d}" for index in range(len(task_specs))]
    actual_dirs = sorted(path for path in attempt_root.iterdir() if path.is_dir()) if attempt_root.is_dir() else []
    if actual_dirs != expected_dirs:
        raise ValueError("task directory inventory is not exact")
    cps_protocol = _load_json(_resolve_repo_path(protocol["inputs"]["cps_protocol"]["path"], "Cps protocol"))
    payloads: list[dict[str, Any]] = []
    artifact_records: list[dict[str, str]] = []
    resource = protocol["resources"][stage]
    for task_spec, task_dir, terminal in zip(task_specs, expected_dirs, terminal_rows):
        manifest_path = task_dir / "TASK_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_files = {"result.json", "started.json"}
        if (
            manifest.get("schema") != TASK_MANIFEST_SCHEMA
            or manifest.get("protocol_sha256") != protocol_sha256
            or manifest.get("stage") != stage
            or set(manifest.get("files_sha256", {})) != expected_files
        ):
            raise ValueError("task manifest contract differs")
        for name, digest in manifest["files_sha256"].items():
            if not is_sha256(digest) or sha256_file(task_dir / name) != digest:
                raise ValueError("task manifest byte hash differs")
        result_path = task_dir / "result.json"
        started_path = task_dir / "started.json"
        started = json.loads(started_path.read_text(encoding="utf-8"))
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if (
            set(started)
            != {
                "claim_eligible",
                "prerequisite_admission",
                "protocol_sha256",
                "schema",
                "source_git_head",
                "stage",
                "started_utc",
                "task",
            }
            or started.get("schema") != START_SCHEMA
            or started.get("claim_eligible") is not False
            or started.get("prerequisite_admission") != prerequisite
            or started.get("protocol_sha256") != protocol_sha256
            or started.get("source_git_head") != expected_source_git_head
            or started.get("stage") != stage
            or started.get("task") != task_spec
            or not isinstance(started.get("started_utc"), str)
            or not started["started_utc"]
            or payload.get("admission_eligible") is not False
            or payload.get("claim_eligible") is not False
            or payload.get("speed_claim_eligible") is not False
            or payload.get("schema") != TASK_SCHEMA
            or payload.get("stage") != stage
            or payload.get("task") != task_spec
            or payload.get("prerequisite_admission") != prerequisite
            or payload.get("provenance", {}).get("protocol_sha256") != protocol_sha256
            or payload.get("provenance", {}).get("source_git_head") != expected_source_git_head
            or payload.get("provenance", {}).get("source_sha256") != protocol["computational_sources"]
            or payload.get("provenance", {}).get("input_bindings") != input_bindings
            or payload.get("provenance", {}).get("executed_batch_sha256")
            != protocol["computational_sources"][SOURCE_WRAPPERS[stage]]
            or payload.get("provenance", {}).get("runtime") != protocol["runtime"]
            or not isinstance(payload.get("provenance", {}).get("hardware"), dict)
            or not isinstance(payload.get("provenance", {}).get("hostname"), str)
            or payload.get("worker_result") != payload.get("execution", {}).get("worker_result")
        ):
            raise ValueError("qualification task identity or provenance differs")
        expected_numeric = numerical_gate(payload["execution"], protocol, stage, cps_protocol)
        expected_thread = gmsh_thread_gate(payload["execution"], 1)
        gate = payload.get("gate", {})
        if (
            gate.get("integrity_pass") is not True
            or gate.get("numerical_resource") != expected_numeric
            or expected_numeric.get("pass") is not True
            or gate.get("thread_observation") != expected_thread
            or expected_thread.get("pass") is not True
        ):
            raise ValueError("qualification task gate does not recompute")
        worker = payload["worker_result"]
        if (
            not isinstance(worker.get("cps_pf"), (int, float))
            or not math.isfinite(float(worker["cps_pf"]))
            or float(worker["cps_pf"]) <= 0.0
            or not is_sha256(worker.get("system_sha256"))
            or worker.get("input_system_sha256") != worker.get("system_sha256")
        ):
            raise ValueError("qualification worker result is malformed")
        _validate_task_scheduler(payload["provenance"]["scheduler"], terminal, resource)
        payloads.append(payload)
        artifact_records.append(
            {
                "manifest_path": repo_relative(manifest_path, "task manifest"),
                "manifest_sha256": sha256_file(manifest_path),
                "result_path": repo_relative(result_path, "task result"),
                "result_sha256": sha256_file(result_path),
                "started_path": repo_relative(started_path, "task start"),
                "started_sha256": sha256_file(started_path),
            }
        )
    return payloads, artifact_records


def max_pairwise_relative(values: Sequence[float]) -> float:
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("repeatability values must be positive and finite")
    return max(
        abs(first - second) / max(abs(first), abs(second), 1e-12)
        for first, second in combinations(values, 2)
    )


def summarize_gate_a(payloads: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]) -> dict[str, Any]:
    by_key = {(row["task"]["layout_id"], row["task"]["repeat_id"]): row for row in payloads}
    tolerance = float(protocol["gates"]["repeatability_max_relative"])
    groups: list[dict[str, Any]] = []
    canonical: list[dict[str, Any]] = []
    for anchor in protocol["anchors"]:
        members = [by_key[(anchor["layout_id"], repeat)] for repeat in range(5)]
        workers = [row["worker_result"] for row in members]
        values = [float(worker["cps_pf"]) for worker in workers]
        systems = [worker["system_sha256"] for worker in workers]
        nodes = [int(worker["mesh_nodes"]) for worker in workers]
        tetrahedra = [int(worker["mesh_tetrahedra"]) for worker in workers]
        spread = max_pairwise_relative(values)
        identity = len(set(systems)) == len(set(nodes)) == len(set(tetrahedra)) == 1
        passed = identity and spread <= tolerance
        groups.append(
            {
                "cps_pf_by_repeat": values,
                "gate_pass": passed,
                "geometry_sha256": anchor["geometry_sha256"],
                "layout_id": anchor["layout_id"],
                "max_pairwise_relative_spread": spread,
                "mesh_identity_pass": identity,
                "mesh_nodes": {"minimum": min(nodes), "maximum": max(nodes)},
                "mesh_tetrahedra": {"minimum": min(tetrahedra), "maximum": max(tetrahedra)},
                "system_sha256_unique_count": len(set(systems)),
            }
        )
        repeat0 = workers[0]
        canonical.append(
            {
                "cps_pf": float(repeat0["cps_pf"]),
                "geometry_sha256": anchor["geometry_sha256"],
                "layout_id": anchor["layout_id"],
                "mesh_nodes": int(repeat0["mesh_nodes"]),
                "mesh_tetrahedra": int(repeat0["mesh_tetrahedra"]),
                "repeat_id": 0,
                "system_sha256": repeat0["system_sha256"],
            }
        )
    return {
        "canonical_repeat0": canonical,
        "gate_pass": all(group["gate_pass"] for group in groups),
        "groups": groups,
        "maximum_pairwise_relative_spread": max(group["max_pairwise_relative_spread"] for group in groups),
        "stage": "gate_a",
    }


def _delta_summary(values: Sequence[float], *, median_limit: float, max_limit: float) -> dict[str, Any]:
    median = float(statistics.median(values))
    maximum = max(values)
    return {
        "gate_pass": median <= median_limit and maximum <= max_limit,
        "maximum_pct": maximum,
        "maximum_tolerance_pct": max_limit,
        "median_pct": median,
        "median_tolerance_pct": median_limit,
        "values_pct": list(values),
    }


def summarize_gate_b(
    payloads: Sequence[Mapping[str, Any]], gate_a: Mapping[str, Any], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    reference = {row["layout_id"]: row for row in gate_a["qualification_summary"]["canonical_repeat0"]}
    rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    for payload in payloads:
        layout_id = payload["task"]["layout_id"]
        r3p16 = float(reference[layout_id]["cps_pf"])
        r3p20 = float(payload["worker_result"]["cps_pf"])
        delta = 100.0 * abs(r3p16 - r3p20) / abs(r3p20)
        deltas.append(delta)
        rows.append({"layout_id": layout_id, "r3p16_cps_pf": r3p16, "r3p20_cps_pf": r3p20, "domain_delta_pct": delta})
    summary = _delta_summary(
        deltas,
        median_limit=float(protocol["gates"]["domain_delta_median_pct"]),
        max_limit=float(protocol["gates"]["domain_delta_max_pct"]),
    )
    return {"domain_delta": summary, "gate_pass": summary["gate_pass"], "rows": rows, "stage": "gate_b"}


def summarize_gate_c(
    payloads: Sequence[Mapping[str, Any]], gate_a: Mapping[str, Any], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    """Qualify R4 repeatability and separately measure cross-fidelity delta.

    The mesh threshold is not a closeness requirement for an explicit
    multi-fidelity package.  A valid threshold failure is retained as an
    admitted negative scientific observation; only invalid tasks or failed
    sentinel repeatability block package qualification.
    """
    by_key = {(row["task"]["layout_id"], row["task"]["repeat_id"]): row for row in payloads}
    reference = {row["layout_id"]: row for row in gate_a["qualification_summary"]["canonical_repeat0"]}
    sentinels = set(protocol["gate_c_sentinel_selection"]["layout_ids"])
    tolerance = float(protocol["gates"]["repeatability_max_relative"])
    repeat_groups: list[dict[str, Any]] = []
    mesh_rows: list[dict[str, Any]] = []
    mesh_deltas: list[float] = []
    for anchor in protocol["anchors"]:
        layout_id = anchor["layout_id"]
        repeats = range(5 if layout_id in sentinels else 1)
        workers = [by_key[(layout_id, repeat)]["worker_result"] for repeat in repeats]
        if layout_id in sentinels:
            values = [float(worker["cps_pf"]) for worker in workers]
            systems = [worker["system_sha256"] for worker in workers]
            nodes = [int(worker["mesh_nodes"]) for worker in workers]
            tetrahedra = [int(worker["mesh_tetrahedra"]) for worker in workers]
            spread = max_pairwise_relative(values)
            identity = len(set(systems)) == len(set(nodes)) == len(set(tetrahedra)) == 1
            repeat_groups.append(
                {
                    "gate_pass": identity and spread <= tolerance,
                    "layout_id": layout_id,
                    "max_pairwise_relative_spread": spread,
                    "mesh_identity_pass": identity,
                    "system_sha256_unique_count": len(set(systems)),
                }
            )
        r3p16 = float(reference[layout_id]["cps_pf"])
        r4p16 = float(workers[0]["cps_pf"])
        delta = 100.0 * abs(r3p16 - r4p16) / abs(r4p16)
        mesh_deltas.append(delta)
        mesh_rows.append({"layout_id": layout_id, "r3p16_cps_pf": r3p16, "r4p16_cps_pf": r4p16, "mesh_delta_pct": delta})
    mesh = _delta_summary(
        mesh_deltas,
        median_limit=float(protocol["gates"]["mesh_delta_median_pct"]),
        max_limit=float(protocol["gates"]["mesh_delta_max_pct"]),
    )
    repeatability_pass = len(repeat_groups) == 3 and all(row["gate_pass"] for row in repeat_groups)
    return {
        "gate_pass": repeatability_pass,
        "mesh_delta": mesh,
        "mesh_threshold_pass": mesh["gate_pass"],
        "mesh_rows": mesh_rows,
        "multifidelity_qualification_pass": repeatability_pass,
        "repeatability_groups": repeat_groups,
        "repeatability_pass": repeatability_pass,
        "stage": "gate_c",
    }


def build_summary(
    stage: str,
    payloads: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    gate_a_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if stage == "gate_a":
        return summarize_gate_a(payloads, protocol)
    if gate_a_result is None:
        raise ValueError("downstream qualification stage lacks admitted Gate-A result")
    if stage == "gate_b":
        return summarize_gate_b(payloads, gate_a_result, protocol)
    return summarize_gate_c(payloads, gate_a_result, protocol)


def classify_scientific_outcome(
    stage: str, summary: Mapping[str, Any], stage_pass: bool
) -> str:
    """Classify validity separately from the Gate-C mesh observation."""
    if summary.get("scientific_outcome") == "INDETERMINATE":
        return "INDETERMINATE"
    if stage == "gate_c" and summary.get("mesh_threshold_pass") is not True:
        return "SCIENTIFIC_NEGATIVE"
    return "POSITIVE" if stage_pass else "SCIENTIFIC_NEGATIVE"


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.source_array_job_id.isdigit():
        raise SystemExit("source-array job ID must be decimal")
    protocol, protocol_sha256 = authenticate_protocol(args.protocol, args.expected_protocol_sha256)
    input_root = canonical_output_root(args.input_root, "qualification input root")
    prerequisite = validate_prerequisite(
        stage=args.stage,
        path=args.prerequisite_admission,
        expected_sha256=args.expected_prerequisite_admission_sha256,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
        output_root=input_root,
    )
    _, input_bindings = validate_inputs(protocol)
    source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=ROOT / PROTOCOL_RELATIVE,
        protocol_sha256=protocol_sha256,
    )
    finalizer_scheduler = validate_finalizer_allocation(protocol)
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch_sha = protocol["computational_sources"][FINALIZER_WRAPPERS[args.stage]]
    if not executed_batch.is_file() or sha256_file(executed_batch) != expected_batch_sha:
        raise SystemExit("executed finalizer batch differs from frozen source")
    terminal_raw, accounting_provenance = query_accounting(
        args.source_array_job_id,
        expected_rows=len(stage_tasks(protocol, args.stage)),
    )
    terminal = validate_terminal_accounting(
        terminal_raw,
        source_array_job_id=args.source_array_job_id,
        protocol=protocol,
        stage=args.stage,
    )
    all_source_success = all(row["terminal_success"] for row in terminal)
    gate_a_result = None
    if prerequisite is not None and all_source_success:
        gate_a_result = gate_a_result_from_prerequisite(
            args.stage,
            _resolve_repo_path(prerequisite["path"], "prerequisite admission"),
            prerequisite["sha256"],
            protocol_sha256,
        )
    artifacts: list[dict[str, str]] = []
    if all_source_success:
        try:
            payloads, artifacts = load_tasks(
                root=input_root,
                stage=args.stage,
                source_array_job_id=args.source_array_job_id,
                protocol=protocol,
                protocol_sha256=protocol_sha256,
                expected_source_git_head=args.expected_source_git_head,
                prerequisite=prerequisite,
                terminal_rows=terminal,
                input_bindings=input_bindings,
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            summary = {
                "gate_pass": False,
                "indeterminate_reason": str(exc),
                "scientific_outcome": "INDETERMINATE",
                "stage": args.stage,
            }
        else:
            summary = build_summary(args.stage, payloads, protocol, gate_a_result)
    else:
        summary = {
            "gate_pass": False,
            "indeterminate_reason": "one or more source tasks did not complete with exit code 0:0",
            "scientific_outcome": "INDETERMINATE",
            "stage": args.stage,
        }
    stage_pass = bool(all_source_success and summary["gate_pass"])
    scientific_outcome = classify_scientific_outcome(
        args.stage, summary, stage_pass
    )
    next_stage = NEXT_STAGE[args.stage]
    finalizer_job_id = str(finalizer_scheduler["job_id"])
    final_source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=ROOT / PROTOCOL_RELATIVE,
        protocol_sha256=protocol_sha256,
    )
    _, final_input_bindings = validate_inputs(protocol)
    if final_source_hashes != source_hashes or final_input_bindings != input_bindings:
        raise SystemExit("finalizer source or bound input changed during validation")
    result = {
        "admission_eligible": False,
        "artifact_stage": "preterminal_finalizer_output",
        "claim_eligible": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "all_source_tasks_completed_zero": all_source_success,
            "next_stage": next_stage,
            "next_stage_may_run": False,
            "provisional_multifidelity_v2_may_start": bool(
                args.stage == "gate_c" and stage_pass
            ),
            "provisional_qualification_stage_pass": stage_pass,
            "provisional_r3_v2_generation_may_start": bool(
                args.stage == "gate_b" and stage_pass
            ),
            "scientific_outcome": scientific_outcome,
        },
        "post_run_admission": {
            "finalizer_job_id": finalizer_job_id,
            "required": True,
            "required_exit_code": "0:0",
            "required_state": "COMPLETED",
            "terminal_accounting_verified": False,
        },
        "prerequisite_admission": prerequisite,
        "protocol_sha256": protocol_sha256,
        "provenance": {
            "accounting": accounting_provenance,
            "executed_batch_sha256": expected_batch_sha,
            "finalizer_scheduler": finalizer_scheduler,
            "input_bindings": input_bindings,
            "source_git_head": args.expected_source_git_head,
            "source_sha256": final_source_hashes,
        },
        "qualification_summary": summary,
        "schema": FINAL_SCHEMA,
        "source_array": {
            "array_job_id": args.source_array_job_id,
            "artifacts": artifacts,
            "terminal_accounting": terminal,
        },
        "speed_claim_eligible": False,
        "stage": args.stage,
    }
    target = (
        input_root
        / "final"
        / args.stage
        / f"source_job_{args.source_array_job_id}"
        / f"finalizer_job_{finalizer_job_id}"
    )
    if target.exists():
        raise SystemExit("refusing to overwrite a qualification final directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        result_path = staging / "result.json"
        atomic_write_json(result_path, result)
        atomic_write_json(
            staging / "FINAL_MANIFEST.json",
            {
                "files_sha256": {"result.json": sha256_file(result_path)},
                "finalizer_job_id": finalizer_job_id,
                "protocol_sha256": protocol_sha256,
                "schema": FINAL_MANIFEST_SCHEMA,
                "source_array_job_id": args.source_array_job_id,
                "stage": args.stage,
            },
        )
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(
        json.dumps(
            {
                "artifact": repo_relative(target, "qualification final"),
                "provisional_qualification_stage_pass": stage_pass,
                "stage": args.stage,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
