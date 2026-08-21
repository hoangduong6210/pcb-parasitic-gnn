#!/usr/bin/env python3
"""Run one hash-frozen FEM-v2 qualification task under Slurm.

The staged qualification is deliberately separate from the historical Corpus-v4
FEM artifacts.  Gate A qualifies repeatable R3P16 meshes, Gate B evaluates
the R3P16-to-R3P20 domain change, and Gate C qualifies repeatable
R4P16 meshes while measuring the R3P16-to-R4P16 mesh change.  A valid Gate-C
mesh-threshold failure is a terminally authenticated negative qualification
result; it does not
by itself disqualify an explicit multi-fidelity package.  This runner never
admits a stage; it only writes one immutable task attempt.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import math
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    evaluate_result,
    parse_scontrol_records,
    scheduler_resource_contract_matches,
    select_scheduler_task_record,
)
from experiments_corpus_v4_fem_repeatability import (  # noqa: E402
    _arm_environment,
    _assert_source_stable,
    _hardware_identity,
    _load_json,
    _resolve_repo_path,
    _same_node_identity,
    gmsh_thread_gate,
    run_repeatability_worker,
)


PROTOCOL_RELATIVE = "protocols/corpus_v4_fem_v2_qualification_v1.json"
OUTPUT_ROOT_RELATIVE = "results/corpus_v4/cps_reference_v2/qualification/v1"
SOURCE_WRAPPERS = {
    "gate_a": "code/jobs/submit_corpus_v4_fem_v2_gate_a.sh",
    "gate_b": "code/jobs/submit_corpus_v4_fem_v2_gate_b.sh",
    "gate_c": "code/jobs/submit_corpus_v4_fem_v2_gate_c.sh",
}
PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-protocol.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-task.v1"
START_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-start.v1"
TASK_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-task-manifest.v1"
ADMISSION_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-qualification-admission.v1"
STAGES = ("gate_a", "gate_b", "gate_c")
PREDECESSOR = {"gate_a": None, "gate_b": "gate_a", "gate_c": "gate_b"}
NEXT_STAGE = {"gate_a": "gate_b", "gate_b": "gate_c", "gate_c": None}
SHA256_HEX = frozenset("0123456789abcdef")
EXPECTED_COMPUTATIONAL_SOURCE_NAMES = frozenset(
    {
        "code/core/geometry_contract.py",
        "code/core/scientific_artifact.py",
        "code/data/verified_geometry_corpus.py",
        "code/env.sh",
        "code/experiments/proofs/admit_corpus_v4_fem_v2_qualification.py",
        "code/experiments/proofs/experiments_corpus_v4_fem_repeatability.py",
        "code/experiments/proofs/finalize_corpus_v4_fem_v2_qualification.py",
        "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py",
        "code/experiments/proofs/run_corpus_v4_fem_v2_qualification.py",
        "code/jobs/slurm_job_env.sh",
        *SOURCE_WRAPPERS.values(),
        "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_a.sh",
        "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_b.sh",
        "code/jobs/submit_finalize_corpus_v4_fem_v2_gate_c.sh",
        "code/solvers/fem_capacitance_3d.py",
        "code/solvers/fem_cps_bounded_worker.py",
        "code/solvers/fem_cps_diagnostic_worker.py",
        "code/solvers/fem_cps_repeatability_worker.py",
        "requirements-proof.txt",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--prerequisite-admission", type=Path)
    parser.add_argument("--expected-prerequisite-admission-sha256")
    parser.add_argument("--output-root", type=Path, default=Path(OUTPUT_ROOT_RELATIVE))
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_HEX


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def repo_relative(path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc


def canonical_output_root(path: Path, label: str) -> Path:
    """Resolve and require the one versioned qualification namespace."""
    cursor = ROOT
    for component in Path(OUTPUT_ROOT_RELATIVE).parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError(f"{label} contains a symlinked path component")
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    canonical = (ROOT / OUTPUT_ROOT_RELATIVE).resolve()
    if supplied != canonical:
        raise ValueError(f"{label} must equal {OUTPUT_ROOT_RELATIVE}")
    return supplied


def stage_tasks(protocol: Mapping[str, Any], stage: str) -> list[dict[str, Any]]:
    """Expand the frozen compact stage mapping into dense array tasks."""
    anchors = [dict(row) for row in protocol["anchors"]]
    if stage == "gate_a":
        tasks = [
            {"anchor_index": index, "repeat_id": repeat_id, **anchor}
            for index, anchor in enumerate(anchors)
            for repeat_id in range(5)
        ]
    elif stage == "gate_b":
        tasks = [
            {"anchor_index": index, "repeat_id": 0, **anchor}
            for index, anchor in enumerate(anchors)
        ]
    elif stage == "gate_c":
        sentinels = set(protocol["gate_c_sentinel_selection"]["layout_ids"])
        tasks = [
            {"anchor_index": index, "repeat_id": repeat_id, **anchor}
            for index, anchor in enumerate(anchors)
            for repeat_id in range(5 if int(anchor["layout_id"]) in sentinels else 1)
        ]
    else:  # pragma: no cover - argparse and protocol validation prevent this.
        raise ValueError("unsupported qualification stage")
    return [{"array_task_id": index, **task} for index, task in enumerate(tasks)]


def validate_protocol(protocol: Mapping[str, Any]) -> None:
    expected_top_level = {
        "anchors",
        "artifact_contract",
        "computational_sources",
        "gate_c_sentinel_selection",
        "gates",
        "inputs",
        "protocol_name",
        "resources",
        "runtime",
        "schema",
        "scientific_semantics",
        "stages",
    }
    if set(protocol) != expected_top_level:
        raise ValueError("qualification protocol top-level fields differ")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unexpected FEM-v2 qualification protocol schema")
    if protocol.get("protocol_name") != "corpus-v4-fem-v2-staged-qualification-v1":
        raise ValueError("unexpected FEM-v2 qualification protocol name")

    anchors = protocol.get("anchors")
    expected_layouts = [1055, 407, 1351, 149, 275, 897, 2, 173, 1400]
    if not isinstance(anchors, list) or [row.get("layout_id") for row in anchors] != expected_layouts:
        raise ValueError("qualification anchors differ from the frozen convergence panel")
    if len({row.get("geometry_sha256") for row in anchors}) != 9 or any(
        not is_sha256(row.get("geometry_sha256")) for row in anchors
    ):
        raise ValueError("qualification anchor geometry identities are malformed")

    sentinel = protocol.get("gate_c_sentinel_selection", {})
    if (
        sentinel.get("layout_ids") != [407, 275, 173]
        or sentinel.get("target_values_used") is not True
        or sentinel.get("new_v2_outputs_used") is not False
        or sentinel.get("source_input") != "refine34_convergence_evidence"
        or sentinel.get("method")
        != "inherited_median_cps_member_per_trace_count_stratum_v1"
    ):
        raise ValueError("Gate-C sentinel selection differs")

    expected_stages = {
        "gate_a": {
            "array_task_count": 45,
            "fidelity_id": "cps_fem_r3_p16_t1_v2",
            "pad_mm": 16.0,
            "prerequisite_stage": None,
            "refine": 3,
            "repeats": "five_per_anchor",
            "worker_timeout_s": 1800,
        },
        "gate_b": {
            "array_task_count": 9,
            "fidelity_id": "cps_fem_r3_p20_t1_v2",
            "pad_mm": 20.0,
            "prerequisite_stage": "gate_a",
            "refine": 3,
            "repeats": "one_per_anchor",
            "worker_timeout_s": 3600,
        },
        "gate_c": {
            "array_task_count": 21,
            "fidelity_id": "cps_fem_r4_p16_t1_v2",
            "pad_mm": 16.0,
            "prerequisite_stage": "gate_b",
            "refine": 4,
            "repeats": "five_for_407_275_173_one_for_other_anchors",
            "worker_timeout_s": 7200,
        },
    }
    if protocol.get("stages") != expected_stages:
        raise ValueError("qualification stage definitions differ")
    for stage, expected_count in (("gate_a", 45), ("gate_b", 9), ("gate_c", 21)):
        tasks = stage_tasks(protocol, stage)
        if len(tasks) != expected_count or [row["array_task_id"] for row in tasks] != list(range(expected_count)):
            raise ValueError(f"{stage} task expansion is not exact and dense")

    gates = protocol.get("gates", {})
    if gates != {
        "domain_delta_formula": "100*abs(C_R3P16-C_R3P20)/abs(C_R3P20)",
        "domain_delta_max_pct": 5.0,
        "domain_delta_median_pct": 2.0,
        "mesh_delta_formula": "100*abs(C_R3P16-C_R4P16)/abs(C_R4P16)",
        "mesh_delta_max_pct": 5.0,
        "mesh_delta_median_pct": 2.0,
        "relative_residual_max": 1e-9,
        "repeatability_formula": "abs(x-y)/max(abs(x),abs(y),1e-12)",
        "repeatability_max_relative": 1e-4,
        "repeatability_requires_fixed_mesh_counts": True,
        "repeatability_requires_one_system_sha256": True,
    }:
        raise ValueError("qualification numerical gates differ")

    resources = protocol.get("resources", {})
    expected_resource_core = {
        "gate_a": (45, 8, 1, 48),
        "gate_b": (9, 8, 1, 48),
        "gate_c": (21, 2, 1, 160),
    }
    for stage, (count, throttle, cpus, memory) in expected_resource_core.items():
        resource = resources.get(stage, {})
        if (
            resource.get("account") != "pgs0407"
            or resource.get("array_task_count") != count
            or resource.get("array_throttle") != throttle
            or resource.get("requested_cpus_per_task") != cpus
            or resource.get("memory_gib") != memory
            or resource.get("partition") != "nextgen"
            or resource.get("time_limit")
            != ("03:00:00" if stage == "gate_c" else "02:00:00")
            or resource.get("allocated_cpus_may_exceed_request") is not True
        ):
            raise ValueError(f"{stage} Slurm resources differ")
    finalizer_resource = resources.get("finalizer", {})
    if finalizer_resource != {
        "account": "pgs0407",
        "allocated_cpus_may_exceed_request": True,
        "memory_gib": 16,
        "partition": "nextgen",
        "requested_cpus_per_task": 2,
        "time_limit": "00:30:00",
    }:
        raise ValueError("qualification finalizer resources differ")

    limits = resources
    for stage in STAGES:
        fail_fast = limits[stage].get("fail_fast", {})
        if (
            not isinstance(fail_fast.get("mesh_nodes_max"), int)
            or not isinstance(fail_fast.get("mesh_tetrahedra_max"), int)
            or not isinstance(fail_fast.get("wall_s_max"), (int, float))
            or not isinstance(fail_fast.get("worker_peak_rss_gib_max"), (int, float))
            or fail_fast.get("operator_complexity_max") != 1.25
        ):
            raise ValueError(f"{stage} fail-fast limits are malformed")

    runtime = protocol.get("runtime", {})
    if runtime.get("thread_environment", {}).get("PCB_GNN_GMSH_THREADS") != "1":
        raise ValueError("FEM-v2 qualification requires one Gmsh thread")
    if any(value != "1" for name, value in runtime.get("thread_environment", {}).items() if name.endswith("NUM_THREADS")):
        raise ValueError("FEM-v2 numerical thread environment is not serialized")

    contract = protocol.get("artifact_contract", {})
    required_true = {
        "all_attempts_retained",
        "atomic_task_files",
        "child_gmsh_thread_observation_required",
        "complete_failed_diagnostics_retained",
        "immutable_attempt_directory",
        "post_finalizer_terminal_admission_required",
        "prerequisite_positive_admission_required",
        "raw_worker_result_required",
        "source_reauthenticated_after_solve",
        "terminal_accounting_required",
    }
    if any(contract.get(name) is not True for name in required_true):
        raise ValueError("qualification artifact contract was weakened")
    semantics = protocol.get("scientific_semantics", {})
    if semantics != {
        "claim_eligible": False,
        "gate_c_mesh_threshold_failure_blocks_multifidelity_package": False,
        "gate_c_mesh_threshold_is_measured_scientific_outcome": True,
        "old_cps_values_are_new_references": False,
        "speed_claim_eligible": False,
        "tolerance_may_change_after_observation": False,
    }:
        raise ValueError("qualification scientific semantics were weakened")

    source_map = protocol.get("computational_sources")
    if (
        not isinstance(source_map, dict)
        or set(source_map) != EXPECTED_COMPUTATIONAL_SOURCE_NAMES
        or any(
        not is_sha256(value) for value in source_map.values()
        )
    ):
        raise ValueError("qualification source closure is missing or malformed")
    inputs = protocol.get("inputs")
    if not isinstance(inputs, dict) or not inputs or any(
        not isinstance(binding, dict) or not is_sha256(binding.get("sha256"))
        for binding in inputs.values()
    ):
        raise ValueError("qualification input closure is missing or malformed")


def authenticate_protocol(path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    canonical = (ROOT / PROTOCOL_RELATIVE).resolve()
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if supplied != canonical:
        raise ValueError("qualification protocol is not at its canonical path")
    observed = sha256_file(canonical)
    if not is_sha256(expected_sha256) or observed != expected_sha256:
        raise ValueError("qualification protocol SHA-256 differs from explicit pin")
    protocol = load_json_object(canonical, "qualification protocol")
    validate_protocol(protocol)
    return protocol, observed


def validate_inputs(protocol: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[str, str]]:
    bindings: dict[str, str] = {}
    for label, binding in protocol["inputs"].items():
        path = _resolve_repo_path(binding["path"], label)
        observed = sha256_file(path)
        if observed != binding["sha256"]:
            raise ValueError(f"input SHA-256 mismatch: {label}")
        bindings[label] = observed
    for name, expected in protocol["computational_sources"].items():
        if sha256_file(_resolve_repo_path(name, "computational source")) != expected:
            raise ValueError(f"computational source SHA-256 mismatch: {name}")

    geometry = protocol["inputs"]["geometry_contract"]
    records, _ = load_verified_geometry_corpus(
        _resolve_repo_path(geometry["directory"], "geometry corpus"),
        geometry["loader_contract"],
    )
    by_id = {int(record["layout_id"]): record for record in records}
    for anchor in protocol["anchors"]:
        record = by_id.get(int(anchor["layout_id"]))
        if record is None or record.get("geometry_sha256") != anchor["geometry_sha256"]:
            raise ValueError("qualification anchor differs from verified geometry")
        layout = record["layout"]
        primary = sum(trace["net"] == "pri" for trace in layout["traces"])
        secondary = sum(trace["net"] == "sec" for trace in layout["traces"])
        lower, upper = sorted((primary, secondary))
        if anchor.get("turn_family") != f"turns-{lower:02d}-{upper:02d}":
            raise ValueError("qualification anchor turn family differs from geometry")

    convergence = load_json_object(
        _resolve_repo_path(
            protocol["inputs"]["refine34_convergence_evidence"]["path"],
            "refine34 convergence evidence",
        ),
        "refine34 convergence evidence",
    )
    if convergence.get("schema") != "pcb-gnn.corpus-v4-refine34-convergence-final.v1":
        raise ValueError("unexpected convergence evidence schema")
    expected_layouts = [row["layout_id"] for row in protocol["anchors"]]
    comparisons = convergence.get("comparisons", {})
    if not comparisons:
        raise ValueError("convergence evidence has no comparison panels")
    for comparison in comparisons.values():
        rows = comparison.get("per_layout", [])
        if [row.get("layout_id") for row in rows] != expected_layouts:
            raise ValueError("qualification panel differs from convergence evidence")

    hf_registry = load_json_object(
        _resolve_repo_path(
            protocol["inputs"]["hf_selection_registry"]["path"],
            "high-fidelity selection registry",
        ),
        "high-fidelity selection registry",
    )
    if (
        hf_registry.get("schema") != "pcb-gnn.hf-selection-registry.v1"
        or not isinstance(hf_registry.get("rows"), list)
        or len(hf_registry["rows"]) != 198
    ):
        raise ValueError("high-fidelity selection registry identity differs")

    run02_admission = load_json_object(
        _resolve_repo_path(protocol["inputs"]["run02_repeatability_admission"]["path"], "Run-02 admission"),
        "Run-02 admission",
    )
    preterminal = run02_admission.get("preterminal_final", {})
    result_path = _resolve_repo_path(preterminal.get("final_result_path", ""), "Run-02 result")
    if sha256_file(result_path) != preterminal.get("final_result_sha256"):
        raise ValueError("Run-02 admission does not bind its result")
    run02_result = load_json_object(result_path, "Run-02 result")
    if run02_result.get("repeatability_summary", {}).get("decision", {}).get("arm_b_repeatability_gates_pass") is not True:
        raise ValueError("Run-02 does not support the serialized Gmsh candidate")
    return by_id, bindings


def validate_prerequisite(
    *,
    stage: str,
    path: Path | None,
    expected_sha256: str | None,
    protocol_sha256: str,
    expected_source_git_head: str | None,
    output_root: Path,
) -> dict[str, Any] | None:
    predecessor = PREDECESSOR[stage]
    if predecessor is None:
        if path is not None or expected_sha256 is not None:
            raise ValueError("Gate A must not receive a prerequisite admission")
        return None
    if path is None or expected_sha256 is None or not is_sha256(expected_sha256):
        raise ValueError(f"{stage} requires a hash-pinned predecessor admission")
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    admission_root = (output_root / "admission" / predecessor).resolve()
    try:
        supplied.relative_to(admission_root)
    except ValueError as exc:
        raise ValueError("prerequisite admission is outside its canonical stage root") from exc
    if supplied.name != "FINAL_ADMISSION.json" or supplied.is_symlink() or not supplied.is_file():
        raise ValueError("prerequisite admission path is not canonical")
    observed = sha256_file(supplied)
    if observed != expected_sha256:
        raise ValueError("prerequisite admission SHA-256 differs from explicit pin")
    admission = load_json_object(supplied, "prerequisite admission")
    if (
        admission.get("schema") != ADMISSION_SCHEMA
        or admission.get("artifact_stage") != "postterminal_finalizer_admission"
        or admission.get("stage") != predecessor
        or admission.get("protocol_sha256") != protocol_sha256
        or admission.get("source_git_head") != expected_source_git_head
        or admission.get("decision", {}).get("qualification_stage_pass") is not True
        or admission.get("decision", {}).get("next_stage_may_run") is not True
        or admission.get("decision", {}).get("next_stage") != stage
    ):
        raise ValueError("prerequisite admission is not a positive predecessor receipt")
    return {
        "path": repo_relative(supplied, "prerequisite admission"),
        "sha256": observed,
        "stage": predecessor,
    }


def runtime_identity(protocol: Mapping[str, Any]) -> dict[str, Any]:
    expected = protocol["runtime"]
    observed = {
        "packages": {
            name: importlib.metadata.version(name) for name in expected["packages"]
        },
        "python": platform.python_version(),
        "thread_environment": {
            name: os.environ.get(name) for name in expected["thread_environment"]
        },
    }
    if observed != expected:
        raise SystemExit("runtime or thread environment differs from qualification protocol")
    return observed


def validate_slurm_allocation(
    protocol: Mapping[str, Any], stage: str, task_count: int
) -> dict[str, Any]:
    required = (
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
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"FEM-v2 solving is Slurm-only; missing {missing}")
    resource = protocol["resources"][stage]
    observed = {
        "array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
        "array_task_count": int(os.environ["SLURM_ARRAY_TASK_COUNT"]),
        "array_task_id": int(os.environ["SLURM_ARRAY_TASK_ID"]),
        "array_task_max": int(os.environ["SLURM_ARRAY_TASK_MAX"]),
        "array_task_min": int(os.environ["SLURM_ARRAY_TASK_MIN"]),
        "allocated_cpus_per_task": int(os.environ["SLURM_CPUS_PER_TASK"]),
        "job_account": os.environ["SLURM_JOB_ACCOUNT"],
        "job_id": os.environ["SLURM_JOB_ID"],
        "mem_per_node_mb": int(os.environ["SLURM_MEM_PER_NODE"]),
        "partition": os.environ["SLURM_JOB_PARTITION"],
        "slurmd_nodename": os.environ["SLURMD_NODENAME"],
    }
    if (
        observed["array_task_count"] != task_count
        or observed["array_task_min"] != 0
        or observed["array_task_max"] != task_count - 1
        or observed["array_task_id"] not in range(task_count)
        or observed["job_account"] != resource["account"]
        or observed["partition"] != resource["partition"]
        or observed["mem_per_node_mb"] != int(resource["memory_gib"]) * 1024
    ):
        raise SystemExit("Slurm environment differs from the qualification stage")
    component = f"{observed['array_job_id']}_{observed['array_task_id']}"
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", component],
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0 or not query.stdout.strip():
        raise SystemExit("active qualification array element is not confirmed by Slurm")
    record = select_scheduler_task_record(
        parse_scontrol_records(query.stdout),
        job_id=observed["job_id"],
        array_job_id=observed["array_job_id"],
        array_task_id=observed["array_task_id"],
    )
    profile = {
        "cpus_per_task": resource["requested_cpus_per_task"],
        "mem_gib": resource["memory_gib"],
    }
    if (
        record.get("Account") != resource["account"]
        or record.get("ArrayTaskThrottle") != str(resource["array_throttle"])
        or record.get("JobState") not in {"RUNNING", "COMPLETING"}
        or record.get("Partition") != resource["partition"]
        or record.get("TimeLimit") != resource["time_limit"]
        or not _same_node_identity(observed["slurmd_nodename"], record.get("NodeList", ""))
        or not scheduler_resource_contract_matches(
            record,
            allocated_cpus_per_task=observed["allocated_cpus_per_task"],
            mem_per_node_mb=observed["mem_per_node_mb"],
            profile=profile,
        )
    ):
        raise SystemExit("live scheduler record differs from qualification resources")
    retained = {
        name: record[name]
        for name in (
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
        )
    }
    return {
        **observed,
        "requested_cpus_per_task": resource["requested_cpus_per_task"],
        "scheduler_record": retained,
    }


def numerical_gate(
    execution: Mapping[str, Any],
    protocol: Mapping[str, Any],
    stage: str,
    cps_protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Reuse the production gate after substituting the frozen stage fidelity."""
    stage_spec = protocol["stages"][stage]
    fidelity_id = "cps_fem_r3_p16" if int(stage_spec["refine"]) == 3 else "cps_fem_r4_p16"
    effective = copy.deepcopy(dict(cps_protocol))
    effective["fidelities"][fidelity_id] = {
        "coverage": 1,
        "pad_mm": float(stage_spec["pad_mm"]),
        "refine": int(stage_spec["refine"]),
        "role": "qualification_only",
    }
    effective["resource_profiles"][fidelity_id]["fail_fast"] = dict(
        protocol["resources"][stage]["fail_fast"]
    )
    effective["linear_solver"]["residual_max"] = float(
        protocol["gates"]["relative_residual_max"]
    )
    return evaluate_result(dict(execution), effective, fidelity_id)


def execute(args: argparse.Namespace, protocol: dict[str, Any], protocol_sha256: str) -> None:
    if not args.expected_source_git_head:
        raise SystemExit("--expected-source-git-head is required for FEM execution")
    tasks = stage_tasks(protocol, args.stage)
    scheduler = validate_slurm_allocation(protocol, args.stage, len(tasks))
    task = tasks[int(scheduler["array_task_id"])]
    output_root = canonical_output_root(args.output_root, "qualification output root")
    prerequisite = validate_prerequisite(
        stage=args.stage,
        path=args.prerequisite_admission,
        expected_sha256=args.expected_prerequisite_admission_sha256,
        protocol_sha256=protocol_sha256,
        expected_source_git_head=args.expected_source_git_head,
        output_root=output_root,
    )
    records_by_id, input_bindings = validate_inputs(protocol)
    source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=(ROOT / PROTOCOL_RELATIVE),
        protocol_sha256=protocol_sha256,
    )
    runtime = runtime_identity(protocol)
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch_sha = protocol["computational_sources"][SOURCE_WRAPPERS[args.stage]]
    if not executed_batch.is_file() or sha256_file(executed_batch) != expected_batch_sha:
        raise SystemExit("executed source batch differs from frozen qualification source")

    task_dir = (
        output_root
        / "attempts"
        / args.stage
        / f"job_{scheduler['array_job_id']}"
        / f"task_{int(task['array_task_id']):03d}"
    )
    task_dir.mkdir(parents=True, exist_ok=False)
    atomic_write_json(
        task_dir / "started.json",
        {
            "claim_eligible": False,
            "prerequisite_admission": prerequisite,
            "protocol_sha256": protocol_sha256,
            "schema": START_SCHEMA,
            "source_git_head": args.expected_source_git_head,
            "stage": args.stage,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "task": task,
        },
    )

    stage_spec = protocol["stages"][args.stage]
    limit = protocol["resources"][args.stage]["fail_fast"]
    worker_updates = {
        "PCB_GNN_GMSH_THREADS": "1",
        "PCB_GNN_MAX_MESH_NODES": str(limit["mesh_nodes_max"]),
        "PCB_GNN_MAX_MESH_TETRAHEDRA": str(limit["mesh_tetrahedra_max"]),
        "PCB_GNN_MAX_OPERATOR_COMPLEXITY": str(limit["operator_complexity_max"]),
        "PCB_GNN_MAX_RSS_KB": str(int(float(limit["worker_peak_rss_gib_max"]) * 1048576)),
    }
    previous = {name: os.environ.get(name) for name in worker_updates}
    os.environ.update(worker_updates)
    try:
        with _arm_environment(1):
            execution = run_repeatability_worker(
                records_by_id[int(task["layout_id"])]["layout"],
                int(stage_spec["refine"]),
                float(stage_spec["pad_mm"]),
                int(stage_spec["worker_timeout_s"]),
            )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    cps_protocol = _load_json(
        _resolve_repo_path(protocol["inputs"]["cps_protocol"]["path"], "Cps protocol")
    )
    numeric = numerical_gate(execution, protocol, args.stage, cps_protocol)
    thread = gmsh_thread_gate(execution, 1)
    worker_result = execution.get("worker_result")
    valid_worker = isinstance(worker_result, dict) and all(
        is_sha256(worker_result.get(name))
        for name in ("input_system_sha256", "system_sha256")
    )
    final_source_hashes = _assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_path=(ROOT / PROTOCOL_RELATIVE),
        protocol_sha256=protocol_sha256,
    )
    _, final_input_bindings = validate_inputs(protocol)
    integrity_pass = bool(
        numeric.get("pass") is True
        and thread.get("pass") is True
        and valid_worker
        and final_source_hashes == source_hashes
        and final_input_bindings == input_bindings
    )
    result = {
        "admission_eligible": False,
        "claim_eligible": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "gate": {
            "integrity_pass": integrity_pass,
            "numerical_resource": numeric,
            "thread_observation": thread,
        },
        "prerequisite_admission": prerequisite,
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
        "schema": TASK_SCHEMA,
        "speed_claim_eligible": False,
        "stage": args.stage,
        "task": task,
        "worker_result": worker_result,
    }
    result_path = task_dir / "result.json"
    atomic_write_json(result_path, result)
    files = {
        path.name: sha256_file(path)
        for path in sorted(task_dir.iterdir())
        if path.is_file()
    }
    atomic_write_json(
        task_dir / "TASK_MANIFEST.json",
        {
            "files_sha256": files,
            "protocol_sha256": protocol_sha256,
            "schema": TASK_MANIFEST_SCHEMA,
            "stage": args.stage,
        },
    )
    print(
        json.dumps(
            {
                "artifact": repo_relative(task_dir, "qualification task"),
                "integrity_pass": integrity_pass,
                "stage": args.stage,
                "task_id": task["array_task_id"],
            },
            allow_nan=False,
            sort_keys=True,
        )
    )
    if not integrity_pass:
        raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    protocol, protocol_sha256 = authenticate_protocol(args.protocol, args.expected_protocol_sha256)
    records, bindings = validate_inputs(protocol)
    tasks = stage_tasks(protocol, args.stage)
    canonical_output_root(args.output_root, "qualification output root")
    if args.validate_only:
        predecessor = PREDECESSOR[args.stage]
        print(
            json.dumps(
                {
                    "bindings": bindings,
                    "panel_layout_ids": [row["layout_id"] for row in protocol["anchors"]],
                    "prerequisite_stage": predecessor,
                    "protocol_sha256": protocol_sha256,
                    "solver_executed": False,
                    "stage": args.stage,
                    "task_count": len(tasks),
                    "verified_geometry_records": len(records),
                },
                allow_nan=False,
                sort_keys=True,
            )
        )
        return
    execute(args, protocol, protocol_sha256)


if __name__ == "__main__":
    main()
