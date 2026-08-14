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
SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-final.v2"
TASK_SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-task.v2"
EXPECTED_SETTINGS = ((2, 12.0), (2, 16.0), (3, 12.0), (3, 16.0))
EXPECTED_SOLVER = "pyamg_smoothed_aggregation_cg"
RESIDUAL_TOLERANCE = 1e-9
MEDIAN_TOLERANCE_PCT = 2.0
MAX_TOLERANCE_PCT = 5.0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


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


def validate_task_set(
    tasks: list[dict[str, Any]], source_array_job_id: str, head: str
) -> dict[str, set[str]]:
    """Validate all task artifacts and return their common provenance maps."""
    if len(tasks) != 9:
        raise ValueError("preflight requires exactly nine task artifacts")
    for task_id, task in enumerate(tasks):
        provenance = task["provenance"]
        if task.get("schema") != TASK_SCHEMA:
            raise ValueError(f"task {task_id} schema mismatch")
        if provenance["slurm_array_job_id"] != source_array_job_id:
            raise ValueError(f"task {task_id} array-job mismatch")
        if int(provenance["slurm_array_task_id"]) != task_id:
            raise ValueError(f"task {task_id} array-task mismatch")
        if provenance["git_head"] != head or provenance["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch or dirty")
        tracked_task_batch_hash = provenance["file_sha256"][
            "code/jobs/submit_corpus_v4_convergence_preflight.sh"
        ]
        if provenance["executed_batch_script"]["sha256"] != tracked_task_batch_hash:
            raise ValueError(f"task {task_id} executed an untracked batch protocol")
        if not provenance.get("source_stable") or not task.get("task_pass"):
            raise ValueError(f"task {task_id} did not pass its source/setting gates")
        observed = tuple((row["refine"], row["pad_mm"]) for row in task["settings"])
        if observed != EXPECTED_SETTINGS:
            raise ValueError(f"task {task_id} settings mismatch")
        for setting in task["settings"]:
            residual = float(setting.get("relative_residual", float("inf")))
            if (
                not setting.get("success")
                or setting.get("linear_solver") != EXPECTED_SOLVER
                or setting.get("requested_linear_solver") != "amg_cg"
                or not np.isfinite(residual)
                or residual < 0.0
                or residual > RESIDUAL_TOLERANCE
                or not setting.get("input_system_sha256")
            ):
                raise ValueError(
                    f"task {task_id} has an invalid AMG-CG setting result"
                )
    maps = {
        "source": {
            json.dumps(task["provenance"]["file_sha256"], sort_keys=True)
            for task in tasks
        },
        "corpus": {
            json.dumps(task["provenance"]["corpus_artifacts_sha256"], sort_keys=True)
            for task in tasks
        },
        "environment": {
            json.dumps(
                {
                    "python": task["provenance"]["python"],
                    "package_versions": task["provenance"]["package_versions"],
                    "thread_environment": task["provenance"]["thread_environment"],
                },
                sort_keys=True,
            )
            for task in tasks
        },
        "spool": {
            task["provenance"]["executed_batch_script"]["sha256"]
            for task in tasks
        },
        "diagnostic": {
            json.dumps(
                task["provenance"]["native_solver_diagnostic"], sort_keys=True
            )
            for task in tasks
        },
    }
    if any(len(values) != 1 for values in maps.values()):
        raise ValueError("preflight tasks used mixed source, corpus, or environment")
    if len({task["selection"]["geometry_sha256"] for task in tasks}) != 9:
        raise ValueError("preflight geometries are not unique")
    return maps


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
    if (
        args.median_tolerance_pct != MEDIAN_TOLERANCE_PCT
        or args.max_tolerance_pct != MAX_TOLERANCE_PCT
    ):
        raise SystemExit("convergence tolerances are fixed by the protocol")
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
    executed_batch_script = Path(
        os.environ.get("PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT", "")
    )
    if not executed_batch_script.is_file():
        raise SystemExit("exact executed finalizer batch script is unavailable")
    tracked_finalizer_script = (
        ROOT / "code/jobs/submit_finalize_corpus_v4_convergence_preflight.sh"
    )
    if file_sha256(executed_batch_script) != file_sha256(tracked_finalizer_script):
        raise SystemExit("executed finalizer script differs from the tracked protocol")
    source = ROOT / "results/corpus_v4/convergence_preflight/jobs" / (
        f"job_{args.source_array_job_id}"
    )
    task_paths = [source / f"task_{task_id:02d}.json" for task_id in range(9)]
    tasks = [json.loads(path.read_text()) for path in task_paths]
    maps = validate_task_set(tasks, args.source_array_job_id, head)

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
            "finalizer_source_sha256": file_sha256(Path(__file__)),
            "executed_finalizer_batch_script": {
                "path": str(executed_batch_script),
                "sha256": file_sha256(executed_batch_script),
            },
            "source_file_sha256": json.loads(next(iter(maps["source"]))),
            "corpus_artifacts_sha256": json.loads(next(iter(maps["corpus"]))),
            "source_software_environment": json.loads(next(iter(maps["environment"]))),
            "source_batch_script_sha256": next(iter(maps["spool"])),
            "native_solver_diagnostic": json.loads(next(iter(maps["diagnostic"]))),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "protocol": {
            "n_layouts": 9,
            "settings": [list(setting) for setting in EXPECTED_SETTINGS],
            "median_tolerance_pct": MEDIAN_TOLERANCE_PCT,
            "max_tolerance_pct": MAX_TOLERANCE_PCT,
            "linear_solver": EXPECTED_SOLVER,
            "linear_residual_tolerance": RESIDUAL_TOLERANCE,
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
    atomic_write(path, result)
    print(path.relative_to(ROOT), flush=True)
    if not gate_pass:
        raise RuntimeError("production Cps setting rejected by the predeclared convergence gate")


if __name__ == "__main__":
    main()
