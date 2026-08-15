#!/usr/bin/env python3
"""Finalize the frozen nine-layout refine-3/refine-4 convergence gate."""
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

from experiments_corpus_v4_refine34_convergence import (
    EXPECTED_CORPUS_SHA256,
    FEASIBILITY,
    LAYOUTS,
    PRIOR_ARRAY_JOB_ID,
    PRIOR_FINAL_SHA256,
    PRIOR_TASK_SHA256,
    SCHEMA as TASK_SCHEMA,
    SETTINGS,
    SOURCE_NAMES,
    THREAD_NAMES,
    evaluate_gates,
    setting_result_valid,
)


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "pcb-gnn.corpus-v4-refine34-convergence-final.v1"
EXPECTED_SOLVER = "pyamg_smoothed_aggregation_cg"
MEDIAN_TOLERANCE_PCT = 2.0
MAX_TOLERANCE_PCT = 5.0
RESIDUAL_TOLERANCE = 1e-9
PACKAGE_NAMES = {"numpy", "scipy", "scikit-fem", "gmsh", "meshio", "pyamg"}


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
        value = abs(float(a["cps_pf"]) - float(b["cps_pf"])) / abs(
            float(b["cps_pf"])
        ) * 100.0
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
    if len(tasks) != 9:
        raise ValueError("scientific convergence gate requires nine task artifacts")
    for task_id, task in enumerate(tasks):
        provenance = task.get("provenance", {})
        expected_layout_id, expected_geometry = LAYOUTS[task_id]
        if task.get("schema") != TASK_SCHEMA:
            raise ValueError(f"task {task_id} schema mismatch")
        if (
            provenance.get("slurm_array_job_id") != source_array_job_id
            or int(provenance.get("slurm_array_task_id", -1)) != task_id
            or provenance.get("git_head") != head
            or provenance.get("final_git_head") != head
            or provenance.get("git_dirty_paths")
            or provenance.get("final_git_dirty_paths")
            or provenance.get("final_untracked_code")
            or not provenance.get("source_stable")
            or not task.get("task_pass")
        ):
            raise ValueError(f"task {task_id} source/provenance gate failed")
        if (
            set(provenance.get("file_sha256", {})) != set(SOURCE_NAMES)
            or provenance.get("final_file_sha256") != provenance.get("file_sha256")
            or provenance.get("corpus_artifacts_sha256") != EXPECTED_CORPUS_SHA256
            or set(provenance.get("package_versions", {})) != PACKAGE_NAMES
            or set(provenance.get("thread_environment", {})) != set(THREAD_NAMES)
            or not isinstance(provenance.get("platform"), str)
            or not provenance.get("platform")
        ):
            raise ValueError(f"task {task_id} provenance closure is incomplete")
        prior = provenance.get("prior_final", {})
        if (
            prior.get("sha256") != PRIOR_FINAL_SHA256
            or prior.get("source_array_job_id") != PRIOR_ARRAY_JOB_ID
            or prior.get("task_artifacts_sha256") != PRIOR_TASK_SHA256
        ):
            raise ValueError(f"task {task_id} prior evidence mismatch")
        feasibility = provenance.get("refine4_feasibility", {})
        if set(feasibility) != {"149", "407"}:
            raise ValueError(f"task {task_id} feasibility evidence mismatch")
        for layout_id in (149, 407):
            row = feasibility[str(layout_id)]
            if (
                row.get("sha256") != FEASIBILITY[layout_id]["sha256"]
                or row.get("slurm_job_id")
                != FEASIBILITY[layout_id]["slurm_job_id"]
            ):
                raise ValueError(f"task {task_id} feasibility evidence mismatch")
        if (
            int(task["selection"]["layout_id"]) != expected_layout_id
            or task["selection"]["geometry_sha256"] != expected_geometry
        ):
            raise ValueError(f"task {task_id} frozen geometry mismatch")
        tracked_batch_hash = provenance["file_sha256"][
            "code/jobs/submit_corpus_v4_refine34_convergence.sh"
        ]
        if provenance["executed_batch_script"]["sha256"] != tracked_batch_hash:
            raise ValueError(f"task {task_id} executed an untracked batch script")
        observed = tuple((row["refine"], row["pad_mm"]) for row in task["settings"])
        if observed != SETTINGS:
            raise ValueError(f"task {task_id} settings mismatch")
        for setting in task["settings"]:
            residual = float(setting.get("relative_residual", float("inf")))
            cps_pf = float(setting.get("cps_pf", float("nan")))
            gate = setting.get("resource_gate", {})
            recomputed_gate = evaluate_gates(setting)
            if (
                not setting_result_valid(setting)
                or not np.isfinite(residual)
                or residual < 0.0
                or residual > RESIDUAL_TOLERANCE
                or not np.isfinite(cps_pf)
                or cps_pf <= 0.0
                or gate != recomputed_gate
                or not gate.get("pass")
                or not all(gate.get("checks", {}).values())
            ):
                raise ValueError(f"task {task_id} contains an invalid FEM setting")
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
            json.dumps({
                "python": task["provenance"]["python"],
                "platform": task["provenance"]["platform"],
                "package_versions": task["provenance"]["package_versions"],
                "thread_environment": task["provenance"]["thread_environment"],
            }, sort_keys=True)
            for task in tasks
        },
        "spool": {
            task["provenance"]["executed_batch_script"]["sha256"]
            for task in tasks
        },
        "prior": {
            json.dumps(task["provenance"]["prior_final"], sort_keys=True)
            for task in tasks
        },
        "feasibility": {
            json.dumps(task["provenance"]["refine4_feasibility"], sort_keys=True)
            for task in tasks
        },
    }
    if any(len(values) != 1 for values in maps.values()):
        raise ValueError("tasks used mixed source, corpus, environment, or evidence")
    return maps


def task_artifact_paths(source: Path) -> list[Path]:
    """Require the exact task_00..task_08 filename set, with no extras."""
    expected_names = {f"task_{task_id:02d}.json" for task_id in range(9)}
    observed_names = {path.name for path in source.glob("task_*.json")}
    if observed_names != expected_names:
        raise ValueError("task artifact directory is incomplete or contains extras")
    return [source / f"task_{task_id:02d}.json" for task_id in range(9)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id")
    parser.add_argument("--median-tolerance-pct", type=float, default=2.0)
    parser.add_argument("--max-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({
            "schema": SCHEMA,
            "status": "validation-ok",
            "settings": SETTINGS,
            "median_tolerance_pct": MEDIAN_TOLERANCE_PCT,
            "max_tolerance_pct": MAX_TOLERANCE_PCT,
        }))
        return
    if not args.source_array_job_id:
        raise SystemExit("--source-array-job-id is required")
    if (
        args.median_tolerance_pct != MEDIAN_TOLERANCE_PCT
        or args.max_tolerance_pct != MAX_TOLERANCE_PCT
    ):
        raise SystemExit("convergence tolerances are fixed by the protocol")
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit convergence finalization through SLURM")

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty or untracked_code:
        raise SystemExit("Refusing finalization from dirty source")
    executed_script = Path(
        os.environ.get("PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT", "")
    )
    tracked_script = ROOT / "code/jobs/submit_finalize_corpus_v4_refine34_convergence.sh"
    initial_executed_script_sha = (
        file_sha256(executed_script) if executed_script.is_file() else None
    )
    tracked_script_sha = file_sha256(tracked_script)
    if (
        not executed_script.is_file()
        or initial_executed_script_sha != tracked_script_sha
    ):
        raise SystemExit("executed finalizer differs from tracked protocol")
    initial_finalizer_source_hashes = {
        name: file_sha256(ROOT / name) for name in SOURCE_NAMES
    }

    source = ROOT / "results/corpus_v4/refine34_convergence/jobs" / (
        f"job_{args.source_array_job_id}"
    )
    task_paths = task_artifact_paths(source)
    tasks = [json.loads(path.read_text()) for path in task_paths]
    maps = validate_task_set(tasks, args.source_array_job_id, head)
    source_hashes = json.loads(next(iter(maps["source"])))
    if source_hashes != initial_finalizer_source_hashes:
        raise ValueError("current source map differs from task source map")

    comparisons = {
        "domain_12mm_vs_16mm_at_refine3": delta(tasks, (3, 12.0), (3, 16.0)),
        "mesh_refine3_vs_refine4_at_16mm": delta(tasks, (3, 16.0), (4, 16.0)),
    }
    gate_pass = all(
        comparison["median_relative_difference_pct"] <= MEDIAN_TOLERANCE_PCT
        and comparison["max_relative_difference_pct"] <= MAX_TOLERANCE_PCT
        for comparison in comparisons.values()
    )
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_array_job_id": args.source_array_job_id,
            "git_head": head,
            "git_dirty_paths": dirty,
            "untracked_code": untracked_code,
            "finalizer_source_sha256": file_sha256(Path(__file__)),
            "executed_finalizer_batch_script": {
                "path": str(executed_script),
                "sha256": initial_executed_script_sha,
            },
            "source_file_sha256": source_hashes,
            "corpus_artifacts_sha256": json.loads(next(iter(maps["corpus"]))),
            "source_software_environment": json.loads(next(iter(maps["environment"]))),
            "source_batch_script_sha256": next(iter(maps["spool"])),
            "prior_convergence_evidence": json.loads(next(iter(maps["prior"]))),
            "refine4_feasibility_evidence": json.loads(next(iter(maps["feasibility"]))),
            "task_artifacts_sha256": {
                path.name: file_sha256(path) for path in task_paths
            },
        },
        "protocol": {
            "n_layouts": 9,
            "settings": [list(setting) for setting in SETTINGS],
            "median_tolerance_pct": MEDIAN_TOLERANCE_PCT,
            "max_tolerance_pct": MAX_TOLERANCE_PCT,
            "linear_solver": EXPECTED_SOLVER,
            "linear_residual_tolerance": RESIDUAL_TOLERANCE,
            "production_setting_if_pass": {"refine": 3, "pad_mm": 16.0},
            "reference_setting": {"refine": 4, "pad_mm": 16.0},
            "interpretation": (
                "refine-3/pad-16 is accepted only if both the refine-3 domain "
                "gate and refine-3-to-refine-4 mesh gate pass"
            ),
        },
        "comparisons": comparisons,
        "gate_pass": gate_pass,
    }
    final_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    final_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    final_untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    final_source_hashes = {
        name: file_sha256(ROOT / name) for name in SOURCE_NAMES
    }
    final_executed_script_sha = (
        file_sha256(executed_script) if executed_script.is_file() else None
    )
    source_stable = bool(
        final_head == head
        and final_dirty == dirty
        and final_untracked_code == untracked_code
        and final_source_hashes == initial_finalizer_source_hashes
        and final_executed_script_sha == initial_executed_script_sha
        and initial_executed_script_sha == tracked_script_sha
    )
    result["provenance"].update({
        "final_git_head": final_head,
        "final_git_dirty_paths": final_dirty,
        "final_untracked_code": final_untracked_code,
        "final_source_file_sha256": final_source_hashes,
        "source_stable": source_stable,
    })
    output = ROOT / "results/corpus_v4/refine34_convergence/final" / (
        f"job_{os.environ['SLURM_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / "results_corpus_v4_refine34_convergence.json"
    atomic_write(path, result)
    print(path.relative_to(ROOT), flush=True)
    if not source_stable:
        raise RuntimeError("finalizer source/provenance changed during execution")
    if not gate_pass:
        raise RuntimeError("refine-3 production Cps setting rejected by convergence gate")


if __name__ == "__main__":
    main()
