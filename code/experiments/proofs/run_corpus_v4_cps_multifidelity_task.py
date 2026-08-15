#!/usr/bin/env python3
"""Run exactly one frozen Cps geometry/fidelity task under SLURM."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    load_json,
    require_file_sha256,
    sha256_file,
    sha256_json,
)
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402


SCHEMA = "pcb-gnn.cps-multifidelity-task.v1"
MANIFEST_SCHEMA = "pcb-gnn.cps-multifidelity-task-manifest.v1"
EXECUTION_SOURCE_NAMES = (
    "requirements-proof.txt",
    "protocols/corpus_v4_cps_multifidelity_v1.json",
    "code/core/scientific_artifact.py",
    "code/core/geometry_contract.py",
    "code/data/verified_geometry_corpus.py",
    "code/experiments/proofs/build_corpus_v4_cps_candidate_index.py",
    "code/experiments/proofs/plan_corpus_v4_cps_multifidelity.py",
    "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py",
    "code/experiments/proofs/plan_corpus_v4_cps_resume.py",
    "code/experiments/proofs/plan_corpus_v4_cps_submission_shards.py",
    "code/experiments/proofs/finalize_corpus_v4_cps_multifidelity.py",
    "code/solvers/fem_capacitance_3d.py",
    "code/solvers/fem_cps_diagnostic_worker.py",
    "code/solvers/fem_cps_bounded_worker.py",
    "code/jobs/slurm_job_env.sh",
    "code/jobs/submit_corpus_v4_cps_r3.sh",
    "code/jobs/submit_corpus_v4_cps_r4.sh",
    "code/jobs/submit_finalize_corpus_v4_cps_multifidelity.sh",
)
SOURCE_NAMES = EXECUTION_SOURCE_NAMES
THREAD_NAMES = (
    "BLIS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "PCB_GNN_GMSH_THREADS",
)
PLANNER_SOURCE_NAMES = (
    "code/core/geometry_contract.py",
    "code/core/scientific_artifact.py",
    "code/data/verified_geometry_corpus.py",
    "code/experiments/proofs/plan_corpus_v4_cps_multifidelity.py",
)


def parse_prefixed(lines: list[str], prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for line in lines:
        if not line.startswith(prefix):
            continue
        try:
            record = json.loads(
                line[len(prefix) :],
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant: {value}")
                ),
            )
            if not isinstance(record, dict):
                raise TypeError("record is not an object")
            records.append(record)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            errors.append(str(error))
    return records, errors


def runtime_environment() -> dict[str, Any]:
    return {
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("gmsh", "meshio", "numpy", "pyamg", "scikit-fem", "scipy")
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_NAMES},
    }


def run_worker(
    layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int
) -> dict[str, Any]:
    worker = ROOT / "code/solvers/fem_cps_bounded_worker.py"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle, allow_nan=False, sort_keys=True)
        layout_path = Path(handle.name)
    command = [sys.executable, str(worker), str(layout_path), str(refine), str(pad_mm)]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=worker.parent,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONFAULTHANDLER": "1"},
            text=True,
            timeout=timeout_s,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode: int | None = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        returncode = None
        timed_out = True
    finally:
        layout_path.unlink(missing_ok=True)

    stdout_lines = stdout.splitlines()
    stages, stage_errors = parse_prefixed(stdout_lines, "STAGE=")
    results, result_errors = parse_prefixed(stdout_lines, "RESULT=")
    signal_name = None
    if returncode is not None and returncode < 0:
        try:
            signal_name = signal.Signals(-returncode).name
        except ValueError:
            signal_name = f"SIGNAL_{-returncode}"
    return {
        "returncode": returncode,
        "signal": signal_name,
        "stages": stages,
        "stderr_tail": stderr.splitlines()[-80:],
        "stdout_tail": stdout_lines[-20:],
        "telemetry_parse_errors": stage_errors + result_errors,
        "timed_out": timed_out,
        "wall_s": time.perf_counter() - started,
        "worker_result": results[0] if len(results) == 1 else None,
        "worker_result_count": len(results),
    }


def evaluate_result(
    execution: dict[str, Any], protocol: dict[str, Any], fidelity_id: str
) -> dict[str, Any]:
    result = execution.get("worker_result") or {}
    solver = protocol["linear_solver"]
    limits = protocol["resource_profiles"][fidelity_id]["fail_fast"]
    def safe_float(value: Any) -> float | None:
        try:
            converted = float(value)
        except (TypeError, ValueError):
            return None
        return converted if math.isfinite(converted) else None

    def safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    rss_kib = [
        value
        for stage in execution.get("stages", [])
        if (value := safe_float(stage.get("max_rss_kb"))) is not None
    ]
    peak_rss = max(rss_kib) if rss_kib else None
    observed = {
        "cps_pf": safe_float(result.get("cps_pf")),
        "eps_r": safe_float(result.get("eps_r")),
        "iterations": safe_int(result.get("iterations")),
        "maxiter": safe_int(result.get("maxiter")),
        "mesh_nodes": safe_int(result.get("mesh_nodes")),
        "mesh_tetrahedra": safe_int(result.get("mesh_tetrahedra")),
        "operator_complexity": safe_float(result.get("operator_complexity")),
        "pad_mm": safe_float(result.get("pad_mm")),
        "refine": safe_int(result.get("refine")),
        "relative_residual": safe_float(result.get("relative_residual")),
        "rtol": safe_float(result.get("rtol")),
        "solver_info": safe_int(result.get("solver_info")),
        "wall_s": safe_float(execution.get("wall_s")),
        "worker_peak_rss_gib": None if peak_rss is None else peak_rss / 1048576.0,
    }
    fidelity = protocol["fidelities"][fidelity_id]
    positive_finite = lambda value: isinstance(value, (int, float)) and value > 0.0
    input_hash = result.get("input_system_sha256")
    system_hash = result.get("system_sha256")
    valid_hash = lambda value: (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
    checks = {
        "cps_positive_finite": positive_finite(observed["cps_pf"]),
        "fidelity": (
            observed["refine"] == int(fidelity["refine"])
            and observed["pad_mm"] == float(fidelity["pad_mm"])
            and observed["eps_r"] == float(protocol["physics"]["eps_r"])
        ),
        "iterations": positive_finite(observed["iterations"])
        and observed["iterations"] <= int(solver["iterations_max"]),
        "mesh_nodes": positive_finite(observed["mesh_nodes"])
        and observed["mesh_nodes"] <= int(limits["mesh_nodes_max"]),
        "mesh_tetrahedra": (
            positive_finite(observed["mesh_tetrahedra"])
            and observed["mesh_tetrahedra"] <= int(limits["mesh_tetrahedra_max"])
        ),
        "operator_complexity": positive_finite(observed["operator_complexity"])
        and observed["operator_complexity"] <= float(limits["operator_complexity_max"]),
        "relative_residual": observed["relative_residual"] is not None
        and 0.0 <= observed["relative_residual"] <= float(solver["residual_max"]),
        "resource_rss": positive_finite(observed["worker_peak_rss_gib"])
        and observed["worker_peak_rss_gib"]
        <= float(limits["worker_peak_rss_gib_max"]),
        "resource_wall": positive_finite(observed["wall_s"])
        and observed["wall_s"] <= float(limits["wall_s_max"]),
        "solver_contract": (
            result.get("linear_solver") == solver["reported"]
            and observed["maxiter"] == int(solver["maxiter"])
            and observed["rtol"] == float(solver["rtol"])
            and observed["solver_info"] == int(solver["solver_info"])
        ),
        "system_fingerprint": valid_hash(input_hash)
        and valid_hash(system_hash)
        and input_hash == system_hash,
        "worker_execution": (
            execution.get("returncode") == 0
            and execution.get("worker_result_count") == 1
            and not execution.get("timed_out")
            and not execution.get("telemetry_parse_errors")
        ),
    }
    return {
        "checks": checks,
        "limits": limits,
        "observed": observed,
        "pass": all(checks.values()),
    }


def git_state() -> tuple[str, list[str], list[str]]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code", "protocols"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    return head, dirty, untracked_code


def expected_solver_contract_id(protocol: dict[str, Any], fidelity_id: str) -> str:
    fidelity = protocol["fidelities"][fidelity_id]
    return sha256_json(
        {
            "computational_sources": protocol["computational_sources"],
            "fidelity": {
                "pad_mm": fidelity["pad_mm"],
                "refine": fidelity["refine"],
            },
            "linear_solver": protocol["linear_solver"],
            "physics": protocol["physics"],
            "runtime": protocol["runtime"],
        }
    )


def validate_frozen_inputs(
    protocol_path: Path,
    plan_path: Path,
    expected_plan_sha256: str,
    manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str, str]:
    protocol = load_json(protocol_path)
    plan = load_json(plan_path)
    plan_sha256 = sha256_file(plan_path)
    if plan_sha256 != expected_plan_sha256:
        raise ValueError("plan SHA-256 differs from the externally pinned root")
    protocol_sha256 = sha256_file(protocol_path)
    if protocol.get("schema") != "pcb-gnn.cps-multifidelity-protocol.v1":
        raise ValueError("unexpected protocol schema")
    if plan.get("schema") != "pcb-gnn.cps-multifidelity-plan.v1":
        raise ValueError("unexpected plan schema")
    if plan.get("protocol_sha256") != protocol_sha256:
        raise ValueError("plan does not bind the supplied protocol")
    expected_artifacts = {
        "geometry_families.jsonl",
        "hf_selection_registry.json",
        "r3_manifest.jsonl",
        "r4_manifest.jsonl",
        "split_registry.json",
    }
    if set(plan.get("artifact_sha256", {})) != expected_artifacts:
        raise ValueError("plan artifact set differs from the frozen schema")
    if plan.get("counts") != {
        "families": 66,
        "geometries": 1500,
        "r3_tasks": int(protocol["fidelities"]["cps_fem_r3_p16"]["coverage"]),
        "r4_tasks": int(protocol["fidelities"]["cps_fem_r4_p16"]["coverage"]),
    }:
        raise ValueError("plan counts differ from the protocol")
    if plan.get("planner_environment") != {
        "numpy": protocol["runtime"]["packages"]["numpy"],
        "python": protocol["runtime"]["python"],
    }:
        raise ValueError("planner environment differs from the protocol")
    expected_planner_hashes = {
        name: sha256_file(ROOT / name) for name in PLANNER_SOURCE_NAMES
    }
    if plan.get("planner_source_sha256") != expected_planner_hashes:
        raise ValueError("planner sources differ from the frozen plan")

    manifest_name = manifest_path.name
    if manifest_name not in {"r3_manifest.jsonl", "r4_manifest.jsonl"}:
        raise ValueError("unsupported task manifest")
    manifest_sha256 = sha256_file(manifest_path)
    require_file_sha256(
        manifest_path, plan["artifact_sha256"][manifest_name], manifest_name
    )
    rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    fidelity_id = {
        "r3_manifest.jsonl": "cps_fem_r3_p16",
        "r4_manifest.jsonl": "cps_fem_r4_p16",
    }[manifest_name]
    expected_count = int(protocol["fidelities"][fidelity_id]["coverage"])
    expected_contract = expected_solver_contract_id(protocol, fidelity_id)
    if len(rows) != expected_count:
        raise ValueError("task manifest cardinality differs from the protocol")
    for index, row in enumerate(rows):
        if (
            row.get("schema") != MANIFEST_SCHEMA
            or row.get("task_index") != index
            or row.get("fidelity_id") != fidelity_id
            or row.get("protocol_sha256") != protocol_sha256
            or row.get("solver_contract_id") != expected_contract
        ):
            raise ValueError(f"invalid frozen task manifest row {index}")
    if len({row["geometry_sha256"] for row in rows}) != expected_count:
        raise ValueError("task manifest contains duplicate geometry")
    if plan.get("solver_contract_ids", {}).get(fidelity_id) != expected_contract:
        raise ValueError("plan solver contract differs from recomputed contract")
    return protocol, plan, rows, protocol_sha256, manifest_sha256


def validate_execution_lock(
    path: Path, expected_sha256: str
) -> tuple[dict[str, Any], str]:
    observed_sha256 = sha256_file(path)
    if observed_sha256 != expected_sha256:
        raise ValueError("execution-lock SHA-256 differs from the externally pinned root")
    lock = load_json(path)
    if lock.get("schema") != "pcb-gnn.cps-multifidelity-execution-lock.v1":
        raise ValueError("unexpected execution-lock schema")
    if set(lock.get("source_sha256", {})) != set(EXECUTION_SOURCE_NAMES):
        raise ValueError("execution-lock source set is not exact")
    observed_sources = {
        name: sha256_file(ROOT / name) for name in EXECUTION_SOURCE_NAMES
    }
    if lock["source_sha256"] != observed_sources:
        raise ValueError("execution sources differ from the externally pinned lock")
    return lock, observed_sha256


def parse_tres(specification: Any) -> dict[str, str]:
    """Parse the comma-delimited TRES fields emitted by ``scontrol -o``."""
    parsed: dict[str, str] = {}
    for item in str(specification or "").split(","):
        name, separator, value = item.partition("=")
        if separator and name:
            parsed[name] = value
    return parsed


def scheduler_resource_contract_matches(
    scheduler_fields: dict[str, str],
    *,
    allocated_cpus_per_task: int,
    mem_per_node_mb: int,
    profile: dict[str, Any],
) -> bool:
    """Separate the submitted request from memory-inflated CPU allocation.

    OSC may allocate more CPUs than ``--cpus-per-task`` when a large memory
    request determines the node share.  ``ReqTRES`` and ``TresPerTask`` retain
    the requested CPU count, whereas ``NumCPUs`` and ``CPUs/Task`` describe the
    actual allocation.  Both sides are validated and recorded explicitly.
    """
    requested_cpus = int(profile["cpus_per_task"])
    requested_mem_gib = int(profile["mem_gib"])
    requested_tres = parse_tres(scheduler_fields.get("ReqTRES"))
    per_task_tres = parse_tres(scheduler_fields.get("TresPerTask"))
    allocated_tres = parse_tres(scheduler_fields.get("AllocTRES"))
    return (
        allocated_cpus_per_task >= requested_cpus
        and mem_per_node_mb == requested_mem_gib * 1024
        and int(scheduler_fields.get("NumCPUs", "0"))
        == allocated_cpus_per_task
        and int(scheduler_fields.get("NumTasks", "0")) == 1
        and int(scheduler_fields.get("CPUs/Task", "0"))
        == allocated_cpus_per_task
        and requested_tres.get("cpu") == str(requested_cpus)
        and requested_tres.get("mem") == f"{requested_mem_gib}G"
        and per_task_tres.get("cpu") == str(requested_cpus)
        and allocated_tres.get("cpu") == str(allocated_cpus_per_task)
        and allocated_tres.get("mem") == f"{requested_mem_gib}G"
        and scheduler_fields.get("MinMemoryNode") == f"{requested_mem_gib}G"
    )


def validate_slurm_contract(
    fidelity_id: str, task_count: int, protocol: dict[str, Any]
) -> dict[str, Any]:
    required = (
        "SLURM_ARRAY_JOB_ID",
        "SLURM_ARRAY_TASK_ID",
        "SLURM_ARRAY_TASK_MIN",
        "SLURM_ARRAY_TASK_MAX",
        "SLURM_ARRAY_TASK_COUNT",
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_ID",
    )
    missing = [name for name in required if os.environ.get(name) is None]
    if missing:
        raise SystemExit(f"SLURM array environment is incomplete: {missing}")
    profile = protocol["resource_profiles"][fidelity_id]["slurm"]
    observed = {
        "array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
        "array_task_count": int(os.environ["SLURM_ARRAY_TASK_COUNT"]),
        "array_task_id": int(os.environ["SLURM_ARRAY_TASK_ID"]),
        "array_task_max": int(os.environ["SLURM_ARRAY_TASK_MAX"]),
        "array_task_min": int(os.environ["SLURM_ARRAY_TASK_MIN"]),
        "allocated_cpus_per_task": int(os.environ["SLURM_CPUS_PER_TASK"]),
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "mem_per_node_mb": int(os.environ.get("SLURM_MEM_PER_NODE", "0")),
        "partition": os.environ.get("SLURM_JOB_PARTITION"),
        "requested_cpus_per_task": int(profile["cpus_per_task"]),
    }
    scheduler_query = subprocess.run(
        ["scontrol", "show", "job", "-o", str(observed["job_id"])],
        capture_output=True,
        check=False,
        text=True,
    )
    if scheduler_query.returncode != 0 or not scheduler_query.stdout.strip():
        raise SystemExit("SLURM_JOB_ID is not confirmed by the active scheduler")
    scheduler_fields = {
        token.split("=", 1)[0]: token.split("=", 1)[1]
        for token in scheduler_query.stdout.split()
        if "=" in token
    }
    array_query = subprocess.run(
        ["scontrol", "show", "job", "-o", str(observed["array_job_id"])],
        capture_output=True,
        check=False,
        text=True,
    )
    if array_query.returncode != 0 or not array_query.stdout.strip():
        raise SystemExit("SLURM array job is not confirmed by the active scheduler")
    array_fields = {
        token.split("=", 1)[0]: token.split("=", 1)[1]
        for token in array_query.stdout.splitlines()[0].split()
        if "=" in token
    }
    expected_time = (
        f"{int(profile['time_s']) // 3600:02d}:"
        f"{(int(profile['time_s']) % 3600) // 60:02d}:"
        f"{int(profile['time_s']) % 60:02d}"
    )
    if (
        observed["array_task_min"] != 0
        or observed["array_task_max"] != task_count - 1
        or observed["array_task_count"] != task_count
        or observed["partition"] != profile["partition"]
        or scheduler_fields.get("ArrayJobId") != observed["array_job_id"]
        or int(scheduler_fields.get("ArrayTaskId", "-1")) != observed["array_task_id"]
        or scheduler_fields.get("Partition") != profile["partition"]
        or not scheduler_resource_contract_matches(
            scheduler_fields,
            allocated_cpus_per_task=observed["allocated_cpus_per_task"],
            mem_per_node_mb=observed["mem_per_node_mb"],
            profile=profile,
        )
        or scheduler_fields.get("TimeLimit") != expected_time
        or scheduler_fields.get("JobState") not in {"RUNNING", "COMPLETING"}
        or int(array_fields.get("ArrayTaskThrottle", "-1"))
        != int(profile["max_concurrent"])
    ):
        raise SystemExit(f"SLURM allocation differs from frozen protocol: {observed}")
    observed["scheduler_record"] = scheduler_fields
    observed["scheduler_array_record"] = array_fields
    return observed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--execution-lock", type=Path)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--retry-task-set", type=Path)
    parser.add_argument("--expected-retry-task-set-sha256")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--timeout-s", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    static_inputs = (
        args.protocol,
        args.plan,
        args.expected_plan_sha256,
        args.manifest,
        args.execution_lock,
        args.expected_execution_lock_sha256,
    )
    if any(value is None for value in static_inputs):
        raise SystemExit(
            "protocol, plan, expected-plan-sha256, and manifest are required"
        )
    protocol, plan, rows, protocol_sha256, initial_manifest_sha256 = (
        validate_frozen_inputs(
            args.protocol,
            args.plan,
            args.expected_plan_sha256,
            args.manifest,
        )
    )
    execution_lock, execution_lock_sha256 = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    initial_plan_sha256 = sha256_file(args.plan)
    manifest_name = args.manifest.name
    retry_enabled = args.retry_task_set is not None or args.expected_retry_task_set_sha256 is not None
    if retry_enabled and (
        args.retry_task_set is None or args.expected_retry_task_set_sha256 is None
    ):
        raise SystemExit("retry task set and its externally pinned SHA-256 are both required")
    active_task_indices = list(range(len(rows)))
    retry_task_set_sha256 = None
    if retry_enabled:
        retry_task_set_sha256 = sha256_file(args.retry_task_set)
        if retry_task_set_sha256 != args.expected_retry_task_set_sha256:
            raise ValueError("retry task-set SHA-256 differs from its pinned root")
        retry = load_json(args.retry_task_set)
        if (
            retry.get("schema") != "pcb-gnn.cps-multifidelity-pending-task-set.v1"
            or retry.get("plan_sha256") != initial_plan_sha256
            or retry.get("manifest_sha256") != initial_manifest_sha256
            or retry.get("execution_lock_sha256") != execution_lock_sha256
            or retry.get("fidelity_id") != rows[0]["fidelity_id"]
        ):
            raise ValueError("retry task set does not bind the canonical manifest")
        active_task_indices = [int(entry["task_index"]) for entry in retry.get("pending", [])]
        if (
            not active_task_indices
            or len(set(active_task_indices)) != len(active_task_indices)
            or any(index not in range(len(rows)) for index in active_task_indices)
        ):
            raise ValueError("retry task set is empty, duplicate, or outside the manifest")
        for entry, canonical_index in zip(retry["pending"], active_task_indices):
            canonical = rows[canonical_index]
            if (
                entry.get("layout_id") != canonical["layout_id"]
                or entry.get("geometry_sha256") != canonical["geometry_sha256"]
            ):
                raise ValueError("retry task identity differs from the canonical manifest")
    if args.validate_only:
        print(
            json.dumps(
                {
                    "manifest_sha256": initial_manifest_sha256,
                    "n_tasks": len(active_task_indices),
                    "plan_sha256": initial_plan_sha256,
                    "retry_task_set_sha256": retry_task_set_sha256,
                    "execution_lock_sha256": execution_lock_sha256,
                    "schema": SCHEMA,
                    "status": "validation-ok",
                },
                sort_keys=True,
            )
        )
        return
    if args.corpus is None or args.output_root is None:
        raise SystemExit("corpus and output-root are required for execution")
    array_task_id = int(os.environ.get("SLURM_ARRAY_TASK_ID", "-1"))
    if array_task_id not in range(len(active_task_indices)):
        raise SystemExit("SLURM task ID is outside the frozen manifest")
    task_id = active_task_indices[array_task_id]
    task = rows[task_id]
    if task.get("schema") != MANIFEST_SCHEMA or task.get("task_index") != task_id:
        raise ValueError("task manifest is not dense or uses an unexpected schema")
    if task.get("protocol_sha256") != protocol_sha256:
        raise ValueError("task does not bind the supplied protocol")
    fidelity_id = task["fidelity_id"]
    if fidelity_id not in protocol["fidelities"]:
        raise ValueError("task requests a fidelity outside the frozen protocol")
    expected_manifest = {
        "cps_fem_r3_p16": "r3_manifest.jsonl",
        "cps_fem_r4_p16": "r4_manifest.jsonl",
    }[fidelity_id]
    if manifest_name != expected_manifest:
        raise ValueError("manifest filename/fidelity mismatch")
    if task.get("solver_contract_id") != plan["solver_contract_ids"][fidelity_id]:
        raise ValueError("task solver contract differs from the frozen plan")
    slurm = validate_slurm_contract(fidelity_id, len(active_task_indices), protocol)
    slurm["canonical_task_index"] = task_id
    slurm["retry_task_set_sha256"] = retry_task_set_sha256

    head, dirty, untracked_code = git_state()
    if dirty or untracked_code:
        raise SystemExit("refusing scientific task from dirty or untracked source")
    source_hashes = {name: sha256_file(ROOT / name) for name in SOURCE_NAMES}
    if source_hashes != execution_lock["source_sha256"]:
        raise ValueError("execution source map differs from the pinned lock")
    for name, expected in protocol["computational_sources"].items():
        if source_hashes.get(name) != expected:
            raise ValueError(f"computational source differs from protocol: {name}")
    executed_batch_script = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not executed_batch_script.is_file():
        raise SystemExit("exact executed batch script is unavailable")
    tracked_batch = {
        "cps_fem_r3_p16": "code/jobs/submit_corpus_v4_cps_r3.sh",
        "cps_fem_r4_p16": "code/jobs/submit_corpus_v4_cps_r4.sh",
    }[fidelity_id]
    executed_batch_sha256 = sha256_file(executed_batch_script)
    if executed_batch_sha256 != source_hashes[tracked_batch]:
        raise SystemExit("executed batch script differs from tracked source")

    environment = runtime_environment()
    expected_runtime = protocol["runtime"]
    if (
        environment["python"] != expected_runtime["python"]
        or environment["package_versions"] != expected_runtime["packages"]
        or environment["thread_environment"] != expected_runtime["threads"]
    ):
        raise SystemExit("runtime environment differs from frozen protocol")

    records, corpus_summary = load_verified_geometry_corpus(
        args.corpus, protocol["input_geometry_corpus"]
    )
    record_by_id = {record["layout_id"]: record for record in records}
    record = record_by_id.get(task["layout_id"])
    if record is None:
        raise ValueError("manifest layout ID is absent from the verified corpus")
    if (
        record["layout_id"] != task["layout_id"]
        or record["geometry_sha256"] != task["geometry_sha256"]
    ):
        raise ValueError("manifest geometry differs from verified corpus")

    attempt_dir = (
        args.output_root
        / "attempts"
        / f"job_{slurm['array_job_id']}"
    )
    output_path = attempt_dir / f"task_{task_id:04d}.json"
    started_path = attempt_dir / f"task_{task_id:04d}.started.json"
    if output_path.exists() or started_path.exists():
        raise SystemExit("refusing to overwrite an existing task attempt")
    fidelity = protocol["fidelities"][fidelity_id]
    timeout_s = args.timeout_s or int(
        protocol["resource_profiles"][fidelity_id]["fail_fast"]["wall_s_max"]
    )
    if timeout_s != int(
        protocol["resource_profiles"][fidelity_id]["fail_fast"]["wall_s_max"]
    ):
        raise ValueError("worker timeout differs from the frozen resource profile")
    atomic_write_json(
        started_path,
        {
            "fidelity_id": fidelity_id,
            "geometry_sha256": record["geometry_sha256"],
            "git_head": head,
            "layout_id": record["layout_id"],
            "manifest_sha256": initial_manifest_sha256,
            "plan_sha256": initial_plan_sha256,
            "protocol_sha256": protocol_sha256,
            "schema": "pcb-gnn.cps-multifidelity-attempt-start.v1",
            "slurm": slurm,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "task_index": task_id,
        },
    )
    execution = run_worker(
        record["layout"], int(fidelity["refine"]), float(fidelity["pad_mm"]), timeout_s
    )
    gate = evaluate_result(execution, protocol, fidelity_id)

    final_head, final_dirty, final_untracked_code = git_state()
    final_source_hashes = {name: sha256_file(ROOT / name) for name in SOURCE_NAMES}
    final_plan_sha256 = sha256_file(args.plan)
    final_manifest_sha256 = sha256_file(args.manifest)
    final_retry_task_set_sha256 = (
        sha256_file(args.retry_task_set) if retry_enabled else None
    )
    final_executed_batch_sha256 = sha256_file(executed_batch_script)
    final_execution_lock_sha256 = sha256_file(args.execution_lock)
    source_stable = (
        final_head == head
        and not final_dirty
        and not final_untracked_code
        and final_source_hashes == source_hashes
        and final_plan_sha256 == initial_plan_sha256
        and final_manifest_sha256 == initial_manifest_sha256
        and final_retry_task_set_sha256 == retry_task_set_sha256
        and final_executed_batch_sha256 == executed_batch_sha256
        and final_execution_lock_sha256 == execution_lock_sha256
    )
    payload = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "fidelity": {"fidelity_id": fidelity_id, **fidelity},
        "geometry": {
            "geometry_sha256": record["geometry_sha256"],
            "layout_id": record["layout_id"],
        },
        "numerical_resource_gate": gate,
        "provenance": {
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "environment": environment,
            "executed_batch_script": {
                "path": str(executed_batch_script),
                "sha256": executed_batch_sha256,
            },
            "execution_lock_sha256": execution_lock_sha256,
            "final_git_dirty_paths": final_dirty,
            "final_git_head": final_head,
            "final_source_file_sha256": final_source_hashes,
            "final_untracked_code": final_untracked_code,
            "git_dirty_paths": dirty,
            "git_head": head,
            "hostname": socket.gethostname(),
            "final_executed_batch_script_sha256": final_executed_batch_sha256,
            "final_manifest_sha256": final_manifest_sha256,
            "final_plan_sha256": final_plan_sha256,
            "manifest_sha256": initial_manifest_sha256,
            "plan_sha256": initial_plan_sha256,
            "retry_task_set_sha256": retry_task_set_sha256,
            "protocol_sha256": protocol_sha256,
            "slurm": slurm,
            "source_file_sha256": source_hashes,
            "source_stable": source_stable,
            "untracked_code": untracked_code,
        },
        "schema": SCHEMA,
        "solver_contract_id": task["solver_contract_id"],
        "task_index": task_id,
        "task_pass": bool(gate["pass"] and source_stable),
    }
    atomic_write_json(output_path, payload)
    print(json.dumps({"output": str(output_path), "task_pass": payload["task_pass"]}))
    if not payload["task_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
