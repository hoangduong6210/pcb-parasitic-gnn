"""Tiny geometry/linear-algebra identities, never an extractor invocation."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/core"), str(ROOT / "code/solvers")]
from geometry_contract import trace_box, validate_layout


@pytest.mark.parametrize("module", ["fastcap_ref", "fastercap_ref"])
def test_legacy_panels_are_not_current_smoke_geometry(module):
    # Twelve simple box faces only: no mesher, subprocess or field solver.
    adapter = importlib.import_module(module)
    layout = json.loads((ROOT / "protocols/tcad_cps_reference_v1.json").read_text())["smoke"]["layout"]
    validate_layout(layout)
    canonical = [trace_box(layout, t)[4:6] for t in layout["traces"]]
    legacy = []
    for trace in layout["traces"]:
        z = [float(vertex[2]) / adapter.M for face in adapter._box_panels(trace, 1) for vertex in face]
        legacy.append((min(z), max(z)))
    assert canonical[1][0] - canonical[0][1] == pytest.approx(.11)
    assert legacy[1][0] - legacy[0][1] == pytest.approx(.13)
    assert legacy != canonical


def test_maxwell_scalar_and_neutral_terminal_quantity_are_distinct():
    # Arbitrary positive-definite matrix, not project data. V=(1,0) gives
    # twice-energy C11; a charge-neutral unit-voltage pair gives det(C)/sum(C).
    c11, c12, c22 = 3., -1., 2.
    neutral = (c11*c22 - c12*c12) / (c11+c22+2*c12)
    v1 = (c12+c22) / (c11+c22+2*c12)
    v2 = v1 - 1
    q1, q2 = c11*v1 + c12*v2, c12*v1 + c22*v2
    assert q1 + q2 == pytest.approx(0)
    assert q1 == pytest.approx(neutral)
    assert v1*q1 + v2*q2 == pytest.approx(neutral)
    assert neutral != c11 and neutral != abs(c12)
