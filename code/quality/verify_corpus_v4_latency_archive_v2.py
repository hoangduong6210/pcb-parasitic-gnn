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

from corpus_v4_accuracy_contract_v3 import canonical_tres, tres_equivalent  # noqa: E402
from corpus_v4_latency_contract_v2 import (  # noqa: E402
    EXECUTION_SOURCE_NAMES,
    EXPECTED_INPUT_NAMES,
    EXPECTED_LAYOUTS,
    PLANNER_SOURCE_NAMES,
    PREFLIGHT_SACCT_FIELDS,
    SCHEMA_PREFIX,
    TASK_RESULT_SCHEMA,
    load_json,
    load_jsonl,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_preflight_admission,
    validate_protocol,
    validate_root_closure,
    validate_terminal_array_completion,
)
from finalize_corpus_v4_latency_v2 import (  # noqa: E402
    ACCEPTED_SCHEMA,
    ANALYSIS_MANIFEST_SCHEMA,
    ARTIFACT_MANIFEST_SCHEMA,
    FINAL_SCHEMA,
    TASK_INDEX_SCHEMA,
    load_admitted_mesh_identities,
    load_expected_references,
    summarize_records,
    validate_full_task_result,
)
from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402


ARCHIVE_SCHEMA = f"{SCHEMA_PREFIX}-archive.v1"
CANDIDATE_SCHEMA = f"{SCHEMA_PREFIX}-candidate-index.v1"


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _completion(job_id: str) -> dict[str, str]:
    query = subprocess.run(
        [
            "sacct", "-X", "-n", "-P", "-j", job_id,
            f"--format={','.join(PREFLIGHT_SACCT_FIELDS)}",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    rows: list[dict[str, str]] = []
    for line in query.stdout.splitlines():
        values = line.split("|")
        if values and values[-1] == "":
            values.pop()
        if len(values) == len(PREFLIGHT_SACCT_FIELDS):
            rows.append(dict(zip(PREFLIGHT_SACCT_FIELDS, values)))
    matches = [row for row in rows if row.get("JobID") == job_id]
    if (
        query.returncode != 0
        or len(matches) != 1
        or matches[0]["State"].split()[0].rstrip("+") != "COMPLETED"
        or matches[0]["ExitCode"] != "0:0"
        or matches[0].get("Restarts") != "0"
        or not matches[0].get("ElapsedRaw", "").isdigit()
        or not 1 <= int(matches[0]["ElapsedRaw"]) <= 1200
        or matches[0].get("Partition") != "nextgen"
        or matches[0].get("Timelimit") != "00:20:00"
        or not matches[0].get("NodeList")
        or matches[0].get("NodeList") in {"(null)", "None", "Unknown"}
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
    if (
        args.accepted_set.is_symlink()
        or sha256_file(args.accepted_set) != args.expected_accepted_set_sha256
    ):
        raise ValueError("accepted set is missing or hash-mismatched")
    accepted = load_json(args.accepted_set)
    entries = accepted.get("entries")
    admission_reference = accepted.get("preflight_admission")
    expected_accepted_fields = {
        *bindings,
        "candidate_index",
        "entries",
        "full_array_job_id",
        "n_accepted",
        "n_expected",
        "preflight_admission",
        "schema",
    }
    if (
        set(accepted) != expected_accepted_fields
        or accepted.get("schema") != ACCEPTED_SCHEMA
        or any(accepted.get(name) != digest for name, digest in bindings.items())
        or accepted.get("n_expected") != EXPECTED_LAYOUTS
        or accepted.get("n_accepted") != EXPECTED_LAYOUTS
        or not isinstance(entries, list)
        or len(entries) != EXPECTED_LAYOUTS
        or not isinstance(accepted.get("full_array_job_id"), str)
        or not accepted["full_array_job_id"].isdigit()
        or not isinstance(admission_reference, dict)
        or set(admission_reference) != {"path", "sha256"}
    ):
        raise ValueError("accepted set is not complete or root-bound")
    admission, canonical_admission_reference = validate_preflight_admission(
        resolve_repo_path(admission_reference["path"], "preflight admission"),
        admission_reference["sha256"],
        bindings=bindings,
        expected_source_git_head=args.expected_source_git_head,
        tasks=tasks,
        lock=lock,
        checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
    )
    if canonical_admission_reference != admission_reference:
        raise ValueError("accepted set preflight admission reference is not canonical")

    if (
        args.analysis_manifest.is_symlink()
        or sha256_file(args.analysis_manifest)
        != args.expected_analysis_manifest_sha256
    ):
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
        block_median_ratio_max=float(
            protocol["gnn_timing"]["block_median_ratio_max"]
        ),
    )
    summary = load_json(analysis_root / "summary.json")
    expected_summary_bindings = {
        **bindings,
        "accepted_set_sha256": args.expected_accepted_set_sha256,
        "expected_source_git_head": args.expected_source_git_head,
        "full_array_job_id": accepted["full_array_job_id"],
        "preflight_admission": admission_reference,
    }
    expected_finalizer_runtime = {
        "packages": protocol["runtime"]["packages"],
        "python": protocol["runtime"]["python"],
        "thread_environment": {
            name: "2"
            for name in (
                "BLIS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
            )
        },
    }
    if (
        summary.get("schema") != FINAL_SCHEMA
        or summary.get("bindings") != expected_summary_bindings
        or summary.get("summary") != reconstructed
        or summary.get("provenance", {}).get("source_git_head") != args.expected_source_git_head
        or summary.get("provenance", {}).get("source_sha256")
        != lock["source_sha256"]
        or summary.get("provenance", {}).get("runtime")
        != expected_finalizer_runtime
        or summary.get("scientific_scope")
        != {
            "checkpoint_task_id": 12,
            "comparison": (
                "sequential FastHenry-plus-one-thread-FEM-v2-R3P16 all-four-target "
                "workflow versus warm-loaded batch-one in-memory "
                "raw-JSON-record-to-four-output GNN"
            ),
            "primary_comparison": "paired_four_target",
            "secondary_comparisons": [
                "fasthenry_three_target",
                "fem_v2_capacitance",
            ],
            "split_seed": 42,
        }
    ):
        raise ValueError("stored latency summary differs from deterministic reconstruction")
    task_index = load_json(analysis_root / "task_index.json")
    if (
        task_index.get("schema") != TASK_INDEX_SCHEMA
        or not isinstance(task_index.get("entries"), list)
        or len(task_index["entries"]) != EXPECTED_LAYOUTS
    ):
        raise ValueError("latency task index is incomplete")
    references = load_expected_references(protocol)
    admitted_mesh = load_admitted_mesh_identities(protocol)
    full_array_job_id = accepted["full_array_job_id"]
    full_job_root = (
        ROOT
        / "results/corpus_v4/latency_fem_v2/jobs/attempts"
        / f"job_{full_array_job_id}"
    )
    expected_job_tasks = {f"task_{index:03d}" for index in range(EXPECTED_LAYOUTS)}
    if (
        full_job_root.is_symlink()
        or not full_job_root.is_dir()
        or {child.name for child in full_job_root.iterdir()} != expected_job_tasks
    ):
        raise ValueError("full-array archive does not contain one exact job panel")
    for task_id, (accepted_entry, index_entry) in enumerate(zip(entries, task_index["entries"])):
        if index_entry != {
            "manifest_path": accepted_entry["manifest_path"],
            "manifest_sha256": accepted_entry["manifest_sha256"],
            "scheduler_completion": accepted_entry["scheduler_completion"],
            "task_id": task_id,
        }:
            raise ValueError(f"task index entry {task_id} differs from accepted evidence")
        manifest_path = resolve_repo_path(
            accepted_entry["manifest_path"], "accepted task manifest"
        )
        task_root = full_job_root / f"task_{task_id:03d}"
        result_path = task_root / "result.json"
        if (
            manifest_path.is_symlink()
            or manifest_path != task_root / "TASK_MANIFEST.json"
            or not manifest_path.is_file()
            or sha256_file(manifest_path) != accepted_entry["manifest_sha256"]
            or task_root.is_symlink()
            or not task_root.is_dir()
            or {child.name for child in task_root.iterdir()}
            != {"TASK_MANIFEST.json", "result.json"}
            or result_path.is_symlink()
            or not result_path.is_file()
        ):
            raise ValueError(f"task index entry {task_id} artifact inventory differs")
        manifest = load_json(manifest_path)
        if (
            set(manifest) != {"files_sha256", "schema"}
            or manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA
            or manifest.get("files_sha256")
            != {"result.json": sha256_file(result_path)}
        ):
            raise ValueError(f"task index entry {task_id} result digest differs")
        result = load_json(result_path)
        validate_full_task_result(
            result,
            task=tasks[task_id],
            bindings=bindings,
            preflight_admission=admission_reference,
            checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
            external_solver_sha256=protocol["solver_workflow"]["inductance"]["binary_sha256"],
            fem_v2_dataset_admission=protocol["inputs"]["fem_v2_dataset_admission"],
            expected_source_git_head=args.expected_source_git_head,
            locked_source_sha256=lock["source_sha256"],
            expected_runtime=protocol["runtime"],
            expected_array_job_id=full_array_job_id,
            expected_reference=references[tasks[task_id]["layout_id"]],
            expected_mesh_identity=admitted_mesh[tasks[task_id]["layout_id"]],
            expected_repetitions=int(protocol["gnn_timing"]["measured_repetitions"]),
            block_median_ratio_max=float(protocol["gnn_timing"]["block_median_ratio_max"]),
            reference_agreement_tolerance=float(
                protocol["solver_workflow"]["reference_agreement_max_relative_error"]
            ),
        )
        if result["record"] != records[task_id]:
            raise ValueError(f"task index entry {task_id} record differs from analysis")
        if (
            result.get("schema") != TASK_RESULT_SCHEMA
            or result.get("stage") != "full_array"
            or result.get("bindings", {}).get("preflight_admission")
            != admission_reference
        ):
            raise ValueError(
                f"task index entry {task_id} does not bind the preflight admission"
            )
        completion = accepted_entry.get("scheduler_completion")
        validated_completion = (
            validate_terminal_array_completion(
                result.get("provenance", {}).get("scheduler", {}), [completion]
            )
            if isinstance(completion, dict)
            else None
        )
        if validated_completion is None or validated_completion != completion:
            raise ValueError(
                f"task index entry {task_id} lacks exact terminal accounting"
            )

    tracked: list[Path] = [
        args.protocol,
        args.plan,
        args.task_manifest,
        panel_path,
        args.execution_lock,
        args.accepted_set,
        args.analysis_manifest,
        *(analysis_root / name for name in expected_names),
        resolve_repo_path(admission_reference["path"], "preflight admission"),
    ]
    for admission_entry in admission["entries"]:
        manifest_path = resolve_repo_path(
            admission_entry["manifest_path"], "preflight task manifest"
        )
        tracked.extend((manifest_path, manifest_path.parent / "result.json"))
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
    if (
        candidates.get("schema") != CANDIDATE_SCHEMA
        or candidates.get("full_array_job_id") != full_array_job_id
        or candidates.get("preflight_admission") != admission_reference
        or not isinstance(candidates.get("entries"), list)
        or len(candidates["entries"]) != EXPECTED_LAYOUTS
    ):
        raise ValueError("candidate index does not bind the preflight admission")
    for candidate in candidates.get("entries", []):
        manifest_path = resolve_repo_path(candidate["manifest_path"], "candidate manifest")
        if (
            not manifest_path.is_file()
            or manifest_path.is_symlink()
            or sha256_file(manifest_path) != candidate["manifest_sha256"]
        ):
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
        or set(finalizer_completion) != set(PREFLIGHT_SACCT_FIELDS)
        or finalizer_completion.get("Restarts") != "0"
        or not finalizer_completion.get("ElapsedRaw", "").isdigit()
        or not 1 <= int(finalizer_completion["ElapsedRaw"]) <= 1200
        or finalizer_completion.get("Partition") != "nextgen"
        or finalizer_completion.get("Timelimit") != "00:20:00"
        or not finalizer_completion.get("NodeList")
        or finalizer_completion.get("NodeList") in {"(null)", "None", "Unknown"}
        or finalizer_completion.get("Account")
        != summary["provenance"]["scheduler"]["scheduler_record"].get("Account")
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
