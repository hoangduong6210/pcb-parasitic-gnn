#!/usr/bin/env python3
"""Five-task strict encoded-graph E(3) ablation on finalized corpus v3."""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "models/gnn", CODE / "experiments/proofs"):
    sys.path.insert(0, str(directory))

from experiments_strict_egnn_ablation import (
    InvariantScalarMPNN, StrictScalarEGNN, SymmetryPreservingNorm,
    count_params, evaluate, matched_baseline_hidden, symmetry_check, train_model,
)
from v3_dataset import load_final_corpus, sha256, split_indices


SCHEMA = "pcb-gnn.corpus-v3-strict-e3-task.v1"
SEEDS = (40, 41, 42, 43, 44)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--strict-hidden", type=int, default=96)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    matched_hidden, parameter_match = matched_baseline_hidden(args.strict_hidden)
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "parameter_match": parameter_match}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing strict-E3 training outside a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing strict-E3 training from a dirty tracked worktree")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if not 0 <= task_id < 5:
        raise SystemExit("canonical strict-E3 array has tasks 0..4")
    seed = SEEDS[task_id]
    samples, corpus_summary = load_final_corpus(args.corpus)
    train, test = split_indices(samples, 42, "family")
    normalizer = SymmetryPreservingNorm(samples, train)
    work = [normalizer.transform(sample) for sample in samples]
    specifications = (
        ("invariant_matched", InvariantScalarMPNN(matched_hidden)),
        ("strict_egnn", StrictScalarEGNN(args.strict_hidden)),
        ("invariant_same_width", InvariantScalarMPNN(args.strict_hidden)),
    )
    runs = []
    for name, model in specifications:
        torch.manual_seed(seed)
        model, training_wall_s = train_model(model, work, train, seed, args.epochs, args.batch_size)
        metrics, predictions, design_log_error = evaluate(model, normalizer, work, samples, test)
        symmetry = symmetry_check(model, work, test, seed)
        if not symmetry["strict_pass"]:
            raise RuntimeError(f"encoded-graph E(3) check failed for {name}, seed {seed}")
        runs.append({
            "model": name, "seed": seed, "params": count_params(model),
            "n_train": len(train), "n_test": len(test), "training_wall_s": training_wall_s,
            "metrics": metrics, "predictions": predictions,
            "design_log_error": design_log_error.tolist(), "symmetry_check": symmetry,
        })
        print(
            f"seed={seed} model={name} MALE={metrics['primary_mean_absolute_log_error']:.6f} "
            f"macroMdRE={metrics['macro_median_relative_error_pct']:.3f}%",
            flush=True,
        )
    sources = [Path(__file__), CODE / "experiments/proofs/experiments_strict_egnn_ablation.py",
               CODE / "data/v3_dataset.py", CODE / "core/geometry_contract.py",
               CODE / "core/planar_to_graph.py"]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id, "hostname": socket.gethostname(),
            "platform": platform.platform(), "python": platform.python_version(),
            "numpy": np.__version__, "torch": torch.__version__,
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "git_dirty_paths": dirty,
            "arguments": {"corpus": args.corpus.resolve().as_posix(), "epochs": args.epochs,
                          "strict_hidden": args.strict_hidden, "batch_size": args.batch_size},
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        },
        "protocol": {
            "split": "fixed seed-42 held-out turn-count families",
            "split_seed": 42, "initialization_seed": seed,
            "parameter_match": parameter_match,
            "normalization": "train-only scalar statistics and one isotropic coordinate scale",
            "symmetry_scope": "strict E(3) on the encoded graph; axis-aligned graph construction excluded",
            "primary_metric": "per-design mean absolute log1p error across four targets",
        },
        "train_layout_ids": [samples[index]["layout_id"] for index in train],
        "test_layout_ids": [samples[index]["layout_id"] for index in test],
        "runs": runs,
    }
    output = ROOT / "results/corpus_v3/strict_e3/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
