"""Hand-counted rectangles and tiny exact budgets, never actual layouts."""
import copy
from fractions import Fraction as F
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/solvers"))
import tcad_cps_sizing_budget_math as m

BOXES = [[1.,2.,1.,2.,1.,2.], [1.,2.,1.,2.,3.,4.]]
DOMAIN = [0.,3.,0.,3.,0.,5.]
POLICY = {"near_size_mm": 1., "far_size_mm": 2., "face_band_half_width_mm": .5}
CFG = {"axis_points_max": 4096, "subdivision_depth_max": 64, "rectangle_cap": 128, "reference_cells_max": 100000}
LIMITS = {"mesh_nodes_max": 100, "mesh_tetrahedra_max": 90, "planar_nodes_max": 12, "planar_triangles_max": 100}


def sizing():
    field = {"XMin": .75, "XMax": 2.25, "YMin": .75, "YMax": 2.25, "ZMin": -.25, "ZMax": .25,
        "VIn": 1., "VOut": 2., "Thickness": .25}
    return {"box_fields": [dict(field),dict(field)], "policy": dict(POLICY), "background": "Min",
        "options": {"Mesh.MeshSizeMin": 1., "Mesh.MeshSizeMax": 2.}}


def diagnose(**kwargs):
    args = dict(boxes=copy.deepcopy(BOXES), domain=list(DOMAIN), requested_sizing=sizing(), policy=dict(POLICY),
        limits=dict(LIMITS), cfg=dict(CFG), native_log="Info    : 16 nodes 50 elements\n")
    args.update(kwargs)
    return m.diagnose(**args)


def test_hand_counted_complete_duplicate_footprints_and_step_indices():
    r = diagnose()
    parts = r["coverage"]
    assert [m.unpack(parts[k]["union_area_mm2"]) for k in parts] == [F(1),F(9,4),F(4)]
    assert m.unpack(parts["near_core"]["sum_clipped_rectangle_areas_mm2"]) == F(9,2)
    assert m.unpack(parts["near_core"]["overlap_excess_area_mm2"]) == F(9,4)
    assert parts["near_core"]["unique_clipped_rectangles"] == 1
    assert {k:m.unpack(v) for k,v in r["step_field_workload_indices"].items()} == {"conductors":F(3),"near_core":F(63,16),"expanded_envelope":F(21,4)}
    assert r["step_field_index_is_node_prediction"] is False and r["transition_function_replayed"] is False
    assert r["expanded_envelope_is_measured_transition_area"] is False
    assert r["native_log_counts"]["independently_audited"] is False
    assert r["native_log_counts"]["triangle_count_inferred"] is False
    assert r["logged_nodes_within_capture_cap"] is False
    assert r["conditional_full_column_node_bound_from_log"] == 96
    assert r["conditional_full_column_node_bound_passes"] is True
    assert r["candidate_selected"] is False and all(r[k] is False for k in m.CLOSED)


def test_hand_counted_vertical_budget_is_not_a_mesh_count_prediction():
    r = diagnose()["vertical_budget"]
    assert r["vertical_axis"]["points_mm"] == [0.,1.,2.,3.,4.,5.]
    assert r["planar_node_budget_from_full_column_bound"] == 16
    assert r["planar_node_budget_with_capture_cap"] == 12
    assert r["planar_triangle_sufficient_budget"] == 6 and r["planar_triangle_necessary_ceiling"] == 10
    assert r["minimum_retained_intervals"] == 3 and r["maximum_retained_intervals"] == 5
    assert m.unpack(r["exact_dielectric_volume_mm3"]) == 43
    assert r["groups"][1]["retained_intervals"] == [0,2,4]
    assert r["mesh_connectivity_observed"] is False


def test_node_capture_and_column_budgets_are_independent():
    r = diagnose(limits={**LIMITS, "mesh_nodes_max": 90, "planar_nodes_max": 100})
    assert r["logged_nodes_within_capture_cap"] and not r["conditional_full_column_node_bound_passes"]
    assert r["vertical_budget"]["planar_node_budget_with_capture_cap"] == 15


def test_clipping_duplicate_and_disjoint_rectangles_conserve_weighted_area():
    r = m.coverage([[-1,2,-1,2],[1,4,1,4],[10,11,10,11]], [0,3,0,3])
    assert r["rectangle_count"] == 3 and r["nonempty_clipped_rectangles"] == 2
    assert m.unpack(r["union_area_mm2"]) == 7
    assert m.unpack(r["sum_clipped_rectangle_areas_mm2"]) == 8
    assert {v["multiplicity"]:m.unpack(v["area_mm2"]) for v in r["area_by_multiplicity_mm2"]} == {0:F(2),1:F(6),2:F(1)}


def test_all_rectangles_outside_domain_is_exact_zero_union():
    r = m.coverage([[2,3,2,3]], [0,1,0,1])
    assert m.unpack(r["union_area_mm2"]) == 0 and r["unique_clipped_rectangles"] == 0


def test_one_ulp_strip_and_exact_nonrepresentable_envelope_not_snapped():
    x = math.nextafter(1.,2.)
    r = m.coverage([[1.,x,0.,1.]], [0.,2.,0.,1.])
    assert m.unpack(r["union_area_mm2"]) == F.from_float(x)-1 > 0
    exact = F(1)-F.from_float(.1)
    assert exact != F.from_float(float(exact))
    r = m.coverage([[0,exact,0,1]], [0,2,0,1])
    assert m.unpack(r["union_area_mm2"]) == exact


@pytest.mark.parametrize("kind", ["empty", "reversed", "nan", "bool", "dimension", "rectangle_cap", "cell_cap"])
def test_invalid_or_unbounded_coverage(kind):
    rects, kwargs = [[0,1,0,1]], {}
    if kind == "empty": rects = []
    if kind == "reversed": rects[0][1] = -1
    if kind == "nan": rects[0][0] = math.nan
    if kind == "bool": rects[0][0] = False
    if kind == "dimension": rects[0].append(0)
    if kind == "rectangle_cap": kwargs["rectangle_cap"] = 0
    if kind == "cell_cap": kwargs["cell_cap"] = 1
    with pytest.raises(ValueError): m.coverage(rects, [-1,2,-1,2], **kwargs)


@pytest.mark.parametrize("text", ["", "Info : 1 nodes 2 elements\nInfo : 2 nodes 3 elements", "Info : 0 nodes 2 elements",
    "Info : 3 nodes 2 elements", "Info : 2 nodes 1000000000 elements", "Info : 2.0 nodes 3 elements", "x"*2097153])
def test_bad_native_log_identity_or_bounds(text):
    with pytest.raises(ValueError): m.logged_counts(text)


@pytest.mark.parametrize("kind", ["fields", "z", "near", "far", "thickness", "core", "background", "policy", "option", "extra", "nonfinite", "overlap", "limit"])
def test_invalid_diagnostic_configuration(kind):
    s, boxes, limits = sizing(), copy.deepcopy(BOXES), dict(LIMITS)
    if kind == "fields": s["box_fields"].pop()
    if kind == "z": s["box_fields"][0]["ZMin"] = .1
    if kind == "near": s["box_fields"][0]["VIn"] = .5
    if kind == "far": s["box_fields"][0]["VOut"] = 3.
    if kind == "thickness": s["box_fields"][0]["Thickness"] = -1.
    if kind == "core": s["box_fields"][0]["XMin"] = 1.1
    if kind == "background": s["background"] = "Max"
    if kind == "policy": s["policy"]["near_size_mm"] = .5
    if kind == "option": s["options"]["Mesh.MeshSizeMin"] = .5
    if kind == "extra": s["box_fields"][0]["surprise"] = 1
    if kind == "nonfinite": s["box_fields"][0]["Thickness"] = math.inf
    if kind == "overlap": boxes[1] = list(boxes[0])
    if kind == "limit": limits["mesh_nodes_max"] = True
    with pytest.raises(ValueError): diagnose(requested_sizing=s, boxes=boxes, limits=limits)


def test_negative_budget_is_retained_not_silently_repaired():
    r = diagnose(limits={**LIMITS,"mesh_nodes_max":1,"mesh_tetrahedra_max":1})
    assert r["vertical_budget"]["planar_node_budget_from_full_column_bound"] == 0
    assert r["vertical_budget"]["planar_triangle_sufficient_budget"] == 0
    assert r["conditional_full_column_node_bound_passes"] is False
