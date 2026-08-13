#!/usr/bin/env python3
"""Crossed split/initialization study for four-target field accuracy.

This is a training-heavy protocol and refuses to run outside SLURM.  It consumes
the immutable per-layout target record produced by the strict-E(3) proof, then
reconstructs each seeded layout without invoking a field solver.  Five data
splits crossed with five initialization/training-order seeds separate the two
major sources of retraining variability.
"""
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
for _directory in (
    CODE / "experiments/proofs", CODE / "models/gnn", CODE / "core",
    CODE / "solvers", CODE / "data",
):
    sys.path.insert(0, str(_directory))

from experiments_claim_proof import TrainOnlyNorm, make_sample
from experiments_v5 import big_layout, mk
from gnn_baseline import PCBParasiticGNN, collate
from pipeline import TARGETS


SCHEMA = "pcb-gnn.multisplit-accuracy.v1"
DEFAULT_TARGETS = (
    ROOT / "results/proof_updates/jobs/strict_e3/job_51174496/field_grade_targets.jsonl"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--split-seeds", type=int, nargs="+", default=[40, 41, 42, 43, 44])
    parser.add_argument("--init-seeds", type=int, nargs="+", default=[40, 41, 42, 43, 44])
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--bundle-split-seed", type=int, default=42)
    parser.add_argument("--bundle-init-seed", type=int, default=42)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def load_samples(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    attempted = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    records = [record for record in attempted if record.get("valid") and record.get("target") is not None]
    layouts: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    for record in records:
        layout = big_layout(42 + int(record["layout_id"]), 36)
        target = record["target"]
        samples.append(make_sample(
            layout,
            float(target[0]),
            {"L_pri_nH": target[1], "L_sec_nH": target[2], "L_mut_nH": target[3]},
        ))
        layouts.append(layout)
    if len(samples) != 332:
        raise ValueError(
            f"Expected 332 valid field-grade samples, found {len(samples)} "
            f"among {len(attempted)} attempted records"
        )
    return records, layouts, samples


def split_indices(n_samples: int, seed: int) -> tuple[list[int], list[int]]:
    permutation = np.random.RandomState(seed).permutation(n_samples)
    cut = int(0.8 * n_samples)
    return permutation[:cut].astype(int).tolist(), permutation[cut:].astype(int).tolist()


def train_once(
    samples: list[dict[str, Any]], split_seed: int, init_seed: int, epochs: int
) -> tuple[PCBParasiticGNN, TrainOnlyNorm, dict[str, Any]]:
    train_idx, test_idx = split_indices(len(samples), split_seed)
    torch.manual_seed(init_seed)
    torch.use_deterministic_algorithms(True)
    normalizer = TrainOnlyNorm(samples, train_idx)
    work = [mk(sample, normalizer) for sample in samples]
    model = PCBParasiticGNN(
        node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
        hidden=96, n_layers=4, n_targets=4,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_fn = nn.SmoothL1Loss()
    order_rng = np.random.RandomState(init_seed)
    started = time.perf_counter()
    for _ in range(epochs):
        model.train()
        order = np.asarray(train_idx, dtype=int).copy()
        order_rng.shuffle(order)
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
        for index in test_idx:
            standardized = model(collate([work[index]])).numpy()[0]
            predictions.append(normalizer.inv(standardized))
            references.append(samples[index]["y"])
    prediction = np.stack(predictions).astype(np.float64)
    reference = np.stack(references).astype(np.float64)
    metrics: dict[str, Any] = {}
    for column, target in enumerate(TARGETS):
        residual = prediction[:, column] - reference[:, column]
        relative = np.abs(residual) / (np.abs(reference[:, column]) + 1e-9) * 100.0
        denominator = np.sum((reference[:, column] - reference[:, column].mean()) ** 2) + 1e-12
        metrics[target] = {
            "r2": float(1.0 - np.sum(residual ** 2) / denominator),
            "median_relative_error_pct": float(np.median(relative)),
            "mean_relative_error_pct": float(np.mean(relative)),
            "p95_relative_error_pct": float(np.percentile(relative, 95)),
        }
    macro_log_error = np.mean(
        np.abs(np.log1p(np.maximum(prediction, 0.0)) - np.log1p(reference)), axis=1
    )
    result = {
        "split_seed": split_seed,
        "init_seed": init_seed,
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "train_indices": train_idx,
        "test_indices": test_idx,
        "training_wall_s": time.perf_counter() - started,
        "primary_macro_log_error_mean": float(macro_log_error.mean()),
        "per_target": metrics,
        "predictions": prediction.tolist(),
        "references": reference.tolist(),
    }
    return model, normalizer, result


def crossed_bootstrap(
    runs: list[dict[str, Any]], split_seeds: list[int], init_seeds: list[int],
    target: str, metric: str, resamples: int,
) -> dict[str, Any]:
    matrix = np.empty((len(split_seeds), len(init_seeds)), dtype=np.float64)
    lookup = {(run["split_seed"], run["init_seed"]): run for run in runs}
    for row, split_seed in enumerate(split_seeds):
        for column, init_seed in enumerate(init_seeds):
            matrix[row, column] = lookup[(split_seed, init_seed)]["per_target"][target][metric]
    rng = np.random.default_rng(20260812)
    draws = np.empty(resamples, dtype=np.float64)
    for iteration in range(resamples):
        rows = rng.integers(0, len(split_seeds), len(split_seeds))
        columns = rng.integers(0, len(init_seeds), len(init_seeds))
        draws[iteration] = matrix[np.ix_(rows, columns)].mean()
    return {
        "mean_across_25_runs": float(matrix.mean()),
        "std_across_25_runs": float(matrix.std(ddof=1)),
        "min_across_25_runs": float(matrix.min()),
        "max_across_25_runs": float(matrix.max()),
        "crossed_bootstrap_mean_95_ci": [
            float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))
        ],
        "matrix_rows_split_seeds_columns_init_seeds": matrix.tolist(),
    }


def save_safe_bundle(
    output_dir: Path, model: PCBParasiticGNN, normalizer: TrainOnlyNorm,
    run: dict[str, Any], records: list[dict[str, Any]], layouts: list[dict[str, Any]],
) -> dict[str, Any]:
    bundle = output_dir / "inference_bundle_seed42"
    bundle.mkdir(exist_ok=True)
    arrays: dict[str, np.ndarray] = {
        "norm_ym": np.asarray(normalizer.ym), "norm_ys": np.asarray(normalizer.ys),
        "norm_nfm": np.asarray(normalizer.nfm), "norm_nfs": np.asarray(normalizer.nfs),
        "norm_efm": np.asarray(normalizer.efm), "norm_efs": np.asarray(normalizer.efs),
    }
    for name, tensor in model.state_dict().items():
        arrays[f"state__{name}"] = tensor.detach().cpu().numpy()
    weight_path = bundle / "weights_and_norm.npz"
    np.savez_compressed(weight_path, **arrays)

    example_positions = run["test_indices"][:5]
    with (bundle / "example_layouts.jsonl").open("w") as handle:
        for position in example_positions:
            handle.write(json.dumps({
                "layout_id": records[position]["layout_id"], "layout": layouts[position]
            }, sort_keys=True) + "\n")
    position_to_prediction = {
        position: prediction for position, prediction in zip(run["test_indices"], run["predictions"])
    }
    expected = [
        {"layout_id": records[position]["layout_id"], "prediction": position_to_prediction[position]}
        for position in example_positions
    ]
    (bundle / "expected_predictions.json").write_text(json.dumps(expected, indent=2) + "\n")
    metadata = {
        "schema": "pcb-gnn.safe-inference-bundle.v1",
        "format": "numeric NumPy arrays; load with allow_pickle=False",
        "targets": TARGETS,
        "architecture": {"node_dim": 9, "edge_dim": 7, "hidden": 96, "n_layers": 4, "n_targets": 4},
        "split_seed": run["split_seed"], "init_seed": run["init_seed"],
        "train_indices": run["train_indices"], "test_indices": run["test_indices"],
        "weights_sha256": sha256(weight_path),
    }
    metadata_path = bundle / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    artifact_paths = [
        weight_path, metadata_path, bundle / "example_layouts.jsonl",
        bundle / "expected_predictions.json",
    ]
    return {
        path.relative_to(output_dir).as_posix(): sha256(path) for path in artifact_paths
    }


def main() -> None:
    args = parse_args()
    args.targets = args.targets.resolve()
    if args.validate_only:
        if len(set(args.split_seeds)) != len(args.split_seeds):
            raise SystemExit("split seeds must be unique")
        if len(set(args.init_seeds)) != len(args.init_seeds):
            raise SystemExit("initialization seeds must be unique")
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Refusing training outside SLURM; submit submit_multisplit_accuracy.sh")

    records, layouts, samples = load_samples(args.targets)
    output_dir = ROOT / "results/proof_updates/jobs/multisplit_accuracy" / f"job_{os.environ['SLURM_JOB_ID']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    bundle_payload = None
    for split_seed in args.split_seeds:
        for init_seed in args.init_seeds:
            model, normalizer, run = train_once(samples, split_seed, init_seed, args.epochs)
            runs.append(run)
            print(
                f"split={split_seed} init={init_seed} "
                f"Cps={run['per_target']['Cps_pF']['median_relative_error_pct']:.3f}% "
                f"M={run['per_target']['L_mut_nH']['median_relative_error_pct']:.3f}%",
                flush=True,
            )
            if split_seed == args.bundle_split_seed and init_seed == args.bundle_init_seed:
                bundle_payload = model, normalizer, run

    summaries = {
        target: {
            metric: crossed_bootstrap(
                runs, args.split_seeds, args.init_seeds, target, metric,
                args.bootstrap_resamples,
            )
            for metric in ("median_relative_error_pct", "r2")
        }
        for target in TARGETS
    }
    code_inputs = [
        Path(__file__), ROOT / "code/experiments/proofs/experiments_claim_proof.py",
        ROOT / "code/core/experiments_v5.py", ROOT / "code/data/gen_corpus_fh.py",
        ROOT / "code/core/planar_to_graph.py", ROOT / "code/models/gnn/gnn_baseline.py",
    ]
    reconstructed_layouts_sha256 = hashlib.sha256(
        json.dumps(layouts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if bundle_payload is None:
        raise RuntimeError("Requested safe-bundle seed pair was not evaluated")
    bundle_artifacts = save_safe_bundle(output_dir, *bundle_payload, records, layouts)
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__,
            "scipy": package_version("scipy"),
            "torch_num_threads": torch.get_num_threads(),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "git_head": git_output("rev-parse", "HEAD"),
            "git_dirty_paths": git_output("status", "--short", "--untracked-files=no").splitlines(),
            "arguments": {**vars(args), "targets": args.targets.relative_to(ROOT).as_posix()},
            "inputs": {args.targets.relative_to(ROOT).as_posix(): sha256(args.targets)},
            "file_sha256": {
                path.relative_to(ROOT).as_posix(): sha256(path) for path in code_inputs
            },
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        },
        "protocol": {
            "design": "five split seeds crossed with five initialization/training-order seeds",
            "normalization": "node, edge, and target statistics fitted on each training split only",
            "bootstrap": "split rows and initialization columns resampled independently",
            "layout_reconstruction": "big_layout(seed=42+layout_id, max_per_net=36)",
            "reconstructed_layouts_sha256": reconstructed_layouts_sha256,
            "n_samples": len(samples), "n_runs": len(runs),
        },
        "summaries": summaries,
        "runs": runs,
        "safe_inference_bundle": {
            "arm": {"split_seed": args.bundle_split_seed, "init_seed": args.bundle_init_seed},
            "artifacts_sha256": bundle_artifacts,
        },
    }
    result_path = output_dir / "results_multisplit_accuracy.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(result_path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
