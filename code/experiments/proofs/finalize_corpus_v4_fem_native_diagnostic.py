#!/usr/bin/env python3
"""Aggregate both FEM native diagnostic tasks into one mandatory verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TASK_SCHEMA = "pcb-gnn.corpus-v4-fem-native-diagnostic-task.v2"
SUMMARY_SCHEMA = "pcb-gnn.corpus-v4-fem-native-diagnostic-summary.v1"
COMMON_PROVENANCE_KEYS = (
    "git_head",
    "corpus_artifacts_sha256",
    "file_sha256",
    "package_versions",
    "thread_environment",
    "slurm_resources",
    "arm_timeout_s",
)


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


def finalize(job_dir: Path, array_job_id: str) -> dict[str, Any]:
    task_paths = [job_dir / f"task_{task_id:02d}.json" for task_id in (0, 1)]
    missing = [str(path) for path in task_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing diagnostic task artifacts: {missing}")
    tasks = [json.loads(path.read_text()) for path in task_paths]
    for task_id, task in enumerate(tasks):
        if task.get("schema") != TASK_SCHEMA:
            raise RuntimeError(f"task {task_id} has an unexpected schema")
        if task.get("protocol_revision") != 2 or task.get("task_id") != task_id:
            raise RuntimeError(f"task {task_id} does not match protocol revision 2")
        provenance = task.get("provenance", {})
        if str(provenance.get("slurm_array_job_id")) != str(array_job_id):
            raise RuntimeError(f"task {task_id} belongs to another array job")
        if int(provenance.get("slurm_array_task_id", -1)) != task_id:
            raise RuntimeError(f"task {task_id} has inconsistent SLURM task provenance")
        if not provenance.get("source_stable"):
            raise RuntimeError(f"task {task_id} source changed during execution")
        if not task.get("gates", {}).get("pass"):
            raise RuntimeError(f"task {task_id} scientific gate failed")
    if tasks[0]["selection"] != tasks[1]["selection"]:
        raise RuntimeError("diagnostic tasks used different layouts")
    for key in COMMON_PROVENANCE_KEYS:
        if tasks[0]["provenance"].get(key) != tasks[1]["provenance"].get(key):
            raise RuntimeError(f"diagnostic task provenance differs for {key}")
    spool_hashes = {
        task["provenance"].get("executed_batch_script", {}).get("sha256")
        for task in tasks
    }
    if None in spool_hashes or len(spool_hashes) != 1:
        raise RuntimeError("diagnostic tasks executed different SLURM batch scripts")
    return {
        "schema": SUMMARY_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "array_job_id": str(array_job_id),
        "selection": tasks[0]["selection"],
        "task_artifacts_sha256": {
            path.name: file_sha256(path) for path in task_paths
        },
        "task_gates": {
            str(task_id): tasks[task_id]["gates"] for task_id in (0, 1)
        },
        "common_provenance": {
            key: tasks[0]["provenance"].get(key) for key in COMMON_PROVENANCE_KEYS
        },
        "pass": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--array-job-id")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SUMMARY_SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit the FEM native diagnostic finalizer through SLURM")
    if not args.array_job_id:
        raise SystemExit("--array-job-id is required")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing diagnostic finalization from a dirty worktree")
    job_dir = (
        ROOT
        / "results/corpus_v4/fem_native_diagnostic/jobs"
        / f"job_{args.array_job_id}"
    )
    summary = finalize(job_dir, args.array_job_id)
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if current_head != summary["common_provenance"]["git_head"]:
        raise RuntimeError("finalizer and diagnostic tasks use different commits")
    executed_batch_script = Path(
        os.environ.get("PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT", "")
    )
    if not executed_batch_script.is_file():
        raise RuntimeError("exact executed finalizer batch script is unavailable")
    summary["finalizer_provenance"] = {
        "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "git_head": current_head,
        "source_sha256": file_sha256(Path(__file__)),
        "executed_batch_script": {
            "path": str(executed_batch_script),
            "sha256": file_sha256(executed_batch_script),
        },
    }
    output = job_dir / "summary.json"
    atomic_write(output, summary)
    print(output.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
