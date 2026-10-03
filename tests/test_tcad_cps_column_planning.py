"""Tiny hand-counted packet integration; no native kernel or actual layout."""
import copy
from fractions import Fraction
import hashlib
import json

import numpy as np
import pytest

from test_tcad_cps_column_mesh import packet_fixture, report_fixture, BOXES, DOMAIN, CFG, OPTIONS, LIMITS
import tcad_cps_column_planning as planning
from tcad_cps_column_contract import prism_condition_bound, unpack

POLICY = {"near_size_mm": 1., "far_size_mm": 1., "face_band_half_width_mm": .5}
SETTINGS = {"axis_points_max": 4096, "subdivision_depth_max": 64, "jacobian_condition_bound_max": 10000}
CAPS = {**LIMITS, "mesh_nodes_max": 1000, "mesh_tetrahedra_max": 1000}


def plan(packet=None, settings=None, limits=None):
    return planning.plan_packet(packet if packet is not None else packet_fixture(), report_fixture(), BOXES, DOMAIN,
        CFG, OPTIONS, POLICY, settings or SETTINGS, limits or CAPS)


def test_exact_hand_counted_columns_and_certificate_sequence():
    p, r = packet_fixture(), plan()
    assert r["vertical_axis"]["points_mm"] == [0., 1., 2., 3., 4., 5.]
    assert r["capacity"]["prisms"] == 86 and r["capacity"]["tetrahedra"] == 258
    assert r["capacity"]["column_node_upper_bound"] == 96
    assert unpack(r["prospective_mesh_volume_mm3"]) == 43
    assert unpack(r["mesh_canonical_volume_error_mm3"]) == 0
    assert r["planning_feasible"] is True and r["planar_mesh_validated"] is True
    assert all(r[k] is False for k in planning.CLOSED)
    # Retain the counting helper's narrower scope; it did not audit the mesh.
    assert r["capacity"]["planar_mesh_validated"] is False
    c = r["conditioning"]
    assert c["triangles_checked"] == 18 and c["templates_checked"] == 54 and c["failed_triangles"] == 0
    digest = hashlib.sha256(b"pcb-gnn.column-condition-sequence.v1\0")
    certificates = []
    for tag, nodes, face in zip(p["triangle_tags"].tolist(), p["triangle_nodes"].tolist(), p["triangle_surfaces"].tolist()):
        ordered = sorted(nodes)
        certificate = prism_condition_bound([p["coordinates_mm"][n-1,:2].tolist() for n in ordered], Fraction(1), Fraction(1))
        item = {"triangle_tag": tag, "ordered_node_tags": ordered, "owners": [] if face == 1 else [0,1], "certificate": certificate}
        digest.update(json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
        certificates.append(item)
    assert c["certificate_sequence_sha256"] == digest.hexdigest()
    assert c["worst_witness"] == max(certificates, key=lambda v: unpack(v["certificate"]["condition_upper_bound_squared"]))
    assert c["condition_upper_bound_squared"] == c["worst_witness"]["certificate"]["condition_upper_bound_squared"]


@pytest.mark.parametrize("cap", ["mesh_nodes_max", "mesh_tetrahedra_max"])
def test_capacity_failure_keeps_complete_geometry_and_condition_report(cap):
    r = plan(limits={**CAPS, cap: 1})
    assert not r["planning_feasible"] and not r["capacity"]["capacity_feasible"]
    assert r["conditioning"]["triangles_checked"] == 18 and r["conditioning"]["conditioning_passed"]
    assert r["planar_audit"]["planar_mesh_validated"]


def test_condition_failure_keeps_counts_and_witness():
    r = plan(settings={**SETTINGS, "jacobian_condition_bound_max": 1})
    assert r["capacity"]["capacity_feasible"] and not r["planning_feasible"]
    assert r["conditioning"]["failed_triangles"] == 18
    assert r["conditioning"]["worst_witness"]


def test_raw_orientation_and_record_order_do_not_change_template_certification():
    p = packet_fixture()
    p["triangle_nodes"][:, [1,2]] = p["triangle_nodes"][:, [2,1]]
    p["triangle_tags"] = p["triangle_tags"][::-1]
    p["triangle_nodes"] = p["triangle_nodes"][::-1]
    p["triangle_surfaces"] = p["triangle_surfaces"][::-1]
    r = plan(p)
    assert r["conditioning"] == plan()["conditioning"]
    assert r["planar_audit"]["raw_clockwise_triangles"] == 18


def test_plan_does_not_mutate_raw_input_and_bad_mesh_cannot_be_counted():
    p = packet_fixture()
    original = copy.deepcopy(p)
    plan(p)
    assert all(np.array_equal(p[k], original[k]) for k in p)
    p["triangle_surfaces"][0] = 2
    with pytest.raises(ValueError): plan(p)


def test_exact_nonrepresentable_height_difference_reaches_certificate(monkeypatch):
    boxes = copy.deepcopy(BOXES)
    boxes[0][4] = .1
    report = report_fixture()
    report["canonical_boxes_mm"] = boxes
    observed, original = [], planning.prism_condition_bound
    def capture(xy, lo, hi, maximum):
        assert isinstance(lo, Fraction) and isinstance(hi, Fraction)
        observed.append((lo, hi))
        return original(xy, lo, hi, maximum)
    monkeypatch.setattr(planning, "prism_condition_bound", capture)
    r = planning.plan_packet(packet_fixture(), report, boxes, DOMAIN, CFG, OPTIONS,
        {**POLICY, "near_size_mm": 10., "far_size_mm": 10.}, SETTINGS, CAPS)
    difference = Fraction(2)-Fraction.from_float(.1)
    assert difference != Fraction.from_float(float(difference))
    assert any(hi == difference for lo, hi in observed)
    assert unpack(r["mesh_canonical_volume_error_mm3"]) == 0


@pytest.mark.parametrize("value", [True, 0, -1, 1.5])
def test_invalid_condition_settings(value):
    with pytest.raises(ValueError): plan(settings={**SETTINGS, "jacobian_condition_bound_max": value})
