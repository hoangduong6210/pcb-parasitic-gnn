"""Geometry regression tests for the independent finite-segment Neumann reference."""
from __future__ import annotations

import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/solvers"))

from fem_inductance_ref import _pair_M_nh, parallel_segments_mutual_nh  # noqa: E402


def test_general_segment_formula_reduces_to_aligned_equal_length_formula() -> None:
    expected = _pair_M_nh(0.04, 0.0012)
    actual = parallel_segments_mutual_nh(0.0, 0.04, 0.0, 0.04, 0.0012)
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_parallel_segment_mutual_is_reciprocal_and_decreases_with_offset() -> None:
    forward = parallel_segments_mutual_nh(0.002, 0.04, 0.009, 0.032, 0.001)
    reverse = parallel_segments_mutual_nh(0.009, 0.032, 0.002, 0.04, 0.001)
    far = parallel_segments_mutual_nh(0.002, 0.04, 0.029, 0.032, 0.001)
    assert forward > 0.0
    assert math.isclose(forward, reverse, rel_tol=1e-12, abs_tol=1e-12)
    assert far < forward
