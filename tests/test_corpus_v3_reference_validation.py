"""Lightweight contracts for the corpus-v3 reference-validation protocol."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "code/core", ROOT / "code/data", ROOT / "code/solvers",
                  ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from experiments_corpus_v3_reference_validation import SETTINGS, selected_indices  # noqa: E402
from finalize_corpus_v3_reference_validation import relative_delta  # noqa: E402


def test_validation_selection_is_unique_and_stratified() -> None:
    samples = []
    for index in range(15):
        samples.append({
            "layout": {"traces": [{}] * (8 + index)},
            "y": [float((index * 7) % 13 + 1), 1.0, 1.0, 0.5],
        })
    selected = selected_indices(samples)
    assert len(selected) == len(set(selected)) == 9
    assert SETTINGS == ((1, 8.0), (1, 12.0), (2, 8.0), (2, 12.0))


def test_relative_delta_uses_right_setting_as_denominator() -> None:
    tasks = [{
        "selection": {"layout_id": 17},
        "settings": [
            {"refine": 1, "pad_mm": 8.0, "cps_pf": 11.0},
            {"refine": 2, "pad_mm": 8.0, "cps_pf": 10.0},
        ],
    }]
    result = relative_delta(tasks, (1, 8.0), (2, 8.0))
    assert result["n_paired"] == 1
    assert result["median_relative_difference_pct"] == 10.0
    assert result["max_relative_difference_pct"] == 10.0
