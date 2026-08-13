#!/usr/bin/env python3
"""Cross-check v3 inductive labels and held-out GNN predictions with Neumann integration."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "models/gnn", CODE / "solvers",
                  CODE / "inference"):
    sys.path.insert(0, str(directory))

from fem_inductance_ref import neumann_totals  # noqa: E402
from predict_safe_bundle import load_bundle, predict_layout  # noqa: E402
from v3_dataset import load_final_corpus, sha256  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v3-cross-solver.v1"
TARGETS = ("L_pri_nH", "L_sec_nH", "L_mut_nH")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solve_neumann(layout: dict[str, Any]) -> dict[str, float]:
    return neumann_totals(layout, nw=5, nt=2)


def metrics(prediction: np.ndarray, reference: np.ndarray) -> dict[str, float]:
    relative = np.abs(prediction - reference) / np.maximum(np.abs(reference), 1e-12) * 100.0
    denominator = np.sum((reference - reference.mean()) ** 2)
    return {
        "median_relative_error_pct": float(np.median(relative)),
        "mean_relative_error_pct": float(np.mean(relative)),
        "p95_relative_error_pct": float(np.percentile(relative, 95)),
        "r2": float(1.0 - np.sum((prediction - reference) ** 2) / max(float(denominator), 1e-12)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--n-designs", type=int, default=70)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        aligned = parallel_smoke = solve_neumann({"traces": [
            {"net": "pri", "x0": 0.0, "y0": 0.0, "z_mm": 0.05,
             "length_mm": 35.0, "width_mm": 1.0, "thick_mm": 0.07},
            {"net": "sec", "x0": 1.0, "y0": 2.0, "z_mm": 0.23,
             "length_mm": 32.0, "width_mm": 1.2, "thick_mm": 0.07},
        ]})
        if aligned["L_mut_nH"] <= 0:
            raise ValueError("Neumann smoke result is not positive")
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "smoke": parallel_smoke}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit the v3 cross-solver study through SLURM")
    if args.corpus is None or args.bundle is None:
        raise SystemExit("--corpus and --bundle are required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing cross-solver validation from a dirty tracked worktree")

    samples, corpus_summary = load_final_corpus(args.corpus)
    model, norm, metadata = load_bundle(args.bundle)
    if metadata.get("schema") != "pcb-gnn.safe-inference-bundle.v2":
        raise ValueError("unexpected safe-bundle schema")
    by_id = {sample["layout_id"]: sample for sample in samples}
    test_ids = sorted(int(layout_id) for layout_id in metadata["test_layout_ids"])
    if args.n_designs > len(test_ids):
        raise ValueError("requested cross-solver designs exceed held-out bundle designs")
    positions = np.linspace(0, len(test_ids) - 1, args.n_designs, dtype=int)
    chosen = [by_id[test_ids[int(position)]] for position in positions]
    predictions = np.stack([predict_layout(model, norm, sample["layout"]) for sample in chosen])
    workers = max(1, int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        neumann = list(executor.map(solve_neumann, (sample["layout"] for sample in chosen)))

    records = []
    fh_matrix = np.stack([sample["y"][1:].astype(float) for sample in chosen])
    neumann_matrix = np.asarray([[row[target] for target in TARGETS] for row in neumann])
    gnn_matrix = predictions[:, 1:].astype(float)
    for index, sample in enumerate(chosen):
        records.append({
            "layout_id": sample["layout_id"],
            "geometry_sha256": sample["geometry_sha256"],
            "fasthenry": {target: float(value) for target, value in zip(TARGETS, fh_matrix[index])},
            "neumann": {target: float(value) for target, value in zip(TARGETS, neumann_matrix[index])},
            "gnn": {target: float(value) for target, value in zip(TARGETS, gnn_matrix[index])},
        })
    summary = {target: {
        "fasthenry_vs_neumann": metrics(fh_matrix[:, offset], neumann_matrix[:, offset]),
        "gnn_vs_neumann": metrics(gnn_matrix[:, offset], neumann_matrix[:, offset]),
    } for offset, target in enumerate(TARGETS)}

    sources = [Path(__file__), CODE / "solvers/fem_inductance_ref.py", CODE / "data/v3_dataset.py",
               CODE / "inference/predict_safe_bundle.py", CODE / "core/planar_to_graph.py",
               CODE / "core/geometry_contract.py", CODE / "models/gnn/gnn_baseline.py"]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                text=True, check=True,
            ).stdout.strip(),
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "bundle_sha256": {
                path.name: sha256(path) for path in args.bundle.iterdir() if path.is_file()
            },
            "file_sha256": {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sources},
        },
        "protocol": {
            "n_designs": len(chosen),
            "selection": "evenly spaced layout IDs within the safe bundle held-out split",
            "filament_grid": [5, 2],
            "geometry": "finite parallel segments with longitudinal, lateral, and vertical offsets",
        },
        "summary": summary,
        "records": records,
    }
    output = ROOT / "results/corpus_v3/cross_solver/jobs" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_cross_solver.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
