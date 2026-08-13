#!/usr/bin/env python3
"""Verify and aggregate the five-seed corpus-v3 strict-E(3) array."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from experiments_strict_egnn_ablation import hierarchical_paired_bootstrap  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v3-strict-e3-final.v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--equivalence-margin-pct", type=float, default=2.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
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
    source = ROOT / "results/corpus_v3/strict_e3/jobs" / f"job_{args.source_array_job_id}"
    tasks = []
    for task_id in range(5):
        path = source / f"task_{task_id:02d}.json"
        task = json.loads(path.read_text())
        if task.get("schema") != "pcb-gnn.corpus-v3-strict-e3-task.v1":
            raise ValueError(f"task {task_id} schema mismatch")
        provenance = task["provenance"]
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        tasks.append(task)
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    split_maps = {
        json.dumps([task["train_layout_ids"], task["test_layout_ids"]]) for task in tasks
    }
    if len(source_maps) != 1 or len(corpus_maps) != 1 or len(split_maps) != 1:
        raise ValueError("strict-E3 tasks used mixed source, corpus, or split")
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
    output = ROOT / "results/corpus_v3/strict_e3/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_strict_e3.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
