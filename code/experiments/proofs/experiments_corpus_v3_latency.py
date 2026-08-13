#!/usr/bin/env python3
"""Paired solver-to-raw-layout GNN latency on geometry-valid v3 designs."""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers", CODE / "inference"):
    sys.path.insert(0, str(directory))

from fasthenry_ref import FASTHENRY, fasthenry_totals
from geometry_contract import validate_passive_labels
from predict_safe_bundle import load_bundle, predict_layout
from runtime_paths import fem_cps_worker_path
from v3_dataset import load_final_corpus, sha256


SCHEMA = "pcb-gnn.corpus-v3-paired-latency.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--n-designs", type=int, default=100)
    parser.add_argument("--inference-repetitions", type=int, default=30)
    parser.add_argument("--fem-refine", type=int, default=1)
    parser.add_argument("--fem-timeout-s", type=int, default=180)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def safe_fem(layout: dict[str, Any], refine: int, timeout_s: int) -> tuple[float, float]:
    worker = fem_cps_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        path = Path(handle.name)
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), str(path), str(refine)], cwd=worker.parent,
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
        for line in completed.stdout.splitlines():
            if line.startswith("CPS="):
                return float(line.removeprefix("CPS=")), (time.perf_counter_ns() - started) / 1e6
        raise RuntimeError(f"FEM worker failed: {completed.stderr[-500:]}")
    finally:
        path.unlink(missing_ok=True)


def bootstrap_median(values: np.ndarray, resamples: int) -> list[float]:
    rng = np.random.default_rng(20260813)
    draws = np.empty(resamples)
    for index in range(resamples):
        draws[index] = np.median(rng.choice(values, size=len(values), replace=True))
    return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]


def main() -> None:
    args = parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Refusing paired solver benchmark outside SLURM")
    if args.corpus is None or args.bundle is None:
        raise SystemExit("--corpus and --bundle are required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing latency benchmark from a dirty tracked worktree")
    binary = Path(FASTHENRY).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(binary)
    samples, corpus_summary = load_final_corpus(args.corpus)
    started = time.perf_counter_ns()
    model, norm, metadata = load_bundle(args.bundle)
    model_load_ms = (time.perf_counter_ns() - started) / 1e6
    if metadata.get("schema") != "pcb-gnn.safe-inference-bundle.v2":
        raise ValueError("expected the v3 state-dict-only bundle")
    eligible = metadata["test_layout_ids"]
    if args.n_designs > len(eligible):
        raise ValueError("n-designs exceeds the held-out split")
    rng = np.random.default_rng(20260813)
    selected = sorted(rng.choice(eligible, size=args.n_designs, replace=False).astype(int).tolist())
    by_id = {sample["layout_id"]: sample for sample in samples}
    predict_layout(model, norm, by_id[selected[0]]["layout"])
    records = []
    for layout_id in selected:
        sample = by_id[layout_id]
        layout = sample["layout"]
        fh_started = time.perf_counter_ns()
        inductance = fasthenry_totals(layout, 1e5)
        fh_ms = (time.perf_counter_ns() - fh_started) / 1e6
        if inductance is None:
            raise RuntimeError(f"FastHenry failed for layout {layout_id}")
        cps, fem_ms = safe_fem(layout, args.fem_refine, args.fem_timeout_s)
        label = {"Cps_pF": cps, **inductance}
        passivity = validate_passive_labels(label)
        repetitions = []
        prediction = None
        for _ in range(args.inference_repetitions):
            infer_started = time.perf_counter_ns()
            prediction = predict_layout(model, norm, layout)
            repetitions.append((time.perf_counter_ns() - infer_started) / 1e6)
        reference = sample["y"].astype(np.float64)
        rerun = np.asarray([cps, inductance["L_pri_nH"], inductance["L_sec_nH"], inductance["L_mut_nH"]])
        drift = np.abs(rerun - reference) / np.maximum(np.abs(reference), 1e-9)
        if np.max(drift) > 1e-4:
            raise RuntimeError(f"solver-label drift exceeds tolerance for layout {layout_id}: {drift}")
        inference_ms = float(np.median(repetitions))
        records.append({
            "layout_id": layout_id, "geometry_sha256": sample["geometry_sha256"],
            "solver_ms": {"fasthenry": fh_ms, "fem": fem_ms, "paired": fh_ms + fem_ms},
            "inference_raw_layout_ms": {"median": inference_ms, "repetitions": repetitions},
            "speedup_paired_four_target_x": (fh_ms + fem_ms) / inference_ms,
            "solver_label_max_relative_drift": float(np.max(drift)),
            "coupling_coefficient": passivity["coupling_coefficient"],
            "prediction": prediction.tolist(), "reference": reference.tolist(),
        })
        print(
            f"layout={layout_id:04d} solver={fh_ms+fem_ms:.1f}ms "
            f"gnn={inference_ms:.3f}ms speedup={records[-1]['speedup_paired_four_target_x']:.1f}x",
            flush=True,
        )
    speedups = np.asarray([record["speedup_paired_four_target_x"] for record in records])
    solver_ms = np.asarray([record["solver_ms"]["paired"] for record in records])
    inference_ms = np.asarray([record["inference_raw_layout_ms"]["median"] for record in records])
    source_paths = [Path(__file__), CODE / "data/v3_dataset.py", CODE / "inference/predict_safe_bundle.py",
                    CODE / "core/geometry_contract.py", CODE / "core/planar_to_graph.py",
                    CODE / "solvers/fasthenry_ref.py", CODE / "solvers/fem_capacitance_3d.py",
                    fem_cps_worker_path(), binary]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"], "hostname": socket.gethostname(),
            "platform": platform.platform(), "python": platform.python_version(),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "git_dirty_paths": dirty,
            "arguments": {**vars(args), "corpus": args.corpus.resolve().as_posix(), "bundle": args.bundle.resolve().as_posix()},
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "bundle_sha256": {path.name: sha256(path) for path in args.bundle.iterdir() if path.is_file()},
            "file_sha256": {
                (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else f"external/{path.name}"): sha256(path)
                for path in source_paths
            },
        },
        "protocol": {
            "comparison": "paired FastHenry plus electrostatic FEM for all four targets versus raw-layout graph construction plus batch-one GNN",
            "interval_scope": "design bootstrap on one evaluated node and fixed checkpoint",
            "model_load_excluded_from_per_design_inference": True,
            "model_load_ms": model_load_ms,
        },
        "summary": {
            "n_designs": len(records),
            "paired_solver_median_ms": float(np.median(solver_ms)),
            "raw_layout_gnn_median_ms": float(np.median(inference_ms)),
            "median_paired_speedup_x": float(np.median(speedups)),
            "median_paired_speedup_design_bootstrap_95_ci": bootstrap_median(speedups, args.bootstrap_resamples),
        },
        "records": records,
    }
    output = ROOT / "results/corpus_v3/latency/jobs" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_latency.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
