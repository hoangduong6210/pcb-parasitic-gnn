#!/usr/bin/env python3
"""SLURM-array accuracy study on a finalized geometry-valid v3 corpus."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "models/gnn"):
    sys.path.insert(0, str(directory))

from gnn_baseline import PCBParasiticGNN, collate
from v3_dataset import load_final_corpus, sha256, split_indices


SCHEMA = "pcb-gnn.corpus-v3-accuracy-task.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
SPLIT_SEEDS = (40, 41, 42, 43, 44)
INIT_SEEDS = (40, 41, 42, 43, 44)


class TrainOnlyNorm:
    def __init__(self, samples: list[dict[str, Any]], train: list[int]):
        targets = np.stack([samples[index]["y"] for index in train])
        logged = np.log1p(np.maximum(targets, 0.0))
        self.ym, self.ys = logged.mean(0), logged.std(0) + 1e-8
        nodes = np.concatenate([samples[index]["node_feat"] for index in train], axis=0)
        edges = np.concatenate([samples[index]["edge_feat"] for index in train], axis=0)
        self.nfm, self.nfs = nodes.mean(0), nodes.std(0) + 1e-6
        self.efm, self.efs = edges.mean(0), edges.std(0) + 1e-6

    def sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        return {
            "node_feat": ((sample["node_feat"] - self.nfm) / self.nfs).astype(np.float32),
            "edge_feat": ((sample["edge_feat"] - self.efm) / self.efs).astype(np.float32),
            "edge_index": sample["edge_index"], "edge_dim": 7,
            "y": ((np.log1p(np.maximum(sample["y"], 0.0)) - self.ym) / self.ys).astype(np.float32),
        }

    def inverse(self, value: np.ndarray) -> np.ndarray:
        return np.expm1(value * self.ys + self.ym)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def train_one(
    samples: list[dict[str, Any]], train: list[int], test: list[int],
    split_kind: str, split_seed: int, init_seed: int, epochs: int,
) -> tuple[PCBParasiticGNN, TrainOnlyNorm, dict[str, Any]]:
    torch.manual_seed(init_seed)
    np.random.seed(init_seed)
    torch.use_deterministic_algorithms(True)
    normalizer = TrainOnlyNorm(samples, train)
    work = [normalizer.sample(sample) for sample in samples]
    model = PCBParasiticGNN(node_dim=9, edge_dim=7, hidden=96, n_layers=4, n_targets=4)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_fn = nn.SmoothL1Loss()
    rng = np.random.default_rng(init_seed)
    started = time.perf_counter()
    for _ in range(epochs):
        model.train()
        order = np.asarray(train, dtype=int).copy()
        rng.shuffle(order)
        for offset in range(0, len(order), 32):
            batch = collate([work[index] for index in order[offset:offset + 32]])
            optimizer.zero_grad()
            loss_fn(model(batch), batch.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        scheduler.step()
    model.eval()
    predictions = []
    references = []
    with torch.no_grad():
        for index in test:
            predictions.append(normalizer.inverse(model(collate([work[index]])).numpy()[0]))
            references.append(samples[index]["y"])
    prediction = np.asarray(predictions, dtype=np.float64)
    reference = np.asarray(references, dtype=np.float64)
    per_target = {}
    for column, target in enumerate(TARGETS):
        residual = prediction[:, column] - reference[:, column]
        relative = np.abs(residual) / np.maximum(np.abs(reference[:, column]), 1e-9) * 100.0
        denominator = np.sum((reference[:, column] - reference[:, column].mean()) ** 2)
        per_target[target] = {
            "r2": float(1.0 - np.sum(residual ** 2) / max(denominator, 1e-12)),
            "median_relative_error_pct": float(np.median(relative)),
            "mean_relative_error_pct": float(np.mean(relative)),
            "p95_relative_error_pct": float(np.percentile(relative, 95)),
        }
    primary = np.mean(np.abs(np.log1p(prediction) - np.log1p(reference)), axis=1)
    return model, normalizer, {
        "split_kind": split_kind, "split_seed": split_seed, "init_seed": init_seed,
        "n_train": len(train), "n_test": len(test),
        "train_layout_ids": [samples[index]["layout_id"] for index in train],
        "test_layout_ids": [samples[index]["layout_id"] for index in test],
        "test_families": [list(family) for family in sorted({
            tuple(samples[index]["family"]) for index in test
        })],
        "training_wall_s": time.perf_counter() - started,
        "primary_macro_absolute_log_error_mean": float(primary.mean()),
        "per_target": per_target,
        "predictions": prediction.tolist(), "references": reference.tolist(),
    }


def save_bundle(
    output: Path, model: PCBParasiticGNN, norm: TrainOnlyNorm,
    run: dict[str, Any], samples: list[dict[str, Any]], test: list[int],
) -> dict[str, str]:
    bundle = output / "inference_bundle"
    bundle.mkdir(exist_ok=True)
    arrays = {
        "norm_ym": norm.ym, "norm_ys": norm.ys, "norm_nfm": norm.nfm,
        "norm_nfs": norm.nfs, "norm_efm": norm.efm, "norm_efs": norm.efs,
    }
    arrays.update({f"state__{name}": tensor.detach().numpy() for name, tensor in model.state_dict().items()})
    weights = bundle / "weights_and_norm.npz"
    np.savez_compressed(weights, **arrays)
    examples = test[:5]
    (bundle / "example_layouts.jsonl").write_text("".join(
        json.dumps({"layout_id": samples[index]["layout_id"], "layout": samples[index]["layout"]}, sort_keys=True) + "\n"
        for index in examples
    ))
    prediction_by_id = dict(zip(run["test_layout_ids"], run["predictions"]))
    expected = bundle / "expected_predictions.json"
    expected.write_text(json.dumps([
        {"layout_id": samples[index]["layout_id"], "prediction": prediction_by_id[samples[index]["layout_id"]]}
        for index in examples
    ], indent=2) + "\n")
    metadata = bundle / "metadata.json"
    metadata.write_text(json.dumps({
        "schema": "pcb-gnn.safe-inference-bundle.v2", "format": "NumPy; allow_pickle=False",
        "targets": TARGETS, "split_kind": run["split_kind"],
        "split_seed": run["split_seed"], "init_seed": run["init_seed"],
        "architecture": {
            "node_dim": 9, "edge_dim": 7, "hidden": 96,
            "n_layers": 4, "n_targets": 4,
        },
        "weights_sha256": sha256(weights),
    }, indent=2) + "\n")
    return {path.relative_to(output).as_posix(): sha256(path) for path in (weights, expected, metadata, bundle / "example_layouts.jsonl")}


def main() -> None:
    args = parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 10}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing v3 training outside a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing training from a dirty tracked worktree")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if not 0 <= task_id < 10:
        raise SystemExit("canonical accuracy array has tasks 0..9")
    split_kind = "random" if task_id < 5 else "family"
    split_seed = SPLIT_SEEDS[task_id % 5]
    samples, corpus_summary = load_final_corpus(args.corpus)
    train, test = split_indices(samples, split_seed, split_kind)
    output = ROOT / "results/corpus_v3/accuracy/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    runs = []
    bundle_artifacts = None
    for init_seed in INIT_SEEDS:
        model, norm, run = train_one(samples, train, test, split_kind, split_seed, init_seed, args.epochs)
        runs.append(run)
        print(
            f"kind={split_kind} split={split_seed} init={init_seed} "
            f"Cps={run['per_target']['Cps_pF']['median_relative_error_pct']:.3f}% "
            f"M={run['per_target']['L_mut_nH']['median_relative_error_pct']:.3f}%",
            flush=True,
        )
        if split_kind == "random" and split_seed == 42 and init_seed == 42:
            bundle_artifacts = save_bundle(output, model, norm, run, samples, test)
    source_paths = [Path(__file__), CODE / "data/v3_dataset.py", CODE / "core/geometry_contract.py",
                    CODE / "core/planar_to_graph.py", CODE / "models/gnn/gnn_baseline.py"]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id, "hostname": socket.gethostname(),
            "platform": platform.platform(), "python": platform.python_version(),
            "numpy": np.__version__, "torch": torch.__version__, "scipy": package_version("scipy"),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "git_dirty_paths": dirty,
            "arguments": {"corpus": args.corpus.resolve().as_posix(), "epochs": args.epochs},
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in source_paths},
        },
        "protocol": {
            "split_kind": split_kind, "split_seed": split_seed, "init_seeds": INIT_SEEDS,
            "normalization": "node, edge, and target statistics fitted on training designs only",
            "primary_metric": "per-design mean absolute log(1+y) error across four targets",
        },
        "runs": runs, "safe_inference_bundle": bundle_artifacts,
    }
    path = output / f"task_{task_id:02d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
