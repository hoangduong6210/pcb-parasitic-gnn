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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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

from corpus_v4_accuracy_dataset import load_corpus_v4_accuracy_dataset  # noqa: E402
from corpus_v4_latency_contract import (  # noqa: E402
    EXPECTED_LAYOUTS,
    load_json,
    load_jsonl,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
)
from corpus_v4_latency_inference import (  # noqa: E402
    canonical_layout_bytes,
    load_designated_model,
    measure_raw_record_inference,
    parse_canonical_layout,
)
from fem_corpus_v4_latency import run_fem_r3p16_timed  # noqa: E402
from fasthenry_latency import run_fasthenry_timed  # noqa: E402
from geometry_contract import geometry_sha256, validate_passive_labels  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


TASK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v2"
RECORD_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-record.v2"
ARTIFACT_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task-artifact-manifest.v2"
FAILURE_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-failure-diagnostic.v1"
FAILURE_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-failure-manifest.v1"
PENDING_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-pending-set.v2"


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
    parser.add_argument("--pending-set", type=Path)
    parser.add_argument("--expected-pending-set-sha256")
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
    if (args.pending_set is None) != (args.expected_pending_set_sha256 is None):
        raise SystemExit("pending-set path and digest must be supplied together")


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


def _validate_pending_set(
    path: Path,
    expected_sha256: str,
    *,
    bindings: Mapping[str, str],
) -> list[int]:
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("pending set is missing or hash-mismatched")
    payload = load_json(path)
    expected_fields = {*bindings, "n_pending", "pending_task_ids", "schema"}
    task_ids = payload.get("pending_task_ids")
    if (
        set(payload) != expected_fields
        or payload.get("schema") != PENDING_SCHEMA
        or any(payload.get(name) != digest for name, digest in bindings.items())
        or not isinstance(task_ids, list)
        or any(type(value) is not int or value < 0 or value >= EXPECTED_LAYOUTS for value in task_ids)
        or task_ids != sorted(set(task_ids))
        or payload.get("n_pending") != len(task_ids)
        or not task_ids
    ):
        raise ValueError("pending set differs from the frozen retry contract")
    return task_ids


def _smoke_rows(path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(path)
    if len(rows) != 5:
        raise ValueError("checkpoint smoke fixture must contain exactly five layouts")
    return rows


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
    cps_protocol: Mapping[str, Any],
    binary: Path,
) -> tuple[dict[str, Any], dict[str, float]]:
    solver = protocol["solver_workflow"]
    inductance = solver["inductance"]
    capacitance = solver["capacitance"]
    fast = run_fasthenry_timed(
        raw_layout,
        parse_layout=parse_canonical_layout,
        binary=binary,
        frequency_hz=float(inductance["frequency_hz"]),
        timeout_s=int(inductance["timeout_s"]),
    )
    fem = run_fem_r3p16_timed(
        raw_layout,
        parse_layout=parse_canonical_layout,
        cps_protocol=cps_protocol,
        timeout_s=int(capacitance["timeout_s"]),
    )
    targets = {**fem["target"], **fast["targets"]}
    component_ms = {
        "fasthenry": float(fast["elapsed_ms"]),
        "fem_r3_p16": float(fem["elapsed_ms"]),
    }
    component_ms["paired_four_target"] = (
        component_ms["fasthenry"] + component_ms["fem_r3_p16"]
    )
    if any(not math.isfinite(value) or value <= 0.0 for value in component_ms.values()):
        raise RuntimeError("solver latency is not positive and finite")
    telemetry = {
        "fasthenry": {
            "returncode": fast["returncode"],
            "start_ns": fast["start_ns"],
            "stop_ns": fast["stop_ns"],
        },
        "fem_r3_p16": {
            "checks": fem["gate"]["checks"],
            "observed": fem["gate"]["observed"],
            "start_ns": fem["start_ns"],
            "stop_ns": fem["stop_ns"],
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
                    "fem_fidelity_id": "cps_fem_r3_p16",
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
    allowed = None
    retry_binding = None
    if args.pending_set is not None:
        allowed = _validate_pending_set(
            args.pending_set, args.expected_pending_set_sha256, bindings=bindings
        )
        retry_binding = {
            "path": args.pending_set.resolve().relative_to(ROOT.resolve()).as_posix(),
            "sha256": args.expected_pending_set_sha256,
        }
    scheduler = validate_slurm_allocation(
        protocol,
        stage=args.stage,
        allowed_task_ids=allowed,
    )
    task_id = int(scheduler["array_task_id"])
    task = tasks[task_id]
    record = panel[task_id]
    if task["layout_id"] != record["layout_id"]:
        raise ValueError("task and panel record layout identity differs")

    head, dirty, untracked_source = _source_state()
    if head != args.expected_source_git_head or dirty or untracked_source:
        raise SystemExit("latency task requires the exact clean source commit")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch = {
        "full_array": "code/jobs/submit_corpus_v4_latency.sh",
        "preflight": "code/jobs/submit_corpus_v4_latency_preflight.sh",
    }[args.stage]
    if (
        not executed_batch.is_file()
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
    dataset = load_corpus_v4_accuracy_dataset(ROOT, accuracy_protocol_path)
    sample = dataset.sample_by_layout_id()[record["layout_id"]]
    if (
        sample.geometry_sha256 != record["geometry_sha256"]
        or dict(sample.layout) != record["layout"]
        or geometry_sha256(record["layout"]) != record["geometry_sha256"]
    ):
        raise ValueError("panel layout differs from the authenticated accuracy dataset")
    raw_layout = canonical_layout_bytes(record["layout"])
    parse_canonical_layout(raw_layout)

    torch.set_num_threads(int(protocol["gnn_timing"]["torch_intraop_threads"]))
    torch.set_num_interop_threads(int(protocol["gnn_timing"]["torch_interop_threads"]))
    smoke_path = resolve_repo_path(
        protocol["inputs"]["checkpoint_smoke_examples"]["path"], "smoke fixture"
    )
    accuracy_bindings = {
        "evaluation_dataset_sha256": protocol["inputs"]["evaluation_dataset"]["sha256"],
        "execution_lock_sha256": protocol["inputs"]["accuracy_execution_lock"]["sha256"],
        "plan_sha256": protocol["inputs"]["accuracy_plan"]["sha256"],
        "protocol_sha256": protocol["inputs"]["accuracy_protocol"]["sha256"],
        "task_manifest_sha256": protocol["inputs"]["accuracy_task_manifest"]["sha256"],
    }
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

    pre = measure_raw_record_inference(
        model,
        normalizer,
        raw_layout,
        warmups=int(protocol["gnn_timing"]["warmup_repetitions"]),
        repetitions=int(protocol["gnn_timing"]["measured_repetitions_per_block"]),
    )
    cps_protocol = load_json(
        resolve_repo_path(
            protocol["inputs"]["cps_multifidelity_protocol"]["path"],
            "Cps multifidelity protocol",
        )
    )
    solver_measurement, rerun_targets = run_solver_workflow(
        raw_layout,
        protocol=protocol,
        cps_protocol=cps_protocol,
        binary=fast_binary,
    )
    post = measure_raw_record_inference(
        model,
        normalizer,
        raw_layout,
        warmups=0,
        repetitions=int(protocol["gnn_timing"]["measured_repetitions_per_block"]),
    )
    if pre["prediction"] != post["prediction"]:
        raise RuntimeError("pre/post solver GNN predictions differ")
    inference_repetitions = pre["repetitions_ms"] + post["repetitions_ms"]
    if len(inference_repetitions) != int(protocol["gnn_timing"]["measured_repetitions"]):
        raise RuntimeError("combined GNN measurement count differs from protocol")
    inference_median_ms = float(np.median(np.asarray(inference_repetitions)))

    target_order = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
    rerun = np.asarray([rerun_targets[name] for name in target_order], dtype=np.float64)
    reference = np.asarray(sample.training_target_values, dtype=np.float64)
    drift = _relative_drift(rerun, reference)
    tolerance = float(protocol["solver_workflow"]["reference_agreement_max_relative_error"])
    if float(np.max(drift)) > tolerance:
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
        failure = {
            "admission_eligible": False,
            "bindings": {
                **bindings,
                "checkpoint_archive_sha256": protocol["inputs"]["checkpoint_archive"][
                    "sha256"
                ],
                "retry_pending_set": retry_binding,
            },
            "claim_eligible": False,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "diagnostic": {
                "gnn": {
                    "model_load_ms": model_load["elapsed_ms"],
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
                "solver_ms": solver_measurement["component_ms"],
                "solver_telemetry": solver_measurement["telemetry"],
            },
            "failure_code": "reference_agreement_exceeded",
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
        raise RuntimeError("solver rerun differs from frozen references beyond tolerance")
    passivity = validate_passive_labels(rerun_targets)
    paired_ms = solver_measurement["component_ms"]["paired_four_target"]
    speedup = paired_ms / inference_median_ms
    if not math.isfinite(speedup) or speedup <= 0.0:
        raise RuntimeError("paired speedup is not positive and finite")

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

    timing_record = {
        "family_id": record["family_id"],
        "geometry_sha256": record["geometry_sha256"],
        "inference_raw_record_ms": {
            "median": inference_median_ms,
            "post_solver_median": post["median_ms"],
            "post_solver_repetitions": post["repetitions_ms"],
            "pre_solver_median": pre["median_ms"],
            "pre_solver_repetitions": pre["repetitions_ms"],
            "repetitions": inference_repetitions,
            "timed_repetitions": len(inference_repetitions),
            "warmups": int(protocol["gnn_timing"]["warmup_repetitions"]),
        },
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
        "speedup_paired_four_target_x": speedup,
        "timer": {"clock": "perf_counter_ns", "monotonic": True},
        "winding_coupling_coefficient": passivity["coupling_coefficient"],
    }
    result = {
        "bindings": {
            **bindings,
            "checkpoint_archive_sha256": protocol["inputs"]["checkpoint_archive"]["sha256"],
            "retry_pending_set": retry_binding,
        },
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
