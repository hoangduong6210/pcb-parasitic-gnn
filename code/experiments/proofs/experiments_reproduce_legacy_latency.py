#!/usr/bin/env python3
"""Reproduce the legacy 1.16845 ms pre-collated batch timing on SLURM."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from gnn_baseline import PCBParasiticGNN, collate
from pipeline import build_samples, load_dataset


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
DATA_ROOT = Path(os.environ.get("PCB_GNN_DATA_ROOT", ROOT / "datasets")).resolve()
CHECKPOINT_ROOT = Path(os.environ.get("PCB_GNN_CHECKPOINT_ROOT", ROOT / "results")).resolve()
SCHEMA = "research13.legacy-latency-reproduction.v1"
HISTORICAL_MS_PER_DESIGN = 1.16845


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--legacy-repeats", type=int, default=20)
    parser.add_argument("--extended-repeats", type=int, default=100)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_key(path: Path) -> str:
    """Return a portable provenance label without exposing checkout paths."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return "dataset/" + resolved.relative_to(DATA_ROOT).as_posix()
        except ValueError:
            return "external/" + resolved.name


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def summary(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p05": float(np.percentile(array, 5)),
        "p95": float(np.percentile(array, 95)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def cpu_model() -> str:
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def normalize_samples(
    samples: list[dict[str, Any]], checkpoint: dict[str, Any]
) -> None:
    node_mean, node_std = [np.asarray(part, dtype=np.float32) for part in checkpoint["node_norm"]]
    edge_mean, edge_std = [np.asarray(part, dtype=np.float32) for part in checkpoint["edge_norm"]]
    y_mean, y_std = [np.asarray(part, dtype=np.float32) for part in checkpoint["y_log_norm"]]
    for sample in samples:
        sample["node_feat"] = ((sample["node_feat"] - node_mean) / node_std).astype(np.float32)
        if sample["edge_feat"].size:
            sample["edge_feat"] = ((sample["edge_feat"] - edge_mean) / edge_std).astype(np.float32)
        logged = np.sign(sample["y"]) * np.log1p(np.abs(sample["y"]))
        sample["y"] = ((logged - y_mean) / y_std).astype(np.float32)


def time_batch(model: PCBParasiticGNN, batch: Any, repeats: int) -> list[float]:
    elapsed_ms: list[float] = []
    with torch.no_grad():
        for _ in range(repeats):
            started = time.perf_counter()
            model(batch)
            elapsed_ms.append((time.perf_counter() - started) * 1000)
    return elapsed_ms


def main() -> None:
    args = parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    job_id = os.environ.get("SLURM_JOB_ID")
    if not job_id:
        raise SystemExit("Submit submit_reproduce_legacy_latency.sh; do not time on login")

    dataset = DATA_ROOT / "synth_v1"
    checkpoint_path = CHECKPOINT_ROOT / "run_v1" / "gnn_checkpoint.pt"
    historical_path = ROOT / "results" / "run_v1" / "results.json"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    layouts, labels, _ = load_dataset(dataset)
    samples = build_samples(layouts, labels)
    normalize_samples(samples, checkpoint)

    rng = np.random.default_rng(args.seed)
    indices = np.arange(len(samples))
    rng.shuffle(indices)
    n_test = max(1, int(0.2 * len(samples)))
    test_indices = indices[:n_test]
    config = checkpoint["config"]
    model = PCBParasiticGNN(
        node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
        hidden=int(config["hidden"]), n_layers=int(config["layers"]), n_targets=4,
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    batch = collate([samples[int(index)] for index in test_indices])

    # Exact legacy protocol: three warmups, then 20 back-to-back batch forwards.
    with torch.no_grad():
        for _ in range(3):
            model(batch)
    legacy_batch_ms = time_batch(model, batch, args.legacy_repeats)

    # Extended protocol quantifies timing variation without replacing the legacy result.
    with torch.no_grad():
        for _ in range(20):
            model(batch)
    extended_batch_ms = time_batch(model, batch, args.extended_repeats)
    legacy_per_design = [value / n_test for value in legacy_batch_ms]
    extended_per_design = [value / n_test for value in extended_batch_ms]
    reproduced = float(np.median(legacy_per_design))

    output_dir = ROOT / "results" / "proof_updates" / "jobs" / "legacy_latency" / f"job_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "provenance": {
            "schema": SCHEMA,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": job_id,
            "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
            "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
            "slurm_node_list": os.environ.get("SLURM_JOB_NODELIST"),
            "slurm_cpus_on_node": os.environ.get("SLURM_CPUS_ON_NODE"),
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cpu_model": cpu_model(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "torch": torch.__version__,
            "torch_num_threads": torch.get_num_threads(),
            "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
            "git_head": git_output("rev-parse", "HEAD"),
            "git_dirty_paths": git_output(
                "status", "--short", "--untracked-files=no"
            ).splitlines(),
            "arguments": vars(args),
            "sha256": {
                artifact_key(Path(__file__)): sha256(Path(__file__)),
                artifact_key(CODE / "models" / "gnn" / "gnn_baseline.py"): sha256(CODE / "models" / "gnn" / "gnn_baseline.py"),
                artifact_key(checkpoint_path): sha256(checkpoint_path),
                artifact_key(historical_path): sha256(historical_path),
                artifact_key(dataset / "layouts.jsonl"): sha256(dataset / "layouts.jsonl"),
                artifact_key(dataset / "labels.json"): sha256(dataset / "labels.json"),
            },
        },
        "protocol": {
            "dataset": "synth_v1",
            "n_samples": len(samples),
            "n_test_batch": n_test,
            "split": "np.random.default_rng(42).shuffle; first 20% test",
            "legacy_warmups": 3,
            "legacy_repeats": args.legacy_repeats,
            "extended_warmups": 20,
            "extended_repeats": args.extended_repeats,
            "timed_scope": "pre-collated full held-out batch forward only",
        },
        "historical": {
            "slurm_cluster_name": "ascend",
            "slurm_job_id": "5676466",
            "hostname": "compute-node",
            "ms_per_design": HISTORICAL_MS_PER_DESIGN,
        },
        "reproduction": {
            "legacy_batch_total_ms": summary(legacy_batch_ms),
            "legacy_ms_per_design": summary(legacy_per_design),
            "extended_batch_total_ms": summary(extended_batch_ms),
            "extended_ms_per_design": summary(extended_per_design),
            "median_ratio_reproduced_to_historical": reproduced / HISTORICAL_MS_PER_DESIGN,
            "relative_difference_pct":
                (reproduced - HISTORICAL_MS_PER_DESIGN) / HISTORICAL_MS_PER_DESIGN * 100,
        },
        "verdict": {
            "protocol_reproduced": True,
            "exact_numeric_equality_expected_across_hardware": False,
            "note": "Latency is hardware/thread/runtime dependent; compare protocol and report hardware.",
        },
        "raw_ms": {
            "legacy_batch_total": legacy_batch_ms,
            "legacy_per_design": legacy_per_design,
            "extended_batch_total": extended_batch_ms,
            "extended_per_design": extended_per_design,
        },
    }
    path = output_dir / "results_legacy_latency_reproduction.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"LEGACY_LATENCY_REPRODUCTION={path}", flush=True)
    print(json.dumps({"reproduction": result["reproduction"], "verdict": result["verdict"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
