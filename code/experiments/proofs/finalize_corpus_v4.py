#!/usr/bin/env python3
"""Finalize 1,500 refined Cps labels into the canonical corpus-v4 package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data"):
    sys.path.insert(0, str(directory))

from geometry_contract import validate_passive_labels  # noqa: E402
from v3_dataset import load_final_corpus, sha256  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-final.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-refined-cps-task.v1"
EXPECTED_REFINE = 2
EXPECTED_PAD_MM = 12.0
EXPECTED_CHUNK_SIZE = 10


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-corpus", type=Path)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--n-tasks", type=int, default=150)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit corpus-v4 finalization through SLURM")
    if args.source_corpus is None:
        raise SystemExit("--source-corpus is required")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing corpus-v4 finalization from a dirty tracked worktree")
    samples, source_summary = load_final_corpus(args.source_corpus)
    source = ROOT / "results/corpus_v4/refined_cps/jobs" / f"job_{args.source_array_job_id}"
    task_paths = [source / f"task_{task:03d}.json" for task in range(args.n_tasks)]
    tasks = [json.loads(path.read_text()) for path in task_paths]
    records = []
    observed_ranges = []
    for task_id, task in enumerate(tasks):
        provenance = task["provenance"]
        if task.get("schema") != TASK_SCHEMA:
            raise ValueError(f"task {task_id} schema mismatch")
        if provenance["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if int(provenance["slurm_array_task_id"]) != task_id:
            raise ValueError(f"task {task_id} array-task mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        protocol = task["protocol"]
        if (
            int(protocol["fem_refine"]) != EXPECTED_REFINE
            or float(protocol["pad_mm"]) != EXPECTED_PAD_MM
        ):
            raise ValueError(f"task {task_id} solver protocol mismatch")
        observed_ranges.append(tuple(protocol["range"]))
        records.extend(task["records"])
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["source_corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    environment_maps = {
        json.dumps(
            {
                "python": task["provenance"]["python"],
                "package_versions": task["provenance"]["package_versions"],
            },
            sort_keys=True,
        )
        for task in tasks
    }
    if len(source_maps) != 1 or len(corpus_maps) != 1 or len(environment_maps) != 1:
        raise ValueError("refined-Cps tasks used mixed source, corpus, or software environment")
    observed_corpus_hashes = json.loads(next(iter(corpus_maps)))
    if observed_corpus_hashes != source_summary["artifacts_sha256"]:
        raise ValueError("refined-Cps tasks do not match the requested source corpus")
    expected_ranges = [
        (start, min(start + EXPECTED_CHUNK_SIZE, len(samples)))
        for start in range(0, len(samples), EXPECTED_CHUNK_SIZE)
    ]
    if observed_ranges != expected_ranges or len(expected_ranges) != args.n_tasks:
        raise ValueError("refined-Cps task ranges are not exact and contiguous")
    if len(records) != len(samples) or len({row["layout_id"] for row in records}) != len(samples):
        raise ValueError("refined-Cps record cardinality/identity mismatch")
    by_id = {record["layout_id"]: record for record in records}
    if set(by_id) != {sample["layout_id"] for sample in samples}:
        raise ValueError("refined-Cps record IDs do not match the source corpus")
    for sample in samples:
        if by_id[sample["layout_id"]]["geometry_sha256"] != sample["geometry_sha256"]:
            raise ValueError(f"geometry hash mismatch for layout {sample['layout_id']}")
    output = ROOT / "results/corpus_v4/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    layouts_path = output / "layouts.jsonl"
    labels_path = output / "labels.jsonl"
    source_layouts = args.source_corpus / "layouts.jsonl"
    layouts_path.write_bytes(source_layouts.read_bytes())
    labels = []
    differences = []
    solver_ms = []
    for sample in samples:
        refined = by_id[sample["layout_id"]]
        label = {
            "layout_id": sample["layout_id"], "geometry_sha256": sample["geometry_sha256"],
            "Cps_pF": refined["Cps_pF"], "L_pri_nH": float(sample["y"][1]),
            "L_sec_nH": float(sample["y"][2]), "L_mut_nH": float(sample["y"][3]),
        }
        validate_passive_labels(label)
        labels.append(label)
        differences.append(refined["coarse_to_refined_relative_difference_pct"])
        solver_ms.append(refined["solver_ms"])
    labels_path.write_text("".join(json.dumps(label, sort_keys=True) + "\n" for label in labels))
    difference_array = np.asarray(differences)
    solver_array = np.asarray(solver_ms)
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head, "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "source_corpus_artifacts_sha256": source_summary["artifacts_sha256"],
            "source_software_environment": json.loads(next(iter(environment_maps))),
            "finalizer_sha256": file_sha256(Path(__file__)),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "gates": {
            "n_layouts": len(samples), "n_unique_geometry": len({sample["geometry_sha256"] for sample in samples}),
            "geometry_valid": True, "all_labels_passive": True,
            "all_array_tasks_clean_and_source_identical": True,
        },
        "protocol": {
            "Cps_reference": "electrostatic FEM refine=2, 12 mm domain padding",
            "inductance_reference": "unchanged FastHenry labels from source corpus-v3",
        },
        "coarse_to_refined_cps_difference_pct": {
            "median": float(np.median(difference_array)), "mean": float(np.mean(difference_array)),
            "p95": float(np.percentile(difference_array, 95)), "max": float(np.max(difference_array)),
        },
        "refined_cps_solver_ms": {
            "median": float(np.median(solver_array)), "p95": float(np.percentile(solver_array, 95)),
        },
        "artifacts_sha256": {"layouts.jsonl": sha256(layouts_path), "labels.jsonl": sha256(labels_path)},
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n")
    print(summary_path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
