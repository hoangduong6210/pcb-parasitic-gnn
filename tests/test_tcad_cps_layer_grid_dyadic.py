"""Small synthetic boxes and guarded orchestration; no real-layout planning."""
import ast
import copy
from fractions import Fraction
from contextlib import redirect_stdout
import io
import itertools
import json
import math
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_layer_grid_dyadic as c
import tcad_cps_layer_grid_dyadic_worker as worker
import tcad_cps_layer_grid_dyadic_axes as axes
import run_tcad_cps_layer_grid_dyadic as runner
import run_tcad_cps_layer_grid_plan as previous_runner
import tcad_cps_dielectric_cad_metadata as cad_metadata
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

P = c.protocol()
CFG = P[c.PHASE]
LIMITS = P["worker_limits"]["toy"]
BOXES = [[1.,2.,1.,2.,1.,2.], [1.,2.,1.,2.,3.,4.]]
DOMAIN = [0.,3.,0.,3.,0.,5.]
POLICY = {"near_size_mm": 1., "far_size_mm": 1., "face_band_half_width_mm": .5, "pad_mm": 1.}


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def plan(boxes=None, domain=None, policy=None, cfg=None, limits=None):
    return axes.plan_boxes(copy.deepcopy(boxes or BOXES), list(domain or DOMAIN), dict(policy or POLICY), cfg or CFG, limits or LIMITS)


def test_hand_counted_two_box_plan():
    report = plan()
    assert [a["point_count"] for a in report["axes"]] == [4, 4, 6]
    assert report["total_tensor_cells"] == 45
    assert report["dielectric_cells"] == 43
    assert report["tetrahedra"] == 258 and report["tensor_node_upper_bound"] == 96
    assert report["conductor_cell_counts"] == [1,1]
    assert report["exact_dielectric_volume_mm3"] == {"numerator": "43", "denominator": "1"}
    assert report["planning_feasible"] and all(report[k] is False for k in c.CLOSED)


def test_one_ulp_distinct_planes_are_never_snapped():
    boxes = copy.deepcopy(BOXES)
    boxes[1][0] = math.nextafter(1., 2.)
    planes = axes.canonical_planes(boxes, DOMAIN, 0)
    assert 1. in planes and boxes[1][0] in planes
    with pytest.raises(ValueError, match="point cap"):
        plan(boxes=boxes, cfg={**CFG, "axis_points_max": 32})


@pytest.mark.parametrize("cap", ["mesh_nodes_max", "mesh_tetrahedra_max"])
def test_infeasible_capacity_is_a_retained_plan(cap):
    report = plan(limits={**LIMITS, cap: 1})
    assert not report["planning_feasible"]
    assert report["axes"] and report["dielectric_cells"] == 43


def test_smaller_nominal_size_preserves_all_planes():
    coarse = plan()
    fine = plan(policy={**POLICY, "near_size_mm": .25})
    assert fine["dielectric_cells"] > coarse["dielectric_cells"]
    for a, b in zip(coarse["axes"], fine["axes"]):
        assert a["canonical_planes_mm"] == b["canonical_planes_mm"]
        assert set(a["canonical_planes_mm"]).issubset(b["points_mm"])
    assert fine["exact_dielectric_volume_mm3"] == coarse["exact_dielectric_volume_mm3"]


@pytest.mark.parametrize("kind", ["overlap", "touch_outer", "nan", "negative_size", "axis_cap", "near_gt_far", "reversed", "box_cap", "divisor", "depth", "band"])
def test_invalid_or_unbounded_inputs_fail(kind):
    boxes, domain, policy, cfg = copy.deepcopy(BOXES), list(DOMAIN), dict(POLICY), dict(CFG)
    if kind == "overlap": boxes[1] = list(boxes[0])
    if kind == "touch_outer": boxes[0][0] = domain[0]
    if kind == "nan": boxes[0][0] = float("nan")
    if kind == "negative_size": policy["near_size_mm"] = -1.
    if kind == "axis_cap": cfg["axis_points_max"] = 3
    if kind == "near_gt_far": policy["near_size_mm"] = 2.
    if kind == "reversed": boxes[0][1] = .5
    if kind == "box_cap": cfg["conductor_cap"] = 1
    if kind == "divisor": cfg["width_budget_divisor"] = 10
    if kind == "depth": cfg["subdivision_depth_max"] = 65
    if kind == "band": policy["face_band_half_width_mm"] = 0.
    with pytest.raises(ValueError):
        plan(boxes, domain, policy, cfg)


def test_subdivision_cap_checked_before_large_allocation():
    with pytest.raises(ValueError, match="point cap"):
        plan(policy={**POLICY, "near_size_mm": 1e-10}, cfg={**CFG, "axis_points_max": 32})


@pytest.mark.parametrize("widths", [(1,1,1), (1,2,3), (Fraction(1,100), 3, 5)])
@pytest.mark.parametrize("permutation", list(itertools.permutations(range(3))))
def test_condition_bound_for_each_kuhn_axis_order(widths, permutation):
    h = [Fraction(widths[k]) for k in permutation]
    # Rows permuted into the simplex's axis order; row/column permutations
    # do not change Frobenius or spectral norms. Orientation swap is allowed.
    matrix = [[h[0],h[0],h[0]], [0,h[1],h[1]], [0,0,h[2]]]
    inverse = [[1/h[0],-1/h[1],0], [0,1/h[1],-1/h[2]], [0,0,1/h[2]]]
    assert [[sum(matrix[i][k]*inverse[k][j] for k in range(3)) for j in range(3)] for i in range(3)] == [[1,0,0],[0,1,0],[0,0,1]]
    norm_product_squared = sum(v*v for row in matrix for v in row)*sum(v*v for row in inverse for v in row)
    assert norm_product_squared <= 30*(max(h)/min(h))**2


def setup_worker(monkeypatch, tmp_path):
    p = copy.deepcopy(P)
    layout = {"geometry_schema": "pcb-planar-active-legs.v3", "n_layers": 2, "board_w_mm": 4., "board_h_mm": 4.,
        "stackup": {"layer_pitch_mm": 2., "layer_z0_mm": 1.5},
        "traces": [{"trace_id": str(i), "net": net, "layer": i, "x0": 1., "y0": 1., "length_mm": 1., "width_mm": 1.,
                    "thick_mm": 1., "current_sign": 1} for i, net in enumerate(("pri", "sec"))]}
    arm = {"name": "synthetic", "level": 0, "pad_mm": 1., "far_size_mm": 1.}
    cad = {"canonical_boxes_mm": copy.deepcopy(BOXES), "domain_box_mm": list(DOMAIN)}
    for m in p[c.PHASE]["modes"]:
        p["dielectric_mesh"]["cad_report_sha256"][m] = sha256_json(cad)
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "protocol", lambda: p)
    monkeypatch.setattr(c, "mode_input", lambda *a: ("synthetic", layout, arm))
    monkeypatch.setattr(c, "cad_report", lambda *a: cad)
    monkeypatch.setattr(c, "policy", lambda *a: dict(POLICY))
    monkeypatch.setattr(cad_metadata, "review_report", lambda *a: {})
    monkeypatch.setattr(c, "check_source", lambda **kw: {})
    monkeypatch.setattr(c, "check_allocation", lambda *a: {"JobId": "123"})
    monkeypatch.setattr(c, "check_runtime", lambda *a: runner.expected_runtime(p))
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "synthetic"})
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    return p, c.attempt_directory("123", create=True)


def synthetic_arm(monkeypatch, directory, mode):
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", mode])
    buffer = io.StringIO()
    with redirect_stdout(buffer): worker.main()
    output = buffer.getvalue()
    (directory / f"{mode}.stdout").write_text(output)
    (directory / f"{mode}.stderr").write_text("")
    result = json.loads(output.split("RESULT=")[1])
    record = {"mode": mode, "passed": True, "returncode": 0, "failure": None, "elapsed_s": 1.,
        "observed_peak_rss_gib": .1, "files_sha256": runner.mode_files(directory, mode), "result": result}
    atomic_write_json(directory / f"{mode}.json", record)
    return record


@pytest.mark.parametrize("guard", ["check_allocation", "check_source", "check_runtime"])
@pytest.mark.parametrize("entry", [worker, runner])
def test_guards_before_real_layout_planning(monkeypatch, tmp_path, guard, entry):
    setup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(c, guard, Mock(side_effect=ValueError("guard failure")))
    heavy = Mock(side_effect=AssertionError("planning before guard"))
    monkeypatch.setattr(axes, "plan_boxes", heavy)
    monkeypatch.setattr(runner, "run", heavy)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="guard failure"): entry.main()
    heavy.assert_not_called()


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
def test_synthetic_worker_report_and_no_overwrite(monkeypatch, tmp_path, mode):
    p, directory = setup_worker(monkeypatch, tmp_path)
    arm = synthetic_arm(monkeypatch, directory, mode)
    runner.validate_result(arm["result"], mode, p, "123", directory)
    with pytest.raises(FileExistsError): worker.main()


@pytest.mark.parametrize("infeasible", [False, True])
def test_complete_attempt_retains_feasible_or_failed_planning(monkeypatch, tmp_path, infeasible):
    p, directory = setup_worker(monkeypatch, tmp_path)
    if infeasible:
        for limits in p["worker_limits"].values(): limits["mesh_nodes_max"] = 1
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p), "failure": None,
        "modes": {m: synthetic_arm(monkeypatch, directory, m) for m in p[c.PHASE]["modes"]}}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    monkeypatch.setattr(axes, "plan_boxes", Mock(side_effect=AssertionError("verifier must not replan")))
    assert runner.validate_attempt(directory, p) == record
    assert record["diagnostic_passed"] and record["planning_feasible"] is not infeasible
    assert all(record[k] is False for k in c.CLOSED)


@pytest.mark.parametrize("mutation", ["hash", "job", "mode", "claim", "time", "source", "summary"])
def test_result_mutations_rejected(monkeypatch, tmp_path, mutation):
    p, directory = setup_worker(monkeypatch, tmp_path)
    r = synthetic_arm(monkeypatch, directory, "toy")["result"]
    if mutation == "hash": r["report_sha256"] = "0"*64
    if mutation == "job": r["scheduler"]["JobId"] = "124"
    if mutation == "mode": r["mode"] = "local1"
    if mutation == "claim": r["claim_eligible"] = True
    if mutation == "time": r["elapsed_s"] = 181
    if mutation == "source": r["source_commit"] = "changed"
    if mutation == "summary": r["summary"]["planning_feasible"] = False
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


@pytest.mark.parametrize("mutation", ["coordinate", "plane", "count", "bound", "snapped", "geometry", "hex", "feasible", "policy", "base", "leaf", "leaf_count", "budget", "far_flag"])
def test_resealed_report_metadata_mutations_rejected(monkeypatch, tmp_path, mutation):
    p, directory = setup_worker(monkeypatch, tmp_path)
    r = synthetic_arm(monkeypatch, directory, "toy")["result"]
    path = directory / "toy.report.json"
    report = c.read_json(path)
    if mutation == "coordinate": report["axes"][0]["points_mm"][0] = -1.
    if mutation == "plane": report["axes"][0]["canonical_planes_mm"].pop()
    if mutation == "count": report["dielectric_cells"] += 1
    if mutation == "bound": report["jacobian_condition_upper_bound_squared"]["numerator"] = "0"
    if mutation == "snapped": report["coordinates_snapped"] = True
    if mutation == "geometry": report["canonical_boxes_mm"][0][0] += .01
    if mutation == "hex": report["axes"][0]["points_hex_mm"][0] = "changed"
    if mutation == "feasible": report["planning_feasible"] = False
    if mutation == "policy": report["policy"]["near_size_mm"] = 2.
    if mutation == "base": report["axes"][0]["base_planes_mm"].append(1.5)
    if mutation == "leaf": report["axes"][0]["leaf_intervals"][0]["depth"] = 65
    if mutation == "leaf_count": report["axes"][0]["leaf_intervals"].pop()
    if mutation == "budget": report["width_budget"]["planning_width_floor_mm"]["numerator"] = "99"
    if mutation == "far_flag": report["width_budget"]["far_spacing_reduced"] = True
    atomic_write_json(path, report)
    r.update(report_sha256=sha256_file(path), report_bytes=path.stat().st_size, summary={k: report[k] for k in worker.SUMMARY_KEYS})
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


def test_inherited_watchdog_and_receipt_control_flow_unchanged():
    def body(module, name):
        node = next(n for n in ast.parse(Path(module.__file__).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
        class Normalize(ast.NodeTransformer):
            def visit_Constant(self, n):
                return ast.copy_location(ast.Constant(n.value.replace("arithmetic", "grid planning")), n) if isinstance(n.value, str) else n
        return ast.dump(Normalize().visit(node))
    for function in ("bounded_mode", "validate_attempt", "run", "main", "mode_files"):
        assert body(runner, function) == body(previous_runner, function)


def test_cap_inheritance_and_no_active_allocation(monkeypatch):
    original = c.parent.protocol()
    for m in P[c.PHASE]["modes"]:
        assert P["worker_limits"][m]["mesh_nodes_max"] == original["worker_limits"][m]["mesh_nodes_max"]
        assert P["worker_limits"][m]["mesh_tetrahedra_max"] == original["worker_limits"][m]["mesh_tetrahedra_max"]
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    with pytest.raises(ValueError, match="login-node"): c.check_allocation(c.PHASE, P)


def test_frozen_source_byte_only():
    if not (ROOT / c.LOCK).exists(): pytest.skip("pre-freeze only")
    assert c.check_source(execution=False)["files_sha256"]

def test_face_band_edges_are_not_inserted():
    # Tiny synthetic regression of the previously observed auxiliary-plane trap.
    boxes = [[1.,2.,1.,2.,.1,.135], [1.,2.,1.,2.,.24500000000000002,.3]]
    policy = {**POLICY, "face_band_half_width_mm": .055}
    report = plan(boxes=boxes, domain=[0.,3.,0.,3.,0.,1.], policy=policy)
    axis = report["axes"][2]
    assert axis["base_planes_mm"] == [0.,.1,.135,.24500000000000002,.3,1.]
    assert .19 not in axis["base_planes_mm"] and .19000000000000003 not in axis["base_planes_mm"]
    assert axes.unpack(axis["minimum_cell_width_mm"]) > Fraction(1,100)
    assert report["planning_feasible"]


def test_budget_decreases_far_spacing_for_small_canonical_gap():
    boxes = copy.deepcopy(BOXES)
    boxes[0][1] = 1.001
    report = plan(boxes=boxes)
    budget = report["width_budget"]
    assert budget["far_spacing_reduced"]
    assert axes.unpack(budget["maximum_target_width_mm"]) < 1
    assert report["planning_checks"]["jacobian_condition_bound"]


def test_dyadic_leaves_meet_targets_and_have_canonical_coverage():
    report = plan(policy={**POLICY, "near_size_mm": .125, "face_band_half_width_mm": .05})
    for axis in report["axes"]:
        canonical = axis["canonical_planes_mm"]
        for leaf in axis["leaf_intervals"]:
            width = axes.fraction(leaf["right_mm"])-axes.fraction(leaf["left_mm"])
            assert 0 < width <= axes.unpack(leaf["target_max_width_mm"])
            i = leaf["canonical_interval"]
            assert canonical[i] <= leaf["left_mm"] < leaf["right_mm"] <= canonical[i+1]
            assert width == (axes.fraction(canonical[i+1])-axes.fraction(canonical[i]))/2**leaf["depth"]
    assert plan(policy={**POLICY, "near_size_mm": .125, "face_band_half_width_mm": .05}) == report


def test_depth_cap_fails_without_snapping():
    with pytest.raises(ValueError, match="depth cap"):
        plan(policy={**POLICY, "near_size_mm": .01}, cfg={**CFG, "subdivision_depth_max": 1})


def test_unchanged_actual_width_condition_gate_is_recomputed():
    report = plan(policy={**POLICY, "near_size_mm": .25})
    widths = [axes.fraction(b)-axes.fraction(a) for axis in report["axes"]
              for a,b in zip(axis["points_mm"],axis["points_mm"][1:])]
    assert axes.unpack(report["axis_width_ratio"]) == max(widths)/min(widths)
    assert axes.unpack(report["jacobian_condition_upper_bound_squared"]) == 30*(max(widths)/min(widths))**2
