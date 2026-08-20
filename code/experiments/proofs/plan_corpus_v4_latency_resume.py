#!/usr/bin/env python3
"""Admit terminal latency attempts and emit an exact retry set."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_latency_contract import (  # noqa: E402
    EXPECTED_LAYOUTS,
    PENDING_SCHEMA,
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
from finalize_corpus_v4_latency import validate_timing_record  # noqa: E402
from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402


TASK_SCHEMA = TASK_RESULT_SCHEMA
ARTIFACT_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task-artifact-manifest.v2"
CANDIDATE_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-candidate-index.v3"
ACCEPTED_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-accepted-set.v3"


def _parse_sacct(text: str) -> list[dict[str, str]]:
    fields = (
        "JobID",
        "JobIDRaw",
        "Account",
        "State",
        "ExitCode",
        "ElapsedRaw",
        "ReqTRES",
        "AllocTRES",
    )
    records: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        values = line.rstrip("\n").split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) != len(fields):
            raise ValueError("sacct row field count differs from the frozen query")
        records.append(dict(zip(fields, values)))
    return records


def _query_sacct(job_ids: list[str]) -> list[dict[str, str]]:
    """Query live scheduler state; production exposes no fixture path."""
    if not job_ids:
        return []
    query = subprocess.run(
        [
            "sacct", "-X", "-n", "-P", "-j", ",".join(sorted(set(job_ids))),
            "--format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if query.returncode != 0:
        raise RuntimeError("sacct query failed")
    return _parse_sacct(query.stdout)


def _manifest_candidates(roots: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError("attempt root escapes the repository") from exc
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"attempt root is not a regular directory: {root}")
        candidates.extend(root.glob("job_*/task_*/TASK_MANIFEST.json"))
    unique = sorted(set(path.resolve() for path in candidates))
    return [Path(path) for path in unique]


def _candidate(
    manifest_path: Path,
    *,
    tasks: list[dict[str, Any]],
    bindings: Mapping[str, str],
    preflight_admission: Mapping[str, str],
    expected_source_git_head: str,
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
            manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA
            or manifest.get("files_sha256") != {"result.json": sha256_file(result_path)}
        ):
            raise ValueError("artifact manifest is invalid")
        result = load_json(result_path)
        task_id = result.get("task", {}).get("task_id")
        if type(task_id) is not int or task_id < 0 or task_id >= EXPECTED_LAYOUTS:
            raise ValueError("task ID is outside 0..305")
        task = tasks[task_id]
        expected_task = {
            "family_id": task["family_id"],
            "geometry_sha256": task["geometry_sha256"],
            "layout_id": task["layout_id"],
            "task_id": task_id,
        }
        if (
            result.get("schema") != TASK_SCHEMA
            or result.get("stage") != "full_array"
            or result.get("task") != expected_task
            or result.get("integrity") != {"passed": True}
            or result.get("provenance", {}).get("source_git_head") != expected_source_git_head
            or any(result.get("bindings", {}).get(name) != digest for name, digest in bindings.items())
            or result.get("bindings", {}).get("preflight_admission")
            != dict(preflight_admission)
        ):
            raise ValueError("result roots, stage, or task identity differ")
        validate_timing_record(result.get("record", {}), expected_repetitions=200)
        record.update({"task_id": task_id, "valid_artifact": True})
        return record, result
    except (KeyError, OSError, TypeError, ValueError) as exc:
        record["reason"] = str(exc)
        return record, None


def _completion(
    result: Mapping[str, Any], accounting: list[dict[str, str]]
) -> dict[str, str] | None:
    scheduler = result.get("provenance", {}).get("scheduler", {})
    return validate_terminal_array_completion(scheduler, accounting)


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
    parser.add_argument("--attempt-root", type=Path, action="append", required=True)
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
    for path in _manifest_candidates(args.attempt_root):
        candidate, result = _candidate(
            path,
            tasks=tasks,
            bindings=bindings,
            preflight_admission=admission_reference,
            expected_source_git_head=args.expected_source_git_head,
        )
        candidates.append(candidate)
        if result is not None:
            valid.append((candidate, result))
    array_jobs = [
        str(result["provenance"]["scheduler"]["array_job_id"])
        for _, result in valid
    ]
    accounting = _query_sacct(array_jobs)
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
    args.out_dir.mkdir(parents=True, exist_ok=False)
    candidate_path = args.out_dir / "candidate_index.json"
    atomic_write_json(
        candidate_path,
        {
            "entries": candidates,
            "preflight_admission": admission_reference,
            "schema": CANDIDATE_SCHEMA,
        },
    )
    common = {
        **bindings,
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
