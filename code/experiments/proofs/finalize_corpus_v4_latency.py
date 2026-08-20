#!/usr/bin/env python3
"""Finalize admitted Corpus V4 paired-latency tasks under SLURM."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_accuracy_contract import canonical_tres, tres_equivalent  # noqa: E402
from corpus_v4_latency_contract import (  # noqa: E402
    EXPECTED_FAMILIES,
    EXPECTED_LAYOUTS,
    load_json,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
)
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    sha256_file,
)


TASK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v2"
RECORD_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-record.v2"
ARTIFACT_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task-artifact-manifest.v2"
ACCEPTED_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-accepted-set.v2"
FINAL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-final.v2"
ANALYSIS_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-analysis-manifest.v2"


def _positive(value: Any, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _finite_vector(value: Any, length: int, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must contain exactly {length} finite values")
    return array


def validate_timing_record(
    record: Mapping[str, Any], *, expected_repetitions: int = 200
) -> dict[str, Any]:
    """Recompute every timing-derived value from retained raw observations."""
    expected_fields = {
        "family_id",
        "geometry_sha256",
        "inference_raw_record_ms",
        "layout_id",
        "model_load_ms",
        "prediction",
        "reference",
        "rerun_reference",
        "schema",
        "solver_label_max_relative_drift",
        "solver_label_relative_drift",
        "solver_ms",
        "solver_telemetry",
        "speedup_paired_four_target_x",
        "timer",
        "winding_coupling_coefficient",
    }
    if set(record) != expected_fields or record.get("schema") != RECORD_SCHEMA:
        raise ValueError("latency record schema or fields are not exact")
    layout_id = record.get("layout_id")
    family_id = record.get("family_id")
    geometry = record.get("geometry_sha256")
    if (
        type(layout_id) is not int
        or layout_id < 0
        or not isinstance(family_id, str)
        or not family_id
        or not isinstance(geometry, str)
        or len(geometry) != 64
        or any(character not in "0123456789abcdef" for character in geometry)
    ):
        raise ValueError("latency record design identity is malformed")

    solver = record.get("solver_ms")
    if not isinstance(solver, dict) or set(solver) != {
        "fasthenry", "fem_r3_p16", "paired_four_target"
    }:
        raise ValueError("solver timing components are not exact")
    fasthenry_ms = _positive(solver["fasthenry"], "FastHenry latency")
    fem_ms = _positive(solver["fem_r3_p16"], "FEM latency")
    paired_ms = _positive(solver["paired_four_target"], "paired solver latency")
    if not math.isclose(paired_ms, fasthenry_ms + fem_ms, rel_tol=1e-12, abs_tol=1e-9):
        raise ValueError("paired solver latency differs from component sum")

    inference = record.get("inference_raw_record_ms")
    expected_inference_fields = {
        "median",
        "post_solver_median",
        "post_solver_repetitions",
        "pre_solver_median",
        "pre_solver_repetitions",
        "repetitions",
        "timed_repetitions",
        "warmups",
    }
    if not isinstance(inference, dict) or set(inference) != expected_inference_fields:
        raise ValueError("GNN timing record fields are not exact")
    repetitions = _finite_vector(
        inference["repetitions"], expected_repetitions, "GNN repetitions"
    )
    pre = _finite_vector(
        inference["pre_solver_repetitions"], expected_repetitions // 2, "pre-solver GNN repetitions"
    )
    post = _finite_vector(
        inference["post_solver_repetitions"], expected_repetitions // 2, "post-solver GNN repetitions"
    )
    if np.any(repetitions <= 0.0) or np.any(pre <= 0.0) or np.any(post <= 0.0):
        raise ValueError("GNN repetitions must be strictly positive")
    if not np.array_equal(repetitions, np.concatenate((pre, post))):
        raise ValueError("combined GNN repetitions differ from pre/post blocks")
    if inference.get("timed_repetitions") != expected_repetitions or inference.get("warmups") != 50:
        raise ValueError("GNN warmup/repetition counts differ from protocol")
    medians = {
        "median": float(np.median(repetitions)),
        "pre_solver_median": float(np.median(pre)),
        "post_solver_median": float(np.median(post)),
    }
    for name, expected in medians.items():
        observed = _positive(inference.get(name), f"GNN {name}")
        if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"stored GNN {name} differs from raw repetitions")

    speedup = _positive(record.get("speedup_paired_four_target_x"), "paired speedup")
    if not math.isclose(speedup, paired_ms / medians["median"], rel_tol=1e-12, abs_tol=1e-9):
        raise ValueError("stored paired speedup differs from timing reconstruction")
    _positive(record.get("model_load_ms"), "model-load latency")
    _finite_vector(record.get("prediction"), 4, "prediction")
    reference = _finite_vector(record.get("reference"), 4, "reference")
    rerun = _finite_vector(record.get("rerun_reference"), 4, "rerun reference")
    if np.any(reference <= 0.0):
        raise ValueError("frozen references must be positive")
    expected_drift = np.abs(rerun - reference) / np.maximum(np.abs(reference), 1e-12)
    drift = _finite_vector(record.get("solver_label_relative_drift"), 4, "solver drift")
    if not np.allclose(drift, expected_drift, rtol=1e-12, atol=1e-15):
        raise ValueError("stored solver drift differs from reference reconstruction")
    maximum = float(np.max(drift))
    if not math.isclose(
        float(record.get("solver_label_max_relative_drift")), maximum,
        rel_tol=1e-12, abs_tol=1e-15,
    ):
        raise ValueError("stored maximum solver drift is inconsistent")
    coupling = float(record.get("winding_coupling_coefficient"))
    if not math.isfinite(coupling) or coupling < 0.0 or coupling > 1.000001:
        raise ValueError("winding coupling coefficient violates passivity")
    if record.get("timer") != {"clock": "perf_counter_ns", "monotonic": True}:
        raise ValueError("latency timer contract is not exact")
    telemetry = record.get("solver_telemetry")
    if not isinstance(telemetry, dict) or set(telemetry) != {
        "fasthenry", "fem_r3_p16"
    }:
        raise ValueError("solver telemetry fields are not exact")
    fast_telemetry = telemetry["fasthenry"]
    fem_telemetry = telemetry["fem_r3_p16"]
    if (
        not isinstance(fast_telemetry, dict)
        or set(fast_telemetry) != {"returncode", "start_ns", "stop_ns"}
        or fast_telemetry["returncode"] != 0
        or type(fast_telemetry["start_ns"]) is not int
        or type(fast_telemetry["stop_ns"]) is not int
        or fast_telemetry["stop_ns"] <= fast_telemetry["start_ns"]
        or not math.isclose(
            (fast_telemetry["stop_ns"] - fast_telemetry["start_ns"]) / 1e6,
            fasthenry_ms,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("FastHenry telemetry differs from its timing record")
    if (
        not isinstance(fem_telemetry, dict)
        or set(fem_telemetry) != {"checks", "observed", "start_ns", "stop_ns"}
        or not isinstance(fem_telemetry["checks"], dict)
        or not fem_telemetry["checks"]
        or any(value is not True for value in fem_telemetry["checks"].values())
        or not isinstance(fem_telemetry["observed"], dict)
        or fem_telemetry["observed"].get("refine") != 3
        or fem_telemetry["observed"].get("pad_mm") != 16.0
        or fem_telemetry["observed"].get("solver_info") != 0
        or type(fem_telemetry["start_ns"]) is not int
        or type(fem_telemetry["stop_ns"]) is not int
        or fem_telemetry["stop_ns"] <= fem_telemetry["start_ns"]
        or not math.isclose(
            (fem_telemetry["stop_ns"] - fem_telemetry["start_ns"]) / 1e6,
            fem_ms,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("FEM telemetry differs from its R3P16 timing record")
    return dict(record)


def _family_cluster_interval(
    records: Sequence[Mapping[str, Any]], *, resamples: int, seed: int
) -> list[float]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_family[str(record["family_id"])].append(
            float(record["speedup_paired_four_target_x"])
        )
    families = sorted(by_family)
    if len(families) < 2:
        raise ValueError("family-cluster bootstrap requires at least two families")
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        selected = rng.choice(families, size=len(families), replace=True)
        values = [value for family in selected for value in by_family[str(family)]]
        draws[index] = float(np.median(np.asarray(values, dtype=np.float64)))
    return [
        float(value)
        for value in np.quantile(draws, [0.025, 0.975], method="linear")
    ]


def summarize_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_repetitions: int = 200,
    bootstrap_resamples: int = 10_000,
    bootstrap_seed: int = 20260820,
) -> dict[str, Any]:
    if type(bootstrap_resamples) is not int or bootstrap_resamples < 1:
        raise ValueError("bootstrap resamples must be a positive integer")
    validated = [
        validate_timing_record(record, expected_repetitions=expected_repetitions)
        for record in records
    ]
    layout_ids = [record["layout_id"] for record in validated]
    geometries = [record["geometry_sha256"] for record in validated]
    if len(layout_ids) != len(set(layout_ids)) or len(geometries) != len(set(geometries)):
        raise ValueError("duplicate layout or geometry in latency records")
    speedups = np.asarray(
        [record["speedup_paired_four_target_x"] for record in validated],
        dtype=np.float64,
    )
    paired = np.asarray(
        [record["solver_ms"]["paired_four_target"] for record in validated],
        dtype=np.float64,
    )
    fast = np.asarray(
        [record["solver_ms"]["fasthenry"] for record in validated], dtype=np.float64
    )
    fem = np.asarray(
        [record["solver_ms"]["fem_r3_p16"] for record in validated], dtype=np.float64
    )
    gnn = np.asarray(
        [record["inference_raw_record_ms"]["median"] for record in validated],
        dtype=np.float64,
    )
    model_load = np.asarray(
        [record["model_load_ms"] for record in validated], dtype=np.float64
    )
    return {
        "bootstrap_cluster": "family",
        "bootstrap_resamples": bootstrap_resamples,
        "component_medians_ms": {
            "fasthenry": float(np.median(fast)),
            "fem_r3_p16": float(np.median(fem)),
            "model_load": float(np.median(model_load)),
            "paired_four_target": float(np.median(paired)),
            "warm_loaded_raw_record_gnn": float(np.median(gnn)),
        },
        "interval_semantics": (
            "descriptive family-cluster sensitivity interval on the evaluated split "
            "and CPU-node class; not a population confidence interval"
        ),
        "median_paired_speedup_family_cluster_bootstrap_95_interval": (
            _family_cluster_interval(
                validated, resamples=bootstrap_resamples, seed=bootstrap_seed
            )
        ),
        "median_paired_speedup_x": float(np.median(speedups)),
        "n_designs": len(validated),
        "n_families": len({record["family_id"] for record in validated}),
        "paired_speedup_p05_x": float(np.quantile(speedups, 0.05, method="linear")),
        "paired_speedup_p95_x": float(np.quantile(speedups, 0.95, method="linear")),
        "primary_estimand": "median of per-design paired solver-to-GNN ratios",
        "ratio_of_component_medians_x": float(np.median(paired) / np.median(gnn)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--execution-lock", type=Path)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--accepted-set", type=Path)
    parser.add_argument("--expected-accepted-set-sha256")
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--source-array-job-id")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _runtime_required(args: argparse.Namespace) -> None:
    names = (
        "protocol", "expected_protocol_sha256", "plan", "expected_plan_sha256",
        "task_manifest", "expected_task_manifest_sha256", "execution_lock",
        "expected_execution_lock_sha256", "accepted_set",
        "expected_accepted_set_sha256", "expected_source_git_head", "output_root",
    )
    missing = [name for name in names if getattr(args, name) is None]
    if missing:
        raise SystemExit(f"missing latency finalizer arguments: {missing}")


def _accepted_entries(
    path: Path,
    expected_sha256: str,
    *,
    bindings: Mapping[str, str],
) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("accepted set is missing or hash-mismatched")
    payload = load_json(path)
    expected_fields = {*bindings, "candidate_index", "entries", "n_accepted", "n_expected", "schema"}
    entries = payload.get("entries")
    if (
        set(payload) != expected_fields
        or payload.get("schema") != ACCEPTED_SCHEMA
        or any(payload.get(name) != digest for name, digest in bindings.items())
        or payload.get("n_expected") != EXPECTED_LAYOUTS
        or payload.get("n_accepted") != EXPECTED_LAYOUTS
        or not isinstance(entries, list)
        or len(entries) != EXPECTED_LAYOUTS
    ):
        raise ValueError("accepted set is not the exact complete latency closure")
    if [entry.get("task_id") for entry in entries] != list(range(EXPECTED_LAYOUTS)):
        raise ValueError("accepted latency entries are not dense tasks 0..305")
    return entries


def _load_task_result(
    entry: Mapping[str, Any],
    *,
    task: Mapping[str, Any],
    bindings: Mapping[str, str],
    expected_source_git_head: str,
) -> tuple[dict[str, Any], Path]:
    manifest_path = resolve_repo_path(entry.get("manifest_path"), "accepted task manifest")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("accepted task manifest is missing")
    if sha256_file(manifest_path) != entry.get("manifest_sha256"):
        raise ValueError("accepted task manifest hash differs")
    manifest = load_json(manifest_path)
    result_path = manifest_path.parent / "result.json"
    if (
        manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA
        or manifest.get("files_sha256") != {"result.json": sha256_file(result_path)}
    ):
        raise ValueError("accepted task artifact manifest is invalid")
    result = load_json(result_path)
    expected_task = {
        "family_id": task["family_id"],
        "geometry_sha256": task["geometry_sha256"],
        "layout_id": task["layout_id"],
        "task_id": task["task_id"],
    }
    if (
        result.get("schema") != TASK_SCHEMA
        or result.get("stage") != "full_array"
        or result.get("task") != expected_task
        or result.get("integrity") != {"passed": True}
        or result.get("provenance", {}).get("source_git_head") != expected_source_git_head
        or any(result.get("bindings", {}).get(name) != digest for name, digest in bindings.items())
    ):
        raise ValueError("accepted task result differs from frozen roots or task identity")
    completion = entry.get("scheduler_completion")
    scheduler = result["provenance"]["scheduler"]
    if (
        not isinstance(completion, dict)
        or completion.get("State") != "COMPLETED"
        or completion.get("ExitCode") != "0:0"
        or completion.get("JobID") != scheduler.get("job_id")
        or completion.get("Account")
        != scheduler["scheduler_record"].get("Account")
        or any(
            not tres_equivalent(completion.get(name), scheduler["scheduler_record"].get(name))
            for name in ("ReqTRES", "AllocTRES")
        )
    ):
        raise ValueError("accepted task lacks matching terminal SLURM accounting")
    validate_timing_record(result["record"])
    return result, manifest_path


def main() -> None:
    args = _parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "bootstrap_cluster": "family",
                    "bootstrap_resamples": 10_000,
                    "schema": FINAL_SCHEMA,
                    "status": "validation-ok",
                },
                sort_keys=True,
            )
        )
        return
    _runtime_required(args)
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
    scheduler = validate_slurm_allocation(protocol, stage="finalizer")
    bindings = {
        "execution_lock_sha256": lock_sha,
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_sha,
    }
    entries = _accepted_entries(
        args.accepted_set, args.expected_accepted_set_sha256, bindings=bindings
    )
    results: list[dict[str, Any]] = []
    manifests: list[Path] = []
    for task, entry in zip(tasks, entries):
        result, manifest = _load_task_result(
            entry,
            task=task,
            bindings=bindings,
            expected_source_git_head=args.expected_source_git_head,
        )
        results.append(result)
        manifests.append(manifest)
    records = [result["record"] for result in results]
    if [record["layout_id"] for record in records] != [row["layout_id"] for row in panel]:
        raise ValueError("accepted latency records differ from frozen panel order")
    if len({record["family_id"] for record in records}) != EXPECTED_FAMILIES:
        raise ValueError("accepted latency records do not cover all held-out families")
    tolerance = float(
        protocol["solver_workflow"]["reference_agreement_max_relative_error"]
    )
    if any(
        float(record["solver_label_max_relative_drift"]) > tolerance
        for record in records
    ):
        raise ValueError("an accepted solver rerun exceeds the frozen reference tolerance")
    hardware_classes = {
        result["provenance"]["hardware"]["anonymous_class_sha256"] for result in results
    }
    if len(hardware_classes) != 1:
        raise ValueError("latency evidence spans multiple CPU-node classes")
    summary = summarize_records(
        records,
        expected_repetitions=int(protocol["gnn_timing"]["measured_repetitions"]),
        bootstrap_resamples=int(protocol["statistics"]["bootstrap"]["resamples"]),
        bootstrap_seed=int(protocol["statistics"]["bootstrap"]["seed"]),
    )
    if summary["n_designs"] != EXPECTED_LAYOUTS or summary["n_families"] != EXPECTED_FAMILIES:
        raise ValueError("final latency summary cardinality differs from protocol")

    output = args.output_root / f"job_{scheduler['job_id']}"
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        atomic_write_jsonl(temporary / "records.jsonl", records)
        atomic_write_json(
            temporary / "task_index.json",
            {
                "entries": [
                    {
                        "manifest_path": path.relative_to(ROOT).as_posix(),
                        "manifest_sha256": sha256_file(path),
                        "scheduler_completion": entry["scheduler_completion"],
                        "task_id": index,
                    }
                    for index, (path, entry) in enumerate(zip(manifests, entries))
                ],
                "schema": "pcb-gnn.corpus-v4-paired-latency-task-index.v2",
            },
        )
        final = {
            "bindings": {
                **bindings,
                "accepted_set_sha256": args.expected_accepted_set_sha256,
                "expected_source_git_head": args.expected_source_git_head,
            },
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "hardware_class_sha256": next(iter(hardware_classes)),
                "scheduler": scheduler,
                "source_git_head": args.expected_source_git_head,
            },
            "schema": FINAL_SCHEMA,
            "scientific_scope": {
                "checkpoint_task_id": 12,
                "comparison": (
                    "sequential FastHenry-plus-FEM-R3P16 four-target workflow versus "
                    "warm-loaded batch-one in-memory raw-JSON-record-to-four-output GNN"
                ),
                "split_seed": 42,
            },
            "summary": summary,
        }
        atomic_write_json(temporary / "summary.json", final)
        analysis_files = {
            name: sha256_file(temporary / name)
            for name in ("records.jsonl", "summary.json", "task_index.json")
        }
        atomic_write_json(
            temporary / "ANALYSIS_MANIFEST.json",
            {
                "accepted_set": {
                    "path": args.accepted_set.resolve().relative_to(ROOT.resolve()).as_posix(),
                    "sha256": args.expected_accepted_set_sha256,
                },
                "files_sha256": analysis_files,
                "schema": ANALYSIS_MANIFEST_SCHEMA,
            },
        )
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(output.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
