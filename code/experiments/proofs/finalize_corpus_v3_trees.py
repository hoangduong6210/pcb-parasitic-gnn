#!/usr/bin/env python3
"""Verify corpus-v3 tree tasks and compare them with finalized GNN accuracy."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "pcb-gnn.corpus-v3-trees-final.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")


def summarize(values: list[float]) -> dict[str, float]:
    array = np.asarray(values)
    return {"mean": float(array.mean()), "std": float(array.std(ddof=1)),
            "min": float(array.min()), "max": float(array.max())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--gnn-final", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit tree finalization through SLURM")
    if args.gnn_final is None:
        raise SystemExit("--gnn-final is required")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing tree finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v3/trees/jobs" / f"job_{args.source_array_job_id}"
    tasks = []
    for task_id in range(10):
        task = json.loads((source / f"task_{task_id:02d}.json").read_text())
        if task.get("schema") != "pcb-gnn.corpus-v3-trees-task.v1":
            raise ValueError(f"task {task_id} schema mismatch")
        if task["provenance"]["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} job mismatch")
        if task["provenance"]["git_head"] != head or task["provenance"]["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch")
        tasks.append(task)
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    if len(source_maps) != 1 or len(corpus_maps) != 1:
        raise ValueError("tree tasks used mixed source or corpus")
    gnn = json.loads(args.gnn_final.read_text())
    if gnn.get("schema") != "pcb-gnn.corpus-v3-accuracy-final.v1":
        raise ValueError("unexpected GNN accuracy schema")
    if gnn["provenance"]["corpus_artifacts_sha256"] != json.loads(next(iter(corpus_maps))):
        raise ValueError("GNN and tree results use different corpora")
    summaries = {}
    for kind in ("random", "family"):
        kind_tasks = [task for task in tasks if task["protocol"]["split_kind"] == kind]
        summaries[kind] = {}
        for model in ("random_forest", "extra_trees"):
            runs = [run for task in kind_tasks for run in task["runs"] if run["model"] == model]
            summaries[kind][model] = {
                "primary_macro_absolute_log_error": summarize([
                    run["primary_macro_absolute_log_error_mean"] for run in runs
                ]),
                "per_target": {
                    target: {
                        metric: summarize([run["per_target"][target][metric] for run in runs])
                        for metric in ("median_relative_error_pct", "r2")
                    }
                    for target in TARGETS
                },
            }
        summaries[kind]["gnn"] = gnn["summaries"][kind]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "gnn_final": args.gnn_final.resolve().as_posix(),
            "git_head": head, "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "corpus_artifacts_sha256": json.loads(next(iter(corpus_maps))),
        },
        "protocol": {
            "comparison": "same finalized corpus and identical random/family split registry",
            "tree_runs_per_kind_model": 25, "gnn_runs_per_kind": 25,
        },
        "summaries": summaries,
    }
    output = ROOT / "results/corpus_v3/trees/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_trees.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
