#!/usr/bin/env python3
"""Gate the production Cps setting using the corpus-v4 convergence preflight."""
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
SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-final.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-task.v1"
EXPECTED_SETTINGS = ((2, 12.0), (2, 16.0), (3, 12.0), (3, 16.0))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def delta(
    tasks: list[dict[str, Any]], left: tuple[int, float], right: tuple[int, float]
) -> dict[str, Any]:
    details = []
    for task in tasks:
        settings = {(row["refine"], row["pad_mm"]): row for row in task["settings"]}
        a, b = settings[left], settings[right]
        value = abs(float(a["cps_pf"]) - float(b["cps_pf"])) / abs(float(b["cps_pf"])) * 100.0
        details.append({
            "layout_id": task["selection"]["layout_id"],
            "relative_difference_pct": value,
        })
    values = np.asarray([row["relative_difference_pct"] for row in details])
    return {
        "left": {"refine": left[0], "pad_mm": left[1]},
        "right_reference": {"refine": right[0], "pad_mm": right[1]},
        "n_paired": len(details),
        "median_relative_difference_pct": float(np.median(values)),
        "max_relative_difference_pct": float(np.max(values)),
        "per_layout": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--median-tolerance-pct", type=float, default=2.0)
    parser.add_argument("--max-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit corpus-v4 convergence finalization through SLURM")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing convergence finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v4/convergence_preflight/jobs" / (
        f"job_{args.source_array_job_id}"
    )
    task_paths = [source / f"task_{task_id:02d}.json" for task_id in range(9)]
    tasks = [json.loads(path.read_text()) for path in task_paths]
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
        observed = tuple((row["refine"], row["pad_mm"]) for row in task["settings"])
        if observed != EXPECTED_SETTINGS:
            raise ValueError(f"task {task_id} settings mismatch")
    source_maps = {json.dumps(task["provenance"]["file_sha256"], sort_keys=True) for task in tasks}
    corpus_maps = {json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True) for task in tasks}
    environment_maps = {json.dumps({
        "python": task["provenance"]["python"],
        "package_versions": task["provenance"]["package_versions"],
    }, sort_keys=True) for task in tasks}
    geometry_ids = {task["selection"]["geometry_sha256"] for task in tasks}
    if any(len(values) != 1 for values in (source_maps, corpus_maps, environment_maps)):
        raise ValueError("preflight tasks used mixed source, corpus, or environment")
    if len(geometry_ids) != 9:
        raise ValueError("preflight geometries are not unique")

    comparisons = {
        "domain_12mm_vs_16mm_at_refine2": delta(tasks, (2, 12.0), (2, 16.0)),
        "domain_12mm_vs_16mm_at_refine3": delta(tasks, (3, 12.0), (3, 16.0)),
        "mesh_refine2_vs_refine3_at_12mm": delta(tasks, (2, 12.0), (3, 12.0)),
        "mesh_refine2_vs_refine3_at_16mm": delta(tasks, (2, 16.0), (3, 16.0)),
    }
    critical = (
        comparisons["domain_12mm_vs_16mm_at_refine3"],
        comparisons["mesh_refine2_vs_refine3_at_16mm"],
    )
    gate_pass = all(
        comparison["median_relative_difference_pct"] <= args.median_tolerance_pct
        and comparison["max_relative_difference_pct"] <= args.max_tolerance_pct
        for comparison in critical
    )
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head,
            "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
            "corpus_artifacts_sha256": json.loads(next(iter(corpus_maps))),
            "source_software_environment": json.loads(next(iter(environment_maps))),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "protocol": {
            "n_layouts": 9,
            "settings": [list(setting) for setting in EXPECTED_SETTINGS],
            "median_tolerance_pct": args.median_tolerance_pct,
            "max_tolerance_pct": args.max_tolerance_pct,
            "production_setting_if_pass": {"refine": 2, "pad_mm": 16.0},
            "interpretation": "refine-3/pad-16-mm is the comparison reference; the production setting is accepted only when both domain and mesh sensitivity gates pass",
        },
        "comparisons": comparisons,
        "gate_pass": gate_pass,
    }
    output = ROOT / "results/corpus_v4/convergence_preflight/final" / (
        f"job_{os.environ['SLURM_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v4_convergence_preflight.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)
    if not gate_pass:
        raise RuntimeError("production Cps setting rejected by the predeclared convergence gate")


if __name__ == "__main__":
    main()
