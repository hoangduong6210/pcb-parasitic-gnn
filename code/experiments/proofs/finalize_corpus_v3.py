#!/usr/bin/env python3
"""SLURM finalizer for a complete v3 field-label array job."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
import sys
for _directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(_directory))

from geometry_contract import geometry_sha256, validate_layout, validate_passive_labels


SCHEMA = "pcb-gnn.corpus-v3-final.v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--n-tasks", type=int, default=30)
    parser.add_argument("--n-layouts", type=int, default=1500)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit corpus finalization through SLURM")
    if args.n_tasks != 30 or args.n_layouts != 1500:
        raise SystemExit("Canonical v3 finalization requires 30 tasks and 1,500 layouts")
    finalizer_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    finalizer_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if finalizer_dirty:
        raise SystemExit("Refusing finalization from a dirty tracked worktree")

    source = ROOT / "results/corpus_v3/jobs" / f"job_{args.source_array_job_id}"
    metas = []
    records = []
    for task_id in range(args.n_tasks):
        meta_path = source / f"task_{task_id:02d}_meta.json"
        records_path = source / f"task_{task_id:02d}_records.jsonl"
        if not meta_path.is_file() or not records_path.is_file():
            raise FileNotFoundError(f"missing task {task_id:02d} output")
        meta = json.loads(meta_path.read_text())
        if meta.get("schema") != "pcb-gnn.corpus-v3-field-label-chunk.v1":
            raise ValueError(f"task {task_id:02d} schema mismatch")
        if meta["provenance"]["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id:02d} array-job mismatch")
        expected_args = {
            "n_total": 1500, "chunk_size": 50, "seed_start": 42000,
            "fem_refine": 1, "fem_timeout_s": 180, "validate_only": False,
        }
        if meta["provenance"]["arguments"] != expected_args:
            raise ValueError(f"task {task_id:02d} protocol arguments mismatch")
        if meta["provenance"]["git_dirty_paths"]:
            raise ValueError(f"task {task_id:02d} ran from a dirty tracked tree")
        if sha256(records_path) != meta["records_sha256"]:
            raise ValueError(f"task {task_id:02d} record hash mismatch")
        metas.append(meta)
        records.extend(json.loads(line) for line in records_path.read_text().splitlines() if line.strip())

    commits = {meta["provenance"]["git_head"] for meta in metas}
    source_maps = {
        json.dumps(meta["provenance"]["file_sha256"], sort_keys=True) for meta in metas
    }
    if len(commits) != 1 or len(source_maps) != 1:
        raise ValueError("array tasks did not use one immutable source/environment contract")
    source_commit = next(iter(commits))
    if finalizer_head != source_commit:
        raise ValueError("finalizer commit differs from the field-label source commit")
    records.sort(key=lambda row: row["layout_id"])
    if [row["layout_id"] for row in records] != list(range(args.n_layouts)):
        raise ValueError("layout IDs are incomplete, duplicated, or out of order")

    coupling = []
    trace_counts = []
    geometry_hashes = set()
    for record in records:
        if not record["valid"] or record["label"] is None:
            raise ValueError(f"layout {record['layout_id']} has no accepted label")
        audit = validate_layout(record["layout"])
        digest = geometry_sha256(record["layout"])
        if digest != record["geometry_sha256"]:
            raise ValueError(f"layout {record['layout_id']} geometry hash mismatch")
        if digest in geometry_hashes:
            raise ValueError(f"duplicate geometry at layout {record['layout_id']}")
        geometry_hashes.add(digest)
        passive = validate_passive_labels(record["label"])
        if abs(passive["coupling_coefficient"] - record["passivity"]["coupling_coefficient"]) > 1e-12:
            raise ValueError(f"layout {record['layout_id']} passivity record mismatch")
        coupling.append(passive["coupling_coefficient"])
        trace_counts.append(audit["n_traces"])

    output = ROOT / "results/corpus_v3/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    layouts_path = output / "layouts.jsonl"
    labels_path = output / "labels.jsonl"
    with layouts_path.open("w") as layouts_handle, labels_path.open("w") as labels_handle:
        for record in records:
            layouts_handle.write(json.dumps({
                "layout_id": record["layout_id"], "geometry_sha256": record["geometry_sha256"],
                "layout": record["layout"],
            }, sort_keys=True) + "\n")
            labels_handle.write(json.dumps({
                "layout_id": record["layout_id"], "geometry_sha256": record["geometry_sha256"],
                **record["label"], "coupling_coefficient": record["passivity"]["coupling_coefficient"],
                "timing_ms": record["timing_ms"],
            }, sort_keys=True) + "\n")

    target_summary = {}
    for target in ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"):
        values = np.asarray([record["label"][target] for record in records], dtype=np.float64)
        target_summary[target] = {
            "min": float(values.min()), "median": float(np.median(values)), "max": float(values.max())
        }
    paired = np.asarray([record["timing_ms"]["paired"] for record in records], dtype=np.float64)
    summary = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "source_git_head": source_commit,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "finalizer_git_head": finalizer_head,
            "finalizer_git_dirty_paths": finalizer_dirty,
            "finalizer_sha256": sha256(Path(__file__)),
        },
        "gates": {
            "n_layouts": len(records), "n_unique_geometry_hashes": len(geometry_hashes),
            "geometry_valid": True, "all_labels_passive": True,
            "all_array_tasks_clean_and_source_identical": True,
        },
        "geometry": {
            "trace_count_min": min(trace_counts), "trace_count_median": float(np.median(trace_counts)),
            "trace_count_max": max(trace_counts),
        },
        "labels": {
            "coupling_min": float(np.min(coupling)), "coupling_median": float(np.median(coupling)),
            "coupling_max": float(np.max(coupling)), "targets": target_summary,
        },
        "paired_solver_timing_ms": {
            "median": float(np.median(paired)), "p95": float(np.percentile(paired, 95)),
        },
        "artifacts_sha256": {
            "layouts.jsonl": sha256(layouts_path), "labels.jsonl": sha256(labels_path),
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
