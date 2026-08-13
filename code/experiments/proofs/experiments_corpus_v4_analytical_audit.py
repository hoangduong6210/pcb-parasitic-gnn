#!/usr/bin/env python3
"""Audit the analytical four-target baseline against finalized corpus v4."""
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
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data"):
    sys.path.insert(0, str(directory))

from geometry_contract import validate_passive_labels  # noqa: E402
from planar_to_graph import compute_reference_labels_allpairs  # noqa: E402
from v3_dataset import load_final_corpus, sha256  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-analytical-audit.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")


def summarize(prediction: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    relative = np.abs(prediction - reference) / np.maximum(np.abs(reference), 1e-12) * 100.0
    denominator = np.sum((reference - reference.mean()) ** 2)
    return {
        "median_relative_error_pct": float(np.median(relative)),
        "mean_relative_error_pct": float(np.mean(relative)),
        "p95_relative_error_pct": float(np.percentile(relative, 95)),
        "max_relative_error_pct": float(np.max(relative)),
        "r2": float(
            1.0 - np.sum((prediction - reference) ** 2) / max(float(denominator), 1e-12)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit the corpus-v4 analytical audit through SLURM")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing analytical audit from a dirty tracked worktree")
    samples, corpus_summary = load_final_corpus(args.corpus)
    prediction = []
    reference = []
    nonpassive = []
    for sample in samples:
        label = compute_reference_labels_allpairs(sample["layout"])
        prediction.append([float(label[target]) for target in TARGETS])
        reference.append(sample["y"].astype(np.float64))
        try:
            validate_passive_labels(label)
        except ValueError:
            nonpassive.append(sample["layout_id"])
    predictions = np.asarray(prediction, dtype=np.float64)
    references = np.asarray(reference, dtype=np.float64)
    sources = [
        Path(__file__), ROOT / "requirements-proof.txt", CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py", CODE / "core/planar_to_graph.py",
        CODE / "core/trace_peec.py",
    ]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "package_versions": {
                name: importlib.metadata.version(name) for name in ("numpy", "scipy")
            },
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {
                path.relative_to(ROOT).as_posix(): sha256(path) for path in sources
            },
        },
        "protocol": {
            "n_layouts": len(samples),
            "comparison": "analytical all-pairs estimator versus paired high-resolution FEM/FastHenry corpus-v4 references",
        },
        "nonpassive_analytical_layout_ids": nonpassive,
        "per_target": {
            target: summarize(predictions[:, index], references[:, index])
            for index, target in enumerate(TARGETS)
        },
    }
    output = ROOT / "results/corpus_v4/analytical_audit/jobs" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v4_analytical_audit.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
