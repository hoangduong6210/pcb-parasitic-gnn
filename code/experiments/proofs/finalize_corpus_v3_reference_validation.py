#!/usr/bin/env python3
"""Finalize v3 FEM sensitivity and analytical-baseline validation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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

from planar_to_graph import compute_reference_labels_allpairs  # noqa: E402
from v3_dataset import load_final_corpus  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v3-reference-validation-final.v1"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_delta(rows: list[dict[str, Any]], left: tuple[int, float], right: tuple[int, float]) -> dict[str, Any]:
    values = []
    details = []
    for task in rows:
        settings = {(row["refine"], row["pad_mm"]): row for row in task["settings"]}
        a, b = settings[left], settings[right]
        value = abs(float(a["cps_pf"]) - float(b["cps_pf"])) / abs(float(b["cps_pf"])) * 100.0
        values.append(value)
        details.append({"layout_id": task["selection"]["layout_id"], "relative_difference_pct": value})
    array = np.asarray(values)
    return {
        "left": {"refine": left[0], "pad_mm": left[1]},
        "right_reference": {"refine": right[0], "pad_mm": right[1]},
        "n_paired": len(values),
        "median_relative_difference_pct": float(np.median(array)),
        "max_relative_difference_pct": float(np.max(array)),
        "per_layout": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit v3 reference finalization through SLURM")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing reference finalization from a dirty tracked worktree")

    source = ROOT / "results/corpus_v3/reference_validation/jobs" / f"job_{args.source_array_job_id}"
    tasks = [json.loads((source / f"task_{task:02d}.json").read_text()) for task in range(9)]
    for index, task in enumerate(tasks):
        provenance = task["provenance"]
        if task.get("schema") != "pcb-gnn.corpus-v3-reference-validation-task.v1":
            raise ValueError(f"task {index} schema mismatch")
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {index} array-job mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {index} source mismatch or dirty")
        if len(task["settings"]) != 4:
            raise ValueError(f"task {index} setting count mismatch")
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    geometry_ids = {task["selection"]["geometry_sha256"] for task in tasks}
    if len(source_maps) != 1 or len(corpus_maps) != 1 or len(geometry_ids) != 9:
        raise ValueError("mixed source/corpus or duplicate validation geometry")

    samples, corpus_summary = load_final_corpus(args.corpus)
    analytical_values = {target: [] for target in TARGETS}
    nonpassive = 0
    for sample in samples:
        analytical = compute_reference_labels_allpairs(sample["layout"])
        reference = dict(zip(TARGETS, sample["y"].astype(float)))
        for target in TARGETS:
            analytical_values[target].append(
                abs(analytical[target] - reference[target]) / abs(reference[target]) * 100.0
            )
        if abs(analytical["L_mut_nH"]) > np.sqrt(
            analytical["L_pri_nH"] * analytical["L_sec_nH"]
        ) * (1.0 + 1e-6):
            nonpassive += 1
    analytical_summary = {}
    for target, values in analytical_values.items():
        array = np.asarray(values)
        analytical_summary[target] = {
            "median_relative_error_pct": float(np.median(array)),
            "mean_relative_error_pct": float(np.mean(array)),
            "p95_relative_error_pct": float(np.percentile(array, 95)),
            "max_relative_error_pct": float(np.max(array)),
        }

    published_delta = []
    for task in tasks:
        baseline = next(row for row in task["settings"] if row["refine"] == 1 and row["pad_mm"] == 8.0)
        published = float(task["selection"]["published_reference_cps_pf"])
        published_delta.append(abs(float(baseline["cps_pf"]) - published) / abs(published) * 100.0)
    published_array = np.asarray(published_delta)
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head,
            "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "finalizer_sha256": file_sha256(Path(__file__)),
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
        },
        "protocol": {
            "fem_selection": "nine layouts: trace-count terciles crossed with low/median/high Cps",
            "fem_settings": [[1, 8.0], [1, 12.0], [2, 8.0], [2, 12.0]],
            "analytical_scope": "all 1500 geometry-valid layouts against their paired field labels",
        },
        "analytical_baseline": {
            "n_layouts": len(samples),
            "nonpassive_layouts": nonpassive,
            "per_target": analytical_summary,
        },
        "fem_sensitivity": {
            "published_refine1_pad8_recompute": {
                "n_paired": len(published_delta),
                "median_relative_difference_pct": float(np.median(published_array)),
                "max_relative_difference_pct": float(np.max(published_array)),
            },
            "mesh_refine1_vs_refine2_at_8mm": relative_delta(tasks, (1, 8.0), (2, 8.0)),
            "domain_8mm_vs_12mm_at_refine2": relative_delta(tasks, (2, 8.0), (2, 12.0)),
            "published_setting_vs_highest_setting": relative_delta(tasks, (1, 8.0), (2, 12.0)),
        },
        "task_records": [f"task_{task:02d}.json" for task in range(9)],
    }
    output = ROOT / "results/corpus_v3/reference_validation/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v3_reference_validation.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
