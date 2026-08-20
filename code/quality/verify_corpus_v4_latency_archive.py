#!/usr/bin/env python3
"""Reconstruct and authenticate the Corpus V4 paired-latency archive."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_accuracy_contract import canonical_tres, tres_equivalent  # noqa: E402
from corpus_v4_latency_contract import (  # noqa: E402
    EXECUTION_SOURCE_NAMES,
    EXPECTED_INPUT_NAMES,
    EXPECTED_LAYOUTS,
    PLANNER_SOURCE_NAMES,
    load_json,
    load_jsonl,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_protocol,
    validate_root_closure,
)
from finalize_corpus_v4_latency import (  # noqa: E402
    ACCEPTED_SCHEMA,
    ANALYSIS_MANIFEST_SCHEMA,
    FINAL_SCHEMA,
    summarize_records,
)
from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402


ARCHIVE_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-archive.v2"


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _completion(job_id: str) -> dict[str, str]:
    query = subprocess.run(
        [
            "sacct", "-X", "-n", "-P", "-j", job_id,
            "--format=JobID,JobIDRaw,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    fields = ("JobID", "JobIDRaw", "State", "ExitCode", "ElapsedRaw", "ReqTRES", "AllocTRES")
    rows: list[dict[str, str]] = []
    for line in query.stdout.splitlines():
        values = line.split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) == len(fields):
            rows.append(dict(zip(fields, values)))
    matches = [row for row in rows if row.get("JobID") == job_id]
    if (
        query.returncode != 0
        or len(matches) != 1
        or matches[0]["State"].split()[0].rstrip("+") != "COMPLETED"
        or matches[0]["ExitCode"] != "0:0"
    ):
        raise ValueError("finalizer lacks exact COMPLETED/0:0 terminal accounting")
    result = dict(matches[0])
    result["State"] = "COMPLETED"
    result["ReqTRES"] = canonical_tres(result["ReqTRES"])
    result["AllocTRES"] = canonical_tres(result["AllocTRES"])
    return result


def _require_git_tracked_clean(paths: list[Path]) -> None:
    relative = sorted(
        {
            path.resolve().relative_to(ROOT.resolve()).as_posix()
            for path in paths
        }
    )
    if not relative:
        raise ValueError("tracked closure is empty")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", *relative],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if tracked.returncode != 0:
        raise ValueError("archive closure contains an untracked file")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", *relative],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    if dirty:
        raise ValueError("archive closure contains dirty tracked bytes")


def verify(args: argparse.Namespace) -> dict[str, Any]:
    if args.require_git_tracked and not args.check:
        raise ValueError("--require-git-tracked requires --check")
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
    if args.accepted_set.is_symlink() or sha256_file(args.accepted_set) != args.expected_accepted_set_sha256:
        raise ValueError("accepted set is missing or hash-mismatched")
    accepted = load_json(args.accepted_set)
    entries = accepted.get("entries")
    if (
        accepted.get("schema") != ACCEPTED_SCHEMA
        or any(accepted.get(name) != digest for name, digest in bindings.items())
        or accepted.get("n_expected") != EXPECTED_LAYOUTS
        or accepted.get("n_accepted") != EXPECTED_LAYOUTS
        or not isinstance(entries, list)
        or len(entries) != EXPECTED_LAYOUTS
    ):
        raise ValueError("accepted set is not complete or root-bound")

    if args.analysis_manifest.is_symlink() or sha256_file(args.analysis_manifest) != args.expected_analysis_manifest_sha256:
        raise ValueError("analysis manifest is missing or hash-mismatched")
    analysis = load_json(args.analysis_manifest)
    expected_names = {"records.jsonl", "summary.json", "task_index.json"}
    files = analysis.get("files_sha256")
    if (
        analysis.get("schema") != ANALYSIS_MANIFEST_SCHEMA
        or not isinstance(files, dict)
        or set(files) != expected_names
        or analysis.get("accepted_set")
        != {
            "path": _repo_relative(args.accepted_set),
            "sha256": args.expected_accepted_set_sha256,
        }
    ):
        raise ValueError("analysis inventory is not exact")
    analysis_root = args.analysis_manifest.parent
    observed_files = {
        child.name for child in analysis_root.iterdir()
        if child.is_file() and not child.is_symlink()
    }
    if observed_files != expected_names | {"ANALYSIS_MANIFEST.json"}:
        raise ValueError("analysis directory inventory differs from its manifest")
    for name, digest in files.items():
        if sha256_file(analysis_root / name) != digest:
            raise ValueError(f"analysis file hash differs: {name}")

    records = load_jsonl(analysis_root / "records.jsonl")
    if [row.get("layout_id") for row in records] != [row["layout_id"] for row in panel]:
        raise ValueError("analysis records differ from frozen panel order")
    reconstructed = summarize_records(
        records,
        expected_repetitions=int(protocol["gnn_timing"]["measured_repetitions"]),
        bootstrap_resamples=int(protocol["statistics"]["bootstrap"]["resamples"]),
        bootstrap_seed=int(protocol["statistics"]["bootstrap"]["seed"]),
    )
    summary = load_json(analysis_root / "summary.json")
    expected_summary_bindings = {
        **bindings,
        "accepted_set_sha256": args.expected_accepted_set_sha256,
        "expected_source_git_head": args.expected_source_git_head,
    }
    if (
        summary.get("schema") != FINAL_SCHEMA
        or summary.get("bindings") != expected_summary_bindings
        or summary.get("summary") != reconstructed
        or summary.get("provenance", {}).get("source_git_head") != args.expected_source_git_head
    ):
        raise ValueError("stored latency summary differs from deterministic reconstruction")
    task_index = load_json(analysis_root / "task_index.json")
    if (
        task_index.get("schema") != "pcb-gnn.corpus-v4-paired-latency-task-index.v2"
        or not isinstance(task_index.get("entries"), list)
        or len(task_index["entries"]) != EXPECTED_LAYOUTS
    ):
        raise ValueError("latency task index is incomplete")
    for task_id, (accepted_entry, index_entry) in enumerate(zip(entries, task_index["entries"])):
        if index_entry != {
            "manifest_path": accepted_entry["manifest_path"],
            "manifest_sha256": accepted_entry["manifest_sha256"],
            "scheduler_completion": accepted_entry["scheduler_completion"],
            "task_id": task_id,
        }:
            raise ValueError(f"task index entry {task_id} differs from accepted evidence")

    tracked: list[Path] = [
        args.protocol,
        args.plan,
        args.task_manifest,
        panel_path,
        args.execution_lock,
        args.accepted_set,
        args.analysis_manifest,
        *(analysis_root / name for name in expected_names),
    ]
    for name in EXPECTED_INPUT_NAMES:
        tracked.append(resolve_repo_path(protocol["inputs"][name]["path"], f"input {name}"))
    tracked.extend(resolve_repo_path(name, "planner source") for name in PLANNER_SOURCE_NAMES)
    tracked.extend(resolve_repo_path(name, "execution source") for name in EXECUTION_SOURCE_NAMES)
    candidate_path = resolve_repo_path(
        accepted["candidate_index"]["path"], "candidate index"
    )
    if sha256_file(candidate_path) != accepted["candidate_index"]["sha256"]:
        raise ValueError("candidate index hash differs from accepted set")
    tracked.append(candidate_path)
    candidates = load_json(candidate_path)
    for candidate in candidates.get("entries", []):
        manifest_path = resolve_repo_path(candidate["manifest_path"], "candidate manifest")
        if sha256_file(manifest_path) != candidate["manifest_sha256"]:
            raise ValueError("candidate manifest bytes differ from the index")
        tracked.extend((manifest_path, manifest_path.parent / "result.json"))

    stored: dict[str, Any] | None = None
    if args.check:
        if args.out.is_symlink() or not args.out.is_file():
            raise ValueError("stored latency archive is missing")
        stored = load_json(args.out)
        if stored.get("schema") != ARCHIVE_SCHEMA:
            raise ValueError("stored latency archive schema is invalid")
        finalizer_completion = stored.get("finalizer_scheduler_completion")
    else:
        finalizer_completion = _completion(
            str(summary["provenance"]["scheduler"]["job_id"])
        )
    if (
        not isinstance(finalizer_completion, dict)
        or finalizer_completion.get("State") != "COMPLETED"
        or finalizer_completion.get("ExitCode") != "0:0"
        or finalizer_completion.get("JobID")
        != str(summary["provenance"]["scheduler"]["job_id"])
        or any(
            not tres_equivalent(
                finalizer_completion.get(name),
                summary["provenance"]["scheduler"]["scheduler_record"].get(name),
            )
            for name in ("ReqTRES", "AllocTRES")
        )
    ):
        raise ValueError("finalizer terminal accounting differs from its in-run receipt")
    payload = {
        "analysis_manifest": {
            "path": _repo_relative(args.analysis_manifest),
            "sha256": args.expected_analysis_manifest_sha256,
        },
        "bindings": expected_summary_bindings,
        "finalizer_scheduler_completion": finalizer_completion,
        "schema": ARCHIVE_SCHEMA,
        "verified_analysis_files_sha256": files,
    }
    if args.check:
        if stored != payload:
            raise ValueError("stored latency archive differs from reconstruction")
    else:
        if args.out.exists() or args.out.is_symlink():
            raise FileExistsError(args.out)
        atomic_write_json(args.out, payload)
    if args.require_git_tracked:
        tracked.append(args.out)
        _require_git_tracked_clean(tracked)
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
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    payload = verify(args)
    print(
        f"Corpus V4 latency archive: PASS "
        f"({len(payload['verified_analysis_files_sha256'])} analysis files)"
    )


if __name__ == "__main__":
    main()
