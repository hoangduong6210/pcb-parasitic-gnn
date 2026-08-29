from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/quality"))

from verify_corpus_v4_fem_v2_production_archive import (  # noqa: E402
    ArchiveVerificationError,
    EXPECTED_WAVE_ADMISSIONS,
    R3_FIDELITY,
    R4_FIDELITY,
    _load_jsonl,
    _positive_number,
    _safe_relative_path,
    _validate_result,
    _verify_source_commit,
    verify_archive,
)


def test_tracked_production_closure_passes_byte_and_identity_audit() -> None:
    result = verify_archive()

    assert result["status"] == "PASS"
    assert result["result_files_verified"] == 1698
    assert result["training_may_start"] is False
    assert result["fidelity_counts"] == {R3_FIDELITY: 1500, R4_FIDELITY: 198}


def test_wave_inventory_is_frozen_to_five_r3_waves_and_one_r4_wave() -> None:
    assert len(EXPECTED_WAVE_ADMISSIONS) == 6
    assert sum("/waves/r3/" in path for path in EXPECTED_WAVE_ADMISSIONS) == 5
    assert sum("/waves/r4/" in path for path in EXPECTED_WAVE_ADMISSIONS) == 1
    assert all((ROOT / path).is_file() for path in EXPECTED_WAVE_ADMISSIONS)


def test_result_cross_join_rejects_changed_observation_value() -> None:
    observations = ROOT / (
        "results/corpus_v4/cps_reference_v2/production/v1/dataset/final/"
        "source_set_f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b/"
        "finalizer_job_7084776/label_observations.jsonl"
    )
    row = dict(_load_jsonl(observations)[0])
    result_path = ROOT / row["artifact_result_path"]
    row["cps_pf"] *= 1.01

    with pytest.raises(ArchiveVerificationError, match="payload mismatch"):
        _validate_result(row, result_path)


def test_source_commit_gate_rejects_wrong_blob_hash() -> None:
    with pytest.raises(ArchiveVerificationError, match="bytes changed"):
        _verify_source_commit(
            "c01b97bc90cbe3d1f2094e9441eb2e18219e4eb1",
            {"requirements-proof.txt": "0" * 64},
        )


@pytest.mark.parametrize(
    "value",
    ("../escape.json", "/absolute.json", "mixed\\separator.json", ""),
)
def test_repository_path_gate_rejects_unsafe_paths(value: str) -> None:
    with pytest.raises(ArchiveVerificationError):
        _safe_relative_path(value, "test")


@pytest.mark.parametrize("value", (0, -1, float("inf"), float("nan"), "1"))
def test_positive_numeric_gate_is_fail_closed(value: object) -> None:
    with pytest.raises(ArchiveVerificationError):
        _positive_number(value, "test")
