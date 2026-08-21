#!/usr/bin/env python3
"""Run one immutable Corpus-v4 FEM repeatability pair under SLURM.

This is a diagnostic experiment, not a latency or accuracy benchmark.  Each
array element remeshes one frozen geometry twice: once with the admitted
25-thread Gmsh setting and once with a one-thread diagnostic setting.  The
isolated worker preserves the frozen R3P16 numerical and resource path while
adding mandatory child-observed thread telemetry.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
for directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/experiments/proofs",
    ROOT / "code/solvers",
):
    sys.path.insert(0, str(directory))

from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    evaluate_result,
    parse_prefixed,
)
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402


PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-protocol.v1"
ATTEMPT_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-attempt.v1"
ARM_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-arm.v1"
MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-attempt-manifest.v1"
SUMMARY_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-summary.v1"
VALIDATION_SCHEMA = "pcb-gnn.corpus-v4-fem-repeatability-validation.v1"
GMSH_TELEMETRY_SCHEMA = "pcb-gnn.gmsh-thread-observation.v1"
EXPECTED_COMPUTATIONAL_SOURCE_NAMES = {
    "code/core/geometry_contract.py",
    "code/core/scientific_artifact.py",
    "code/data/verified_geometry_corpus.py",
    "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py",
    "code/experiments/proofs/experiments_corpus_v4_fem_repeatability.py",
    "code/experiments/proofs/finalize_corpus_v4_fem_repeatability.py",
    "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py",
    "code/jobs/slurm_job_env.sh",
    "code/jobs/submit_corpus_v4_fem_repeatability.sh",
    "code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh",
    "code/solvers/fem_capacitance_3d.py",
    "code/solvers/fem_cps_bounded_worker.py",
    "code/solvers/fem_cps_diagnostic_worker.py",
    "code/solvers/fem_cps_repeatability_worker.py",
    "requirements-proof.txt",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("protocols/corpus_v4_fem_repeatability_v1.json"),
    )
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/corpus_v4/fem_repeatability/v1"),
    )
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _resolve_repo_path(value: str, label: str) -> Path:
    candidate = (ROOT / value).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    return candidate


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"expected JSON-object rows: {path}")
    return rows


def validate_protocol(protocol: Mapping[str, Any]) -> None:
    """Reject any change to the predeclared experiment semantics."""
    expected_keys = {
        "arms",
        "artifact_contract",
        "computational_sources",
        "diagnostic_semantics",
        "gates",
        "inputs",
        "panel",
        "protocol_name",
        "repetitions",
        "resources",
        "runtime",
        "schema",
        "statistics",
        "workflow",
    }
    if set(protocol) != expected_keys:
        raise ValueError("repeatability protocol top-level contract differs")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unexpected repeatability protocol schema")
    if protocol.get("protocol_name") != "corpus-v4-fem-r3p16-repeatability-v1":
        raise ValueError("unexpected repeatability protocol name")

    arms = protocol["arms"]
    if arms != [
        {
            "arm_id": "arm_a_threads25",
            "gmsh_threads": 25,
            "old_reference_gate_required": True,
            "role": "admitted_r3p16_resource_replay_with_telemetry",
        },
        {
            "arm_id": "arm_b_threads1",
            "gmsh_threads": 1,
            "old_reference_gate_required": False,
            "role": "deterministic_candidate_diagnostic_only",
        },
    ]:
        raise ValueError("repeatability arm definitions differ")

    repetitions = protocol["repetitions"]
    if repetitions != {
        "array_mapping": "panel_index=array_task_id//5; repeat_id=array_task_id%5",
        "array_task_count": 15,
        "array_task_ids": list(range(15)),
        "fresh_mesh_per_arm": True,
        "independent_repeats_per_layout_arm": 5,
        "repeat_ids": list(range(5)),
        "sequential_arms_in_one_allocation": True,
    }:
        raise ValueError("repeatability mapping differs")

    expected_panel = [
        (0, 3, "turns-06-06", "7a2d1c6a3de5064e483a6db9c2d4612fe2978fcefa4ad675cfccbd1dc3fbf685"),
        (152, 734, "turns-05-11", "9c30ee48eb3920b031a21cb4464e0547ba65f88cda116572ecdb08aa2f684f0a"),
        (305, 1495, "turns-05-12", "c22655637cfbebd74aaf33cfae599056561ce4ab39126afee9a7b35885fc1788"),
    ]
    panel = protocol["panel"]
    observed_panel = [
        (
            row.get("latency_task_id"),
            row.get("layout_id"),
            row.get("family_id"),
            row.get("geometry_sha256"),
        )
        for row in panel
    ]
    if observed_panel != expected_panel:
        raise ValueError("repeatability panel differs from frozen preflight anchors")
    references = [row.get("frozen_r3_cps_pf") for row in panel]
    if references != [12.033283413797877, 39.604875462334206, 40.31623684447307]:
        raise ValueError("frozen Cps references differ")

    workflow = protocol["workflow"]
    if workflow != {
        "fidelity_id": "cps_fem_r3_p16",
        "linear_solver_requested": "amg_cg",
        "pad_mm": 16.0,
        "refine": 3,
        "repeatability_worker": "code/solvers/fem_cps_repeatability_worker.py",
        "timeout_s": 1800,
    }:
        raise ValueError("repeatability solver workflow differs from R3P16")

    resources = protocol["resources"]
    if resources != {
        "finalizer": {
            "account": "pgs0407",
            "allocated_cpus_may_exceed_request": True,
            "cpus_per_task": 2,
            "memory_gib": 8,
            "nodes": 1,
            "ntasks": 1,
            "partition": "nextgen",
            "time_limit": "00:30:00",
        },
        "source_array": {
            "account": "pgs0407",
            "allocated_cpus_may_exceed_request": False,
            "array": "0-14%3",
            "array_throttle": 3,
            "cpus_per_task": 25,
            "memory_gib": 48,
            "nodes": 1,
            "ntasks": 1,
            "partition": "nextgen",
            "time_limit": "02:00:00",
        },
    }:
        raise ValueError("repeatability SLURM resources differ")

    gates = protocol["gates"]
    if float(gates.get("relative_tolerance", -1.0)) != 1e-4:
        raise ValueError("the predeclared 1e-4 tolerance changed")
    if gates.get("relative_formula") != "abs(x-y)/max(abs(x),abs(y),1e-12)":
        raise ValueError("unexpected repeatability relative-difference formula")
    if gates.get("reference_formula") != "abs(rerun-reference)/max(abs(reference),1e-12)":
        raise ValueError("unexpected frozen-reference formula")
    if gates.get("arm_a_all_five_reference_drifts_must_pass") is not True:
        raise ValueError("arm-A reference gate must remain strict")
    if gates.get("mesh_identity_requires_one_system_sha256") is not True:
        raise ValueError("system identity gate must remain strict")
    if gates.get("mesh_identity_requires_fixed_counts") is not True:
        raise ValueError("mesh-count identity gate must remain strict")
    if gates.get("all_15_scheduler_rows_completed_zero_required_for_resume") is not True:
        raise ValueError("terminal accounting gate must remain strict")

    contract = protocol["artifact_contract"]
    required_true = (
        "all_attempts_retained",
        "atomic_final_directory",
        "atomic_per_arm_write",
        "complete_failed_diagnostics_retained",
        "immutable_attempt_directory",
        "raw_worker_result_required",
        "source_reauthenticated_after_each_arm",
        "child_gmsh_thread_observation_required",
        "post_finalizer_terminal_admission_required",
        "terminal_accounting_required",
    )
    if any(contract.get(name) is not True for name in required_true):
        raise ValueError("repeatability artifact contract was weakened")
    semantics = protocol["diagnostic_semantics"]
    if (
        semantics.get("claim_eligible") is not False
        or semantics.get("speed_claim_eligible") is not False
        or semantics.get("old_labels_may_be_replaced") is not False
        or semantics.get("tolerance_may_be_changed_after_observation") is not False
    ):
        raise ValueError("repeatability diagnostic semantics were weakened")

    source_map = protocol["computational_sources"]
    if (
        set(source_map) != EXPECTED_COMPUTATIONAL_SOURCE_NAMES
        or any(not _is_sha256(value) for value in source_map.values())
    ):
        raise ValueError("computational source map is missing or malformed")
    for binding in protocol["inputs"].values():
        if not isinstance(binding, dict) or not _is_sha256(binding.get("sha256")):
            raise ValueError("input binding is missing a SHA-256")


def task_mapping(array_task_id: int, protocol: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
    if type(array_task_id) is not int or array_task_id not in range(15):
        raise ValueError("array task ID is outside 0..14")
    repeat_id = array_task_id % 5
    panel_index = array_task_id // 5
    return dict(protocol["panel"][panel_index]), repeat_id


def arm_order(repeat_id: int, protocol: Mapping[str, Any]) -> list[dict[str, Any]]:
    if type(repeat_id) is not int or repeat_id not in range(5):
        raise ValueError("repeat ID is outside 0..4")
    arms = [dict(arm) for arm in protocol["arms"]]
    return arms if repeat_id % 2 == 0 else list(reversed(arms))


def _validate_bound_inputs(
    protocol: Mapping[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[str, str]]:
    bindings: dict[str, str] = {}
    for label, binding in protocol["inputs"].items():
        path = _resolve_repo_path(binding["path"], label)
        observed = sha256_file(path)
        if observed != binding["sha256"]:
            raise ValueError(f"input SHA-256 mismatch: {label}")
        bindings[label] = observed
    for name, expected in protocol["computational_sources"].items():
        path = _resolve_repo_path(name, "computational source")
        if sha256_file(path) != expected:
            raise ValueError(f"computational source SHA-256 mismatch: {name}")

    cps_protocol = _load_json(
        _resolve_repo_path(protocol["inputs"]["cps_protocol"]["path"], "Cps protocol")
    )
    fidelity = cps_protocol["fidelities"]["cps_fem_r3_p16"]
    if (
        int(fidelity["refine"]) != 3
        or float(fidelity["pad_mm"]) != 16.0
        or cps_protocol["linear_solver"]["requested"] != "amg_cg"
        or int(cps_protocol["resource_profiles"]["cps_fem_r3_p16"]["fail_fast"]["wall_s_max"]) != 1800
    ):
        raise ValueError("bound Cps protocol no longer defines exact R3P16")

    geometry_contract = protocol["inputs"]["geometry_contract"]
    records, _ = load_verified_geometry_corpus(
        _resolve_repo_path(geometry_contract["directory"], "geometry corpus"),
        geometry_contract["loader_contract"],
    )
    records_by_id = {int(record["layout_id"]): record for record in records}

    latency_rows = _load_jsonl(
        _resolve_repo_path(
            protocol["inputs"]["latency_task_manifest"]["path"],
            "latency task manifest",
        )
    )
    evaluation_rows = {
        int(row["layout_id"]): row
        for row in _load_jsonl(
            _resolve_repo_path(
                protocol["inputs"]["evaluation_dataset"]["path"],
                "evaluation dataset",
            )
        )
    }
    for expected in protocol["panel"]:
        task_id = int(expected["latency_task_id"])
        if task_id >= len(latency_rows):
            raise ValueError("panel task is absent from latency manifest")
        task = latency_rows[task_id]
        record = records_by_id.get(int(expected["layout_id"]))
        evaluation = evaluation_rows.get(int(expected["layout_id"]))
        identity = ("layout_id", "family_id", "geometry_sha256")
        if any(task.get(name) != expected[name] for name in identity):
            raise ValueError("panel differs from latency task manifest")
        if record is None or any(record.get(name) != expected[name] for name in ("layout_id", "geometry_sha256")):
            raise ValueError("panel differs from verified geometry corpus")
        if evaluation is None or any(evaluation.get(name) != expected[name] for name in identity):
            raise ValueError("panel differs from evaluation dataset")
        cps_reference = evaluation["training_reference"]["Cps_pF"]
        if (
            cps_reference.get("fidelity_id") != "cps_fem_r3_p16"
            or cps_reference.get("units") != "pF"
            or float(cps_reference.get("value")) != float(expected["frozen_r3_cps_pf"])
        ):
            raise ValueError("panel Cps reference differs from frozen evaluation dataset")
    return records_by_id, bindings


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
    source_untracked = subprocess.run(
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
    return head, tracked, source_untracked


def _assert_source_stable(
    *,
    expected_head: str,
    protocol: Mapping[str, Any],
    protocol_path: Path,
    protocol_sha256: str,
) -> dict[str, str]:
    head, dirty, untracked = _source_state()
    if head != expected_head or dirty or untracked:
        raise SystemExit("refusing repeatability execution from changed source state")
    source_hashes = {
        name: sha256_file(_resolve_repo_path(name, "computational source"))
        for name in protocol["computational_sources"]
    }
    if source_hashes != protocol["computational_sources"]:
        raise SystemExit("computational source changed during repeatability execution")
    if sha256_file(protocol_path) != protocol_sha256:
        raise SystemExit("repeatability protocol changed during execution")
    for label, binding in protocol["inputs"].items():
        if sha256_file(_resolve_repo_path(binding["path"], label)) != binding["sha256"]:
            raise SystemExit(f"bound input changed during execution: {label}")
    return source_hashes


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


def _memory_is_48_gib(value: str) -> bool:
    # Slurm exports SLURM_MEM_PER_NODE as an integer MiB value, while scontrol
    # normally renders the same allocation as 48G.
    return value in {"49152", "48G", "49152M", "50331648K"}


def _same_node_identity(first: str, second: str) -> bool:
    """Match the same scheduler node across short-name and FQDN renderings."""
    return bool(first and second) and first.split(".", 1)[0] == second.split(".", 1)[0]


def parse_tres_exact(value: str) -> dict[str, str]:
    """Parse a canonical comma-separated TRES map without substring matching."""
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


def validate_slurm_allocation(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Require the exact 15-element diagnostic allocation and live task record."""
    required_environment = (
        "SLURM_ARRAY_JOB_ID",
        "SLURM_ARRAY_TASK_COUNT",
        "SLURM_ARRAY_TASK_ID",
        "SLURM_ARRAY_TASK_MAX",
        "SLURM_ARRAY_TASK_MIN",
        "SLURM_CPUS_PER_TASK",
        "SLURM_JOB_ACCOUNT",
        "SLURM_JOB_ID",
        "SLURM_JOB_PARTITION",
        "SLURM_MEM_PER_NODE",
        "SLURMD_NODENAME",
    )
    missing = [name for name in required_environment if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"FEM repeatability solving is SLURM-only; missing {missing}")
    resources = protocol["resources"]["source_array"]
    observed = {
        "array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
        "array_task_count": int(os.environ["SLURM_ARRAY_TASK_COUNT"]),
        "array_task_id": int(os.environ["SLURM_ARRAY_TASK_ID"]),
        "array_task_max": int(os.environ["SLURM_ARRAY_TASK_MAX"]),
        "array_task_min": int(os.environ["SLURM_ARRAY_TASK_MIN"]),
        "cpus_per_task": int(os.environ["SLURM_CPUS_PER_TASK"]),
        "job_account": os.environ["SLURM_JOB_ACCOUNT"],
        "job_id": os.environ["SLURM_JOB_ID"],
        "partition": os.environ["SLURM_JOB_PARTITION"],
        "memory": os.environ["SLURM_MEM_PER_NODE"],
        "slurmd_nodename": os.environ["SLURMD_NODENAME"],
    }
    if (
        observed["array_task_count"] != 15
        or observed["array_task_min"] != 0
        or observed["array_task_max"] != 14
        or observed["array_task_id"] not in range(15)
        or observed["cpus_per_task"] != int(resources["cpus_per_task"])
        or observed["job_account"] != resources["account"]
        or observed["partition"] != resources["partition"]
        or not _memory_is_48_gib(observed["memory"])
    ):
        raise SystemExit("SLURM environment differs from frozen repeatability resources")

    component_id = f"{observed['array_job_id']}_{observed['array_task_id']}"
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", component_id],
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0 or not query.stdout.strip():
        raise SystemExit("active repeatability array element is not confirmed by Slurm")
    matches = [
        record
        for record in _parse_scontrol(query.stdout)
        if record.get("JobId") == observed["job_id"]
        and record.get("ArrayJobId") == observed["array_job_id"]
        and record.get("ArrayTaskId") == str(observed["array_task_id"])
    ]
    if len(matches) != 1:
        raise SystemExit("active repeatability scheduler record is missing or ambiguous")
    record = matches[0]
    required_fields = {
        "Account": resources["account"],
        "ArrayTaskThrottle": str(resources["array_throttle"]),
        "CPUs/Task": str(resources["cpus_per_task"]),
        "JobState": "RUNNING",
        "MinMemoryNode": "48G",
        "NumCPUs": str(resources["cpus_per_task"]),
        "NumTasks": str(resources["ntasks"]),
        "Partition": resources["partition"],
        "TimeLimit": resources["time_limit"],
        "TresPerTask": f"cpu={resources['cpus_per_task']}",
    }
    if (
        any(record.get(name) != value for name, value in required_fields.items())
        or not _same_node_identity(
            observed["slurmd_nodename"], record.get("NodeList", "")
        )
    ):
        raise SystemExit("live scheduler record differs from frozen repeatability resources")
    expected_tres = {"billing": "25", "cpu": "25", "mem": "48G", "node": "1"}
    for field in ("ReqTRES", "AllocTRES"):
        try:
            tres = parse_tres_exact(record.get(field, ""))
        except ValueError as exc:
            raise SystemExit(
                f"{field} differs from frozen repeatability resources"
            ) from exc
        if tres != expected_tres:
            raise SystemExit(f"{field} differs from frozen repeatability resources")
    # Retain the scheduler identity fields that were used to select the one
    # live component record.  The finalizer replays them against terminal
    # accounting, so dropping them here would make the producer and consumer
    # contracts inconsistent even though the allocation was validated live.
    retained_fields = set(required_fields) | {
        "AllocTRES",
        "ArrayJobId",
        "ArrayTaskId",
        "JobId",
        "NodeList",
        "ReqTRES",
    }
    retained_record = {name: record[name] for name in sorted(retained_fields)}
    return {**observed, "scheduler_record": retained_record}


def _runtime_identity(protocol: Mapping[str, Any]) -> dict[str, Any]:
    expected = protocol["runtime"]
    actual = {
        "packages": {
            name: importlib.metadata.version(name) for name in expected["packages"]
        },
        "python": platform.python_version(),
        "thread_environment": {
            name: os.environ.get(name) for name in expected["thread_environment"]
        },
    }
    if actual != expected:
        raise SystemExit("runtime or base thread environment differs from protocol")
    return actual


def _hardware_identity() -> dict[str, Any]:
    cpu_model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                cpu_model = line.split(":", 1)[1].strip()
                break
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    payload = {
        "affinity_cpu_count": len(affinity),
        "architecture": platform.machine(),
        "cpu_model": cpu_model,
        "kernel": platform.release(),
    }
    return {**payload, "anonymous_class_sha256": sha256_bytes(canonical_json_bytes(payload))}


@contextmanager
def _arm_environment(gmsh_threads: int) -> Iterator[None]:
    updates = {
        "PCB_GNN_GMSH_THREADS": str(gmsh_threads),
    }
    previous = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def gmsh_thread_gate(
    execution: Mapping[str, Any], expected_threads: int
) -> dict[str, Any]:
    """Gate the thread value observed inside the bounded-worker child."""
    observations = [
        stage
        for stage in execution.get("stages", [])
        if isinstance(stage, dict)
        and stage.get("stage") == "repeatability_environment"
    ]
    observed = None
    telemetry_contract = None
    if len(observations) == 1:
        observed = observations[0].get("gmsh_threads")
        telemetry_contract = observations[0].get("telemetry_contract")
    passed = (
        len(observations) == 1
        and type(observed) is int
        and observed == expected_threads
        and telemetry_contract == GMSH_TELEMETRY_SCHEMA
    )
    return {
        "expected_gmsh_threads": expected_threads,
        "observation_count": len(observations),
        "observed_gmsh_threads": observed,
        "pass": passed,
        "telemetry_contract": telemetry_contract,
    }


def run_repeatability_worker(
    layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int
) -> dict[str, Any]:
    """Run the isolated instrumented worker with production-equivalent limits."""
    worker = ROOT / "code/solvers/fem_cps_repeatability_worker.py"
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
        stdout = (
            error.stdout.decode()
            if isinstance(error.stdout, bytes)
            else (error.stdout or "")
        )
        stderr = (
            error.stderr.decode()
            if isinstance(error.stderr, bytes)
            else (error.stderr or "")
        )
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


def _relative_reference_drift(value: float, reference: float) -> float:
    return abs(value - reference) / max(abs(reference), 1e-12)


def _signed_reference_drift(value: float, reference: float) -> float:
    return (value - reference) / max(abs(reference), 1e-12)


def run_arm(
    *,
    arm: Mapping[str, Any],
    layout: dict[str, Any],
    panel: Mapping[str, Any],
    repeat_id: int,
    order_position: int,
    cps_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute one fresh worker subprocess and preserve its raw result."""
    with _arm_environment(int(arm["gmsh_threads"])):
        execution = run_repeatability_worker(layout, 3, 16.0, 1800)
    gate = evaluate_result(execution, dict(cps_protocol), "cps_fem_r3_p16")
    thread_gate = gmsh_thread_gate(execution, int(arm["gmsh_threads"]))
    worker_result = execution.get("worker_result")
    if not isinstance(worker_result, dict):
        worker_result = {}
    # This also rejects NaN/Infinity before an artifact reaches disk.
    worker_bytes = canonical_json_bytes(worker_result)
    execution_bytes = canonical_json_bytes(execution)
    cps_pf = worker_result.get("cps_pf")
    finite_cps = isinstance(cps_pf, (int, float)) and math.isfinite(float(cps_pf))
    reference = float(panel["frozen_r3_cps_pf"])
    reference_drift = (
        _relative_reference_drift(float(cps_pf), reference) if finite_cps else None
    )
    signed_reference_drift = (
        _signed_reference_drift(float(cps_pf), reference) if finite_cps else None
    )
    return {
        "arm": dict(arm),
        "claim_eligible": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "execution_sha256": sha256_bytes(execution_bytes),
        "frozen_reference": {"cps_pf": reference, "units": "pF"},
        "geometry": {
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "layout_id": panel["layout_id"],
        },
        "gmsh_thread_gate": thread_gate,
        "numerical_resource_gate": gate,
        "old_reference_relative_drift": reference_drift,
        "old_reference_signed_relative_drift": signed_reference_drift,
        "order_position": order_position,
        "repeat_id": repeat_id,
        "schema": ARM_SCHEMA,
        "speed_claim_eligible": False,
        "worker_result": worker_result,
        "worker_result_sha256": sha256_bytes(worker_bytes),
    }


def _max_pairwise_relative(values: Sequence[float]) -> float:
    return max(
        (
            abs(first - second) / max(abs(first), abs(second), 1e-12)
            for first, second in combinations(values, 2)
        ),
        default=0.0,
    )


def summarize_repeatability(
    observations: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply the frozen finite-panel gates to exactly 30 arm observations."""
    validate_protocol(protocol)
    expected_keys = {
        (int(panel["layout_id"]), repeat_id, arm["arm_id"])
        for panel in protocol["panel"]
        for repeat_id in range(5)
        for arm in protocol["arms"]
    }
    indexed: dict[tuple[int, int, str], Mapping[str, Any]] = {}
    for observation in observations:
        key = (
            int(observation["geometry"]["layout_id"]),
            int(observation["repeat_id"]),
            str(observation["arm"]["arm_id"]),
        )
        if key in indexed:
            raise ValueError("duplicate repeatability observation")
        indexed[key] = observation
    if set(indexed) != expected_keys:
        raise ValueError("repeatability observations are incomplete or out of panel")

    tolerance = float(protocol["gates"]["relative_tolerance"])
    groups: list[dict[str, Any]] = []
    for panel in protocol["panel"]:
        reference = float(panel["frozen_r3_cps_pf"])
        for arm in protocol["arms"]:
            members = [
                indexed[(int(panel["layout_id"]), repeat_id, arm["arm_id"])]
                for repeat_id in range(5)
            ]
            raw_results = [member["worker_result"] for member in members]
            cps_values = [float(result["cps_pf"]) for result in raw_results]
            if not all(math.isfinite(value) and value > 0.0 for value in cps_values):
                raise ValueError("repeatability Cps values must be positive and finite")
            system_hashes = [str(result["system_sha256"]) for result in raw_results]
            if not all(_is_sha256(value) for value in system_hashes):
                raise ValueError("repeatability system fingerprint is malformed")
            node_counts = [int(result["mesh_nodes"]) for result in raw_results]
            tet_counts = [int(result["mesh_tetrahedra"]) for result in raw_results]
            median = float(statistics.median(cps_values))
            mad = float(statistics.median(abs(value - median) for value in cps_values))
            pairwise = _max_pairwise_relative(cps_values)
            reference_drifts = [
                _relative_reference_drift(value, reference) for value in cps_values
            ]
            signed_reference_drifts = [
                _signed_reference_drift(value, reference) for value in cps_values
            ]
            numerical_pass = all(
                member.get("numerical_resource_gate", {}).get("pass") is True
                for member in members
            )
            gmsh_thread_pass = all(
                member.get("gmsh_thread_gate", {}).get("pass") is True
                for member in members
            )
            mesh_identity_pass = (
                len(set(system_hashes)) == 1
                and len(set(node_counts)) == 1
                and len(set(tet_counts)) == 1
            )
            repeatability_pass = pairwise <= tolerance
            reference_pass = all(value <= tolerance for value in reference_drifts)
            old_reference_required = bool(arm["old_reference_gate_required"])
            group_pass = (
                numerical_pass
                and gmsh_thread_pass
                and mesh_identity_pass
                and repeatability_pass
                and (reference_pass if old_reference_required else True)
            )
            groups.append(
                {
                    "arm_id": arm["arm_id"],
                    "cps_pf": {
                        "mad_over_median_scaled": 1.4826 * mad / median,
                        "maximum": max(cps_values),
                        "max_pairwise_relative_spread": pairwise,
                        "median": median,
                        "minimum": min(cps_values),
                        "values_by_repeat": cps_values,
                    },
                    "frozen_reference": {
                        "all_five_pass": reference_pass,
                        "absolute_relative_drifts_by_repeat": reference_drifts,
                        "maximum_absolute_relative_drift": max(reference_drifts),
                        "signed_relative_drifts_by_repeat": signed_reference_drifts,
                        "value_cps_pf": reference,
                    },
                    "gate": {
                        "gmsh_thread_observation_pass": gmsh_thread_pass,
                        "group_pass": group_pass,
                        "mesh_identity_pass": mesh_identity_pass,
                        "numerical_resource_pass": numerical_pass,
                        "old_reference_required": old_reference_required,
                        "repeatability_pass": repeatability_pass,
                    },
                    "layout_id": panel["layout_id"],
                    "mesh": {
                        "node_count_range": [min(node_counts), max(node_counts)],
                        "system_sha256_unique_count": len(set(system_hashes)),
                        "tetrahedron_count_range": [min(tet_counts), max(tet_counts)],
                    },
                }
            )

    arm_a = [group for group in groups if group["arm_id"] == "arm_a_threads25"]
    arm_b = [group for group in groups if group["arm_id"] == "arm_b_threads1"]
    arm_a_pass = all(group["gate"]["group_pass"] for group in arm_a)
    arm_b_repeatability_pass = all(
        group["gate"]["numerical_resource_pass"]
        and group["gate"]["gmsh_thread_observation_pass"]
        and group["gate"]["mesh_identity_pass"]
        and group["gate"]["repeatability_pass"]
        for group in arm_b
    )
    return {
        "claim_eligible": False,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "arm_a_all_gates_pass": arm_a_pass,
            "arm_b_repeatability_gates_pass": arm_b_repeatability_pass,
            "paired_latency_preflight_may_resume": arm_a_pass,
            "tolerance_changed": False,
        },
        "groups": groups,
        "panel_headlines": {
            "arm_a_max_pairwise_relative_spread": max(
                group["cps_pf"]["max_pairwise_relative_spread"] for group in arm_a
            ),
            "arm_a_max_reference_relative_drift": max(
                group["frozen_reference"]["maximum_absolute_relative_drift"]
                for group in arm_a
            ),
            "arm_b_max_pairwise_relative_spread": max(
                group["cps_pf"]["max_pairwise_relative_spread"] for group in arm_b
            ),
            "arm_b_max_reference_relative_drift_report_only": max(
                group["frozen_reference"]["maximum_absolute_relative_drift"]
                for group in arm_b
            ),
        },
        "schema": SUMMARY_SCHEMA,
        "speed_claim_eligible": False,
    }


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("repeatability output root escapes the repository") from exc


def _execute(args: argparse.Namespace, protocol: dict[str, Any], protocol_sha256: str) -> None:
    if not args.expected_source_git_head:
        raise SystemExit("--expected-source-git-head is required for solver execution")
    scheduler = validate_slurm_allocation(protocol)
    array_task_id = int(scheduler["array_task_id"])
    panel, repeat_id = task_mapping(array_task_id, protocol)
    order = arm_order(repeat_id, protocol)
    records_by_id, input_bindings = _validate_bound_inputs(protocol)
    source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=args.protocol,
        protocol_sha256=protocol_sha256,
    )
    runtime = _runtime_identity(protocol)
    record = records_by_id[int(panel["layout_id"])]

    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not executed_batch.is_file():
        raise SystemExit("exact executed repeatability batch script is unavailable")
    expected_batch_sha = protocol["computational_sources"][
        "code/jobs/submit_corpus_v4_fem_repeatability.sh"
    ]
    if sha256_file(executed_batch) != expected_batch_sha:
        raise SystemExit("executed batch script differs from frozen source")

    output_root = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    _repo_relative(output_root)
    attempt_dir = (
        output_root
        / "attempts"
        / f"job_{scheduler['array_job_id']}"
        / f"task_{array_task_id:02d}"
    )
    attempt_dir.mkdir(parents=True, exist_ok=False)
    started = {
        "array_task_id": array_task_id,
        "arm_order": [arm["arm_id"] for arm in order],
        "claim_eligible": False,
        "input_bindings": input_bindings,
        "panel": panel,
        "protocol_sha256": protocol_sha256,
        "repeat_id": repeat_id,
        "schema": "pcb-gnn.corpus-v4-fem-repeatability-start.v1",
        "source_git_head": args.expected_source_git_head,
        "source_sha256": source_hashes,
        "speed_claim_eligible": False,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(attempt_dir / "started.json", started)

    cps_protocol = _load_json(
        _resolve_repo_path(protocol["inputs"]["cps_protocol"]["path"], "Cps protocol")
    )
    arm_records: list[dict[str, Any]] = []
    for position, arm in enumerate(order):
        arm_record = run_arm(
            arm=arm,
            layout=record["layout"],
            panel=panel,
            repeat_id=repeat_id,
            order_position=position,
            cps_protocol=cps_protocol,
        )
        arm_path = attempt_dir / f"{arm['arm_id']}.json"
        if arm_path.exists():
            raise SystemExit("refusing to overwrite an arm observation")
        atomic_write_json(arm_path, arm_record)
        arm_records.append(arm_record)
        _assert_source_stable(
            expected_head=args.expected_source_git_head,
            protocol=protocol,
            protocol_path=args.protocol,
            protocol_sha256=protocol_sha256,
        )

    final_source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=args.protocol,
        protocol_sha256=protocol_sha256,
    )
    integrity_pass = all(
        arm_record["numerical_resource_gate"].get("pass") is True
        and arm_record["gmsh_thread_gate"].get("pass") is True
        for arm_record in arm_records
    )
    result = {
        "admission_eligible": False,
        "arms": arm_records,
        "claim_eligible": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": {"passed": integrity_pass},
        "provenance": {
            "executed_batch_sha256": expected_batch_sha,
            "hardware": _hardware_identity(),
            "hostname": socket.gethostname(),
            "input_bindings": input_bindings,
            "protocol_sha256": protocol_sha256,
            "runtime": runtime,
            "scheduler": scheduler,
            "source_git_head": args.expected_source_git_head,
            "source_sha256": final_source_hashes,
        },
        "schema": ATTEMPT_SCHEMA,
        "speed_claim_eligible": False,
        "task": {
            "array_task_id": array_task_id,
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "latency_task_id": panel["latency_task_id"],
            "layout_id": panel["layout_id"],
            "repeat_id": repeat_id,
        },
    }
    result_path = attempt_dir / "result.json"
    atomic_write_json(result_path, result)
    files = {
        path.name: sha256_file(path)
        for path in sorted(attempt_dir.iterdir())
        if path.is_file()
    }
    atomic_write_json(
        attempt_dir / "TASK_MANIFEST.json",
        {
            "files_sha256": files,
            "protocol_sha256": protocol_sha256,
            "schema": MANIFEST_SCHEMA,
        },
    )
    print(
        json.dumps(
            {
                "artifact": _repo_relative(attempt_dir),
                "integrity_pass": integrity_pass,
                "task_id": array_task_id,
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    if not integrity_pass:
        raise SystemExit(1)


def main() -> None:
    args = parse_args()
    protocol_path = args.protocol if args.protocol.is_absolute() else ROOT / args.protocol
    protocol_path = protocol_path.resolve()
    _resolve_repo_path(protocol_path.relative_to(ROOT.resolve()).as_posix(), "protocol")
    protocol_sha256 = sha256_file(protocol_path)
    if protocol_sha256 != args.expected_protocol_sha256:
        raise SystemExit("repeatability protocol SHA-256 differs from explicit pin")
    protocol = _load_json(protocol_path)
    validate_protocol(protocol)
    records, bindings = _validate_bound_inputs(protocol)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "array_task_count": 15,
                    "bindings": bindings,
                    "panel_layout_ids": [row["layout_id"] for row in protocol["panel"]],
                    "protocol_sha256": protocol_sha256,
                    "schema": VALIDATION_SCHEMA,
                    "solver_executed": False,
                    "verified_geometry_records": len(records),
                },
                allow_nan=False,
                sort_keys=True,
            )
        )
        return
    _execute(args, protocol, protocol_sha256)


if __name__ == "__main__":
    main()
