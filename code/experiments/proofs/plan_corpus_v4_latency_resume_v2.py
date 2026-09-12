#!/usr/bin/env python3
"""Authenticate the complete latency array and emit its accepted set."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_latency_contract_v2 import (  # noqa: E402
    EXPECTED_LAYOUTS,
    PENDING_SCHEMA,
    PREFLIGHT_SACCT_FIELDS,
    SCHEMA_PREFIX,
    TASK_MANIFEST_SCHEMA,
    TASK_RESULT_SCHEMA,
    load_json,
    resolve_repo_path,
    validate_terminal_array_completion,
    validate_execution_lock,
    validate_plan,
    validate_preflight_admission,
    validate_protocol,
    validate_root_closure,
)
from finalize_corpus_v4_latency_v2 import (  # noqa: E402
    load_admitted_mesh_identities,
    load_expected_references,
    validate_full_task_result,
)
from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402


TASK_SCHEMA = TASK_RESULT_SCHEMA
ARTIFACT_MANIFEST_SCHEMA = TASK_MANIFEST_SCHEMA
CANDIDATE_SCHEMA = f"{SCHEMA_PREFIX}-candidate-index.v1"
ACCEPTED_SCHEMA = f"{SCHEMA_PREFIX}-accepted-set.v1"


def _parse_sacct(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) != len(PREFLIGHT_SACCT_FIELDS):
            raise ValueError("sacct row field count differs from the frozen query")
        records.append(dict(zip(PREFLIGHT_SACCT_FIELDS, values)))
    return records


def _query_sacct(job_ids: list[str]) -> list[dict[str, str]]:
    """Query live scheduler state; production exposes no fixture path."""
    if not job_ids:
        return []
    query = subprocess.run(
        [
            "sacct", "-X", "-n", "-P", "-j", ",".join(sorted(set(job_ids))),
            f"--format={','.join(PREFLIGHT_SACCT_FIELDS)}",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0:
        raise RuntimeError("sacct query failed")
    return _parse_sacct(query.stdout)


def _manifest_candidates(root: Path) -> tuple[str, list[Path]]:
    """Return artifacts from exactly one canonical full-array job root."""
    resolved = root.resolve()
    canonical_parent = (
        ROOT / "results/corpus_v4/latency_fem_v2/jobs/attempts"
    ).resolve()
    if root.is_symlink() or not root.is_dir() or resolved.parent != canonical_parent:
        raise ValueError("attempt root is not one canonical latency job directory")
    match = re.fullmatch(r"job_([0-9]+)", resolved.name)
    if match is None:
        raise ValueError("attempt root must end in job_<array-job-id>")
    sibling_attempts = list(canonical_parent.glob("job_*"))
    failure_parent = canonical_parent.parent / "failures"
    failure_jobs = (
        sorted(path for path in failure_parent.glob("job_*") if path.exists())
        if failure_parent.is_dir()
        else []
    )
    if sibling_attempts != [resolved] or failure_jobs:
        raise ValueError("latency study contains evidence from another full-array dispatch")
    expected_names = {f"task_{task_id:03d}" for task_id in range(EXPECTED_LAYOUTS)}
    children = list(root.iterdir())
    if (
        {child.name for child in children} != expected_names
        or any(child.is_symlink() or not child.is_dir() for child in children)
    ):
        raise ValueError("full-array job root does not contain exact tasks 0..305")
    candidates: list[Path] = []
    for task_id in range(EXPECTED_LAYOUTS):
        task_root = root / f"task_{task_id:03d}"
        task_files = list(task_root.iterdir())
        if (
            {path.name for path in task_files} != {"TASK_MANIFEST.json", "result.json"}
            or any(path.is_symlink() or not path.is_file() for path in task_files)
        ):
            raise ValueError(f"full-array task {task_id} artifact inventory differs")
        candidates.append(task_root / "TASK_MANIFEST.json")
    return match.group(1), candidates


def _candidate(
    manifest_path: Path,
    *,
    tasks: list[dict[str, Any]],
    bindings: Mapping[str, str],
    preflight_admission: Mapping[str, str],
    expected_source_git_head: str,
    expected_repetitions: int,
    block_median_ratio_max: float,
    expected_array_job_id: str,
    lock: Mapping[str, Any],
    protocol: Mapping[str, Any],
    references: Mapping[int, Sequence[float]],
    mesh_identities: Mapping[int, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    record: dict[str, Any] = {
        "manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "reason": None,
        "task_id": None,
        "valid_artifact": False,
    }
    try:
        manifest = load_json(manifest_path)
        result_path = manifest_path.parent / "result.json"
        if (
            set(manifest) != {"files_sha256", "schema"}
            or manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA
            or manifest.get("files_sha256") != {"result.json": sha256_file(result_path)}
        ):
            raise ValueError("artifact manifest is invalid")
        result = load_json(result_path)
        task_id = result.get("task", {}).get("task_id")
        if type(task_id) is not int or task_id < 0 or task_id >= EXPECTED_LAYOUTS:
            raise ValueError("task ID is outside 0..305")
        task = tasks[task_id]
        validate_full_task_result(
            result,
            task=task,
            bindings=bindings,
            preflight_admission=preflight_admission,
            checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
            external_solver_sha256=protocol["solver_workflow"]["inductance"]["binary_sha256"],
            fem_v2_dataset_admission=protocol["inputs"]["fem_v2_dataset_admission"],
            expected_source_git_head=expected_source_git_head,
            locked_source_sha256=lock["source_sha256"],
            expected_runtime=protocol["runtime"],
            expected_array_job_id=expected_array_job_id,
            expected_reference=references[task["layout_id"]],
            expected_mesh_identity=mesh_identities[task["layout_id"]],
            expected_repetitions=expected_repetitions,
            block_median_ratio_max=block_median_ratio_max,
            reference_agreement_tolerance=float(
                protocol["solver_workflow"]["reference_agreement_max_relative_error"]
            ),
        )
        record.update({"task_id": task_id, "valid_artifact": True})
        return record, result
    except (KeyError, OSError, TypeError, ValueError) as exc:
        record["reason"] = str(exc)
        return record, None


def _completion(
    result: Mapping[str, Any], accounting: list[dict[str, str]]
) -> dict[str, str] | None:
    scheduler = result.get("provenance", {}).get("scheduler", {})
    completion = validate_terminal_array_completion(scheduler, accounting)
    if completion is None or set(completion) != set(PREFLIGHT_SACCT_FIELDS):
        return None
    elapsed = completion.get("ElapsedRaw", "")
    if (
        completion.get("Partition") != "nextgen"
        or completion.get("Timelimit") != "02:00:00"
        or completion.get("Restarts") != "0"
        or not completion.get("NodeList")
        or completion.get("NodeList") in {"(null)", "None", "Unknown"}
        or not elapsed.isdigit()
        or not 1 <= int(elapsed) <= 7200
    ):
        return None
    return completion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--expected-task-manifest-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--preflight-admission", type=Path, required=True)
    parser.add_argument("--expected-preflight-admission-sha256", required=True)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    protocol, protocol_sha = validate_protocol(args.protocol, args.expected_protocol_sha256)
    panel_path = args.plan.parent / "panel_records.jsonl"
    plan, tasks, panel, plan_sha, task_sha, panel_sha = validate_plan(
        args.plan,
        args.task_manifest,
        panel_path,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_task_manifest_sha256=args.expected_task_manifest_sha256,
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=args.plan,
        tasks=tasks,
        panel_records=panel,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock,
        args.expected_execution_lock_sha256,
        protocol_sha256=protocol_sha,
        plan_sha256=plan_sha,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    bindings = {
        "execution_lock_sha256": lock_sha,
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_sha,
    }
    _, admission_reference = validate_preflight_admission(
        args.preflight_admission,
        args.expected_preflight_admission_sha256,
        bindings=bindings,
        expected_source_git_head=args.expected_source_git_head,
        tasks=tasks,
        lock=lock,
        checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
    )
    candidates: list[dict[str, Any]] = []
    valid: list[tuple[dict[str, Any], dict[str, Any]]] = []
    expected_repetitions = int(protocol["gnn_timing"]["measured_repetitions"])
    block_median_ratio_max = float(
        protocol["gnn_timing"]["block_median_ratio_max"]
    )
    references = load_expected_references(protocol)
    mesh_identities = load_admitted_mesh_identities(protocol)
    array_job_id, manifest_paths = _manifest_candidates(args.attempt_root)
    for path in manifest_paths:
        candidate, result = _candidate(
            path,
            tasks=tasks,
            bindings=bindings,
            preflight_admission=admission_reference,
            expected_source_git_head=args.expected_source_git_head,
            expected_repetitions=expected_repetitions,
            block_median_ratio_max=block_median_ratio_max,
            expected_array_job_id=array_job_id,
            lock=lock,
            protocol=protocol,
            references=references,
            mesh_identities=mesh_identities,
        )
        candidates.append(candidate)
        if result is not None:
            valid.append((candidate, result))
    accounting = _query_sacct([array_job_id])
    accepted_by_task: dict[int, dict[str, Any]] = {}
    for candidate, result in valid:
        completion = _completion(result, accounting)
        if completion is None:
            candidate["reason"] = "missing exact COMPLETED/0:0 terminal accounting"
            continue
        task_id = int(candidate["task_id"])
        if task_id in accepted_by_task:
            raise ValueError(f"ambiguous duplicate completed attempts for task {task_id}")
        candidate["terminally_accepted"] = True
        accepted_by_task[task_id] = {
            "manifest_path": candidate["manifest_path"],
            "manifest_sha256": candidate["manifest_sha256"],
            "scheduler_completion": completion,
            "task_id": task_id,
        }
    pending = sorted(set(range(EXPECTED_LAYOUTS)) - set(accepted_by_task))
    if pending:
        raise ValueError(
            "full-array evidence is incomplete; this protocol forbids within-study "
            "retries, so no accepted set can be emitted"
        )
    args.out_dir.mkdir(parents=True, exist_ok=False)
    candidate_path = args.out_dir / "candidate_index.json"
    atomic_write_json(
        candidate_path,
        {
            "entries": candidates,
            "full_array_job_id": array_job_id,
            "preflight_admission": admission_reference,
            "schema": CANDIDATE_SCHEMA,
        },
    )
    common = {
        **bindings,
        "full_array_job_id": array_job_id,
        "preflight_admission": admission_reference,
        "candidate_index": {
            "path": candidate_path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(candidate_path),
        },
    }
    atomic_write_json(
        args.out_dir / "accepted_artifact_set.json",
        {
            **common,
            "entries": [accepted_by_task[index] for index in sorted(accepted_by_task)],
            "n_accepted": len(accepted_by_task),
            "n_expected": EXPECTED_LAYOUTS,
            "schema": ACCEPTED_SCHEMA,
        },
    )
    atomic_write_json(
        args.out_dir / "pending_task_set.json",
        {
            **bindings,
            "full_array_job_id": array_job_id,
            "preflight_admission": admission_reference,
            "n_pending": len(pending),
            "pending_task_ids": pending,
            "schema": PENDING_SCHEMA,
        },
    )
    print(
        json.dumps(
            {"accepted": len(accepted_by_task), "pending": len(pending), "status": "planned"},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
