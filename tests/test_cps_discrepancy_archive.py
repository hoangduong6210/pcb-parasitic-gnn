"""Clean-clone contracts for the job-backed Cps discrepancy archive."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/quality"))

from verify_corpus_v4_discrepancy_archive import (  # noqa: E402
    ANALYSIS_ROOT,
    DEFAULT_MANIFEST,
    DiscrepancyArchiveError,
    _require_canonical_record_paths,
    _require_exact_inventory,
    _require_manifest_structure,
    _require_plan_descendants,
    _require_public_payload,
    _require_public_text,
    _validate_split_registry_strict,
    verify_analysis_archive,
)


def test_job_backed_discrepancy_archive_validates_end_to_end() -> None:
    assert DEFAULT_MANIFEST == ANALYSIS_ROOT / "ANALYSIS_MANIFEST.json"
    assert verify_analysis_archive(ROOT, DEFAULT_MANIFEST) == {
        "families": 66,
        "pairs": 198,
    }


def test_admitted_descriptive_values_are_pinned_to_the_completed_job() -> None:
    summary = json.loads(
        (ANALYSIS_ROOT / "job_6894098/summary.json").read_text()
    )
    selected = summary["metrics"]["selected_set"]
    absolute = selected["absolute_delta_percent"]
    assert selected["direction_counts"] == {
        "r3_equal_r4_within_1e_15_percent": 0,
        "r3_greater_than_r4": 198,
        "r3_less_than_r4": 0,
    }
    assert absolute["count"] == 198
    assert absolute["median"] == 8.479391982064804
    assert absolute["mean"] == 8.84899205282953
    assert absolute["min"] == 2.753572170580615
    assert absolute["max"] == 17.516912882684615
    assert summary["scientific_semantics"]["descriptive_only"] is True
    assert summary["scientific_semantics"]["r4_is_higher_resolution_not_truth"] is True


def test_scheduler_receipts_distinguish_failed_closed_and_completed_jobs() -> None:
    completion = json.loads(
        (ANALYSIS_ROOT / "scheduler_completion.json").read_text()
    )
    history = json.loads(
        (ANALYSIS_ROOT / "operations/submission_history.json").read_text()
    )
    assert completion["job_id"] == "6894098"
    assert completion["state"] == "COMPLETED"
    assert completion["exit_code"] == "0:0"
    assert completion["requested_cpus"] == 2
    assert completion["allocated_cpus"] == 3
    assert history["attempts"][1]["job_id"] == "6894034"
    assert history["attempts"][1]["scientific_artifacts_written"] is False
    assert history["attempts"][2]["scientific_artifacts_written"] is True


def test_exact_inventory_rejects_extra_files_and_symlinks(tmp_path: Path) -> None:
    directory = tmp_path / "archive"
    directory.mkdir()
    (directory / "summary.json").write_text("{}\n")
    _require_exact_inventory(directory, {"summary.json"}, "fixture")
    (directory / "extra.json").write_text("{}\n")
    with pytest.raises(DiscrepancyArchiveError, match="inventory is not exact"):
        _require_exact_inventory(directory, {"summary.json"}, "fixture")

    (directory / "extra.json").unlink()
    (directory / "link").symlink_to(directory / "summary.json")
    with pytest.raises(DiscrepancyArchiveError, match="contains a symlink"):
        _require_exact_inventory(directory, {"summary.json", "link"}, "fixture")


def test_public_archive_rejects_private_execution_paths() -> None:
    with pytest.raises(DiscrepancyArchiveError, match="private path"):
        _require_public_payload(
            {"executed_path": "/users/example/slurm_script"}, "fixture"
        )


def test_analysis_manifest_identity_and_keys_are_exact() -> None:
    manifest = json.loads(DEFAULT_MANIFEST.read_text())
    assert _require_manifest_structure(manifest) == (
        "6894098",
        "f0f60cdf67daf3df6973185d353836677163c02e",
    )

    malformed = dict(manifest)
    malformed["unexpected"] = True
    with pytest.raises(DiscrepancyArchiveError, match="keys are not exact"):
        _require_manifest_structure(malformed)

    wrong_identity = dict(manifest)
    wrong_identity["analysis_id"] = "replacement-analysis"
    with pytest.raises(DiscrepancyArchiveError, match="archive identity"):
        _require_manifest_structure(wrong_identity)


def test_analysis_manifest_records_require_canonical_paths() -> None:
    records = {"summary": {"path": "canonical/summary.json", "sha256": "a" * 64}}
    _require_canonical_record_paths(records, {"summary": "canonical/summary.json"})

    duplicate_path = {
        "summary": {"path": "duplicate/summary.json", "sha256": "a" * 64}
    }
    with pytest.raises(DiscrepancyArchiveError, match="not canonical"):
        _require_canonical_record_paths(
            duplicate_path, {"summary": "canonical/summary.json"}
        )


def test_public_text_scan_covers_logs_and_secrets(tmp_path: Path) -> None:
    log = tmp_path / "stdout.txt"
    log.write_text("audit completed\n", encoding="utf-8")
    _require_public_text(log, "fixture")

    log.write_text("executed under /tmp/private-worktree\n", encoding="utf-8")
    with pytest.raises(DiscrepancyArchiveError, match="private path"):
        _require_public_text(log, "fixture")

    fake_token = "ghp_" + "a" * 30
    log.write_text(f"token {fake_token}\n", encoding="utf-8")
    with pytest.raises(DiscrepancyArchiveError, match="GitHub token"):
        _require_public_text(log, "fixture")


def test_audit_inputs_are_exact_descendants_of_the_frozen_plan() -> None:
    protocol = json.loads(
        (ROOT / "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json").read_text()
    )
    plan = json.loads(
        (
            ROOT
            / "results/corpus_v4/cps_multifidelity/plan/v1/plan.json"
        ).read_text()
    )
    _require_plan_descendants(protocol, plan)

    tampered = copy.deepcopy(protocol)
    tampered["inputs"]["hf_selection_registry"]["path"] = (
        "results/alternative/hf_selection_registry.json"
    )
    with pytest.raises(DiscrepancyArchiveError, match="plan descendant"):
        _require_plan_descendants(tampered, plan)


def test_strict_split_validation_rejects_duplicate_layout_id() -> None:
    plan_dir = ROOT / "results/corpus_v4/cps_multifidelity/plan/v1"
    families = [
        json.loads(line)
        for line in (plan_dir / "geometry_families.jsonl").read_text().splitlines()
    ]
    registry = json.loads((plan_dir / "split_registry.json").read_text())
    selection = json.loads((plan_dir / "hf_selection_registry.json").read_text())
    selected = {row["layout_id"] for row in selection["rows"]}
    _validate_split_registry_strict(families, registry, selected)

    tampered = copy.deepcopy(registry)
    train_ids = tampered["rows"][0]["partitions"]["train"]["layout_ids"]
    train_ids[1] = train_ids[0]
    with pytest.raises(DiscrepancyArchiveError, match="counts or types"):
        _validate_split_registry_strict(families, tampered, selected)
