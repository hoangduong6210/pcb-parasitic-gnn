"""Tiny synthetic diagnostic integration; no actual geometry replay on login."""
import ast
import copy
from contextlib import redirect_stdout
import io
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_sizing_budget as c
import tcad_cps_sizing_budget_worker as worker
import tcad_cps_sizing_budget_math as mathlib
import run_tcad_cps_sizing_budget as runner
import run_tcad_cps_layer_grid_dyadic as previous_runner
import tcad_cps_dielectric_cad_metadata as cad_metadata
import tcad_cps_column_cad as planar_metadata
from tcad_cps_column_builder import sizing_policy
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

P = c.protocol()
BOXES = [[1.,2.,1.,2.,1.,2.], [1.,2.,1.,2.,3.,4.]]
DOMAIN = [0.,3.,0.,3.,0.,5.]
POLICY = {"near_size_mm": 1., "far_size_mm": 2., "face_band_half_width_mm": .5, "pad_mm": 1.}


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def setup_worker(monkeypatch, tmp_path):
    p = copy.deepcopy(P)
    layout = {"geometry_schema": "pcb-planar-active-legs.v3", "n_layers": 2, "board_w_mm": 4., "board_h_mm": 4.,
        "stackup": {"layer_pitch_mm": 2., "layer_z0_mm": 1.5},
        "traces": [{"trace_id": str(i), "net": net, "layer": i, "x0": 1., "y0": 1., "length_mm": 1., "width_mm": 1.,
                    "thick_mm": 1., "current_sign": 1} for i, net in enumerate(("pri", "sec"))]}
    arm = {"name": "synthetic", "level": 0, "pad_mm": 1., "far_size_mm": 2.}
    cad = {"canonical_boxes_mm": copy.deepcopy(BOXES), "domain_box_mm": list(DOMAIN)}
    for m in p[c.PHASE]["modes"]:
        p["dielectric_mesh"]["cad_report_sha256"][m] = sha256_json(cad)
        p["worker_limits"][m].update(mesh_nodes_max=100, mesh_tetrahedra_max=90, planar_nodes_max=12, planar_triangles_max=100)
    requested = sizing_policy(BOXES, POLICY, p)
    paths = {"planar_cad": Path("synthetic.cad.json"), "sizing": Path("synthetic.sizing.json"), "native_stdout": Path("synthetic.stdout")}
    atomic_write_json(tmp_path / paths["planar_cad"], cad)
    atomic_write_json(tmp_path / paths["sizing"], {"requested": requested, "background_tag": 3,
        "box_fields": [{"tag": i+1, "settings": f} for i,f in enumerate(requested["box_fields"])]})
    (tmp_path / paths["native_stdout"]).write_text("Info : 16 nodes 50 elements\n")
    def archived_inputs(*args):
        return paths, {k:{"path": str(v), "sha256": sha256_file(tmp_path/v)} for k,v in paths.items()}
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "protocol", lambda: p)
    monkeypatch.setattr(c, "mode_input", lambda *a: ("synthetic", layout, arm))
    monkeypatch.setattr(c, "cad_report", lambda *a: cad)
    monkeypatch.setattr(c, "policy", lambda *a: dict(POLICY))
    monkeypatch.setattr(c, "archived_inputs", archived_inputs)
    monkeypatch.setattr(cad_metadata, "review_report", lambda *a: {})
    monkeypatch.setattr(planar_metadata, "review_report", lambda *a: {})
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
@pytest.mark.parametrize("entry", [worker, runner, "archived_geometry"])
def test_guards_before_real_geometry(monkeypatch, tmp_path, guard, entry):
    p, _ = setup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(c, guard, Mock(side_effect=ValueError("guard failure")))
    heavy = Mock(side_effect=AssertionError("geometry before guard"))
    monkeypatch.setattr(mathlib, "diagnose", heavy)
    monkeypatch.setattr(cad_metadata, "domain_inputs", heavy)
    monkeypatch.setattr(runner, "run", heavy)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="guard failure"):
        worker.archived_geometry("toy", p) if entry == "archived_geometry" else entry.main()
    heavy.assert_not_called()


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
def test_synthetic_report_and_no_overwrite(monkeypatch, tmp_path, mode):
    p, directory = setup_worker(monkeypatch, tmp_path)
    arm = synthetic_arm(monkeypatch, directory, mode)
    runner.validate_result(arm["result"], mode, p, "123", directory)
    with pytest.raises(FileExistsError): worker.main()


@pytest.mark.parametrize("within", [False, True])
def test_complete_diagnostic_is_not_capacity_or_native_repeat_pass(monkeypatch, tmp_path, within):
    p, directory = setup_worker(monkeypatch, tmp_path)
    for limits in p["worker_limits"].values(): limits["mesh_nodes_max"] = 100 if within else 1
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p), "failure": None,
        "modes": {m: synthetic_arm(monkeypatch, directory, m) for m in p[c.PHASE]["modes"]}}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    monkeypatch.setattr(mathlib, "diagnose", Mock(side_effect=AssertionError("no real replay")))
    monkeypatch.setattr(worker, "archived_geometry", Mock(side_effect=AssertionError("no CAD replay")))
    assert runner.validate_attempt(directory, p) == record
    assert record["diagnostic_passed"] and not record["native_mesh_repeatability_tested"]
    assert not record["candidate_selected"] and all(record[k] is False for k in c.CLOSED)
    assert record["modes"]["local1"]["result"]["summary"]["conditional_full_column_node_bound_passes"] is within


@pytest.mark.parametrize("mutation", ["requested", "observed", "extra", "count", "tag", "background", "geometry"])
def test_archived_effective_sizing_and_geometry_bindings(monkeypatch, tmp_path, mutation):
    p, _ = setup_worker(monkeypatch, tmp_path)
    path = tmp_path / "synthetic.sizing.json"
    sizing = c.read_json(path)
    if mutation == "requested": sizing["requested"]["options"]["Mesh.Algorithm"] = 99
    if mutation == "observed": sizing["box_fields"][0]["settings"]["Thickness"] = 99
    if mutation == "extra": sizing["box_fields"][0]["extra"] = 1
    if mutation == "count": sizing["box_fields"].pop()
    if mutation == "tag": sizing["box_fields"][0]["tag"] = True
    if mutation == "background": sizing["background_tag"] = 1
    if mutation == "geometry": monkeypatch.setattr(cad_metadata, "domain_inputs", lambda *a: (BOXES, [0.,4.,0.,3.,0.,5.]))
    atomic_write_json(path, sizing)
    with pytest.raises(ValueError): worker.archived_geometry("toy", p)


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
    if mutation == "summary": r["summary"]["conditional_full_column_node_bound_passes"] = False
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


@pytest.mark.parametrize("mutation", ["geometry", "policy", "source", "proxy", "transition", "candidate", "mesh", "log", "triangle", "count", "z", "cap", "node_budget", "triangle_budget", "multiplicity", "area", "union", "index", "group", "kept", "volume"])
def test_resealed_report_mutations_rejected(monkeypatch, tmp_path, mutation):
    p, directory = setup_worker(monkeypatch, tmp_path)
    r = synthetic_arm(monkeypatch, directory, "toy")["result"]
    path = directory / "toy.report.json"
    report = c.read_json(path)
    if mutation == "geometry": report["canonical_boxes_mm"][0][0] += .01
    if mutation == "policy": report["policy"]["near_size_mm"] = 2.
    if mutation == "source": report["archived_inputs"]["sizing"]["sha256"] = "0"*64
    if mutation == "proxy": report["step_field_index_is_node_prediction"] = True
    if mutation == "transition": report["expanded_envelope_is_measured_transition_area"] = True
    if mutation == "candidate": report["candidate_selected"] = True
    if mutation == "mesh": report["mesh_generated"] = True
    if mutation == "log": report["native_log_counts"]["independently_audited"] = True
    if mutation == "triangle": report["native_log_counts"]["triangle_count_inferred"] = True
    if mutation == "count": report["conditional_full_column_node_bound_from_log"] += 1
    budget = report["vertical_budget"]
    if mutation == "z": budget["vertical_axis"]["point_count"] += 1
    if mutation == "cap": budget["limits"]["mesh_nodes_max"] += 1
    if mutation == "node_budget": budget["planar_node_budget_with_capture_cap"] += 1
    if mutation == "triangle_budget": budget["planar_triangle_sufficient_budget"] += 1
    if mutation == "group": budget["groups"].append(copy.deepcopy(budget["groups"][0]))
    if mutation == "kept": budget["groups"][0]["retained_intervals"].append(99)
    if mutation == "volume": budget["exact_dielectric_volume_mm3"]["numerator"] = "44"
    cover = report["coverage"]["near_core"]
    if mutation == "multiplicity": cover["area_by_multiplicity_mm2"][0]["multiplicity"] = 99
    if mutation == "area": cover["domain_area_mm2"]["numerator"] = "99"
    if mutation == "union": cover["union_area_mm2"]["numerator"] = "99"
    if mutation == "index": report["step_field_workload_indices"]["near_core"]["numerator"] = "99"
    atomic_write_json(path, report)
    r.update(report_sha256=sha256_file(path), report_bytes=path.stat().st_size, summary={k: report[k] for k in worker.SUMMARY_KEYS})
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


def test_inherited_watchdog_and_receipt_control_flow_unchanged():
    def body(module, name):
        node = next(n for n in ast.parse(Path(module.__file__).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
        class Normalize(ast.NodeTransformer):
            def visit_Constant(self, n):
                return ast.copy_location(ast.Constant(n.value.replace("grid planning", "sizing diagnostic")), n) if isinstance(n.value, str) else n
        return ast.dump(Normalize().visit(node))
    for function in ("bounded_mode", "validate_attempt", "run", "main", "mode_files"):
        assert body(runner, function) == body(previous_runner, function)


@pytest.mark.parametrize("mutation", ["bytes", "symlink", "missing"])
def test_archived_input_bytes_and_path_safety(monkeypatch, tmp_path, mutation):
    monkeypatch.setattr(c, "ROOT", tmp_path)
    paths = [c.INPUTS / "toy.payload/cad.json", c.INPUTS / "toy.payload/sizing.json", c.INPUTS / "toy.stdout"]
    for path in paths:
        (tmp_path/path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path/path).write_text("{}")
    atomic_write_json(tmp_path/c.ARCHIVE, {"files_sha256": {str(path):sha256_file(tmp_path/path) for path in paths}})
    assert c.archived_inputs("toy", P)[0]["planar_cad"] == paths[0]
    target = tmp_path/paths[0]
    if mutation == "bytes": target.write_text("changed")
    if mutation == "missing": target.unlink()
    if mutation == "symlink":
        target.unlink()
        target.symlink_to(tmp_path/paths[1])
    with pytest.raises(ValueError): c.archived_inputs("toy", P)


def test_failed_prefix_is_retained_but_skip_or_extra_member_is_rejected(monkeypatch, tmp_path):
    p, directory = setup_worker(monkeypatch, tmp_path)
    (directory/"toy.stdout").write_text("partial diagnostic")
    (directory/"toy.stderr").write_text("guard failure")
    arm = {"mode": "toy", "passed": False, "returncode": 1, "failure": "guard failure", "elapsed_s": 1.,
        "observed_peak_rss_gib": .1, "files_sha256": runner.mode_files(directory, "toy")}
    atomic_write_json(directory/"toy.json", arm)
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p),
        "failure": None, "modes": {"toy": arm}}
    record.update(c.assessment(record, p))
    atomic_write_json(directory/"attempt.json", record)
    assert not runner.validate_attempt(directory, p)["diagnostic_passed"]
    (directory/"unexpected").write_text("extra")
    with pytest.raises(ValueError, match="closure"): runner.validate_attempt(directory, p)
    (directory/"unexpected").unlink()
    record["modes"] = {"local1": arm}
    atomic_write_json(directory/"attempt.json", record)
    with pytest.raises(ValueError, match="sequence"): runner.validate_attempt(directory, p)


def test_inherited_caps_and_no_allocation(monkeypatch):
    original = c.parent.protocol()
    for m in P[c.PHASE]["modes"]:
        for k in ("mesh_nodes_max", "mesh_tetrahedra_max", "planar_nodes_max", "planar_triangles_max"):
            assert P["worker_limits"][m][k] == original["worker_limits"][m][k]
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    with pytest.raises(ValueError, match="login-node"): c.check_allocation(c.PHASE, P)


def test_frozen_source_byte_only():
    if not (ROOT / c.LOCK).exists(): pytest.skip("pre-freeze only")
    assert c.check_source(execution=False)["files_sha256"]
