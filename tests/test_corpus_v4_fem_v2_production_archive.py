from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/quality"))

from verify_corpus_v4_fem_v2_production_archive import (  # noqa: E402
    ArchiveVerificationError,
    R3_FIDELITY,
    R4_FIDELITY,
    _positive_number,
    _safe_relative_path,
    verify_archive,
)


def test_tracked_production_closure_passes_byte_and_identity_audit() -> None:
    result = verify_archive()

    assert result["status"] == "PASS"
    assert result["result_files_verified"] == 1698
    assert result["training_may_start"] is False
    assert result["fidelity_counts"] == {R3_FIDELITY: 1500, R4_FIDELITY: 198}


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
