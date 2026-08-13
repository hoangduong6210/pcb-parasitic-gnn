#!/usr/bin/env python3
"""Verify and aggregate five-seed corpus-v3 ranking results."""
from __future__ import annotations

import argparse, json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "pcb-gnn.corpus-v3-ranking-final.v1"


def paired_bootstrap(pairwise: list[np.ndarray], pointwise: list[np.ndarray], resamples: int) -> dict:
    rng = np.random.default_rng(20260813); draws = np.empty(resamples)
    observed = np.mean([a.mean() - b.mean() for a, b in zip(pairwise, pointwise)])
    for draw in range(resamples):
        seeds = rng.integers(0, len(pairwise), len(pairwise)); values = []
        for seed in seeds:
            family = rng.integers(0, len(pairwise[seed]), len(pairwise[seed]))
            values.append(float(pairwise[seed][family].mean() - pointwise[seed][family].mean()))
        draws[draw] = np.mean(values)
    return {"definition": "pairwise minus pointwise in 1-Spearman; negative favors pairwise",
            "observed_delta": float(observed),
            "paired_seed_family_bootstrap_95_ci": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
            "resamples": resamples}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--bootstrap-resamples", type=int, default=10000)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"})); return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit ranking finalization through SLURM")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    if dirty: raise SystemExit("Refusing ranking finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v3/ranking/jobs" / f"job_{args.source_array_job_id}"
    tasks = [json.loads((source / f"task_{task:02d}.json").read_text()) for task in range(5)]
    for index, task in enumerate(tasks):
        if task.get("schema") != "pcb-gnn.corpus-v3-ranking-task.v1": raise ValueError(f"task {index} schema")
        p = task["provenance"]
        if p["slurm_array_job_id"] != args.source_array_job_id or p["git_head"] != head or p["git_dirty_paths"]:
            raise ValueError(f"task {index} provenance")
    maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    data = {json.dumps(task["provenance"]["lateral_artifacts_sha256"], sort_keys=True) for task in tasks}
    splits = {json.dumps([task["train_family_ids"], task["test_family_ids"]]) for task in tasks}
    if len(maps) != 1 or len(data) != 1 or len(splits) != 1: raise ValueError("mixed source/data/split")
    by_model = {name: [next(run for run in task["runs"] if run["model"] == name) for task in tasks]
                for name in ("pairwise", "pointwise")}
    analysis = paired_bootstrap([np.asarray(run["family_loss"]) for run in by_model["pairwise"]],
                                [np.asarray(run["family_loss"]) for run in by_model["pointwise"]],
                                args.bootstrap_resamples)
    summary = {name: {metric: {"mean": float(np.mean([run[metric] for run in runs])),
                                      "std": float(np.std([run[metric] for run in runs], ddof=1))}
                      for metric in ("spearman_mean", "spearman_median", "selection_regret_median_pct", "selection_regret_mean_pct")}
               for name, runs in by_model.items()}
    result = {"schema": SCHEMA, "provenance": {"created_utc": datetime.now(timezone.utc).isoformat(),
              "slurm_job_id": os.environ["SLURM_JOB_ID"], "source_array_job_id": args.source_array_job_id,
              "git_head": head, "git_dirty_paths": dirty, "source_file_sha256": json.loads(next(iter(maps))),
              "lateral_artifacts_sha256": json.loads(next(iter(data)))},
              "protocol": {"n_initialization_seeds": 5, "n_test_families": 21,
                           "interval_scope": "paired seed/family bootstrap on the fixed held-out families"},
              "summary": summary, "paired_analysis": analysis}
    output = ROOT / "results/corpus_v3/ranking/final" / f"job_{os.environ['SLURM_JOB_ID']}"; output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_ranking.json"; path.write_text(json.dumps(result, indent=2) + "\n"); print(path.relative_to(ROOT))


if __name__ == "__main__": main()
