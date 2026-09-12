#!/usr/bin/env python3
"""Run one immutable Corpus V4 paired-latency task under SLURM."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
for directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/experiments/proofs",
    ROOT / "code/inference",
    ROOT / "code/models/gnn",
    ROOT / "code/solvers",
):
    sys.path.insert(0, str(directory))

from corpus_v4_accuracy_dataset_v3 import (  # noqa: E402
    load_corpus_v4_accuracy_dataset_v3,
)
from corpus_v4_latency_contract_v2 import (  # noqa: E402
    EXPECTED_LAYOUTS,
    SCHEMA_PREFIX,
    TASK_MANIFEST_SCHEMA,
    TASK_RESULT_SCHEMA,
    load_json,
    load_jsonl,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_preflight_admission,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
)
from corpus_v4_latency_inference_v2 import (  # noqa: E402
    canonical_layout_bytes,
    combine_raw_record_blocks,
    load_designated_model,
    measure_model_only_inference,
    measure_raw_record_inference,
    parse_canonical_layout,
    prepare_model_only_batch,
)
from fem_corpus_v4_latency_v2 import run_fem_v2_r3p16_timed  # noqa: E402
from fasthenry_latency import run_fasthenry_timed  # noqa: E402
from geometry_contract import geometry_sha256, validate_passive_labels  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


TASK_SCHEMA = TASK_RESULT_SCHEMA
RECORD_SCHEMA = f"{SCHEMA_PREFIX}-record.v1"
ARTIFACT_MANIFEST_SCHEMA = TASK_MANIFEST_SCHEMA
FAILURE_SCHEMA = f"{SCHEMA_PREFIX}-failure-diagnostic.v1"
FAILURE_MANIFEST_SCHEMA = f"{SCHEMA_PREFIX}-failure-manifest.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("preflight", "full_array"), default="full_array")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--execution-lock", type=Path)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--preflight-admission", type=Path)
    parser.add_argument("--expected-preflight-admission-sha256")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _require_runtime_args(args: argparse.Namespace) -> None:
    required = (
        "protocol",
        "expected_protocol_sha256",
        "plan",
        "expected_plan_sha256",
        "task_manifest",
        "expected_task_manifest_sha256",
        "execution_lock",
        "expected_execution_lock_sha256",
        "expected_source_git_head",
        "output_root",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        raise SystemExit(f"missing latency task arguments: {missing}")
    admission_supplied = args.preflight_admission is not None
    admission_hash_supplied = args.expected_preflight_admission_sha256 is not None
    if admission_supplied != admission_hash_supplied:
        raise SystemExit("preflight-admission path and digest must be supplied together")
    if args.stage == "full_array" and not admission_supplied:
        raise SystemExit("full-array latency execution requires preflight admission")
    if args.stage == "preflight" and admission_supplied:
        raise SystemExit("preflight stage cannot consume its own admission")


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
            "git", "status", "--short", "--untracked-files=all", "--",
            "code", "protocols", "requirements-proof.txt",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    return head, tracked, source_untracked


def _repo_relative_output(path: Path) -> str:
    """Return a stable public label and reject output paths outside the repo."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("latency output path escapes the repository") from exc


@contextmanager
def _project_temporary_environment(parent: Path) -> Iterator[None]:
    """Confine solver scratch and subprocess temporary files to the repository."""
    resolved = parent.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("latency scratch path escapes the repository") from exc
    if parent.exists() or parent.is_symlink():
        raise FileExistsError(parent)
    parent.mkdir(parents=True)
    previous_tempdir = tempfile.tempdir
    previous_environment = {
        name: os.environ.get(name) for name in ("TMPDIR", "TEMP", "TMP")
    }
    try:
        with tempfile.TemporaryDirectory(prefix="runtime-", dir=parent) as directory:
            tempfile.tempdir = directory
            os.environ.update({name: directory for name in previous_environment})
            yield
    finally:
        tempfile.tempdir = previous_tempdir
        for name, value in previous_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


def _validate_source_stability(
    *,
    expected_head: str,
    expected_dirty: list[str],
    expected_untracked: list[str],
    locked_source_sha256: Mapping[str, str],
    protocol_path: Path,
    protocol_sha256: str,
    plan_path: Path,
    plan_sha256: str,
    task_manifest_path: Path,
    task_manifest_sha256: str,
    panel_path: Path,
    panel_sha256: str,
    execution_lock_path: Path,
    execution_lock_sha256: str,
) -> dict[str, str]:
    """Reauthenticate source and scientific roots after all heavy work."""
    final_head, final_dirty, final_untracked = _source_state()
    final_source_hashes = {
        name: sha256_file(resolve_repo_path(name, "execution source"))
        for name in locked_source_sha256
    }
    if (
        final_head != expected_head
        or final_dirty != expected_dirty
        or final_untracked != expected_untracked
        or final_source_hashes != locked_source_sha256
        or sha256_file(protocol_path) != protocol_sha256
        or sha256_file(plan_path) != plan_sha256
        or sha256_file(task_manifest_path) != task_manifest_sha256
        or sha256_file(panel_path) != panel_sha256
        or sha256_file(execution_lock_path) != execution_lock_sha256
    ):
        raise SystemExit("source or frozen scientific roots changed during execution")
    return final_source_hashes


def _runtime_identity(protocol: Mapping[str, Any]) -> dict[str, Any]:
    packages = {
        name: importlib.metadata.version(name)
        for name in ("gmsh", "meshio", "numpy", "pyamg", "scikit-fem", "scipy", "torch")
    }
    expected = protocol["runtime"]
    threads = {
        name: os.environ.get(name)
        for name in expected["thread_environment"]
    }
    actual = {
        "packages": packages,
        "python": platform.python_version(),
        "thread_environment": threads,
    }
    if actual != expected:
        raise SystemExit("runtime or scientific-thread environment differs from protocol")
    return actual


def _hardware_identity() -> dict[str, Any]:
    model_name = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                model_name = line.split(":", 1)[1].strip()
                break
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    payload = {
        "affinity_cpu_count": len(affinity),
        "architecture": platform.machine(),
        "cpu_model": model_name,
        "kernel": platform.release(),
    }
    return {**payload, "anonymous_class_sha256": sha256_bytes(canonical_json_bytes(payload))}


def _smoke_rows(path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(path)
    if len(rows) != 5:
        raise ValueError("checkpoint smoke fixture must contain exactly five layouts")
    return rows


def _fem_v2_reference_identity(
    path: Path,
    *,
    layout_id: int,
    geometry_sha256_value: str,
) -> dict[str, Any]:
    """Load the exact admitted R3 mesh/system identity for one panel layout."""
    matches = [
        row
        for row in load_jsonl(path)
        if row.get("layout_id") == layout_id
        and row.get("fidelity_id") == "cps_fem_r3_p16_t1_v2"
    ]
    if len(matches) != 1:
        raise ValueError("FEM-v2 observations do not contain one exact R3 row")
    row = matches[0]
    identity = {
        "geometry_sha256": row.get("geometry_sha256"),
        "mesh_nodes": row.get("mesh_nodes"),
        "mesh_tetrahedra": row.get("mesh_tetrahedra"),
        "system_sha256": row.get("system_sha256"),
    }
    if (
        identity["geometry_sha256"] != geometry_sha256_value
        or type(identity["mesh_nodes"]) is not int
        or identity["mesh_nodes"] <= 0
        or type(identity["mesh_tetrahedra"]) is not int
        or identity["mesh_tetrahedra"] <= 0
        or not isinstance(identity["system_sha256"], str)
        or len(identity["system_sha256"]) != 64
    ):
        raise ValueError("FEM-v2 admitted R3 mesh/system identity is malformed")
    return identity


def _relative_drift(observed: np.ndarray, expected: np.ndarray) -> np.ndarray:
    if observed.shape != (4,) or expected.shape != (4,):
        raise ValueError("solver reference vectors must have four targets")
    drift = np.abs(observed - expected) / np.maximum(np.abs(expected), 1e-12)
    if not np.all(np.isfinite(drift)):
        raise ValueError("solver-reference drift is non-finite")
    return drift


def run_solver_workflow(
    raw_layout: bytes,
    *,
    protocol: Mapping[str, Any],
    fem_v2_protocol: Mapping[str, Any],
    binary: Path,
    scratch_parent: Path,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Measure a sequential four-target solve with an enclosing wall timer."""
    solver = protocol["solver_workflow"]
    inductance = solver["inductance"]
    capacitance = solver["capacitance"]
    paired_start_ns = time.perf_counter_ns()
    with _project_temporary_environment(scratch_parent):
        fast = run_fasthenry_timed(
            raw_layout,
            parse_layout=parse_canonical_layout,
            binary=binary,
            frequency_hz=float(inductance["frequency_hz"]),
            timeout_s=int(inductance["timeout_s"]),
        )
        fem = run_fem_v2_r3p16_timed(
            raw_layout,
            parse_layout=parse_canonical_layout,
            fem_v2_protocol=fem_v2_protocol,
            timeout_s=int(capacitance["timeout_s"]),
        )
    targets = {**fem["target"], **fast["targets"]}
    targets = {name: float(value) for name, value in targets.items()}
    paired_stop_ns = time.perf_counter_ns()
    component_ms = {
        "fasthenry": float(fast["elapsed_ms"]),
        "fem_v2_r3_p16_t1": float(fem["elapsed_ms"]),
        "paired_four_target": (paired_stop_ns - paired_start_ns) / 1e6,
    }
    component_ms["orchestration_residual"] = (
        component_ms["paired_four_target"]
        - component_ms["fasthenry"]
        - component_ms["fem_v2_r3_p16_t1"]
    )
    if any(
        not math.isfinite(component_ms[name]) or component_ms[name] <= 0.0
        for name in ("fasthenry", "fem_v2_r3_p16_t1", "paired_four_target")
    ):
        raise RuntimeError("solver latency is not positive and finite")
    if (
        not math.isfinite(component_ms["orchestration_residual"])
        or component_ms["orchestration_residual"] < 0.0
    ):
        raise RuntimeError("paired outer-wall timer does not enclose both components")
    telemetry = {
        "fasthenry": {
            "returncode": fast["returncode"],
            "start_ns": fast["start_ns"],
            "stop_ns": fast["stop_ns"],
        },
        "fem_v2_r3_p16_t1": {
            "checks": {
                **fem["numerical_gate"]["checks"],
                "gmsh_one_thread": fem["thread_gate"]["pass"],
            },
            "observed": {
                **fem["numerical_gate"]["observed"],
                "gmsh_threads": fem["thread_gate"]["observed_gmsh_threads"],
                **fem["mesh_identity"],
            },
            "start_ns": fem["start_ns"],
            "stop_ns": fem["stop_ns"],
        },
        "paired_outer_wall": {
            "start_ns": paired_start_ns,
            "stop_ns": paired_stop_ns,
        },
    }
    return {"component_ms": component_ms, "telemetry": telemetry}, targets


def _atomic_task_directory(
    destination: Path,
    result: Mapping[str, Any],
) -> None:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite task attempt: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        atomic_write_json(temporary / "result.json", dict(result))
        atomic_write_json(
            temporary / "TASK_MANIFEST.json",
            {
                "files_sha256": {"result.json": sha256_file(temporary / "result.json")},
                "schema": ARTIFACT_MANIFEST_SCHEMA,
            },
        )
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _atomic_failure_directory(
    destination: Path,
    failure: Mapping[str, Any],
) -> None:
    """Write one immutable diagnostic that cannot enter the accepted set."""
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite failure attempt: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        atomic_write_json(temporary / "failure.json", dict(failure))
        atomic_write_json(
            temporary / "FAILURE_MANIFEST.json",
            {
                "files_sha256": {
                    "failure.json": sha256_file(temporary / "failure.json")
                },
                "schema": FAILURE_MANIFEST_SCHEMA,
            },
        )
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    args = parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "array_tasks": EXPECTED_LAYOUTS,
                    "fem_fidelity_id": "cps_fem_r3_p16_t1_v2",
                    "schema": TASK_SCHEMA,
                    "status": "validation-ok",
                    "timed_repetitions": 200,
                    "timing_boundary": "in-memory-raw-json-record-to-four-output",
                    "warmups": 50,
                },
                sort_keys=True,
            )
        )
        return
    _require_runtime_args(args)

    protocol, protocol_sha = validate_protocol(args.protocol, args.expected_protocol_sha256)
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
    fem_v2_dataset_admission_reference = dict(
        protocol["inputs"]["fem_v2_dataset_admission"]
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock,
        args.expected_execution_lock_sha256,
        protocol_sha256=protocol_sha,
        plan_sha256=plan_sha,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    bindings = {
        "execution_lock_sha256": lock_sha,
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_sha,
    }
    admission_reference = None
    if args.stage == "full_array":
        _, admission_reference = validate_preflight_admission(
            args.preflight_admission,
            args.expected_preflight_admission_sha256,
            bindings=bindings,
            expected_source_git_head=args.expected_source_git_head,
            tasks=tasks,
            lock=lock,
            checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
        )
    retry_binding = None
    expected_output_root = ROOT / {
        "preflight": "results/corpus_v4/latency_fem_v2/preflight",
        "full_array": "results/corpus_v4/latency_fem_v2/jobs",
    }[args.stage]
    if args.output_root.is_symlink() or args.output_root.resolve() != expected_output_root:
        raise SystemExit("latency output root differs from the canonical stage path")
    scheduler = validate_slurm_allocation(
        protocol,
        stage=args.stage,
        allowed_task_ids=None,
    )
    task_id = int(scheduler["array_task_id"])
    task = tasks[task_id]
    record = panel[task_id]
    scratch_parent = (
        args.output_root
        / "runtime_scratch"
        / f"job_{scheduler['array_job_id']}"
        / f"task_{task_id:03d}"
    )
    if task["layout_id"] != record["layout_id"]:
        raise ValueError("task and panel record layout identity differs")

    head, dirty, untracked_source = _source_state()
    if head != args.expected_source_git_head or dirty or untracked_source:
        raise SystemExit("latency task requires the exact clean source commit")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch = {
        "full_array": "code/jobs/submit_corpus_v4_latency_v2.sh",
        "preflight": "code/jobs/submit_corpus_v4_latency_preflight_v2.sh",
    }[args.stage]
    if (
        executed_batch.is_symlink()
        or not executed_batch.is_file()
        or sha256_file(executed_batch) != lock["source_sha256"].get(expected_batch)
    ):
        raise SystemExit("executed batch script differs from the source lock")
    runtime = _runtime_identity(protocol)

    configured_fast_binary = Path(os.environ.get("FASTHENRY_BIN", ""))
    fast_binary = configured_fast_binary.resolve()
    if (
        configured_fast_binary.is_symlink()
        or not fast_binary.is_file()
        or sha256_file(fast_binary)
        != protocol["solver_workflow"]["inductance"]["binary_sha256"]
    ):
        raise SystemExit("FastHenry executable differs from the frozen digest")

    accuracy_protocol_path = resolve_repo_path(
        protocol["inputs"]["accuracy_protocol"]["path"], "accuracy protocol"
    )
    dataset = load_corpus_v4_accuracy_dataset_v3(ROOT, accuracy_protocol_path)
    sample = dataset.sample_by_layout_id()[record["layout_id"]]
    if (
        sample.geometry_sha256 != record["geometry_sha256"]
        or dict(sample.layout) != record["layout"]
        or geometry_sha256(record["layout"]) != record["geometry_sha256"]
    ):
        raise ValueError("panel layout differs from the authenticated accuracy dataset")
    raw_layout = canonical_layout_bytes(record["layout"])
    parse_canonical_layout(raw_layout)
    fem_v2_reference_identity = _fem_v2_reference_identity(
        resolve_repo_path(
            protocol["inputs"]["fem_v2_final_observations"]["path"],
            "FEM-v2 final observations",
        ),
        layout_id=record["layout_id"],
        geometry_sha256_value=record["geometry_sha256"],
    )

    torch.set_num_threads(int(protocol["gnn_timing"]["torch_intraop_threads"]))
    torch.set_num_interop_threads(int(protocol["gnn_timing"]["torch_interop_threads"]))
    smoke_path = resolve_repo_path(
        protocol["inputs"]["checkpoint_smoke_examples"]["path"], "smoke fixture"
    )
    designated_result = load_json(
        resolve_repo_path(
            protocol["inputs"]["designated_task_result"]["path"],
            "designated accuracy task result",
        )
    )
    accuracy_bindings = designated_result.get("bindings")
    if not isinstance(accuracy_bindings, dict):
        raise ValueError("designated accuracy task has no authenticated bindings")
    checkpoint_task = {
        "designated_downstream_checkpoint": True,
        "init_seed": 42,
        "split_seed": 42,
        "task_id": 12,
    }
    bundle_dir = resolve_repo_path(
        protocol["inputs"]["checkpoint_metadata"]["path"], "checkpoint metadata"
    ).parent
    model, normalizer, model_load = load_designated_model(
        bundle_dir=bundle_dir,
        smoke_rows=_smoke_rows(smoke_path),
        smoke_input_sha256=protocol["inputs"]["checkpoint_smoke_examples"]["sha256"],
        metadata_sha256=protocol["inputs"]["checkpoint_metadata"]["sha256"],
        expected_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
        checkpoint_task=checkpoint_task,
        accuracy_bindings=accuracy_bindings,
        max_archive_bytes=int(protocol["checkpoint"]["maximum_archive_bytes"]),
        max_uncompressed_bytes=int(protocol["checkpoint"]["maximum_uncompressed_bytes"]),
    )
    model_only_design = protocol["gnn_timing"]["model_only_supporting"]
    model_only_measurement = measure_model_only_inference(
        model,
        normalizer,
        prepare_model_only_batch(normalizer, raw_layout),
        warmups=int(model_only_design["warmup_repetitions"]),
        repetitions=int(model_only_design["measured_repetitions"]),
    )

    pre = measure_raw_record_inference(
        model,
        normalizer,
        raw_layout,
        warmups=int(protocol["gnn_timing"]["warmup_repetitions"]),
        repetitions=int(protocol["gnn_timing"]["measured_repetitions_per_block"]),
    )
    fem_v2_protocol = load_json(
        resolve_repo_path(
            protocol["inputs"]["fem_v2_production_protocol"]["path"],
            "FEM-v2 production protocol",
        )
    )
    solver_measurement, rerun_targets = run_solver_workflow(
        raw_layout,
        protocol=protocol,
        fem_v2_protocol=fem_v2_protocol,
        binary=fast_binary,
        scratch_parent=scratch_parent,
    )
    post = measure_raw_record_inference(
        model,
        normalizer,
        raw_layout,
        warmups=0,
        repetitions=int(protocol["gnn_timing"]["measured_repetitions_per_block"]),
    )
    inference_measurement = combine_raw_record_blocks(
        pre,
        post,
        expected_repetitions=int(protocol["gnn_timing"]["measured_repetitions"]),
        expected_warmups=int(protocol["gnn_timing"]["warmup_repetitions"]),
        block_median_ratio_max=float(
            protocol["gnn_timing"]["block_median_ratio_max"]
        ),
    )
    inference_median_ms = float(inference_measurement["median"])

    target_order = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
    rerun = np.asarray([rerun_targets[name] for name in target_order], dtype=np.float64)
    reference = np.asarray(sample.training_target_values, dtype=np.float64)
    drift = _relative_drift(rerun, reference)
    tolerance = float(protocol["solver_workflow"]["reference_agreement_max_relative_error"])
    observed_fem_identity = {
        name: solver_measurement["telemetry"]["fem_v2_r3_p16_t1"]["observed"][name]
        for name in ("mesh_nodes", "mesh_tetrahedra", "system_sha256")
    }
    expected_fem_identity = {
        name: fem_v2_reference_identity[name]
        for name in ("mesh_nodes", "mesh_tetrahedra", "system_sha256")
    }
    fem_identity_matches = observed_fem_identity == expected_fem_identity
    if float(np.max(drift)) > tolerance or not fem_identity_matches:
        if sha256_file(fast_binary) != protocol["solver_workflow"]["inductance"]["binary_sha256"]:
            raise SystemExit("FastHenry executable changed during latency execution")
        absolute_error = np.abs(rerun - reference)
        violating_targets = [
            name
            for name, value in zip(target_order, drift)
            if float(value) > tolerance
        ]
        final_source_hashes = _validate_source_stability(
            expected_head=head,
            expected_dirty=dirty,
            expected_untracked=untracked_source,
            locked_source_sha256=lock["source_sha256"],
            protocol_path=args.protocol,
            protocol_sha256=protocol_sha,
            plan_path=args.plan,
            plan_sha256=plan_sha,
            task_manifest_path=args.task_manifest,
            task_manifest_sha256=task_sha,
            panel_path=panel_path,
            panel_sha256=panel_sha,
            execution_lock_path=args.execution_lock,
            execution_lock_sha256=lock_sha,
        )
        failure_bindings = {
            **bindings,
            "checkpoint_archive_sha256": protocol["inputs"]["checkpoint_archive"][
                "sha256"
            ],
            "fem_v2_dataset_admission": fem_v2_dataset_admission_reference,
            "preflight_admission": admission_reference,
            "retry_pending_set": retry_binding,
        }
        failure = {
            "admission_eligible": False,
            "bindings": failure_bindings,
            "claim_eligible": False,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "diagnostic": {
                "gnn": {
                    "model_load_ms": model_load["elapsed_ms"],
                    "model_only": model_only_measurement,
                    "post_solver": post,
                    "pre_solver": pre,
                },
                "reference_agreement": {
                    "absolute_error": absolute_error.tolist(),
                    "denominator_floor": 1e-12,
                    "formula": "abs(rerun-reference)/max(abs(reference),1e-12)",
                    "maximum_relative_drift": float(np.max(drift)),
                    "reference_values": reference.tolist(),
                    "relative_drift": drift.tolist(),
                    "rerun_values": rerun.tolist(),
                    "target_order": list(target_order),
                    "tolerance": tolerance,
                    "violating_targets": violating_targets,
                },
                "fem_v2_mesh_identity": {
                    "matches": fem_identity_matches,
                    "observed": observed_fem_identity,
                    "reference": expected_fem_identity,
                },
                "solver_ms": solver_measurement["component_ms"],
                "solver_telemetry": solver_measurement["telemetry"],
            },
            "failure_code": (
                "reference_agreement_exceeded"
                if float(np.max(drift)) > tolerance
                else "fem_v2_mesh_identity_mismatch"
            ),
            "integrity": {"passed": False},
            "provenance": {
                "executed_batch_sha256": sha256_file(executed_batch),
                "external_solver": {
                    "label": "external/fasthenry",
                    "sha256": protocol["solver_workflow"]["inductance"][
                        "binary_sha256"
                    ],
                },
                "hardware": _hardware_identity(),
                "runtime": runtime,
                "scheduler": scheduler,
                "source_git_head": head,
                "source_sha256": final_source_hashes,
            },
            "schema": FAILURE_SCHEMA,
            "stage": args.stage,
            "status": "failed",
            "task": {
                "family_id": task["family_id"],
                "geometry_sha256": task["geometry_sha256"],
                "layout_id": task["layout_id"],
                "task_id": task_id,
            },
        }
        failure_path = (
            args.output_root
            / "failures"
            / f"job_{scheduler['array_job_id']}"
            / f"task_{task_id:03d}"
        )
        failure_label = _repo_relative_output(failure_path)
        _atomic_failure_directory(failure_path, failure)
        print(
            f"task={task_id} failure=reference_agreement_exceeded "
            f"artifact={failure_label}",
            file=sys.stderr,
            flush=True,
        )
        raise RuntimeError("solver rerun differs from the frozen numerical reference")
    passivity = validate_passive_labels(rerun_targets)
    solver_ms = solver_measurement["component_ms"]
    paired_ms = solver_ms["paired_four_target"]
    speedups = {
        "speedup_fasthenry_three_target_x": (
            solver_ms["fasthenry"] / inference_median_ms
        ),
        "speedup_fem_v2_capacitance_x": (
            solver_ms["fem_v2_r3_p16_t1"] / inference_median_ms
        ),
        "speedup_paired_four_target_x": paired_ms / inference_median_ms,
    }
    if any(not math.isfinite(value) or value <= 0.0 for value in speedups.values()):
        raise RuntimeError("solver-to-GNN speedups are not positive and finite")

    final_source_hashes = _validate_source_stability(
        expected_head=head,
        expected_dirty=dirty,
        expected_untracked=untracked_source,
        locked_source_sha256=lock["source_sha256"],
        protocol_path=args.protocol,
        protocol_sha256=protocol_sha,
        plan_path=args.plan,
        plan_sha256=plan_sha,
        task_manifest_path=args.task_manifest,
        task_manifest_sha256=task_sha,
        panel_path=panel_path,
        panel_sha256=panel_sha,
        execution_lock_path=args.execution_lock,
        execution_lock_sha256=lock_sha,
    )
    if sha256_file(fast_binary) != protocol["solver_workflow"]["inductance"]["binary_sha256"]:
        raise SystemExit("FastHenry executable changed during latency execution")

    timing_record = {
        "family_id": record["family_id"],
        "fem_v2_reference_identity": fem_v2_reference_identity,
        "geometry_sha256": record["geometry_sha256"],
        "inference_raw_record_ms": inference_measurement,
        "inference_model_only_ms": model_only_measurement,
        "layout_id": record["layout_id"],
        "model_load_ms": model_load["elapsed_ms"],
        "prediction": pre["prediction"],
        "reference": reference.tolist(),
        "rerun_reference": rerun.tolist(),
        "schema": RECORD_SCHEMA,
        "solver_label_max_relative_drift": float(np.max(drift)),
        "solver_label_relative_drift": drift.tolist(),
        "solver_ms": solver_measurement["component_ms"],
        "solver_telemetry": solver_measurement["telemetry"],
        **speedups,
        "timer": {"clock": "perf_counter_ns", "monotonic": True},
        "winding_coupling_coefficient": passivity["coupling_coefficient"],
    }
    result_bindings = {
        **bindings,
        "checkpoint_archive_sha256": protocol["inputs"]["checkpoint_archive"]["sha256"],
        "fem_v2_dataset_admission": fem_v2_dataset_admission_reference,
        "preflight_admission": admission_reference,
        "retry_pending_set": retry_binding,
    }
    result = {
        "bindings": result_bindings,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": {"passed": True},
        "provenance": {
            "executed_batch_sha256": sha256_file(executed_batch),
            "external_solver": {
                "label": "external/fasthenry",
                "sha256": protocol["solver_workflow"]["inductance"]["binary_sha256"],
            },
            "hardware": _hardware_identity(),
            "runtime": runtime,
            "scheduler": scheduler,
            "source_git_head": head,
            "source_sha256": final_source_hashes,
        },
        "record": timing_record,
        "schema": TASK_SCHEMA,
        "stage": args.stage,
        "task": {
            "family_id": task["family_id"],
            "geometry_sha256": task["geometry_sha256"],
            "layout_id": task["layout_id"],
            "task_id": task_id,
        },
    }
    attempt = (
        args.output_root
        / "attempts"
        / f"job_{scheduler['array_job_id']}"
        / f"task_{task_id:03d}"
    )
    attempt_label = _repo_relative_output(attempt)
    _atomic_task_directory(attempt, result)
    print(
        f"task={task_id} layout={task['layout_id']} paired_ms={paired_ms:.6f} "
        f"gnn_ms={inference_median_ms:.6f} artifact={attempt_label}",
        flush=True,
    )


if __name__ == "__main__":
    main()
