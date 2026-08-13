#!/usr/bin/env python3
"""SLURM tree baselines on the exact corpus-v3 split registry."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data"):
    sys.path.insert(0, str(directory))

from v3_dataset import load_final_corpus, sha256, split_indices


SCHEMA = "pcb-gnn.corpus-v3-trees-task.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
SEEDS = (40, 41, 42, 43, 44)


def pooled(nodes: np.ndarray, edges: np.ndarray) -> np.ndarray:
    node_sum = nodes.sum(0)
    node_features = np.concatenate([
        nodes.mean(0), nodes.max(0), np.sign(node_sum) * np.log1p(np.abs(node_sum)),
    ])
    if edges.size:
        edge_sum = edges.sum(0)
        edge_features = np.concatenate([
            edges.mean(0), edges.max(0), np.sign(edge_sum) * np.log1p(np.abs(edge_sum)),
        ])
    else:
        edge_features = np.zeros(21, dtype=np.float32)
    return np.concatenate([node_features, edge_features]).astype(np.float32)


def metrics(prediction: np.ndarray, reference: np.ndarray) -> dict:
    result = {}
    for column, target in enumerate(TARGETS):
        residual = prediction[:, column] - reference[:, column]
        relative = np.abs(residual) / np.maximum(np.abs(reference[:, column]), 1e-9) * 100.0
        denominator = np.sum((reference[:, column] - reference[:, column].mean()) ** 2)
        result[target] = {
            "r2": float(1.0 - np.sum(residual ** 2) / max(denominator, 1e-12)),
            "median_relative_error_pct": float(np.median(relative)),
            "mean_relative_error_pct": float(np.mean(relative)),
        }
    primary = np.mean(np.abs(np.log1p(prediction) - np.log1p(reference)), axis=1)
    return {"primary_macro_absolute_log_error_mean": float(primary.mean()), "per_target": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 10}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing tree fitting outside a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing tree fitting from a dirty tracked worktree")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if not 0 <= task_id < 10:
        raise SystemExit("canonical tree array has tasks 0..9")
    split_kind = "random" if task_id < 5 else "family"
    split_seed = SEEDS[task_id % 5]
    samples, corpus_summary = load_final_corpus(args.corpus)
    train, test = split_indices(samples, split_seed, split_kind)
    node_train = np.concatenate([samples[index]["node_feat"] for index in train], axis=0)
    edge_train = np.concatenate([samples[index]["edge_feat"] for index in train], axis=0)
    node_mean, node_std = node_train.mean(0), node_train.std(0) + 1e-6
    edge_mean, edge_std = edge_train.mean(0), edge_train.std(0) + 1e-6
    features = np.stack([
        pooled((sample["node_feat"] - node_mean) / node_std,
               (sample["edge_feat"] - edge_mean) / edge_std)
        for sample in samples
    ])
    targets = np.stack([sample["y"] for sample in samples]).astype(np.float64)
    logged_targets = np.log1p(targets)
    runs = []
    from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
    for seed in SEEDS:
        models = {
            "random_forest": RandomForestRegressor(
                n_estimators=500, max_depth=16, min_samples_leaf=2,
                random_state=seed, n_jobs=-1,
            ),
            "extra_trees": ExtraTreesRegressor(
                n_estimators=500, max_depth=16, min_samples_leaf=2,
                random_state=seed, n_jobs=-1,
            ),
        }
        for name, model in models.items():
            model.fit(features[train], logged_targets[train])
            prediction = np.expm1(model.predict(features[test]))
            reference = targets[test]
            run_metrics = metrics(prediction, reference)
            runs.append({
                "model": name, "seed": seed, "n_train": len(train), "n_test": len(test),
                **run_metrics, "predictions": prediction.tolist(), "references": reference.tolist(),
            })
            print(
                f"kind={split_kind} split={split_seed} seed={seed} model={name} "
                f"primary={run_metrics['primary_macro_absolute_log_error_mean']:.6f}", flush=True,
            )
    sources = [Path(__file__), CODE / "data/v3_dataset.py", CODE / "core/geometry_contract.py",
               CODE / "core/planar_to_graph.py"]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id, "hostname": socket.gethostname(),
            "platform": platform.platform(), "python": platform.python_version(),
            "numpy": np.__version__, "scikit_learn": importlib.metadata.version("scikit-learn"),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        },
        "protocol": {
            "split_kind": split_kind, "split_seed": split_seed, "fit_seeds": SEEDS,
            "features": "train-standardized node and edge mean, max, signed-log-sum pools",
            "targets": "log1p four-target vector; inverse transformed for metrics",
        },
        "train_layout_ids": [samples[index]["layout_id"] for index in train],
        "test_layout_ids": [samples[index]["layout_id"] for index in test],
        "runs": runs,
    }
    output = ROOT / "results/corpus_v3/trees/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
