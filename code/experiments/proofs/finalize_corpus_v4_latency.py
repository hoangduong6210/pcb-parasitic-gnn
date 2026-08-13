#!/usr/bin/env python3
"""Verify and aggregate all 100 paired corpus-v4 latency tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "pcb-gnn.corpus-v4-paired-latency-final.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bootstrap_median(values: np.ndarray, resamples: int) -> list[float]:
    rng = np.random.default_rng(20260813)
    draws = np.empty(resamples)
    for index in range(resamples):
        draws[index] = np.median(rng.choice(values, size=len(values), replace=True))
    return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--n-tasks", type=int, default=100)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit corpus-v4 latency finalization through SLURM")
    if args.n_tasks != 100:
        raise ValueError("canonical paired-latency finalizer requires 100 tasks")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing latency finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v4/latency/jobs" / f"job_{args.source_array_job_id}"
    task_paths = [source / f"task_{task_id:03d}.json" for task_id in range(args.n_tasks)]
    tasks = [json.loads(path.read_text()) for path in task_paths]
    records = []
    for task_id, task in enumerate(tasks):
        provenance = task["provenance"]
        if task.get("schema") != TASK_SCHEMA:
            raise ValueError(f"task {task_id} schema mismatch")
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if int(provenance["slurm_array_task_id"]) != task_id:
            raise ValueError(f"task {task_id} array-task mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        if task["protocol"]["fem_refine"] != 2 or task["protocol"]["pad_mm"] != 12.0:
            raise ValueError(f"task {task_id} FEM protocol mismatch")
        records.append(task["record"])
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    bundle_maps = {json.dumps(task["provenance"]["bundle_sha256"], sort_keys=True) for task in tasks}
    environment_maps = {json.dumps({
        "python": task["provenance"]["python"],
        "package_versions": task["provenance"]["package_versions"],
    }, sort_keys=True) for task in tasks}
    selection_hashes = {task["protocol"]["selected_layout_ids_sha256"] for task in tasks}
    if any(len(values) != 1 for values in (
        source_maps, corpus_maps, bundle_maps, environment_maps, selection_hashes,
    )):
        raise ValueError("latency tasks used mixed source, inputs, environment, or selection")
    if len({record["layout_id"] for record in records}) != args.n_tasks:
        raise ValueError("latency task layout IDs are not unique")
    speedups = np.asarray([record["speedup_paired_four_target_x"] for record in records])
    solver_ms = np.asarray([record["solver_ms"]["paired"] for record in records])
    inference_ms = np.asarray([
        record["inference_raw_layout_ms"]["median"] for record in records
    ])
    output = ROOT / "results/corpus_v4/latency/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head,
            "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "corpus_artifacts_sha256": json.loads(next(iter(corpus_maps))),
            "bundle_sha256": json.loads(next(iter(bundle_maps))),
            "source_software_environment": json.loads(next(iter(environment_maps))),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "protocol": {
            "comparison": "paired FastHenry plus refine-2/pad-12-mm electrostatic FEM for all four targets versus raw-layout graph construction plus batch-one GNN",
            "n_designs": args.n_tasks,
            "selection_seed": 20260813,
            "selected_layout_ids_sha256": next(iter(selection_hashes)),
            "inference_repetitions_per_design": 30,
            "model_load_excluded_from_per_design_inference": True,
            "interval_scope": "design bootstrap on the evaluated nodes and fixed checkpoint",
        },
        "summary": {
            "paired_solver_median_ms": float(np.median(solver_ms)),
            "raw_layout_gnn_median_ms": float(np.median(inference_ms)),
            "median_paired_speedup_x": float(np.median(speedups)),
            "median_paired_speedup_design_bootstrap_95_ci": bootstrap_median(
                speedups, args.bootstrap_resamples
            ),
        },
        "records": records,
    }
    path = output / "results_corpus_v4_latency.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
