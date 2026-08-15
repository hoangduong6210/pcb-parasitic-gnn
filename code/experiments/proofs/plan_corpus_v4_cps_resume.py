#!/usr/bin/env python3
"""Validate explicit task attempts and emit accepted/pending artifact registries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    load_json,
    require_file_sha256,
    sha256_file,
)
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    SCHEMA as TASK_SCHEMA,
    evaluate_result,
    scheduler_resource_contract_matches,
    validate_execution_lock,
    validate_frozen_inputs,
)


CANDIDATE_SCHEMA = "pcb-gnn.cps-multifidelity-candidate-index.v1"
ACCEPTED_SCHEMA = "pcb-gnn.cps-multifidelity-accepted-artifact-set.v1"
PENDING_SCHEMA = "pcb-gnn.cps-multifidelity-pending-task-set.v1"


def register_valid_attempt(
    valid_by_task: dict[int, dict[str, Any]],
    task_index: int,
    accepted: dict[str, Any],
) -> None:
    """Register exactly one valid artifact per canonical task."""
    if task_index in valid_by_task:
        raise RuntimeError("ambiguous duplicate valid attempts for one task")
    valid_by_task[task_index] = accepted


def load_candidate_index(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Load one candidate index only after verifying its external byte hash."""
    require_file_sha256(path, expected_sha256, "candidate index")
    index = load_json(path)
    if index.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError(f"unexpected candidate-index schema: {path}")
    return index


def resolve_repo_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("candidate artifact path must be repository-relative")
    resolved = (ROOT / path).resolve()
    if ROOT.resolve() not in resolved.parents:
        raise ValueError("candidate artifact escapes the repository")
    return resolved


def validate_task_artifact(
    payload: dict[str, Any],
    expected: dict[str, Any],
    *,
    plan_sha256: str,
    protocol_sha256: str,
    manifest_sha256: str,
    protocol: dict[str, Any],
    execution_lock: dict[str, Any],
    execution_lock_sha256: str,
) -> None:
    gate = payload.get("numerical_resource_gate", {})
    provenance = payload.get("provenance", {})
    execution = payload.get("execution", {})
    worker = execution.get("worker_result") or {}
    if (
        payload.get("schema") != TASK_SCHEMA
        or payload.get("task_pass") is not True
        or payload.get("task_index") != expected["task_index"]
        or payload.get("solver_contract_id") != expected["solver_contract_id"]
        or payload.get("geometry", {}).get("layout_id") != expected["layout_id"]
        or payload.get("geometry", {}).get("geometry_sha256")
        != expected["geometry_sha256"]
        or payload.get("fidelity", {}).get("fidelity_id") != expected["fidelity_id"]
    ):
        raise ValueError("task identity does not match the frozen manifest")
    recomputed_gate = evaluate_result(execution, protocol, expected["fidelity_id"])
    if gate != recomputed_gate or recomputed_gate.get("pass") is not True:
        raise ValueError("task numerical/resource gate does not recompute exactly")
    if (
        provenance.get("plan_sha256") != plan_sha256
        or provenance.get("final_plan_sha256") != plan_sha256
        or provenance.get("protocol_sha256") != protocol_sha256
        or provenance.get("manifest_sha256") != manifest_sha256
        or provenance.get("final_manifest_sha256") != manifest_sha256
        or provenance.get("source_stable") is not True
        or provenance.get("git_dirty_paths")
        or provenance.get("final_git_dirty_paths")
        or provenance.get("untracked_code")
        or provenance.get("final_untracked_code")
        or provenance.get("execution_lock_sha256") != execution_lock_sha256
    ):
        raise ValueError("task provenance is not stable and clean")
    environment = provenance.get("environment", {})
    if (
        environment.get("python") != protocol["runtime"]["python"]
        or environment.get("package_versions") != protocol["runtime"]["packages"]
        or environment.get("thread_environment") != protocol["runtime"]["threads"]
    ):
        raise ValueError("task environment differs from the protocol")
    source_hashes = provenance.get("source_file_sha256", {})
    final_source_hashes = provenance.get("final_source_file_sha256", {})
    if (
        source_hashes != final_source_hashes
        or source_hashes != execution_lock["source_sha256"]
    ):
        raise ValueError("task source hash map changed during execution")
    for name, expected_sha in protocol["computational_sources"].items():
        if source_hashes.get(name) != expected_sha:
            raise ValueError(f"task computational source mismatch: {name}")
    tracked_batch = {
        "cps_fem_r3_p16": "code/jobs/submit_corpus_v4_cps_r3.sh",
        "cps_fem_r4_p16": "code/jobs/submit_corpus_v4_cps_r4.sh",
    }[expected["fidelity_id"]]
    batch = provenance.get("executed_batch_script", {})
    if (
        batch.get("sha256") != source_hashes.get(tracked_batch)
        or provenance.get("final_executed_batch_script_sha256") != batch.get("sha256")
        or provenance.get("git_head") != provenance.get("final_git_head")
    ):
        raise ValueError("task batch/source identity is not stable")
    slurm = provenance.get("slurm", {})
    scheduler = slurm.get("scheduler_record", {})
    profile = protocol["resource_profiles"][expected["fidelity_id"]]["slurm"]
    expected_time = (
        f"{int(profile['time_s']) // 3600:02d}:"
        f"{(int(profile['time_s']) % 3600) // 60:02d}:"
        f"{int(profile['time_s']) % 60:02d}"
    )
    if (
        slurm.get("canonical_task_index") != expected["task_index"]
        or slurm.get("partition") != profile["partition"]
        or int(slurm.get("requested_cpus_per_task", 0))
        != int(profile["cpus_per_task"])
        or scheduler.get("ArrayJobId") != slurm.get("array_job_id")
        or int(scheduler.get("ArrayTaskId", -1)) != int(slurm.get("array_task_id", -2))
        or scheduler.get("Partition") != profile["partition"]
        or not scheduler_resource_contract_matches(
            scheduler,
            allocated_cpus_per_task=int(slurm.get("allocated_cpus_per_task", 0)),
            mem_per_node_mb=int(slurm.get("mem_per_node_mb", 0)),
            profile=profile,
        )
        or scheduler.get("TimeLimit") != expected_time
        or int(slurm.get("scheduler_array_record", {}).get("ArrayTaskThrottle", -1))
        != int(profile["max_concurrent"])
    ):
        raise ValueError("task scheduler record differs from the protocol")
    fidelity = payload["fidelity"]
    if (
        worker.get("refine") != fidelity.get("refine")
        or worker.get("pad_mm") != fidelity.get("pad_mm")
        or worker.get("eps_r") != 4.2
    ):
        raise ValueError("task worker output does not match its fidelity")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-index", type=Path, action="append", default=[])
    parser.add_argument(
        "--expected-candidate-index-sha256", action="append", default=[]
    )
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, _, manifest_rows, protocol_sha256, manifest_sha256 = (
        validate_frozen_inputs(
            args.protocol,
            args.plan,
            args.expected_plan_sha256,
            args.manifest,
        )
    )
    expected_by_task = {row["task_index"]: row for row in manifest_rows}
    if len(args.candidate_index) != len(args.expected_candidate_index_sha256):
        raise ValueError("each candidate index requires one externally pinned SHA-256")
    candidate_index_records = [
        {"path": str(path), "sha256": expected_sha256}
        for path, expected_sha256 in zip(
            args.candidate_index, args.expected_candidate_index_sha256
        )
    ]
    execution_lock, execution_lock_sha256 = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    valid_by_task: dict[int, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    seen_index_entries: set[tuple[str, str]] = set()

    for index_path, expected_index_sha256 in zip(
        args.candidate_index, args.expected_candidate_index_sha256
    ):
        index = load_candidate_index(index_path, expected_index_sha256)
        for entry in index.get("entries", []):
            identity = (str(entry.get("path")), str(entry.get("sha256")))
            if identity in seen_index_entries:
                continue
            seen_index_entries.add(identity)
            try:
                path = resolve_repo_path(identity[0])
                observed_sha = sha256_file(path)
                if observed_sha != identity[1]:
                    raise ValueError("candidate byte hash mismatch")
                payload = load_json(path)
                task_index = int(payload.get("task_index", -1))
                expected = expected_by_task.get(task_index)
                if expected is None:
                    raise ValueError("candidate task is outside the frozen manifest")
                validate_task_artifact(
                    payload,
                    expected,
                    plan_sha256=args.expected_plan_sha256,
                    protocol_sha256=protocol_sha256,
                    manifest_sha256=manifest_sha256,
                    protocol=protocol,
                    execution_lock=execution_lock,
                    execution_lock_sha256=execution_lock_sha256,
                )
                accepted = {
                    "artifact_sha256": observed_sha,
                    "fidelity_id": expected["fidelity_id"],
                    "geometry_sha256": expected["geometry_sha256"],
                    "layout_id": expected["layout_id"],
                    "path": path.relative_to(ROOT).as_posix(),
                    "task_index": task_index,
                }
                register_valid_attempt(valid_by_task, task_index, accepted)
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
                rejected.append({"entry": entry, "reason": str(error)})

    pending = [
        {
            "geometry_sha256": row["geometry_sha256"],
            "layout_id": row["layout_id"],
            "task_index": row["task_index"],
        }
        for row in manifest_rows
        if row["task_index"] not in valid_by_task
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        args.out / "accepted_artifact_set.json",
        {
            "entries": [valid_by_task[index] for index in sorted(valid_by_task)],
            "candidate_index_sha256": candidate_index_records,
            "fidelity_id": manifest_rows[0]["fidelity_id"],
            "candidate_index_sha256": candidate_index_records,
            "execution_lock_sha256": execution_lock_sha256,
            "manifest_sha256": manifest_sha256,
            "n_accepted": len(valid_by_task),
            "n_expected": len(manifest_rows),
            "plan_sha256": args.expected_plan_sha256,
            "protocol_sha256": protocol_sha256,
            "rejected_candidates": rejected,
            "schema": ACCEPTED_SCHEMA,
        },
    )
    atomic_write_json(
        args.out / "pending_task_set.json",
        {
            "fidelity_id": manifest_rows[0]["fidelity_id"],
            "execution_lock_sha256": execution_lock_sha256,
            "manifest_sha256": manifest_sha256,
            "pending": pending,
            "plan_sha256": args.expected_plan_sha256,
            "schema": PENDING_SCHEMA,
        },
    )
    print(
        json.dumps(
            {
                "fidelity_id": manifest_rows[0]["fidelity_id"],
                "n_accepted": len(valid_by_task),
                "n_pending": len(pending),
                "n_rejected": len(rejected),
                "runtime_python": protocol["runtime"]["python"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
