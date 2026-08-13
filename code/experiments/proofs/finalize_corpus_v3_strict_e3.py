#!/usr/bin/env python3
"""Verify and aggregate a five-seed strict-E(3) corpus array."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (
    CODE / "core",
    CODE / "data",
    CODE / "models/gnn",
    CODE / "solvers",
    CODE / "experiments/proofs",
):
    sys.path.insert(0, str(directory))
from experiments_strict_egnn_ablation import hierarchical_paired_bootstrap  # noqa: E402


SUPPORTED_SERIES = ("corpus_v3", "corpus_v4")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--series", choices=SUPPORTED_SERIES, default="corpus_v3")
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--equivalence-margin-pct", type=float, default=2.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    schema = f"pcb-gnn.{args.series.replace('_', '-')}-strict-e3-final.v1"
    task_schema = f"pcb-gnn.{args.series.replace('_', '-')}-strict-e3-task.v1"
    if args.validate_only:
        print(json.dumps({"schema": schema, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit strict-E3 finalization through SLURM")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing strict-E3 finalization from a dirty tracked worktree")
    source = ROOT / "results" / args.series / "strict_e3/jobs" / f"job_{args.source_array_job_id}"
    tasks = []
    task_paths = []
    for task_id in range(5):
        path = source / f"task_{task_id:02d}.json"
        task = json.loads(path.read_text())
        if task.get("schema") != task_schema:
            raise ValueError(f"task {task_id} schema mismatch")
        provenance = task["provenance"]
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if int(provenance["slurm_array_task_id"]) != task_id:
            raise ValueError(f"task {task_id} array-task mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        tasks.append(task)
        task_paths.append(path)
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    split_maps = {
        json.dumps([task["train_layout_ids"], task["test_layout_ids"]]) for task in tasks
    }
    environment_maps = {json.dumps({
        "python": task["provenance"]["python"],
        "numpy": task["provenance"]["numpy"],
        "torch": task["provenance"]["torch"],
    }, sort_keys=True) for task in tasks}
    if any(len(values) != 1 for values in (
        source_maps, corpus_maps, split_maps, environment_maps,
    )):
        raise ValueError("strict-E3 tasks used mixed source, corpus, split, or environment")
    by_name = {
        name: [next(run for run in task["runs"] if run["model"] == name) for task in tasks]
        for name in ("invariant_matched", "strict_egnn", "invariant_same_width")
    }
    matched = hierarchical_paired_bootstrap(
        [np.asarray(run["design_log_error"]) for run in by_name["invariant_matched"]],
        [np.asarray(run["design_log_error"]) for run in by_name["strict_egnn"]],
        args.bootstrap_resamples, 20260813, args.equivalence_margin_pct,
    )
    same_width = hierarchical_paired_bootstrap(
        [np.asarray(run["design_log_error"]) for run in by_name["invariant_same_width"]],
        [np.asarray(run["design_log_error"]) for run in by_name["strict_egnn"]],
        args.bootstrap_resamples, 20260814, args.equivalence_margin_pct,
        baseline_label="same-width invariant baseline",
    )
    symmetry = {}
    for name, runs in by_name.items():
        symmetry[name] = {
            "max_output_relative_residual": max(
                run["symmetry_check"]["output_relative_residual"]["max"] for run in runs
            ),
            "max_coordinate_relative_residual": max(
                run["symmetry_check"]["coordinate_relative_residual"]["max"] for run in runs
            ),
            "all_pass": all(run["symmetry_check"]["strict_pass"] for run in runs),
        }
    result = {
        "schema": schema,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head, "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "corpus_artifacts_sha256": json.loads(next(iter(corpus_maps))),
            "source_software_environment": json.loads(next(iter(environment_maps))),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "protocol": {
            "n_initialization_seeds": 5,
            "split": "one fixed held-out turn-family split shared by all models/seeds",
            "equivalence_margin_pct": args.equivalence_margin_pct,
            "scope": "encoded-graph E(3); graph construction excluded",
        },
        "parameter_match": tasks[0]["protocol"]["parameter_match"],
        "matched_baseline_analysis": matched,
        "same_width_sensitivity": same_width,
        "symmetry": symmetry,
        "per_seed_metrics": {
            name: [{"seed": run["seed"], "metrics": run["metrics"]} for run in runs]
            for name, runs in by_name.items()
        },
    }
    output = ROOT / "results" / args.series / "strict_e3/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"results_{args.series}_strict_e3.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
