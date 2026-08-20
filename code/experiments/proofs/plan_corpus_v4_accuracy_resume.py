#!/usr/bin/env python3
"""Index immutable attempts and freeze the accepted Corpus V4 accuracy set."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for _directory in (ROOT / "code/core", Path(__file__).resolve().parent):
    sys.path.insert(0, str(_directory))

from scientific_artifact import atomic_write_json, load_json, sha256_file  # noqa: E402
from corpus_v4_accuracy_contract import (  # noqa: E402
    ACCEPTED_SCHEMA,
    CANDIDATE_SCHEMA,
    PENDING_SCHEMA,
    TASK_RESULT_SCHEMA,
    canonical_task_row,
    canonical_tres,
    require_repo_relative_path,
    resolve_repo_path,
    runtime_identity,
    tres_equivalent,
    validate_execution_lock,
    validate_file_manifest,
    validate_plan,
    validate_pending_set,
    validate_protocol,
    validate_root_closure,
)
from run_corpus_v4_accuracy_task import (  # noqa: E402
    _smoke_hook,
    expected_bundle_payload,
    expected_bundle_specs,
)
from safe_npz_bundle import BundleLimits, load_safe_npz_bundle  # noqa: E402
from corpus_v4_accuracy_contract import load_jsonl  # noqa: E402


def validate_attempt(
    manifest_path: Path,
    *,
    task_row: dict[str, Any],
    protocol_sha256: str,
    plan_sha256: str,
    task_manifest_sha256: str,
    lock: dict[str, Any],
    lock_sha256: str,
    expected_source_git_head: str,
) -> dict[str, Any]:
    """Validate an attempt's complete byte closure and scientific identity."""
    manifest = validate_file_manifest(manifest_path)
    result_path = manifest_path.parent / "result.json"
    if result_path.name not in manifest["files_sha256"]:
        raise ValueError("attempt manifest does not bind result.json")
    result = load_json(result_path)
    task_id = int(task_row["task_id"])
    canonical = canonical_task_row(task_id)
    if result.get("schema") != TASK_RESULT_SCHEMA:
        raise ValueError("unexpected task-result schema")
    identity = result.get("task", {})
    if any(identity.get(name) != value for name, value in canonical.items()):
        raise ValueError("task result identity differs from the frozen row")
    bindings = result.get("bindings", {})
    expected_bindings = {
        "evaluation_dataset_sha256": task_row["evaluation_dataset_sha256"],
        "execution_lock_sha256": lock_sha256,
        "expected_source_git_head": expected_source_git_head,
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "task_manifest_sha256": task_manifest_sha256,
    }
    if set(bindings) != {*expected_bindings, "retry_pending_set"} or any(
        bindings.get(name) != value for name, value in expected_bindings.items()
    ):
        raise ValueError("task result input bindings differ from the frozen roots")
    retry_pending = bindings.get("retry_pending_set")
    if retry_pending is not None:
        if not isinstance(retry_pending, dict) or set(retry_pending) != {"path", "sha256"}:
            raise ValueError("retry pending-set identity is malformed")
        pending_path = resolve_repo_path(retry_pending["path"], "retry pending set")
        _, pending_ids, _ = validate_pending_set(
            pending_path,
            expected_sha256=retry_pending["sha256"],
            bindings={
                name: expected_bindings[name]
                for name in (
                    "execution_lock_sha256",
                    "plan_sha256",
                    "protocol_sha256",
                    "task_manifest_sha256",
                )
            },
        )
        if task_id not in pending_ids:
            raise ValueError("retry task was not admitted by the bound pending set")
    provenance = result.get("provenance", {})
    if (
        provenance.get("source_file_sha256") != lock["source_sha256"]
        or provenance.get("final_source_file_sha256") != lock["source_sha256"]
        or provenance.get("git_dirty_paths") != []
        or provenance.get("final_git_dirty_paths") != []
        or provenance.get("untracked_source_paths") != []
        or provenance.get("final_untracked_source_paths") != []
        or provenance.get("source_git_head") != provenance.get("final_git_head")
        or provenance.get("source_git_head") != expected_source_git_head
    ):
        raise ValueError("attempt source closure is dirty, mixed, or unstable")
    if result.get("integrity", {}).get("passed") is not True:
        raise ValueError("task integrity gate did not pass")
    if result.get("membership_sha256") != {
        "partition_family_ids": task_row["partition_family_ids_sha256"],
        "partition_layout_ids": task_row["partition_layout_ids_sha256"],
        "r4_test_layout_ids": task_row["r4_test_layout_ids_sha256"],
    }:
        raise ValueError("task membership hashes differ from the frozen row")
    if result.get("evaluation") != {
        "test_or_r4_used_for_normalization_optimization_or_acceptance": False,
        "test_predictions_emitted": False,
    }:
        raise ValueError("task result does not prove the checkpoint-before-test boundary")
    training = result.get("training", {})
    if (
        training.get("epochs_completed") != 200
        or training.get("final_epoch") != 200
        or training.get("model_selection")
        != "fixed final epoch; validation diagnostic only"
    ):
        raise ValueError("task did not preserve the fixed final-epoch contract")
    scheduler = provenance.get("scheduler", {})
    scheduler_record = scheduler.get("scheduler_record", {})
    if (
        scheduler.get("array_task_id") != task_id
        or scheduler_record.get("ArrayTaskId") != str(task_id)
        or scheduler_record.get("JobState") not in {"RUNNING", "COMPLETING"}
        or scheduler.get("requested_cpus_per_task") != 8
        or scheduler.get("requested_memory_gib") != 48
    ):
        raise ValueError("task scheduler receipt differs from the frozen identity")
    software = provenance.get("software", {})
    if {
        name: software.get(name)
        for name in ("numpy_distribution", "python", "torch_distribution")
    } != runtime_identity():
        raise ValueError("task runtime differs from the frozen proof environment")
    expected_files = {
        "bundle/metadata.json",
        "bundle/weights_and_norm.npz",
        "learning_curve.jsonl",
        "result.json",
        "smoke_examples.jsonl",
    }
    if set(manifest["files_sha256"]) != expected_files:
        raise ValueError("attempt artifact set is not exact")
    checkpoint = result.get("checkpoint", {})
    if (
        checkpoint.get("metadata_sha256") != manifest["files_sha256"]["bundle/metadata.json"]
        or checkpoint.get("archive_sha256") != manifest["files_sha256"]["bundle/weights_and_norm.npz"]
        or checkpoint.get("smoke_examples_sha256") != manifest["files_sha256"]["smoke_examples.jsonl"]
    ):
        raise ValueError("checkpoint hashes differ from the task artifact manifest")
    smoke_rows = load_jsonl(manifest_path.parent / "smoke_examples.jsonl")
    if (
        len(smoke_rows) != 5
        or [row.get("layout_id") for row in smoke_rows]
        != task_row["partitions"]["validation"]["layout_ids"][:5]
    ):
        raise ValueError("checkpoint smoke fixture must contain exactly five layouts")
    curve = load_jsonl(manifest_path.parent / "learning_curve.jsonl")
    if (
        len(curve) != 200
        or [row.get("epoch") for row in curve] != list(range(1, 201))
        or any(
            row.get("schema") != "pcb-gnn.corpus-v4-accuracy-learning-curve.v1"
            or not all(
                type(row.get(name)) in {int, float}
                and math.isfinite(float(row[name]))
                for name in (
                    "learning_rate",
                    "train_loss",
                    "validation_loss_diagnostic_only",
                )
            )
            for row in curve
        )
    ):
        raise ValueError("learning curve is incomplete or malformed")
    load_safe_npz_bundle(
        manifest_path.parent / "bundle",
        expected_metadata_sha256=checkpoint["metadata_sha256"],
        expected_specs=expected_bundle_specs(),
        expected_payload=expected_bundle_payload(
            canonical,
            {
                "evaluation_dataset_sha256": task_row["evaluation_dataset_sha256"],
                "execution_lock_sha256": lock_sha256,
                "plan_sha256": plan_sha256,
                "protocol_sha256": protocol_sha256,
                "task_manifest_sha256": task_manifest_sha256,
            },
        ),
        smoke_hook=_smoke_hook(smoke_rows),
        expected_smoke_input_sha256=checkpoint["smoke_examples_sha256"],
        require_smoke=True,
        limits=BundleLimits(max_archive_bytes=64 * 1024 * 1024, max_expanded_bytes=128 * 1024 * 1024),
    )
    return result


def completed_slurm_accounting(result: dict[str, Any]) -> dict[str, str]:
    """Require terminal success for the exact array component that wrote an attempt."""
    scheduler = result["provenance"]["scheduler"]
    component = f"{scheduler['array_job_id']}_{scheduler['array_task_id']}"
    query = subprocess.run(
        [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            component,
            "--format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    fields = (
        "JobIDRaw",
        "JobID",
        "State",
        "ExitCode",
        "ElapsedRaw",
        "ReqTRES",
        "AllocTRES",
    )
    records: list[dict[str, str]] = []
    for line in query.stdout.splitlines():
        values = line.split("|")
        if len(values) >= len(fields):
            records.append(dict(zip(fields, values)))
    matches = [record for record in records if record["JobID"] == component]
    if (
        query.returncode != 0
        or len(matches) != 1
        or matches[0]["State"].split()[0].rstrip("+") != "COMPLETED"
        or matches[0]["ExitCode"] != "0:0"
    ):
        raise ValueError(f"task {component} lacks exact successful SLURM accounting")
    normalized = {
        name: matches[0][name]
        for name in ("JobIDRaw", "State", "ExitCode", "ElapsedRaw", "ReqTRES", "AllocTRES")
    }
    normalized["State"] = "COMPLETED"
    in_run = scheduler.get("scheduler_record", {})
    if any(
        not tres_equivalent(normalized[name], in_run.get(name))
        for name in ("ReqTRES", "AllocTRES")
    ):
        raise ValueError(
            f"task {component} terminal resources differ from its in-run receipt"
        )
    for name in ("ReqTRES", "AllocTRES"):
        normalized[name] = canonical_tres(normalized[name])
    return normalized


def build_candidate_index(attempt_roots: list[Path]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for root in attempt_roots:
        if root.is_symlink():
            raise ValueError("attempt root must not be a symlink")
        resolved_root = root.resolve()
        try:
            resolved_root.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise ValueError("attempt root escapes the repository") from exc
        for task_id in range(25):
            path = resolved_root / f"task_{task_id:02d}" / "TASK_MANIFEST.json"
            if path.exists() and (path.is_symlink() or not path.is_file()):
                raise ValueError("candidate manifest must be a regular non-symlink file")
            if path.is_file():
                relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
                entries.append(
                    {
                        "path": require_repo_relative_path(relative, "candidate manifest"),
                        "sha256": sha256_file(path),
                        "task_id": task_id,
                    }
                )
    return {"entries": entries, "schema": CANDIDATE_SCHEMA}


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
    parser.add_argument("--attempt-root", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        raise SystemExit("refusing to overwrite a non-empty resume-plan directory")
    protocol, protocol_sha = validate_protocol(args.protocol, args.expected_protocol_sha256)
    plan, rows, plan_sha, manifest_sha = validate_plan(
        args.plan,
        args.task_manifest,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_manifest_sha256=args.expected_task_manifest_sha256,
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=args.plan,
        task_rows=rows,
        task_manifest_sha256=manifest_sha,
        lock=lock,
        lock_sha256=lock_sha,
    )
    if runtime_identity() != protocol["runtime"]:
        raise SystemExit("resume validation runtime differs from the frozen proof environment")
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    if current_head != args.expected_source_git_head:
        raise SystemExit("resume source commit differs from the external trust root")

    candidate = build_candidate_index(args.attempt_root)
    args.out.mkdir(parents=True, exist_ok=True)
    candidate_path = args.out / "candidate_index.json"
    atomic_write_json(candidate_path, candidate)
    accepted_by_task: dict[int, dict[str, Any]] = {}
    ambiguous_tasks: set[int] = set()
    rejected: list[dict[str, Any]] = []
    for entry in candidate["entries"]:
        try:
            task_id = entry["task_id"]
            if type(task_id) is not int or not 0 <= task_id < 25:
                raise ValueError("candidate task ID is invalid")
            path = resolve_repo_path(entry["path"], "candidate manifest")
            if sha256_file(path) != entry["sha256"]:
                raise ValueError("candidate manifest byte hash mismatch")
            result = validate_attempt(
                path,
                task_row=rows[task_id],
                protocol_sha256=protocol_sha,
                plan_sha256=plan_sha,
                task_manifest_sha256=manifest_sha,
                lock=lock,
                lock_sha256=lock_sha,
                expected_source_git_head=args.expected_source_git_head,
            )
            accounting = completed_slurm_accounting(result)
            record = {
                "manifest_path": entry["path"],
                "manifest_sha256": entry["sha256"],
                "scheduler_completion": accounting,
                "task_id": task_id,
            }
            prior = accepted_by_task.get(task_id)
            if prior is not None and prior != record:
                ambiguous_tasks.add(task_id)
                del accepted_by_task[task_id]
                raise ValueError("multiple distinct valid attempts require explicit adjudication")
            if task_id in ambiguous_tasks:
                raise ValueError("task has multiple valid attempts and remains unadjudicated")
            accepted_by_task[task_id] = record
        except (IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            rejected.append({"candidate": entry, "reason": str(error)})

    accepted_entries = [accepted_by_task[index] for index in sorted(accepted_by_task)]
    pending_entries = [canonical_task_row(index) for index in range(25) if index not in accepted_by_task]
    bindings = {
        "execution_lock_sha256": lock_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": manifest_sha,
    }
    candidate_relative = candidate_path.resolve().relative_to(ROOT.resolve()).as_posix()
    atomic_write_json(
        args.out / "accepted_artifact_set.json",
        {
            **bindings,
            "candidate_index": {
                "path": candidate_relative,
                "sha256": sha256_file(candidate_path),
            },
            "entries": accepted_entries,
            "n_accepted": len(accepted_entries),
            "n_expected": 25,
            "rejected_candidates": rejected,
            "schema": ACCEPTED_SCHEMA,
        },
    )
    atomic_write_json(
        args.out / "pending_task_set.json",
        {
            **bindings,
            "n_pending": len(pending_entries),
            "pending": pending_entries,
            "schema": PENDING_SCHEMA,
        },
    )
    print(json.dumps({"accepted": len(accepted_entries), "pending": len(pending_entries), "rejected": len(rejected)}, sort_keys=True))


if __name__ == "__main__":
    main()
