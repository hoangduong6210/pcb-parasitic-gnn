#!/usr/bin/env python3
"""Verify the job-backed Corpus v4 R3/R4 discrepancy archive."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = (
    ROOT
    / "results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1"
)
DEFAULT_MANIFEST = ANALYSIS_ROOT / "ANALYSIS_MANIFEST.json"
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

from audit_corpus_v4_cps_fidelity_discrepancy import (  # noqa: E402
    build_audit,
    check_outputs,
)
from verify_corpus_v4_archive import (  # noqa: E402
    ArchiveValidationError,
    load_json,
    require_pinned_file,
    resolve_repo_path,
    validate_archive,
)


SCHEMA = "pcb-gnn.cps-fidelity-discrepancy-analysis-manifest.v1"
ANALYSIS_ID = "corpus-v4-cps-r3-r4-discrepancy-v1"
JOB_RE = re.compile(r"[0-9]+")
SOURCE_RE = re.compile(r"[0-9a-f]{40,64}")
PRIVATE_PATH_RE = re.compile(
    r"/(?:users|home|tmp|scratch|var|opt|mnt|gpfs|fs|projects?)(?:/|\b)",
    re.IGNORECASE,
)
SENSITIVE_TEXT_PATTERNS = (
    (PRIVATE_PATH_RE, "private path"),
    (re.compile(r"\b[A-Za-z]:\\"), "private path"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "cloud access key"),
)


class DiscrepancyArchiveError(ValueError):
    """Raised when the derived analysis archive is incomplete or inconsistent."""


def _require_exact_inventory(directory: Path, names: set[str], label: str) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise DiscrepancyArchiveError(f"{label} is not a real directory")
    entries = list(directory.iterdir())
    if {path.name for path in entries} != names:
        raise DiscrepancyArchiveError(f"{label} inventory is not exact")
    if any(path.is_symlink() for path in entries):
        raise DiscrepancyArchiveError(f"{label} contains a symlink")


def _require_public_payload(value: Any, label: str) -> None:
    if isinstance(value, str):
        for pattern, description in SENSITIVE_TEXT_PATTERNS:
            if pattern.search(value):
                raise DiscrepancyArchiveError(f"{description} appears in {label}")
    if isinstance(value, dict):
        for key, child in value.items():
            _require_public_payload(key, label)
            _require_public_payload(child, label)
    elif isinstance(value, list):
        for child in value:
            _require_public_payload(child, label)


def _require_public_text(path: Path, label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DiscrepancyArchiveError(f"{label} is not UTF-8 text") from exc
    _require_public_payload(text, label)


def _require_manifest_structure(manifest: dict[str, Any]) -> tuple[str, str]:
    if set(manifest) != {"analysis_id", "execution", "files", "schema"}:
        raise DiscrepancyArchiveError("analysis manifest keys are not exact")
    if manifest.get("schema") != SCHEMA or manifest.get("analysis_id") != ANALYSIS_ID:
        raise DiscrepancyArchiveError("unsupported discrepancy archive identity")
    execution = manifest.get("execution")
    if not isinstance(execution, dict) or set(execution) != {
        "job_id",
        "source_git_commit",
    }:
        raise DiscrepancyArchiveError("analysis execution fields are not exact")
    job_id = execution.get("job_id")
    source_commit = execution.get("source_git_commit")
    if (
        not isinstance(job_id, str)
        or JOB_RE.fullmatch(job_id) is None
        or not isinstance(source_commit, str)
        or SOURCE_RE.fullmatch(source_commit) is None
    ):
        raise DiscrepancyArchiveError("analysis execution identity is malformed")
    return job_id, source_commit


def _require_canonical_record_paths(
    records: dict[str, Any], expected_paths: dict[str, str]
) -> None:
    if set(records) != set(expected_paths):
        raise DiscrepancyArchiveError("analysis manifest file set is not exact")
    for name, expected_path in expected_paths.items():
        record = records.get(name)
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256"}
            or record.get("path") != expected_path
        ):
            raise DiscrepancyArchiveError(
                f"analysis manifest path is not canonical: {name}"
            )


def _require_plan_descendants(
    protocol: dict[str, Any], plan: dict[str, Any]
) -> None:
    plan_dir = "results/corpus_v4/cps_multifidelity/plan/v1"
    for input_name, file_name in (
        ("geometry_families", "geometry_families.jsonl"),
        ("hf_selection_registry", "hf_selection_registry.json"),
        ("split_registry", "split_registry.json"),
    ):
        input_record = protocol.get("inputs", {}).get(input_name)
        if (
            not isinstance(input_record, dict)
            or set(input_record) != {"path", "sha256"}
            or input_record.get("path") != f"{plan_dir}/{file_name}"
            or input_record.get("sha256")
            != plan.get("artifact_sha256", {}).get(file_name)
        ):
            raise DiscrepancyArchiveError(
                f"audit input is not a canonical plan descendant: {input_name}"
            )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DiscrepancyArchiveError(
                f"invalid JSONL at {path.name}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise DiscrepancyArchiveError(f"non-object JSONL row in {path.name}")
        rows.append(value)
    return rows


def _validate_split_registry_strict(
    family_rows: list[dict[str, Any]],
    registry: dict[str, Any],
    selected_layout_ids: set[int],
) -> None:
    if (
        len(family_rows) != 66
        or set(registry) != {"init_seeds", "rows", "schema"}
        or registry.get("schema") != "pcb-gnn.swap-closed-split-registry.v1"
        or registry.get("init_seeds") != [40, 41, 42, 43, 44]
    ):
        raise DiscrepancyArchiveError("split registry header is not exact")

    family_members: dict[str, list[int]] = {}
    all_layouts: set[int] = set()
    for family in family_rows:
        family_id = family.get("family_id")
        members = family.get("member_layout_ids")
        if (
            not isinstance(family_id, str)
            or family_id in family_members
            or not isinstance(members, list)
            or any(type(layout_id) is not int for layout_id in members)
            or len(members) != len(set(members))
            or all_layouts.intersection(members)
        ):
            raise DiscrepancyArchiveError("family rows are invalid for split validation")
        family_members[family_id] = members
        all_layouts.update(members)
    if all_layouts != set(range(1500)):
        raise DiscrepancyArchiveError("family rows do not cover 1,500 layouts")

    rows = registry.get("rows")
    if not isinstance(rows, list) or len(rows) != 5:
        raise DiscrepancyArchiveError("split registry must contain five rows")
    seeds: list[int] = []
    expected_family_counts = {"train": 46, "validation": 7, "test": 13}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"partitions", "split_seed"}:
            raise DiscrepancyArchiveError("split row fields are not exact")
        seed = row.get("split_seed")
        partitions = row.get("partitions")
        if type(seed) is not int or not isinstance(partitions, dict):
            raise DiscrepancyArchiveError("split row identity is invalid")
        seeds.append(seed)
        if set(partitions) != set(expected_family_counts):
            raise DiscrepancyArchiveError("split partition names are not exact")

        observed_families: dict[str, set[str]] = {}
        observed_layouts: dict[str, set[int]] = {}
        for name, expected_family_count in expected_family_counts.items():
            partition = partitions[name]
            if not isinstance(partition, dict) or set(partition) != {
                "family_ids",
                "layout_ids",
                "n_families",
                "n_layouts",
            }:
                raise DiscrepancyArchiveError("split partition fields are not exact")
            family_ids = partition.get("family_ids")
            layout_ids = partition.get("layout_ids")
            if (
                not isinstance(family_ids, list)
                or not isinstance(layout_ids, list)
                or any(not isinstance(family_id, str) for family_id in family_ids)
                or any(type(layout_id) is not int for layout_id in layout_ids)
                or len(family_ids) != len(set(family_ids))
                or len(layout_ids) != len(set(layout_ids))
                or partition.get("n_families") != len(family_ids)
                or partition.get("n_layouts") != len(layout_ids)
                or len(family_ids) != expected_family_count
                or any(family_id not in family_members for family_id in family_ids)
            ):
                raise DiscrepancyArchiveError("split partition counts or types are invalid")
            expected_layouts = {
                layout_id
                for family_id in family_ids
                for layout_id in family_members[family_id]
            }
            if set(layout_ids) != expected_layouts:
                raise DiscrepancyArchiveError("split partition is not family closed")
            observed_families[name] = set(family_ids)
            observed_layouts[name] = set(layout_ids)

        if (
            set().union(*observed_families.values()) != set(family_members)
            or sum(len(value) for value in observed_families.values()) != 66
            or set().union(*observed_layouts.values()) != all_layouts
            or sum(len(value) for value in observed_layouts.values()) != 1500
            or len(selected_layout_ids & observed_layouts["test"]) != 39
        ):
            raise DiscrepancyArchiveError("split row is not disjoint, exhaustive, and selected-balanced")
    if seeds != [40, 41, 42, 43, 44]:
        raise DiscrepancyArchiveError("split seeds are not exact")


def _require_tracked(root: Path, paths: list[Path]) -> None:
    for path in paths:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            raise DiscrepancyArchiveError(f"analysis artifact is not tracked: {relative}")


def verify_analysis_archive(
    root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_git_tracked: bool = False,
) -> dict[str, int]:
    root = root.resolve()
    if root != ROOT.resolve():
        raise DiscrepancyArchiveError("discrepancy verifier requires its repository root")
    analysis_root = root / ANALYSIS_ROOT.relative_to(ROOT)
    canonical_manifest = analysis_root / "ANALYSIS_MANIFEST.json"
    if manifest_path.resolve() != canonical_manifest.resolve():
        raise DiscrepancyArchiveError("analysis manifest is not at its canonical path")
    manifest = load_json(manifest_path)
    job_id, source_commit = _require_manifest_structure(manifest)

    records = manifest.get("files", {})
    job_relative = (
        "results/corpus_v4/cps_multifidelity/audits/"
        f"r3_r4_discrepancy/v1/job_{job_id}"
    )
    operations_relative = (
        "results/corpus_v4/cps_multifidelity/audits/"
        "r3_r4_discrepancy/v1/operations"
    )
    expected_record_paths = {
        "batch_script": "code/jobs/submit_corpus_v4_cps_fidelity_discrepancy.sh",
        "execution_receipt": f"{job_relative}/execution_receipt.json",
        "failed_attempt_stdout": f"{operations_relative}/job_6894034.stdout.txt",
        "family_summaries": f"{job_relative}/family_summaries.jsonl",
        "implementation": (
            "code/experiments/proofs/"
            "audit_corpus_v4_cps_fidelity_discrepancy.py"
        ),
        "matched_pairs": f"{job_relative}/matched_pairs.jsonl",
        "protocol": "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json",
        "scheduler_completion": (
            "results/corpus_v4/cps_multifidelity/audits/"
            "r3_r4_discrepancy/v1/scheduler_completion.json"
        ),
        "submission_history": f"{operations_relative}/submission_history.json",
        "successful_attempt_stdout": f"{operations_relative}/job_{job_id}.stdout.txt",
        "summary": f"{job_relative}/summary.json",
        "upstream_archive": (
            "results/corpus_v4/cps_multifidelity/ARCHIVE_MANIFEST.json"
        ),
    }
    _require_canonical_record_paths(records, expected_record_paths)
    paths = {
        name: require_pinned_file(root, record, name)
        for name, record in records.items()
    }

    validate_archive(root, paths["upstream_archive"], require_git_tracked=True)
    protocol = load_json(paths["protocol"])
    if (
        protocol.get("implementation") != records["implementation"]
        or protocol.get("batch_script") != records["batch_script"]
        or protocol.get("inputs", {}).get("archive_manifest")
        != records["upstream_archive"]
    ):
        raise DiscrepancyArchiveError("protocol source pins differ from analysis manifest")

    plan_record = protocol.get("inputs", {}).get("plan")
    if not isinstance(plan_record, dict):
        raise DiscrepancyArchiveError("audit protocol does not pin the canonical plan")
    plan_path = require_pinned_file(root, plan_record, "plan")
    plan = load_json(plan_path)
    _require_plan_descendants(protocol, plan)
    plan_input_paths = {
        name: require_pinned_file(root, protocol["inputs"][name], name)
        for name in ("geometry_families", "hf_selection_registry", "split_registry")
    }
    selection = load_json(plan_input_paths["hf_selection_registry"])
    selected_rows = selection.get("rows")
    if not isinstance(selected_rows, list) or any(
        not isinstance(row, dict) for row in selected_rows
    ):
        raise DiscrepancyArchiveError("selection rows are unavailable")
    selected_layout_ids = {row.get("layout_id") for row in selected_rows}
    if (
        len(selected_layout_ids) != 198
        or any(type(layout_id) is not int for layout_id in selected_layout_ids)
    ):
        raise DiscrepancyArchiveError("selection layout identities are not exact")
    _validate_split_registry_strict(
        _load_jsonl(plan_input_paths["geometry_families"]),
        load_json(plan_input_paths["split_registry"]),
        selected_layout_ids,
    )

    job_dir = paths["summary"].parent
    expected_job_dir = analysis_root / f"job_{job_id}"
    if job_dir.resolve() != expected_job_dir.resolve():
        raise DiscrepancyArchiveError("analysis outputs are not under their job identity")
    _require_exact_inventory(
        job_dir,
        {
            "execution_receipt.json",
            "family_summaries.jsonl",
            "matched_pairs.jsonl",
            "summary.json",
        },
        "analysis job directory",
    )
    summary, pairs, families = build_audit(root, paths["protocol"])
    check_outputs(job_dir, protocol, summary, pairs, families)

    receipt = load_json(paths["execution_receipt"])
    completion = load_json(paths["scheduler_completion"])
    history = load_json(paths["submission_history"])
    if (
        receipt.get("job_id") != job_id
        or receipt.get("source_git_commit") != source_commit
        or completion
        != {
            "allocated_cpus": 3,
            "batch_max_rss_kib": 97956,
            "elapsed_seconds": 7,
            "exit_code": "0:0",
            "job_id": job_id,
            "job_name": "pcb-v4-cps-audit",
            "partition": "nextgen",
            "requested_cpus": 2,
            "requested_memory_gib": 8,
            "schema": "pcb-gnn.slurm-completion-receipt.v1",
            "state": "COMPLETED",
        }
    ):
        raise DiscrepancyArchiveError("scheduler completion does not close the job")
    attempts = history.get("attempts", [])
    if (
        history.get("schema")
        != "pcb-gnn.cps-fidelity-discrepancy-submission-history.v1"
        or len(attempts) != 3
        or attempts[0].get("job_created") is not False
        or attempts[1].get("job_id") != "6894034"
        or attempts[1].get("scientific_artifacts_written") is not False
        or attempts[2].get("job_id") != job_id
        or attempts[2].get("scientific_artifacts_written") is not True
    ):
        raise DiscrepancyArchiveError("submission history is incomplete")

    operations = paths["submission_history"].parent
    _require_exact_inventory(
        operations,
        {
            "job_6894034.stdout.txt",
            f"job_{job_id}.stdout.txt",
            "submission_history.json",
        },
        "analysis operations directory",
    )
    _require_exact_inventory(
        analysis_root,
        {
            "ANALYSIS_MANIFEST.json",
            f"job_{job_id}",
            "operations",
            "scheduler_completion.json",
        },
        "analysis root",
    )
    for name in (
        "execution_receipt",
        "scheduler_completion",
        "submission_history",
        "summary",
    ):
        _require_public_payload(load_json(paths[name]), name)
    for path in sorted(analysis_root.rglob("*")):
        if path.is_file():
            _require_public_text(path, path.relative_to(root).as_posix())
    if require_git_tracked:
        _require_tracked(
            root,
            [manifest_path, plan_path, *plan_input_paths.values(), *paths.values()],
        )
    return {"families": len(families), "pairs": len(pairs)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    try:
        counts = verify_analysis_archive(
            args.root,
            args.manifest,
            require_git_tracked=args.require_git_tracked,
        )
    except (
        ArchiveValidationError,
        DiscrepancyArchiveError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Corpus v4 discrepancy archive: FAIL: {exc}")
        return 1
    print(
        "Corpus v4 discrepancy archive: PASS "
        f"({counts['pairs']} pairs, {counts['families']} families)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
