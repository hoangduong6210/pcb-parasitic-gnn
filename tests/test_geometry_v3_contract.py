"""Geometry-v3 contract tests; no field solver is invoked."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from gen_corpus_v3 import make_layout_v3  # noqa: E402
from geometry_contract import (  # noqa: E402
    GeometryContractError, geometry_sha256, trace_center_mm, trace_z_mm,
    validate_layout, validate_passive_labels,
)
from planar_to_graph import build_graph_from_planar_layout  # noqa: E402
from fasthenry_ref import layout_to_inp  # noqa: E402


def test_1500_seeded_layouts_pass_geometry_gate() -> None:
    hashes = set()
    for layout_id in range(1500):
        layout = make_layout_v3(42000 + layout_id)
        audit = validate_layout(layout)
        assert audit["volume_overlap_pairs"] == 0
        assert audit["board_contained"] and audit["layer_z_consistent"]
        if audit["minimum_same_layer_clearance_mm"] is not None:
            assert audit["minimum_same_layer_clearance_mm"] >= 0.2
        hashes.add(geometry_sha256(layout))
    assert len(hashes) == 1500


def test_graph_and_fasthenry_share_canonical_coordinates() -> None:
    layout = make_layout_v3(42000)
    graph = build_graph_from_planar_layout(layout)
    source, _ = layout_to_inp(layout)
    for index, trace in enumerate(layout["traces"]):
        center = trace_center_mm(layout, trace)
        np.testing.assert_allclose(graph.nodes[index].center_mm, center, atol=1e-8)
        expected = (
            f"N{index}a x={trace['x0']:.4f} y={center[1]:.4f} "
            f"z={trace_z_mm(layout, trace):.4f}"
        )
        assert expected in source


def test_layer_z_conflict_is_rejected() -> None:
    layout = make_layout_v3(42001)
    layout["traces"][0]["z_mm"] = trace_z_mm(layout, layout["traces"][0]) + 0.01
    with pytest.raises(GeometryContractError, match="maps to"):
        validate_layout(layout)


def test_overlap_and_board_escape_are_rejected() -> None:
    layout = make_layout_v3(42002)
    same_layer = [trace for trace in layout["traces"] if trace["layer"] == layout["traces"][0]["layer"]]
    assert len(same_layer) >= 2
    same_layer[1]["x0"] = same_layer[0]["x0"]
    same_layer[1]["y0"] = same_layer[0]["y0"]
    with pytest.raises(GeometryContractError, match="overlap"):
        validate_layout(layout)

    escaped = make_layout_v3(42003)
    escaped["traces"][0]["x0"] = escaped["board_w_mm"]
    with pytest.raises(GeometryContractError, match="board width"):
        validate_layout(escaped)


def test_passivity_gate() -> None:
    good = {"Cps_pF": 10.0, "L_pri_nH": 100.0, "L_sec_nH": 400.0, "L_mut_nH": 190.0}
    assert validate_passive_labels(good)["coupling_coefficient"] == pytest.approx(0.95)
    bad = copy.deepcopy(good)
    bad["L_mut_nH"] = 201.0
    with pytest.raises(GeometryContractError, match="passivity"):
        validate_passive_labels(bad)


def test_duplicate_ids_and_missing_current_are_rejected() -> None:
    duplicate = make_layout_v3(42004)
    duplicate["traces"][1]["trace_id"] = duplicate["traces"][0]["trace_id"]
    with pytest.raises(GeometryContractError, match="duplicate trace_id"):
        validate_layout(duplicate)

    missing_current = make_layout_v3(42005)
    del missing_current["traces"][0]["current_sign"]
    with pytest.raises(GeometryContractError, match="co-directed"):
        validate_layout(missing_current)
