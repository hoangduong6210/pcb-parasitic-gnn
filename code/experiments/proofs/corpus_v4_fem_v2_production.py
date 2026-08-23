#!/usr/bin/env python3
"""Freeze and execute the one-thread Corpus-v4 FEM-v2 production package.

This module is the execution authority for fresh R3/P16 and R4/P16 solves.
It deliberately does not authorize training or scientific claims.  A separate
postterminal package admission must first prove dense coverage and replay the
SLURM accounting for every accepted attempt.
"""
from __future__ import annotations

import argparse
import json
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

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    require_file_sha256,
    sha256_file,
    sha256_json,
)
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    evaluate_result,
    runtime_environment,
    validate_slurm_contract,
)
from experiments_corpus_v4_fem_repeatability import (  # noqa: E402
    _arm_environment,
    _hardware_identity,
    gmsh_thread_gate,
    run_repeatability_worker,
)


PROTOCOL_RELATIVE = "protocols/corpus_v4_fem_v2_production_v1.json"
PLAN_ROOT_RELATIVE = "results/corpus_v4/cps_reference_v2/production/v1/plan"
OUTPUT_ROOT_RELATIVE = "results/corpus_v4/cps_reference_v2/production/v1"
LOCK_RELATIVE = "protocols/corpus_v4_fem_v2_production_lock_v1.json"
PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-protocol.v1"
PLAN_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-plan.v1"
LOCK_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-execution-lock.v1"
MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-task-manifest.v1"
DISPATCH_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-dispatch.v1"
PENDING_SET_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-pending-set.v1"
WAVE_ADMISSION_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-wave-admission.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-task.v1"
START_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-start.v1"
FIDELITIES = ("cps_fem_r3_p16_t1_v2", "cps_fem_r4_p16_t1_v2")
FIDELITY_SLUG = {
    "cps_fem_r3_p16_t1_v2": "r3",
    "cps_fem_r4_p16_t1_v2": "r4",
}
MANIFEST_NAME = {fidelity: f"{FIDELITY_SLUG[fidelity]}_manifest.jsonl" for fidelity in FIDELITIES}
SOURCE_WRAPPER = {
    "cps_fem_r3_p16_t1_v2": "code/jobs/submit_corpus_v4_fem_v2_r3.sh",
    "cps_fem_r4_p16_t1_v2": "code/jobs/submit_corpus_v4_fem_v2_r4.sh",
}
SHA256_HEX = frozenset("0123456789abcdef")


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_HEX


def repo_path(relative: str, label: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a repository-relative path")
    resolved = (ROOT / path).resolve()
    if resolved != ROOT.resolve() and ROOT.resolve() not in resolved.parents:
        raise ValueError(f"{label} escapes the repository")
    return resolved


def repo_relative(path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc


def canonical_file(path: Path, relative: str, label: str) -> Path:
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    expected = repo_path(relative, label)
    if supplied != expected or supplied.is_symlink() or not supplied.is_file():
        raise ValueError(f"{label} must equal {relative}")
    return supplied


def canonical_directory(path: Path, relative: str, label: str) -> Path:
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    expected = repo_path(relative, label)
    if supplied != expected:
        raise ValueError(f"{label} must equal {relative}")
    cursor = ROOT
    for component in Path(relative).parts:
        cursor /= component
        if cursor.is_symlink():
            raise ValueError(f"{label} contains a symlinked component")
    return supplied


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{label} row {line_number} is not an object")
        rows.append(value)
    return rows


def validate_protocol(protocol: Mapping[str, Any]) -> None:
    expected_top = {
        "artifact_contract",
        "authorities",
        "computational_sources",
        "failure_policy",
        "fidelities",
        "linear_solver",
        "physics",
        "protocol_name",
        "resource_profiles",
        "runtime",
        "schema",
        "scientific_semantics",
        "sharding",
    }
    if set(protocol) != expected_top:
        raise ValueError("production protocol top-level fields differ")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unexpected production protocol schema")
    if protocol.get("protocol_name") != "corpus-v4-fem-v2-one-thread-production-v1":
        raise ValueError("unexpected production protocol name")
    expected_fidelities = {
        "cps_fem_r3_p16_t1_v2": {
            "coverage": 1500,
            "pad_mm": 16.0,
            "refine": 3,
            "role": "bulk_low_fidelity",
        },
        "cps_fem_r4_p16_t1_v2": {
            "coverage": 198,
            "pad_mm": 16.0,
            "refine": 4,
            "role": "higher_fidelity_validation",
        },
    }
    if protocol.get("fidelities") != expected_fidelities:
        raise ValueError("production fidelity definitions differ")
    if protocol.get("sharding") != {
        "algorithm": "contiguous_canonical_indices_v1",
        "r3_max_array_size": 400,
        "r4_max_array_size": 198,
        "scheduler_max_submitted_array_elements": 1000,
    }:
        raise ValueError("production sharding contract differs")
    if protocol.get("linear_solver") != {
        "iterations_max": 100,
        "maxiter": 500,
        "reported": "pyamg_smoothed_aggregation_cg",
        "requested": "amg_cg",
        "require_input_system_sha256": True,
        "residual_max": 1e-9,
        "rtol": 1e-10,
        "solver_info": 0,
    } or protocol.get("physics") != {
        "element": "tetrahedral_P1",
        "energy_to_capacitance": "C=2W/V^2",
        "eps_r": 4.2,
        "problem": "3d_electrostatic_capacitance",
    }:
        raise ValueError("production solver and physics contract differs")

    expected_resources = {
        "cps_fem_r3_p16_t1_v2": (1, 48, 8, 7200, 1800.0),
        "cps_fem_r4_p16_t1_v2": (1, 160, 2, 10800, 7200.0),
    }
    for fidelity, (cpus, memory, throttle, time_s, wall_s) in expected_resources.items():
        profile = protocol.get("resource_profiles", {}).get(fidelity, {})
        slurm = profile.get("slurm", {})
        fail_fast = profile.get("fail_fast", {})
        if slurm != {
            "account": "pgs0407",
            "allocated_cpus_may_exceed_request": True,
            "cpus_per_task": cpus,
            "max_concurrent": throttle,
            "mem_gib": memory,
            "partition": "nextgen",
            "time_s": time_s,
        }:
            raise ValueError(f"{fidelity} Slurm resources differ")
        if (
            float(fail_fast.get("wall_s_max", -1.0)) != wall_s
            or fail_fast.get("operator_complexity_max") != 1.25
            or not isinstance(fail_fast.get("mesh_nodes_max"), int)
            or not isinstance(fail_fast.get("mesh_tetrahedra_max"), int)
            or not isinstance(fail_fast.get("worker_peak_rss_gib_max"), (int, float))
        ):
            raise ValueError(f"{fidelity} fail-fast limits differ")

    runtime = protocol.get("runtime", {})
    if runtime.get("threads") != {
        "BLIS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "PCB_GNN_GMSH_THREADS": "1",
    } or runtime.get("omp_dynamic") != "FALSE":
        raise ValueError("production numerical thread environment is not serialized")
    if protocol.get("scientific_semantics") != {
        "claim_eligible": False,
        "ground_truth": False,
        "mesh_converged": False,
        "multifidelity_only": True,
        "physical_accuracy_validated": False,
        "postterminal_package_admission_required_for_training": True,
        "speed_claim_eligible": False,
    }:
        raise ValueError("production scientific semantics were weakened")
    contract = protocol.get("artifact_contract", {})
    if any(
        contract.get(name) is not True
        for name in (
            "all_attempts_retained",
            "atomic_task_files",
            "child_gmsh_thread_observation_required",
            "exact_geometry_rehash_required",
            "immutable_attempt_directory",
            "postterminal_package_admission_required",
            "source_reauthenticated_after_solve",
            "terminal_accounting_required_for_acceptance",
        )
    ):
        raise ValueError("production artifact contract was weakened")
    failure = protocol.get("failure_policy", {})
    if failure != {
        "ambiguous_multiple_valid_attempts": "hard_fail",
        "genuine_numerical_or_resource_failure": "terminal_negative",
        "infrastructure_or_nonterminal_failure": "retry_same_task_same_hashes_only",
        "post_outcome_exclusion": "forbidden",
    }:
        raise ValueError("production failure policy differs")
    sources = protocol.get("computational_sources")
    if not isinstance(sources, dict) or not sources or any(not is_sha256(value) for value in sources.values()):
        raise ValueError("production source closure is malformed")
    authorities = protocol.get("authorities")
    if not isinstance(authorities, dict) or set(authorities) != {
        "cps_protocol",
        "gate_b_admission",
        "gate_c_admission",
        "geometry_layouts",
        "geometry_summary",
        "hf_selection_registry",
        "qualification_protocol",
        "split_registry",
        "family_registry",
    }:
        raise ValueError("production authority closure differs")
    for label, binding in authorities.items():
        if not isinstance(binding, dict) or not is_sha256(binding.get("sha256")) or not isinstance(binding.get("path"), str):
            raise ValueError(f"authority binding is malformed: {label}")


def authenticate_protocol(path: Path, expected_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    canonical = canonical_file(path, PROTOCOL_RELATIVE, "production protocol")
    observed = sha256_file(canonical)
    if expected_sha256 is not None and observed != expected_sha256:
        raise ValueError("production protocol SHA-256 differs from explicit pin")
    protocol = load_json_object(canonical, "production protocol")
    validate_protocol(protocol)
    return protocol, observed


def assert_source_stable(
    *, expected_head: str, protocol: Mapping[str, Any], protocol_sha256: str
) -> dict[str, str]:
    """Fail closed if the execution checkout or any frozen byte changed."""
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
    if head != expected_head or dirty or untracked_source:
        raise SystemExit("refusing production execution from changed source state")
    source_hashes = {
        name: sha256_file(repo_path(name, "computational source"))
        for name in protocol["computational_sources"]
    }
    if source_hashes != protocol["computational_sources"]:
        raise SystemExit("production computational source changed")
    if sha256_file(repo_path(PROTOCOL_RELATIVE, "protocol")) != protocol_sha256:
        raise SystemExit("production protocol changed")
    for label, binding in protocol["authorities"].items():
        if sha256_file(repo_path(binding["path"], label)) != binding["sha256"]:
            raise SystemExit(f"production authority changed: {label}")
    return source_hashes


def validate_authorities(protocol: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    observed: dict[str, str] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for label, binding in protocol["authorities"].items():
        path = repo_path(binding["path"], label)
        actual = sha256_file(path)
        if actual != binding["sha256"]:
            raise ValueError(f"authority SHA-256 mismatch: {label}")
        observed[label] = actual
        if path.suffix == ".json":
            payloads[label] = load_json_object(path, label)

    for stage, permission in (("gate_b", "r3_v2_generation_may_start"), ("gate_c", "multifidelity_v2_may_start")):
        admission = payloads[f"{stage}_admission"]
        if (
            admission.get("schema") != "pcb-gnn.corpus-v4-fem-v2-qualification-admission.v1"
            or admission.get("artifact_stage") != "postterminal_finalizer_admission"
            or admission.get("stage") != stage
            or admission.get("protocol_sha256") != protocol["authorities"]["qualification_protocol"]["sha256"]
            or admission.get("decision", {}).get("qualification_stage_pass") is not True
            or admission.get("decision", {}).get(permission) is not True
        ):
            raise ValueError(f"{stage} admission does not authorize production generation")
    gate_c = payloads["gate_c_admission"]
    if gate_c.get("decision", {}).get("scientific_outcome") != "SCIENTIFIC_NEGATIVE":
        raise ValueError("Gate-C mesh-sensitivity outcome was not preserved")
    inherited = payloads["cps_protocol"]
    qualification = payloads["qualification_protocol"]
    qualified_threads = qualification.get("runtime", {}).get("thread_environment", {})
    if (
        dict(protocol["linear_solver"]) != inherited.get("linear_solver")
        or dict(protocol["physics"]) != inherited.get("physics")
        or protocol["runtime"]["packages"]
        != qualification.get("runtime", {}).get("packages")
        or protocol["runtime"]["python"]
        != qualification.get("runtime", {}).get("python")
        or protocol["runtime"]["threads"]
        != {
            name: qualified_threads[name]
            for name in protocol["runtime"]["threads"]
        }
        or protocol["runtime"]["omp_dynamic"] != qualified_threads.get("OMP_DYNAMIC")
    ):
        raise ValueError(
            "production solver or runtime differs from qualified one-thread contract"
        )

    summary_binding = protocol["authorities"]["geometry_summary"]
    records, summary = load_verified_geometry_corpus(
        repo_path(Path(summary_binding["path"]).parent.as_posix(), "geometry corpus"),
        {
            "layouts_sha256": protocol["authorities"]["geometry_layouts"]["sha256"],
            "n_layouts": 1500,
            "n_unique_geometry": 1500,
            "required_gate": "geometry_valid",
            "summary_schema": "pcb-gnn.corpus-v3-final.v1",
            "summary_sha256": summary_binding["sha256"],
        },
    )
    if [int(row["layout_id"]) for row in records] != list(range(1500)):
        raise ValueError("verified geometry layout IDs are not dense 0..1499")
    if len({row["geometry_sha256"] for row in records}) != 1500:
        raise ValueError("verified geometry identities are not unique")

    selection = payloads["hf_selection_registry"]
    selected = selection.get("rows", [])
    if (
        selection.get("schema") != "pcb-gnn.hf-selection-registry.v1"
        or len(selected) != 198
        or len({int(row["layout_id"]) for row in selected}) != 198
        or len({row["geometry_sha256"] for row in selected}) != 198
    ):
        raise ValueError("high-fidelity registry is not the exact 198-layout authority")
    by_id = {int(row["layout_id"]): row for row in records}
    for row in selected:
        record = by_id.get(int(row["layout_id"]))
        if record is None or record["geometry_sha256"] != row["geometry_sha256"]:
            raise ValueError("high-fidelity selection differs from verified geometry")
    split = payloads["split_registry"]
    if split.get("schema") != "pcb-gnn.swap-closed-split-registry.v1" or split.get("init_seeds") != [40, 41, 42, 43, 44]:
        raise ValueError("split registry identity differs")
    if [row.get("split_seed") for row in split.get("rows", [])] != [40, 41, 42, 43, 44]:
        raise ValueError("split seeds differ")
    family_rows = load_jsonl(repo_path(protocol["authorities"]["family_registry"]["path"], "family registry"), "family registry")
    if len(family_rows) != 66 or len({row.get("family_id") for row in family_rows}) != 66:
        raise ValueError("family registry does not contain exactly 66 families")
    family_members = {
        row["family_id"]: set(int(value) for value in row["member_layout_ids"])
        for row in family_rows
    }
    if (
        any(
            row.get("n_members") != len(family_members[row["family_id"]])
            for row in family_rows
        )
        or set().union(*family_members.values()) != set(range(1500))
        or sum(len(values) for values in family_members.values()) != 1500
    ):
        raise ValueError("family registry membership is incomplete or overlapping")
    for split_row in split["rows"]:
        partitions = split_row.get("partitions", {})
        if set(partitions) != {"train", "validation", "test"}:
            raise ValueError("split partition names differ")
        expected_family_counts = {"train": 46, "validation": 7, "test": 13}
        seen_families: set[str] = set()
        seen_layouts: set[int] = set()
        for name, expected_count in expected_family_counts.items():
            entry = partitions[name]
            families = set(entry.get("family_ids", []))
            layouts = set(int(value) for value in entry.get("layout_ids", []))
            expected_layouts = set().union(
                *(family_members[family] for family in families)
            )
            if (
                len(families) != expected_count
                or entry.get("n_families") != expected_count
                or entry.get("n_layouts") != len(layouts)
                or layouts != expected_layouts
                or seen_families & families
                or seen_layouts & layouts
            ):
                raise ValueError(
                    "split partition membership differs from family registry"
                )
            seen_families |= families
            seen_layouts |= layouts
        if seen_families != set(family_members) or seen_layouts != set(range(1500)):
            raise ValueError("split registry does not exactly cover the frozen corpus")
    return records, observed


def solver_contract_id(protocol: Mapping[str, Any], fidelity_id: str) -> str:
    fidelity = protocol["fidelities"][fidelity_id]
    return sha256_json(
        {
            "computational_sources": protocol["computational_sources"],
            "fidelity": {"pad_mm": fidelity["pad_mm"], "refine": fidelity["refine"]},
            "linear_solver": protocol["linear_solver"],
            "physics": protocol["physics"],
            "runtime": protocol["runtime"],
        }
    )


def manifest_rows(records: Sequence[Mapping[str, Any]], protocol: Mapping[str, Any], protocol_sha256: str, fidelity_id: str) -> list[dict[str, Any]]:
    contract = solver_contract_id(protocol, fidelity_id)
    return [
        {
            "fidelity_id": fidelity_id,
            "geometry_sha256": row["geometry_sha256"],
            "layout_id": int(row["layout_id"]),
            "protocol_sha256": protocol_sha256,
            "schema": MANIFEST_SCHEMA,
            "solver_contract_id": contract,
            "task_index": index,
        }
        for index, row in enumerate(records)
    ]


def dispatch_rows(rows: Sequence[Mapping[str, Any]], *, protocol_sha256: str, manifest_sha256: str, max_array_size: int) -> list[dict[str, Any]]:
    dispatches: list[dict[str, Any]] = []
    for start in range(0, len(rows), max_array_size):
        selected = rows[start : start + max_array_size]
        dispatches.append(
            {
                "entries": [
                    {
                        "geometry_sha256": row["geometry_sha256"],
                        "layout_id": row["layout_id"],
                        "task_index": row["task_index"],
                    }
                    for row in selected
                ],
                "fidelity_id": selected[0]["fidelity_id"],
                "manifest_sha256": manifest_sha256,
                "protocol_sha256": protocol_sha256,
                "schema": DISPATCH_SCHEMA,
            }
        )
    flattened = [entry["task_index"] for dispatch in dispatches for entry in dispatch["entries"]]
    if flattened != list(range(len(rows))):
        raise RuntimeError("dispatch shards do not have exact dense coverage")
    return dispatches


def create_plan(protocol_path: Path, out: Path) -> dict[str, Any]:
    protocol, protocol_sha256 = authenticate_protocol(protocol_path)
    records, authority_hashes = validate_authorities(protocol)
    out = canonical_directory(out, PLAN_ROOT_RELATIVE, "production plan root")
    if out.exists() and any(out.iterdir()):
        raise SystemExit("refusing to overwrite a non-empty production plan")
    out.mkdir(parents=True, exist_ok=True)
    selected_ids = {
        int(row["layout_id"])
        for row in load_json_object(
            repo_path(protocol["authorities"]["hf_selection_registry"]["path"], "HF registry"),
            "HF registry",
        )["rows"]
    }
    r4_records = [row for row in records if int(row["layout_id"]) in selected_ids]
    if len(r4_records) != 198:
        raise RuntimeError("R4 record coverage differs from the frozen registry")
    manifests = {
        "r3_manifest.jsonl": manifest_rows(records, protocol, protocol_sha256, FIDELITIES[0]),
        "r4_manifest.jsonl": manifest_rows(r4_records, protocol, protocol_sha256, FIDELITIES[1]),
    }
    for name, rows in manifests.items():
        atomic_write_jsonl(out / name, rows)
    artifacts: dict[str, str] = {name: sha256_file(out / name) for name in manifests}
    dispatch_summary: dict[str, list[dict[str, Any]]] = {}
    for fidelity_id, rows in zip(FIDELITIES, manifests.values()):
        slug = FIDELITY_SLUG[fidelity_id]
        max_size = int(protocol["sharding"][f"{slug}_max_array_size"])
        shards = dispatch_rows(rows, protocol_sha256=protocol_sha256, manifest_sha256=artifacts[MANIFEST_NAME[fidelity_id]], max_array_size=max_size)
        dispatch_summary[fidelity_id] = []
        for index, payload in enumerate(shards):
            name = f"{slug}_dispatch_{index:03d}.json"
            atomic_write_json(out / name, payload)
            digest = sha256_file(out / name)
            artifacts[name] = digest
            dispatch_summary[fidelity_id].append(
                {
                    "canonical_task_max": payload["entries"][-1]["task_index"],
                    "canonical_task_min": payload["entries"][0]["task_index"],
                    "local_array_max": len(payload["entries"]) - 1,
                    "n_tasks": len(payload["entries"]),
                    "path": name,
                    "sha256": digest,
                }
            )
    plan = {
        "artifact_sha256": {name: artifacts[name] for name in sorted(artifacts)},
        "authority_sha256": authority_hashes,
        "counts": {"geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198},
        "dispatches": dispatch_summary,
        "planner_environment": {"python": platform.python_version()},
        "protocol_sha256": protocol_sha256,
        "schema": PLAN_SCHEMA,
        "solver_contract_ids": {fidelity: solver_contract_id(protocol, fidelity) for fidelity in FIDELITIES},
    }
    atomic_write_json(out / "plan.json", plan)
    return plan


def validate_plan(protocol: Mapping[str, Any], protocol_sha256: str, plan_path: Path, expected_plan_sha256: str) -> tuple[dict[str, Any], str]:
    canonical = canonical_file(plan_path, f"{PLAN_ROOT_RELATIVE}/plan.json", "production plan")
    observed = sha256_file(canonical)
    if observed != expected_plan_sha256:
        raise ValueError("production plan SHA-256 differs from explicit pin")
    plan = load_json_object(canonical, "production plan")
    _, current_authorities = validate_authorities(protocol)
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("protocol_sha256") != protocol_sha256
        or plan.get("authority_sha256") != current_authorities
        or plan.get("counts") != {"geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198}
        or plan.get("solver_contract_ids") != {fidelity: solver_contract_id(protocol, fidelity) for fidelity in FIDELITIES}
    ):
        raise ValueError("production plan identity differs")
    if plan.get("planner_environment") != {"python": protocol["runtime"]["python"]}:
        raise ValueError("production planner environment differs")
    artifacts = plan.get("artifact_sha256", {})
    expected_names = {"r3_manifest.jsonl", "r4_manifest.jsonl", *(f"r3_dispatch_{i:03d}.json" for i in range(4)), "r4_dispatch_000.json"}
    if set(artifacts) != expected_names:
        raise ValueError("production plan artifact set differs")
    for name, digest in artifacts.items():
        require_file_sha256(canonical.parent / name, digest, name)
    return plan, observed


def validate_manifest(protocol: Mapping[str, Any], protocol_sha256: str, plan: Mapping[str, Any], path: Path) -> tuple[list[dict[str, Any]], str, str]:
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    try:
        relative = supplied.relative_to(repo_path(PLAN_ROOT_RELATIVE, "plan root")).as_posix()
    except ValueError as exc:
        raise ValueError("manifest is outside the canonical production plan") from exc
    mapping = {"r3_manifest.jsonl": FIDELITIES[0], "r4_manifest.jsonl": FIDELITIES[1]}
    fidelity_id = mapping.get(relative)
    if fidelity_id is None:
        raise ValueError("unsupported production manifest")
    digest = sha256_file(supplied)
    if digest != plan["artifact_sha256"][relative]:
        raise ValueError("manifest SHA-256 differs from the production plan")
    rows = load_jsonl(supplied, "production manifest")
    expected_count = int(protocol["fidelities"][fidelity_id]["coverage"])
    expected_contract = solver_contract_id(protocol, fidelity_id)
    if len(rows) != expected_count:
        raise ValueError("manifest cardinality differs")
    for index, row in enumerate(rows):
        if row != {
            "fidelity_id": fidelity_id,
            "geometry_sha256": row.get("geometry_sha256"),
            "layout_id": row.get("layout_id"),
            "protocol_sha256": protocol_sha256,
            "schema": MANIFEST_SCHEMA,
            "solver_contract_id": expected_contract,
            "task_index": index,
        } or not is_sha256(row.get("geometry_sha256")) or type(row.get("layout_id")) is not int:
            raise ValueError(f"invalid production manifest row {index}")
    if len({row["geometry_sha256"] for row in rows}) != expected_count:
        raise ValueError("manifest contains duplicate geometry")
    records, _ = validate_authorities(protocol)
    if fidelity_id == FIDELITIES[0]:
        expected_records = records
    else:
        registry = load_json_object(
            repo_path(
                protocol["authorities"]["hf_selection_registry"]["path"],
                "HF registry",
            ),
            "HF registry",
        )
        selected = {
            int(row["layout_id"]): row["geometry_sha256"]
            for row in registry["rows"]
        }
        expected_records = [
            row for row in records if int(row["layout_id"]) in selected
        ]
    expected_identity = [
        (index, int(record["layout_id"]), record["geometry_sha256"])
        for index, record in enumerate(expected_records)
    ]
    observed_identity = [
        (row["task_index"], row["layout_id"], row["geometry_sha256"])
        for row in rows
    ]
    if observed_identity != expected_identity:
        raise ValueError(
            "manifest does not match the exact frozen geometry authority"
        )
    return rows, digest, fidelity_id


def classify_failure(
    execution: Mapping[str, Any],
    numerical: Mapping[str, Any],
    thread: Mapping[str, Any],
    source_stable: bool,
) -> str | None:
    """Keep resource and numerical failures terminal, even without a RESULT."""
    if numerical.get("pass") is True and thread.get("pass") is True and source_stable:
        return None
    stderr = "\n".join(str(line) for line in execution.get("stderr_tail", []))
    markers = (
        "configured resource limit exceeded",
        "AMG-CG did not converge",
        "linear solver returned non-finite values",
        "non-positive electrostatic energy",
        "returned no positive capacitance",
    )
    child_entered_solver = any(
        isinstance(stage, dict) and stage.get("stage") != "repeatability_environment"
        for stage in execution.get("stages", [])
    )
    if (
        execution.get("timed_out") is True
        or any(marker in stderr for marker in markers)
        or (child_entered_solver and execution.get("returncode") not in (0, None))
        or (
            numerical.get("checks", {}).get("worker_execution") is True
            and numerical.get("pass") is not True
        )
    ):
        return "genuine_numerical_or_resource_failure"
    return "infrastructure_or_integrity_failure"


def create_lock(protocol_path: Path, plan_path: Path, expected_plan_sha256: str, out: Path) -> dict[str, Any]:
    protocol, protocol_sha256 = authenticate_protocol(protocol_path)
    validate_authorities(protocol)
    validate_plan(protocol, protocol_sha256, plan_path, expected_plan_sha256)
    canonical_out = out.resolve() if out.is_absolute() else (ROOT / out).resolve()
    if canonical_out != repo_path(LOCK_RELATIVE, "execution lock") or canonical_out.exists():
        raise SystemExit(f"execution lock must be a new file at {LOCK_RELATIVE}")
    payload = {
        "plan_sha256": expected_plan_sha256,
        "protocol_sha256": protocol_sha256,
        "schema": LOCK_SCHEMA,
        "source_sha256": dict(protocol["computational_sources"]),
    }
    atomic_write_json(canonical_out, payload)
    return payload


def validate_lock(protocol: Mapping[str, Any], protocol_sha256: str, plan_sha256: str, path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    canonical = canonical_file(path, LOCK_RELATIVE, "production execution lock")
    observed = sha256_file(canonical)
    if observed != expected_sha256:
        raise ValueError("execution-lock SHA-256 differs from explicit pin")
    lock = load_json_object(canonical, "production execution lock")
    source_hashes = {name: sha256_file(repo_path(name, "computational source")) for name in protocol["computational_sources"]}
    if lock != {
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "schema": LOCK_SCHEMA,
        "source_sha256": source_hashes,
    } or source_hashes != protocol["computational_sources"]:
        raise ValueError("execution lock does not bind the current production source")
    return lock, observed


def validate_dispatch(
    protocol_sha256: str,
    plan: Mapping[str, Any],
    path: Path,
    expected_sha256: str,
    manifest_sha256: str,
    fidelity_id: str,
    manifest: Sequence[Mapping[str, Any]],
    *,
    execution_lock_sha256: str | None = None,
    expected_source_git_head: str | None = None,
    prior_admission: Path | None = None,
    expected_prior_admission_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    supplied = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    observed = sha256_file(supplied)
    if observed != expected_sha256:
        raise ValueError("dispatch SHA-256 differs from its explicit pin")
    dispatch = load_json_object(supplied, "production dispatch")
    if dispatch.get("schema") == PENDING_SET_SCHEMA:
        if (
            execution_lock_sha256 is None
            or expected_source_git_head is None
            or prior_admission is None
            or expected_prior_admission_sha256 is None
        ):
            raise ValueError("retry dispatch requires its prior admission binding")
        admission_path = (
            prior_admission.resolve()
            if prior_admission.is_absolute()
            else (ROOT / prior_admission).resolve()
        )
        wave_root = repo_path(f"{OUTPUT_ROOT_RELATIVE}/waves", "wave root")
        if (
            wave_root not in admission_path.parents
            or admission_path.name != "FINAL_ADMISSION.json"
            or admission_path.is_symlink()
            or not admission_path.is_file()
            or not is_sha256(expected_prior_admission_sha256)
            or sha256_file(admission_path) != expected_prior_admission_sha256
        ):
            raise ValueError("retry prior admission path or SHA-256 differs")
        admission = load_json_object(admission_path, "retry prior admission")
        roots = admission.get("roots", {})
        files = admission.get("preterminal_files", {})
        decision = admission.get("decision", {})
        if (
            admission.get("schema") != WAVE_ADMISSION_SCHEMA
            or admission.get("artifact_stage") != "postterminal_wave_admission"
            or admission.get("admission_eligible") is not True
            or admission.get("fidelity_id") != fidelity_id
            or admission.get("training_may_start") is not False
            or decision.get("terminal_negative") is not False
            or decision.get("scientific_outcome") != "INDETERMINATE"
            or decision.get("retry_may_start") is not True
            or roots.get("protocol_sha256") != protocol_sha256
            or roots.get("plan_sha256") != sha256_file(repo_path(f"{PLAN_ROOT_RELATIVE}/plan.json", "plan"))
            or roots.get("execution_lock_sha256") != execution_lock_sha256
            or roots.get("source_git_head") != expected_source_git_head
            or files.get("pending_set_path") != repo_relative(supplied, "retry dispatch")
            or files.get("pending_set_sha256") != observed
            or dispatch.get("protocol_sha256") != protocol_sha256
            or dispatch.get("plan_sha256") != roots.get("plan_sha256")
            or dispatch.get("execution_lock_sha256") != execution_lock_sha256
            or dispatch.get("manifest_sha256") != manifest_sha256
            or dispatch.get("fidelity_id") != fidelity_id
        ):
            raise ValueError("retry dispatch is not authorized by its admission")
    else:
        if prior_admission is not None or expected_prior_admission_sha256 is not None:
            raise ValueError("frozen plan dispatch must not carry a retry admission")
        try:
            name = supplied.relative_to(repo_path(PLAN_ROOT_RELATIVE, "plan root")).as_posix()
        except ValueError as exc:
            raise ValueError("dispatch is outside the canonical production plan") from exc
        if plan["artifact_sha256"].get(name) != observed:
            raise ValueError("dispatch SHA-256 differs from explicit plan pins")
        if (
            dispatch.get("schema") != DISPATCH_SCHEMA
            or dispatch.get("protocol_sha256") != protocol_sha256
            or dispatch.get("manifest_sha256") != manifest_sha256
            or dispatch.get("fidelity_id") != fidelity_id
        ):
            raise ValueError("dispatch roots differ")
    entries = dispatch.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("dispatch is empty")
    seen: set[int] = set()
    for entry in entries:
        index = int(entry.get("task_index", -1))
        if index in seen or index not in range(len(manifest)):
            raise ValueError("dispatch task index is duplicate or out of range")
        expected = manifest[index]
        if entry != {"geometry_sha256": expected["geometry_sha256"], "layout_id": expected["layout_id"], "task_index": index}:
            raise ValueError("dispatch task identity differs from manifest")
        seen.add(index)
    return dispatch, observed


def execute_task(args: argparse.Namespace) -> None:
    protocol, protocol_sha256 = authenticate_protocol(args.protocol, args.expected_protocol_sha256)
    records, authority_hashes = validate_authorities(protocol)
    plan, plan_sha256 = validate_plan(protocol, protocol_sha256, args.plan, args.expected_plan_sha256)
    manifest, manifest_sha256, fidelity_id = validate_manifest(protocol, protocol_sha256, plan, args.manifest)
    lock, lock_sha256 = validate_lock(protocol, protocol_sha256, plan_sha256, args.execution_lock, args.expected_execution_lock_sha256)
    dispatch, dispatch_sha256 = validate_dispatch(
        protocol_sha256,
        plan,
        args.dispatch,
        args.expected_dispatch_sha256,
        manifest_sha256,
        fidelity_id,
        manifest,
        execution_lock_sha256=lock_sha256,
        expected_source_git_head=args.expected_source_git_head,
        prior_admission=args.prior_admission,
        expected_prior_admission_sha256=args.expected_prior_admission_sha256,
    )
    retry_admission_path: Path | None = None
    retry_authorization: dict[str, str] | None = None
    if dispatch.get("schema") == PENDING_SET_SCHEMA:
        if args.prior_admission is None or args.expected_prior_admission_sha256 is None:
            raise ValueError("retry dispatch lost its prior admission binding")
        retry_admission_path = (
            args.prior_admission.resolve()
            if args.prior_admission.is_absolute()
            else (ROOT / args.prior_admission).resolve()
        )
        retry_authorization = {
            "path": repo_relative(retry_admission_path, "retry prior admission"),
            "sha256": args.expected_prior_admission_sha256,
        }
    if args.validate_only:
        print(json.dumps({"dispatch_sha256": dispatch_sha256, "fidelity_id": fidelity_id, "n_tasks": len(dispatch["entries"]), "plan_sha256": plan_sha256, "protocol_sha256": protocol_sha256, "solver_executed": False}, sort_keys=True))
        return
    if not args.expected_source_git_head:
        raise SystemExit("--expected-source-git-head is required for solver execution")
    slurm = validate_slurm_contract(fidelity_id, len(dispatch["entries"]), protocol)
    if slurm.get("scheduler_record", {}).get("Requeue") != "0":
        raise SystemExit("production arrays must disable Slurm requeue")
    local_index = int(slurm["array_task_id"])
    canonical_index = int(dispatch["entries"][local_index]["task_index"])
    task = manifest[canonical_index]
    slurm["canonical_task_index"] = canonical_index
    slurm["dispatch_sha256"] = dispatch_sha256

    source_hashes = assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
    )
    if source_hashes != lock["source_sha256"]:
        raise SystemExit("production source differs from execution lock")
    wrapper = repo_path(SOURCE_WRAPPER[fidelity_id], "batch wrapper")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not executed_batch.is_file() or sha256_file(executed_batch) != sha256_file(wrapper):
        raise SystemExit("executed Slurm spool source differs from frozen wrapper")
    environment = runtime_environment()
    if (
        environment["python"] != protocol["runtime"]["python"]
        or environment["package_versions"] != protocol["runtime"]["packages"]
        or environment["thread_environment"] != protocol["runtime"]["threads"]
        or os.environ.get("OMP_DYNAMIC") != protocol["runtime"]["omp_dynamic"]
    ):
        raise SystemExit("runtime or thread environment differs from production protocol")
    if (
        os.environ.get("SLURM_JOB_ACCOUNT") != protocol["resource_profiles"][fidelity_id]["slurm"]["account"]
        or slurm.get("scheduler_record", {}).get("Account")
        != protocol["resource_profiles"][fidelity_id]["slurm"]["account"]
    ):
        raise SystemExit("Slurm account differs from production protocol")
    by_id = {int(row["layout_id"]): row for row in records}
    record = by_id.get(int(task["layout_id"]))
    if record is None or record["geometry_sha256"] != task["geometry_sha256"]:
        raise ValueError("task geometry differs from verified corpus")
    expected_root = f"{OUTPUT_ROOT_RELATIVE}/attempts/{FIDELITY_SLUG[fidelity_id]}"
    output_root = canonical_directory(args.output_root, expected_root, "task output root")
    attempt_dir = output_root / f"job_{slurm['array_job_id']}" / f"task_{canonical_index:04d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    atomic_write_json(
        attempt_dir / "started.json",
        {
            "dispatch_sha256": dispatch_sha256,
            "fidelity_id": fidelity_id,
            "geometry_sha256": task["geometry_sha256"],
            "layout_id": task["layout_id"],
            "manifest_sha256": manifest_sha256,
            "plan_sha256": plan_sha256,
            "protocol_sha256": protocol_sha256,
            "retry_authorization": retry_authorization,
            "schema": START_SCHEMA,
            "slurm": slurm,
            "source_git_head": args.expected_source_git_head,
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "task_index": canonical_index,
        },
    )

    fidelity = protocol["fidelities"][fidelity_id]
    limits = protocol["resource_profiles"][fidelity_id]["fail_fast"]
    updates = {
        "PCB_GNN_GMSH_THREADS": "1",
        "PCB_GNN_MAX_MESH_NODES": str(limits["mesh_nodes_max"]),
        "PCB_GNN_MAX_MESH_TETRAHEDRA": str(limits["mesh_tetrahedra_max"]),
        "PCB_GNN_MAX_OPERATOR_COMPLEXITY": str(limits["operator_complexity_max"]),
        "PCB_GNN_MAX_RSS_KB": str(int(float(limits["worker_peak_rss_gib_max"]) * 1048576)),
    }
    previous = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    try:
        with _arm_environment(1):
            execution = run_repeatability_worker(record["layout"], int(fidelity["refine"]), float(fidelity["pad_mm"]), int(limits["wall_s_max"]))
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    numerical = evaluate_result(execution, protocol, fidelity_id)
    thread = gmsh_thread_gate(execution, 1)

    final_source_hashes = assert_source_stable(
        expected_head=args.expected_source_git_head,
        protocol=protocol,
        protocol_sha256=protocol_sha256,
    )
    _, final_authorities = validate_authorities(protocol)
    stable = bool(
        final_source_hashes == source_hashes
        and final_authorities == authority_hashes
        and sha256_file(args.plan) == plan_sha256
        and sha256_file(args.manifest) == manifest_sha256
        and sha256_file(args.dispatch) == dispatch_sha256
        and sha256_file(args.execution_lock) == lock_sha256
        and (
            retry_admission_path is None
            or sha256_file(retry_admission_path)
            == retry_authorization["sha256"]
        )
        and sha256_file(executed_batch) == sha256_file(wrapper)
    )
    task_pass = bool(numerical.get("pass") is True and thread.get("pass") is True and stable)
    failure_class = classify_failure(execution, numerical, thread, stable)
    worker_result = execution.get("worker_result")
    payload = {
        "claim_eligible": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "execution": execution,
        "fidelity": {"fidelity_id": fidelity_id, **fidelity},
        "geometry": {"geometry_sha256": record["geometry_sha256"], "layout_id": record["layout_id"]},
        "gates": {"gmsh_thread": thread, "numerical_resource": numerical, "source_stable": stable},
        "failure_class": failure_class,
        "fresh_production_solve": True,
        "package_admission_eligible": False,
        "provenance": {
            "authority_sha256": authority_hashes,
            "dispatch_sha256": dispatch_sha256,
            "environment": environment,
            "executed_batch_sha256": sha256_file(wrapper),
            "execution_lock_sha256": lock_sha256,
            "hardware": _hardware_identity(),
            "hostname": socket.gethostname(),
            "manifest_sha256": manifest_sha256,
            "plan_sha256": plan_sha256,
            "protocol_sha256": protocol_sha256,
            "retry_authorization": retry_authorization,
            "scheduler": slurm,
            "source_git_head": args.expected_source_git_head,
            "source_sha256": final_source_hashes,
        },
        "schema": TASK_SCHEMA,
        "solver_contract_id": task["solver_contract_id"],
        "speed_claim_eligible": False,
        "task_index": canonical_index,
        "task_pass": task_pass,
        "training_may_start": False,
        "worker_result": worker_result,
    }
    atomic_write_json(attempt_dir / "result.json", payload)
    atomic_write_json(attempt_dir / "TASK_MANIFEST.json", {"files_sha256": {name: sha256_file(attempt_dir / name) for name in ("result.json", "started.json")}, "schema": "pcb-gnn.corpus-v4-fem-v2-production-task-files.v1"})
    print(json.dumps({"artifact": repo_relative(attempt_dir, "task artifact"), "fidelity_id": fidelity_id, "task_index": canonical_index, "task_pass": task_pass}, sort_keys=True))
    if not task_pass:
        raise SystemExit(1)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="materialize the frozen manifests and dispatch shards")
    plan.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    plan.add_argument("--out", type=Path, default=Path(PLAN_ROOT_RELATIVE))
    lock = sub.add_parser("freeze-lock", help="bind the plan and execution source closure")
    lock.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    lock.add_argument("--plan", type=Path, default=Path(f"{PLAN_ROOT_RELATIVE}/plan.json"))
    lock.add_argument("--expected-plan-sha256", required=True)
    lock.add_argument("--out", type=Path, default=Path(LOCK_RELATIVE))
    run = sub.add_parser("run", help="execute one dispatch task under Slurm")
    run.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE))
    run.add_argument("--expected-protocol-sha256", required=True)
    run.add_argument("--plan", type=Path, default=Path(f"{PLAN_ROOT_RELATIVE}/plan.json"))
    run.add_argument("--expected-plan-sha256", required=True)
    run.add_argument("--execution-lock", type=Path, default=Path(LOCK_RELATIVE))
    run.add_argument("--expected-execution-lock-sha256", required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--dispatch", type=Path, required=True)
    run.add_argument("--expected-dispatch-sha256", required=True)
    run.add_argument("--expected-source-git-head")
    run.add_argument("--prior-admission", type=Path)
    run.add_argument("--expected-prior-admission-sha256")
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--validate-only", action="store_true")
    return root


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if args.command == "plan":
        print(json.dumps(create_plan(args.protocol, args.out), indent=2, sort_keys=True))
    elif args.command == "freeze-lock":
        print(json.dumps(create_lock(args.protocol, args.plan, args.expected_plan_sha256, args.out), indent=2, sort_keys=True))
    elif args.command == "run":
        execute_task(args)
    else:  # pragma: no cover
        raise AssertionError("unreachable command")


if __name__ == "__main__":
    main()
