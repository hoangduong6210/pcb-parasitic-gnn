#!/usr/bin/env python3
"""Close a Corpus V4 accuracy archive after its SLURM finalizer exits cleanly.

This verifier is login-safe: it hashes and validates existing artifacts and
queries scheduler accounting, but never trains a model or invokes a solver.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(_directory))

from corpus_v4_accuracy_contract import (  # noqa: E402
    FINAL_SCHEMA,
    assert_finite_json,
    canonical_task_row,
    load_json,
    load_jsonl,
    require_repo_relative_path,
    resolve_repo_path,
    validate_execution_lock,
    validate_file_manifest,
    validate_plan,
    validate_protocol,
    validate_root_closure,
)
from finalize_corpus_v4_accuracy import (  # noqa: E402
    _validate_accepted_set,
    build_matrices,
    recompute_task_metrics,
)
from plan_corpus_v4_accuracy_resume import validate_attempt  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    require_file_sha256,
    sha256_file,
)


ANALYSIS_SCHEMA = "pcb-gnn.corpus-v4-accuracy-analysis-manifest.v1"
ARCHIVE_SCHEMA = "pcb-gnn.corpus-v4-accuracy-archive.v1"


def _require_git_tracked_clean(paths: list[Path]) -> None:
    relative: list[str] = []
    for path in paths:
        resolved = path.resolve()
        try:
            relative.append(resolved.relative_to(ROOT.resolve()).as_posix())
        except ValueError as exc:
            raise ValueError("tracked closure path escapes the repository") from exc
    relative = sorted(set(relative))
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", *relative],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if tracked.returncode != 0:
        raise ValueError("accuracy closure contains an untracked path")
    status = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", *relative],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError("accuracy closure contains modified or untracked bytes")


def _completed_finalizer(job_id: str) -> dict[str, str]:
    if not job_id.isdigit():
        raise ValueError("finalizer job ID is not a canonical numeric SLURM ID")
    query = subprocess.run(
        [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            job_id,
            "--format=JobIDRaw,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    keys = ("JobIDRaw", "State", "ExitCode", "ElapsedRaw", "ReqTRES", "AllocTRES")
    rows: list[dict[str, str]] = []
    for line in query.stdout.splitlines():
        values = line.split("|")
        if len(values) >= len(keys):
            rows.append(dict(zip(keys, values)))
    matches = [row for row in rows if row["JobIDRaw"] == job_id]
    if (
        query.returncode != 0
        or len(matches) != 1
        or matches[0]["State"].split()[0].rstrip("+") != "COMPLETED"
        or matches[0]["ExitCode"] != "0:0"
    ):
        raise ValueError("finalizer lacks exact COMPLETED/0:0 SLURM accounting")
    receipt = dict(matches[0])
    receipt["State"] = "COMPLETED"
    return receipt


def _verify_analysis_inventory(
    analysis_path: Path,
    expected_sha256: str,
    *,
    accepted_set_path: Path,
    accepted_set_sha256: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if analysis_path.is_symlink() or not analysis_path.is_file():
        raise ValueError("analysis manifest must be a regular non-symlink file")
    require_file_sha256(analysis_path, expected_sha256, "accuracy analysis manifest")
    analysis = load_json(analysis_path)
    expected_names = {
        "accepted_set",
        "checkpoint_index.json",
        "matrices.json",
        "summary.json",
        "task_index.json",
        *(f"predictions/task_{task_id:02d}.jsonl" for task_id in range(25)),
    }
    files = analysis.get("files")
    if (
        set(analysis) != {"files", "schema"}
        or analysis.get("schema") != ANALYSIS_SCHEMA
        or not isinstance(files, dict)
        or set(files) != expected_names
    ):
        raise ValueError("analysis-manifest schema or inventory is not exact")
    expected_local_files = {
        "ANALYSIS_MANIFEST.json",
        *(expected_names - {"accepted_set"}),
    }
    observed_local_files: set[str] = set()
    for child in analysis_path.parent.rglob("*"):
        if child.is_symlink():
            raise ValueError("analysis directory contains a symlink")
        if child.is_file():
            observed_local_files.add(child.relative_to(analysis_path.parent).as_posix())
        elif not child.is_dir():
            raise ValueError("analysis directory contains a non-file artifact")
    if observed_local_files != expected_local_files:
        raise ValueError("analysis directory inventory is not exact")

    accepted_relative = accepted_set_path.resolve().relative_to(ROOT.resolve()).as_posix()
    if files["accepted_set"] != {
        "path": accepted_relative,
        "sha256": accepted_set_sha256,
    }:
        raise ValueError("analysis manifest does not bind the supplied accepted set")
    if accepted_set_path.is_symlink() or not accepted_set_path.is_file():
        raise ValueError("accepted set must be a regular non-symlink file")
    require_file_sha256(accepted_set_path, accepted_set_sha256, "accepted set")

    observed: dict[str, str] = {}
    analysis_root_relative = analysis_path.parent.resolve().relative_to(ROOT.resolve())
    for name in sorted(expected_names - {"accepted_set"}):
        record = files[name]
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError(f"analysis file record is malformed: {name}")
        if record["path"] != name:
            raise ValueError(f"analysis file path is not canonical: {name}")
        repository_relative = (analysis_root_relative / name).as_posix()
        artifact = resolve_repo_path(repository_relative, f"analysis file {name}")
        if artifact.is_symlink() or not artifact.is_file():
            raise ValueError(f"analysis file is missing or a symlink: {name}")
        require_file_sha256(artifact, record["sha256"], name)
        observed[name] = record["sha256"]
    return analysis, observed


def verify_archive(args: argparse.Namespace) -> dict[str, Any]:
    if args.require_git_tracked and not args.check:
        raise ValueError("--require-git-tracked is valid only with --check")
    tracked_paths = [
        args.protocol,
        args.plan,
        args.task_manifest,
        args.plan.parent / "evaluation_dataset.jsonl",
        args.execution_lock,
        args.accepted_set,
        args.analysis_manifest,
    ]
    protocol, protocol_sha = validate_protocol(
        args.protocol, args.expected_protocol_sha256
    )
    plan, task_rows, plan_sha, task_manifest_sha = validate_plan(
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
        task_rows=task_rows,
        task_manifest_sha256=task_manifest_sha,
        lock=lock,
        lock_sha256=lock_sha,
    )
    tracked_paths.extend(
        resolve_repo_path(record["path"], f"protocol input {name}")
        for name, record in protocol["inputs"].items()
    )
    tracked_paths.extend(
        resolve_repo_path(name, "planner source")
        for name in plan["planner_source_sha256"]
    )
    tracked_paths.extend(
        resolve_repo_path(name, "execution source")
        for name in lock["source_sha256"]
    )
    analysis, inventory = _verify_analysis_inventory(
        args.analysis_manifest,
        args.expected_analysis_manifest_sha256,
        accepted_set_path=args.accepted_set,
        accepted_set_sha256=args.expected_accepted_set_sha256,
    )
    root_bindings = {
        "execution_lock_sha256": lock_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_manifest_sha,
    }
    accepted = load_json(args.accepted_set)
    accepted_entries = _validate_accepted_set(
        args.accepted_set, accepted, bindings=root_bindings
    )
    candidate_index_path = resolve_repo_path(
        accepted["candidate_index"]["path"], "candidate index"
    )
    tracked_paths.append(candidate_index_path)
    candidate_index = load_json(candidate_index_path)
    for candidate_entry in candidate_index["entries"]:
        candidate_manifest_path = resolve_repo_path(
            candidate_entry["path"], "candidate manifest"
        )
        require_file_sha256(
            candidate_manifest_path,
            candidate_entry["sha256"],
            "candidate manifest",
        )
        tracked_paths.append(candidate_manifest_path)
        try:
            candidate_manifest = validate_file_manifest(candidate_manifest_path)
        except (KeyError, OSError, TypeError, ValueError):
            # The candidate index is the byte-level audit record for malformed
            # attempts. A structurally valid manifest additionally closes all
            # files that it binds, whether or not that attempt was accepted.
            continue
        tracked_paths.extend(
            candidate_manifest_path.parent / name
            for name in candidate_manifest["files_sha256"]
        )
        if "result.json" in candidate_manifest["files_sha256"]:
            try:
                candidate_result = load_json(candidate_manifest_path.parent / "result.json")
                retry_pending = candidate_result.get("bindings", {}).get(
                    "retry_pending_set"
                )
                if (
                    isinstance(retry_pending, dict)
                    and set(retry_pending) == {"path", "sha256"}
                ):
                    retry_path = resolve_repo_path(
                        retry_pending["path"], "candidate retry pending set"
                    )
                    require_file_sha256(
                        retry_path,
                        retry_pending["sha256"],
                        "candidate retry pending set",
                    )
                    tracked_paths.append(retry_path)
            except (AttributeError, KeyError, OSError, TypeError, ValueError):
                # Rejected candidates remain byte-preserved even when their
                # external authorization reference is itself why they failed.
                pass
    for entry in accepted_entries:
        manifest_path = resolve_repo_path(
            entry["manifest_path"], "accepted task manifest"
        )
        manifest = validate_file_manifest(manifest_path)
        tracked_paths.append(manifest_path)
        tracked_paths.extend(manifest_path.parent / name for name in manifest["files_sha256"])

    analysis_root = args.analysis_manifest.parent
    tracked_paths.extend(
        analysis_root / name
        for name in inventory
    )
    task_index = load_json(analysis_root / "task_index.json")
    checkpoint_index = load_json(analysis_root / "checkpoint_index.json")
    matrices = load_json(analysis_root / "matrices.json")
    if (
        set(task_index) != {"entries", "schema"}
        or task_index.get("schema")
        != "pcb-gnn.corpus-v4-accuracy-task-index.v1"
        or not isinstance(task_index.get("entries"), list)
        or len(task_index["entries"]) != 25
        or set(checkpoint_index) != {"entries", "schema"}
        or checkpoint_index.get("schema")
        != "pcb-gnn.corpus-v4-accuracy-checkpoint-index.v1"
        or not isinstance(checkpoint_index.get("entries"), list)
        or len(checkpoint_index["entries"]) != 25
        or set(matrices) != {"schema", "views"}
        or matrices.get("schema") != "pcb-gnn.corpus-v4-accuracy-matrices.v1"
    ):
        raise ValueError("analysis indexes or matrix schema/cardinality is invalid")

    evaluation_rows = load_jsonl(args.plan.parent / "evaluation_dataset.jsonl")
    if len(evaluation_rows) != 1500 or [row.get("layout_id") for row in evaluation_rows] != list(range(1500)):
        raise ValueError("evaluation dataset is not dense layout IDs 0..1499")
    evaluation = {row["layout_id"]: row for row in evaluation_rows}
    metric_results: list[dict[str, Any]] = []
    for task_id, (task_row, accepted_entry, task_entry, checkpoint_entry) in enumerate(
        zip(task_rows, accepted_entries, task_index["entries"], checkpoint_index["entries"])
    ):
        prediction_name = f"predictions/task_{task_id:02d}.jsonl"
        if (
            not isinstance(task_entry, dict)
            or set(task_entry)
            != {
                "manifest_path",
                "manifest_sha256",
                "prediction_path",
                "prediction_sha256",
                "scheduler_completion",
                "task_id",
            }
            or task_entry["task_id"] != task_id
            or task_entry["manifest_path"] != accepted_entry["manifest_path"]
            or task_entry["manifest_sha256"] != accepted_entry["manifest_sha256"]
            or task_entry["scheduler_completion"]
            != accepted_entry["scheduler_completion"]
            or task_entry["prediction_path"] != prediction_name
            or task_entry["prediction_sha256"] != inventory[prediction_name]
        ):
            raise ValueError(f"task index entry {task_id} is not closed to accepted evidence")
        predictions = load_jsonl(analysis_root / prediction_name)
        metrics = recompute_task_metrics(predictions, task_row, evaluation)
        metric_results.append({"metrics": metrics, "task": canonical_task_row(task_id)})

        expected_checkpoint_keys = {
            *canonical_task_row(task_id),
            "archive_sha256",
            "bundle_path",
            "metadata_sha256",
            "smoke_examples_sha256",
        }
        manifest_path = resolve_repo_path(
            accepted_entry["manifest_path"], "accepted task manifest"
        )
        task_result = validate_attempt(
            manifest_path,
            task_row=task_row,
            protocol_sha256=protocol_sha,
            plan_sha256=plan_sha,
            task_manifest_sha256=task_manifest_sha,
            lock=lock,
            lock_sha256=lock_sha,
            expected_source_git_head=args.expected_source_git_head,
        )
        retry_pending = task_result["bindings"]["retry_pending_set"]
        if retry_pending is not None:
            tracked_paths.append(
                resolve_repo_path(retry_pending["path"], "retry pending set")
            )
        expected_checkpoint = {
            **canonical_task_row(task_id),
            **task_result["checkpoint"],
            "bundle_path": (manifest_path.parent / "bundle")
            .relative_to(ROOT)
            .as_posix(),
        }
        if (
            not isinstance(checkpoint_entry, dict)
            or set(checkpoint_entry) != expected_checkpoint_keys
            or checkpoint_entry != expected_checkpoint
        ):
            raise ValueError(f"checkpoint index entry {task_id} is inconsistent")

    expected_matrices = build_matrices(metric_results, protocol)
    if matrices["views"] != expected_matrices:
        raise ValueError("stored matrices differ from prediction-level reconstruction")
    assert_finite_json(matrices, "accuracy matrices")

    summary_path_record = analysis["files"]["summary.json"]
    summary_path = args.analysis_manifest.parent / summary_path_record["path"]
    summary = load_json(summary_path)
    expected_bindings = {
        "accepted_set_sha256": args.expected_accepted_set_sha256,
        **root_bindings,
        "expected_source_git_head": args.expected_source_git_head,
    }
    if (
        summary.get("schema") != FINAL_SCHEMA
        or summary.get("bindings") != expected_bindings
        or summary.get("provenance", {}).get("source_git_head")
        != args.expected_source_git_head
    ):
        raise ValueError("final summary does not bind the supplied scientific roots")
    split_rows = task_rows[::5]
    panel_memberships = [
        layout_id for row in split_rows for layout_id in row["r4_test_layout_ids"]
    ]
    unique_layouts = set(panel_memberships)
    unique_families = {evaluation[index]["family_id"] for index in unique_layouts}
    all_r4_layouts = {
        index
        for index, row in evaluation.items()
        if row["evaluation_only_r4_cps"] is not None
    }
    all_r4_families = {evaluation[index]["family_id"] for index in all_r4_layouts}
    expected_counts = {
        "r4_family_split_appearance_histogram": {
            str(key): value
            for key, value in sorted(
                Counter(
                    Counter(
                        evaluation[index]["family_id"]
                        for row in split_rows
                        for index in row["r4_test_layout_ids"]
                    ).values()
                ).items()
            )
        },
        "r4_layout_split_appearance_histogram": {
            str(key): value
            for key, value in sorted(Counter(Counter(panel_memberships).values()).items())
        },
        "r4_panel_split_layout_memberships": len(panel_memberships),
        "r4_task_layout_evaluations": sum(
            len(row["r4_test_layout_ids"]) for row in task_rows
        ),
        "r4_unique_families_across_split_panels": len(unique_families),
        "r4_unique_layouts_across_split_panels": len(unique_layouts),
        "r4_unseen_selected_families": len(all_r4_families - unique_families),
        "r4_unseen_selected_layouts": len(all_r4_layouts - unique_layouts),
        "tasks": 25,
    }
    if summary.get("counts") != expected_counts:
        raise ValueError("final summary counts differ from task-level reconstruction")
    assert_finite_json(summary, "accuracy final summary")
    stored_archive: dict[str, Any] | None = None
    if args.check:
        if args.out.is_symlink() or not args.out.is_file():
            raise ValueError("tracked archive manifest is missing or a symlink")
        stored_archive = load_json(args.out)
        if (
            not isinstance(stored_archive, dict)
            or set(stored_archive)
            != {
                "analysis_manifest",
                "bindings",
                "finalizer_scheduler_completion",
                "schema",
                "verified_analysis_files_sha256",
            }
            or stored_archive.get("schema") != ARCHIVE_SCHEMA
        ):
            raise ValueError("stored accuracy archive schema is not exact")
        finalizer_receipt = stored_archive["finalizer_scheduler_completion"]
        if (
            not isinstance(finalizer_receipt, dict)
            or set(finalizer_receipt)
            != {"AllocTRES", "ElapsedRaw", "ExitCode", "JobIDRaw", "ReqTRES", "State"}
            or finalizer_receipt["State"] != "COMPLETED"
            or finalizer_receipt["ExitCode"] != "0:0"
        ):
            raise ValueError("stored finalizer scheduler receipt is invalid")
    else:
        finalizer_receipt = _completed_finalizer(
            str(summary.get("provenance", {}).get("scheduler", {}).get("job_id", ""))
        )
    scheduler_record = summary["provenance"]["scheduler"].get("scheduler_record", {})
    if (
        finalizer_receipt["JobIDRaw"]
        != str(summary["provenance"]["scheduler"].get("job_id", ""))
        or any(
            finalizer_receipt[name] != scheduler_record.get(name)
            for name in ("ReqTRES", "AllocTRES")
        )
    ):
        raise ValueError("finalizer post-run TRES differs from its in-run scheduler receipt")
    payload = {
        "analysis_manifest": {
            "path": args.analysis_manifest.resolve().relative_to(ROOT.resolve()).as_posix(),
            "sha256": args.expected_analysis_manifest_sha256,
        },
        "bindings": expected_bindings,
        "finalizer_scheduler_completion": finalizer_receipt,
        "schema": ARCHIVE_SCHEMA,
        "verified_analysis_files_sha256": inventory,
    }
    require_repo_relative_path(
        args.out.resolve().parent.relative_to(ROOT.resolve()).as_posix(),
        "archive output parent",
    )
    if args.check:
        if stored_archive != payload:
            raise ValueError("stored accuracy archive differs from deterministic reconstruction")
    else:
        if args.out.exists():
            raise FileExistsError(args.out)
        atomic_write_json(args.out, payload)
    if args.require_git_tracked:
        tracked_paths.append(args.out)
        _require_git_tracked_clean(tracked_paths)
    return payload


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
    parser.add_argument("--accepted-set", type=Path, required=True)
    parser.add_argument("--expected-accepted-set-sha256", required=True)
    parser.add_argument("--analysis-manifest", type=Path, required=True)
    parser.add_argument("--expected-analysis-manifest-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify a stored closure without querying live scheduler accounting",
    )
    parser.add_argument(
        "--require-git-tracked",
        action="store_true",
        help="require every closure path and the stored archive to be tracked and clean",
    )
    args = parser.parse_args()
    payload = verify_archive(args)
    print(
        f"Corpus V4 accuracy archive: PASS "
        f"({len(payload['verified_analysis_files_sha256'])} analysis files)"
    )


if __name__ == "__main__":
    main()
