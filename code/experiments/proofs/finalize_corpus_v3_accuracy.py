#!/usr/bin/env python3
"""Verify and aggregate all ten corpus-v3 accuracy array tasks."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "pcb-gnn.corpus-v3-accuracy-final.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")


def crossed_bootstrap(matrix: np.ndarray, resamples: int = 10_000) -> dict[str, Any]:
    rng = np.random.default_rng(20260813)
    draws = np.empty(resamples)
    for iteration in range(resamples):
        rows = rng.integers(0, matrix.shape[0], matrix.shape[0])
        columns = rng.integers(0, matrix.shape[1], matrix.shape[1])
        draws[iteration] = matrix[np.ix_(rows, columns)].mean()
    return {
        "mean_across_25_runs": float(matrix.mean()),
        "std_across_25_runs": float(matrix.std(ddof=1)),
        "min_across_25_runs": float(matrix.min()),
        "max_across_25_runs": float(matrix.max()),
        "crossed_split_init_bootstrap_mean_95_ci": [
            float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)),
        ],
        "matrix_rows_split_seeds_columns_init_seeds": matrix.tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit accuracy finalization through SLURM")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v3/accuracy/jobs" / f"job_{args.source_array_job_id}"
    tasks = []
    for task_id in range(10):
        path = source / f"task_{task_id:02d}.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        task = json.loads(path.read_text())
        if task.get("schema") != "pcb-gnn.corpus-v3-accuracy-task.v1":
            raise ValueError(f"task {task_id} schema mismatch")
        provenance = task["provenance"]
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        if len(task["runs"]) != 5:
            raise ValueError(f"task {task_id} does not contain five initialization runs")
        tasks.append(task)
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    if len(source_maps) != 1 or len(corpus_maps) != 1:
        raise ValueError("tasks used mixed source or corpus artifacts")

    summaries: dict[str, Any] = {}
    for kind in ("random", "family"):
        selected = sorted(
            (task for task in tasks if task["protocol"]["split_kind"] == kind),
            key=lambda task: task["protocol"]["split_seed"],
        )
        if len(selected) != 5:
            raise ValueError(f"expected five {kind} split tasks")
        kind_summary = {"primary": {}, "per_target": {}}
        primary = np.asarray([
            [run["primary_macro_absolute_log_error_mean"] for run in task["runs"]]
            for task in selected
        ])
        kind_summary["primary"] = crossed_bootstrap(primary)
        for target in TARGETS:
            kind_summary["per_target"][target] = {}
            for metric in ("median_relative_error_pct", "r2"):
                matrix = np.asarray([
                    [run["per_target"][target][metric] for run in task["runs"]]
                    for task in selected
                ])
                kind_summary["per_target"][target][metric] = crossed_bootstrap(matrix)
        summaries[kind] = kind_summary
    output = ROOT / "results/corpus_v3/accuracy/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head, "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "corpus_artifacts_sha256": json.loads(next(iter(corpus_maps))),
        },
        "protocol": {
            "n_runs": 50, "split_seeds": [40, 41, 42, 43, 44],
            "init_seeds": [40, 41, 42, 43, 44],
            "random_split_role": "in-distribution interpolation",
            "family_split_role": "held-out (n_primary,n_secondary) turn-count combinations",
            "interval_scope": "crossed split/init bootstrap on the evaluated corpus and node class",
        },
        "summaries": summaries,
        "task_records": [f"task_{task_id:02d}.json" for task_id in range(10)],
    }
    path = output / "results_corpus_v3_accuracy.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
