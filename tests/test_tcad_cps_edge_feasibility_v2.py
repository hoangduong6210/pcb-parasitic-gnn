"""Synthetic native API orchestration only; never initialize actual Gmsh here."""
import builtins
import copy
from contextlib import redirect_stdout
import io
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_edge_feasibility_v2 as c
import tcad_cps_edge_builder_v2 as builder
import tcad_cps_edge_worker_v2 as worker
import run_tcad_cps_edge_feasibility_v2 as runner
import tcad_cps_dielectric_cad_metadata as original_cad
from scientific_artifact import sha256_file, sha256_json, atomic_write_json
from test_tcad_cps_column_mesh import BOXES, DOMAIN, report_fixture, fake_native, fake_reader
from test_tcad_cps_column_planning import POLICY

from test_tcad_cps_model_field_probe import fake_native as model_native
import tcad_cps_model_field_probe as adapter

P = c.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def native_fixture():
    report = report_fixture()
    native, state = model_native(original=None)
    state.update(fragmented=False, generated=False)
    before, after = fake_reader(report["before"]).model, fake_native().model
    def reader(): return after if state["fragmented"] else before
    api = native.model
    old_entities, old_nodes, old_elements = api.getEntities, api.mesh.getNodes, api.mesh.getElements
    def is_temp(): return state["current"] == adapter.TEMP_MODEL
    def entities(dim=-1):
        if is_temp(): return old_entities(dim)
        if dim == -1: return [pair for d in range(4) for pair in reader().getEntities(d)]
        return reader().getEntities(dim)
    api.getEntities = entities
    for name in ("getBoundingBox", "getBoundary", "getAdjacencies", "getType", "getValue"):
        setattr(api, name, lambda *args, _name=name, **kwargs:getattr(reader(), _name)(*args, **kwargs))
    api.occ.getMass = lambda *args:reader().occ.getMass(*args)
    def fragment(objects, tools, **kwargs):
        assert objects == [(2,1)] and tools == [(2,2),(2,3)]
        assert kwargs == {"tag":-1, "removeObject":True, "removeTool":True}
        state["fragmented"] = True
        return [(2,1),(2,2)], [[(2,1),(2,2)],[(2,2)],[(2,2)]]
    api.occ.fragment = Mock(side_effect=fragment)
    def nodes(dim=-1, tag=-1, **kwargs):
        return old_nodes() if is_temp() or not state["generated"] else after.mesh.getNodes(dim, tag, **kwargs)
    def elements(dim=-1, tag=-1):
        return old_elements() if is_temp() or not state["generated"] else after.mesh.getElements(dim, tag)
    api.mesh.getNodes, api.mesh.getElements = nodes, elements
    def generate(dim):
        assert dim == 2 and not is_temp() and not state["views"] and adapter.TEMP_MODEL not in state["models"]
        state["generated"] = True
    state["generate"] = Mock(side_effect=generate)
    api.mesh.generate = state["generate"]
    return native, state


def setup_synthetic(monkeypatch, tmp_path):
    p = copy.deepcopy(P)
    layout = {"geometry_schema": "pcb-planar-active-legs.v3", "n_layers": 2, "board_w_mm": 4., "board_h_mm": 4.,
        "stackup": {"layer_pitch_mm": 2., "layer_z0_mm": 1.5},
        "traces": [{"trace_id": str(i), "net": net, "layer": i, "x0": 1., "y0": 1., "length_mm": 1., "width_mm": 1.,
            "thick_mm": 1., "current_sign": 1} for i,net in enumerate(("pri","sec"))]}
    arm = {"name": "synthetic", "level": 0, "pad_mm": 1., "far_size_mm": 1.}
    original = {"canonical_boxes_mm": copy.deepcopy(BOXES), "domain_box_mm": list(DOMAIN)}
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "protocol", lambda: p)
    monkeypatch.setattr(c, "mode_input", lambda *args: ("synthetic", layout, arm))
    monkeypatch.setattr(c, "cad_report", lambda *args: original)
    monkeypatch.setattr(c, "policy", lambda *args: dict(POLICY))
    monkeypatch.setattr(c, "check_allocation", lambda *args: {"JobId": "123"})
    monkeypatch.setattr(c, "check_source", lambda **kwargs: {})
    monkeypatch.setattr(c, "check_runtime", lambda *args: runner.expected_runtime(p))
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "synthetic", "lock_sha256": "0"*64, "protocol_sha256": "1"*64})
    monkeypatch.setattr(original_cad, "review_report", lambda *args: {})
    monkeypatch.setattr(original_cad, "domain_inputs", lambda *args: (copy.deepcopy(BOXES), list(DOMAIN)))
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    native, state = native_fixture()
    monkeypatch.setitem(sys.modules, "gmsh", native)
    return p, c.attempt_directory("123", create=True), native, state


def synthetic_arm(monkeypatch, directory, mode):
    native, state = native_fixture()
    monkeypatch.setitem(sys.modules, "gmsh", native)
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
    native.initialize.assert_called_once_with([], readConfigFiles=False, run=False)
    state["generate"].assert_called_once_with(2)
    native.finalize.assert_called_once()
    return record


@pytest.mark.parametrize("guard", ["check_allocation", "check_source", "check_runtime"])
@pytest.mark.parametrize("entry", ["builder", "worker", "runner"])
def test_guards_precede_native_import_and_real_geometry(monkeypatch, tmp_path, guard, entry):
    p, directory, native, _ = setup_synthetic(monkeypatch, tmp_path)
    monkeypatch.setattr(c, guard, Mock(side_effect=ValueError("guard failure")))
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in ("gmsh", "numpy", "scipy", "skfem"):
            raise AssertionError("native/numerical import before guard")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(original_cad, "domain_inputs", Mock(side_effect=AssertionError("geometry before guard")))
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="guard failure"):
        if entry == "builder": builder.build("toy", Mock(), directory / "toy.payload")
        else: (worker if entry == "worker" else runner).main()
    native.initialize.assert_not_called()


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
def test_fresh_synthetic_worker_and_byte_only_validation(monkeypatch, tmp_path, mode):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    arm = synthetic_arm(monkeypatch, directory, mode)
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in ("gmsh", "numpy", "scipy", "skfem"):
            raise AssertionError("numerical import during byte-only validation")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    import tcad_cps_edge_sizing as edge
    import tcad_cps_column_planning as planning
    for module, name in ((edge,"probe_points"), (edge,"distance_squared"),
                         (adapter,"comparison"), (planning,"plan_packet")):
        monkeypatch.setattr(module, name, Mock(side_effect=AssertionError("real geometry replay on login")))
    runner.validate_result(arm["result"], mode, p, "123", directory)
    assert arm["result"]["planar_mesh_generated"] is True
    assert all(arm["result"][k] is False for k in c.CLOSED)


@pytest.mark.parametrize("infeasible", [False, True])
def test_complete_repeat_keeps_failed_capacity_as_diagnostic(monkeypatch, tmp_path, infeasible):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    if infeasible:
        for limits in p["worker_limits"].values(): limits["mesh_nodes_max"] = 1
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p), "modes": {}, "failure": None}
    for mode in p[c.PHASE]["modes"]:
        record["modes"][mode] = synthetic_arm(monkeypatch, directory, mode)
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    assert runner.validate_attempt(directory, p) == record
    assert record["diagnostic_passed"] is True and record["planning_feasible"] is not infeasible


@pytest.mark.parametrize("damage", ["source", "runtime", "stage", "claim", "volume_mesh", "hash", "bundle", "time", "rss", "planning"])
def test_result_tampering_rejected(monkeypatch, tmp_path, damage):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    r = synthetic_arm(monkeypatch, directory, "toy")["result"]
    if damage == "source": r["source_commit"] = "wrong"
    if damage == "runtime": r["runtime"] = {}
    if damage == "stage": r["stages"].pop()
    if damage == "claim": r["claim_eligible"] = True
    if damage == "volume_mesh": r["volume_mesh_generated"] = True
    if damage == "hash": r["report_sha256"] = "0"*64
    if damage == "bundle": r["bundle"]["packet_sha256"] = "0"*64
    if damage == "time": r["elapsed_s"] = 10000
    if damage == "rss": r["peak_rss_gib"] = 100
    if damage == "planning": r["planning_feasible"] = not r["planning_feasible"]
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


def test_raw_payload_survives_planar_audit_failure(monkeypatch, tmp_path):
    import tcad_cps_column_planning as planning
    p, directory, native, _ = setup_synthetic(monkeypatch, tmp_path)
    monkeypatch.setattr(planning, "plan_packet", Mock(side_effect=ValueError("synthetic planar rejection")))
    with pytest.raises(ValueError, match="synthetic planar rejection"):
        builder.build("toy", Mock(), directory / "toy.payload")
    native.finalize.assert_called_once()
    assert (directory / "toy.payload/raw/manifest.json").is_file()
    assert (directory / "toy.payload/post_mesh_cad.json").is_file()
    assert not (directory / "toy.payload/report.json").exists()


@pytest.mark.parametrize("damage", ["numeric", "plugin", "nonfinite", "original", "cleanup", "extra_view"])
def test_bad_native_probe_is_preserved_before_gate_and_prevents_meshing(monkeypatch, tmp_path, damage):
    p, directory, native, state = setup_synthetic(monkeypatch, tmp_path)
    if damage == "numeric": state["error"] = .01
    else: state["failure"] = damage
    progress = Mock()
    with pytest.raises(ValueError):
        builder.build("toy", progress, directory / "toy.payload")
    payload = directory / "toy.payload"
    assert (payload / "probe_state_before.json").is_file()
    assert (payload / "probe_state_after.json").is_file()
    assert (payload / "distance.cleanup.json").is_file()
    assert not (payload / "report.json").exists() and not (payload / "raw").exists()
    if damage == "numeric":
        assert c.read_json(payload / "field_probe.json")["points"]
        assert progress.call_args_list[-1].args[0] == "probe_state_restored"
    if damage == "nonfinite":
        assert c.read_json(payload / "distance.view_after.json")["data"]["values"][0][0] == {"nonfinite":"nan"}
    state["generate"].assert_not_called()
    native.finalize.assert_called_once()
    if damage != "extra_view": assert not state["views"]


@pytest.mark.parametrize("damage", ["probe_hash", "probe_value", "probe_point", "probe_scope", "sizing_tag"])
def test_probe_and_sizing_rehashed_tampering_rejected(monkeypatch, tmp_path, damage):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    result = synthetic_arm(monkeypatch, directory, "toy")["result"]
    payload = directory / "toy.payload"
    report = c.read_json(payload / "report.json")
    probe = c.read_json(payload / "field_probe.json")
    if damage == "probe_hash": probe["sizing_sha256"] = "f"*64
    if damage == "probe_value": probe["points"][0]["native_size_mm"] += .01
    if damage == "probe_point": probe["points"][0]["point_mm"][0] += .01
    if damage == "probe_scope": probe["probe_is_mesh_accuracy_test"] = True
    if damage == "sizing_tag":
        sizing = c.read_json(payload / "sizing.json")
        sizing["background_tag"] = sizing["minimum_tag"]
        atomic_write_json(payload / "sizing.json",sizing)
        probe["sizing_sha256"] = sha256_json(sizing)
        report["sizing_sha256"] = sha256_json(sizing)
    atomic_write_json(payload / "field_probe.json",probe)
    report["field_probe_sha256"] = sha256_json(probe)
    report["files_sha256"] = {name+".json":sha256_file(payload / (name+".json")) for name in runner.NAMES-{"report"}}
    atomic_write_json(payload / "report.json",report)
    result.update(report_sha256=sha256_file(payload / "report.json"),report_bytes=(payload / "report.json").stat().st_size)
    with pytest.raises(ValueError): runner.validate_result(result,"toy",p,"123",directory)


@pytest.mark.parametrize("damage", ["count", "z", "tetrahedra", "condition", "volume", "tolerance", "leakage", "quantum", "closed", "cad", "post", "sizing"])
def test_rehashed_metadata_tampering_rejected(monkeypatch, tmp_path, damage):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    r = synthetic_arm(monkeypatch, directory, "toy")["result"]
    payload = directory / "toy.payload"
    path = payload / "report.json"
    report = c.read_json(path)
    plan = report["plan"]
    if damage == "count": plan["planar_audit"]["planar_nodes"] += 1
    if damage == "z": plan["vertical_axis"]["points_mm"][1] += .1
    if damage == "tetrahedra": plan["capacity"]["tetrahedra"] += 3
    if damage == "condition": plan["conditioning"]["failed_triangles"] += 1
    if damage == "volume": plan["prospective_mesh_volume_mm3"]["numerator"] = "44"
    if damage == "tolerance": plan["mesh_canonical_volume_limit_mm3"]["numerator"] = "999999999999999999999999"
    if damage == "leakage": plan["planar_audit"]["ownership_leakage_upper_bound_mm2"][0]["numerator"] = "1"
    if damage == "quantum": plan["planar_audit"]["leakage_bound_quantum_mm2"]["numerator"] = "2"
    if damage == "closed": plan["capacity"]["boundary_contract_passed"] = True
    if damage == "cad": report["canonical_cad_sha256"] = "0"*64
    if damage == "post": (payload / "post_mesh_cad.json").write_text("{}")
    if damage == "sizing":
        sizing = c.read_json(payload / "sizing.json")
        sizing["requested"]["options"]["Mesh.Algorithm"] = 6
        (payload / "sizing.json").write_text(json.dumps(sizing))
        report["sizing_sha256"] = sha256_json(sizing)
    report["files_sha256"] = {name+".json":sha256_file(payload / (name+".json")) for name in runner.NAMES-{"report"}}
    path.write_text(json.dumps(report))
    r.update(report_sha256=sha256_file(path), report_bytes=path.stat().st_size)
    with pytest.raises(ValueError): runner.validate_result(r, "toy", p, "123", directory)


def test_no_overwrite_and_native_options_fail_closed(monkeypatch, tmp_path):
    p, directory, native, state = setup_synthetic(monkeypatch, tmp_path)
    target = directory / "toy.payload"
    target.mkdir()
    (target / "inputs.json").write_text("preserved partial")
    with pytest.raises(FileExistsError): builder.build("toy", Mock(), target)
    native.initialize.assert_not_called()
    assert (target / "inputs.json").read_text() == "preserved partial"
    native.option.getNumber = lambda k: -999
    with pytest.raises(ValueError, match="effective planar CAD options"):
        builder.build("local1", Mock(), directory / "local1.payload")
    state["generate"].assert_not_called()
    native.finalize.assert_called_once()


@pytest.mark.parametrize("failure", [False, True])
def test_runner_mode_order_and_stop_on_failure(monkeypatch, tmp_path, failure):
    p, existing, _, _ = setup_synthetic(monkeypatch, tmp_path)
    existing.rmdir()  # Empty synthetic root, not an execution worktree.
    visited = []
    def fake_mode(directory, mode, protocol):
        visited.append(mode)
        return {"passed": not failure, "result": {"report_sha256": "same", "bundle": {}, "planning_feasible": True}}
    monkeypatch.setattr(runner, "bounded_mode", fake_mode)
    monkeypatch.setattr(runner, "validate_attempt", lambda *args: {})
    assert runner.run(p, {"JobId": "123"}, runner.expected_runtime(p)) is not failure
    assert visited == (["toy"] if failure else p[c.PHASE]["modes"])


@pytest.mark.parametrize("gate", ["time", "rss"])
def test_parent_resource_stop_preserves_logs_and_kills_process_group(monkeypatch, tmp_path, gate):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    alive = {"value": True}
    process = SimpleNamespace(pid=876543, returncode=-9,
        poll=lambda: None if alive["value"] else -9, wait=lambda: -9)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)
    ticks = iter([0., 1000. if gate == "time" else 1., 1001. if gate == "time" else 2.])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda pid: 100. if gate == "rss" else .1)
    killed = []
    def stop(pid, sig):
        killed.append((pid,sig)); alive["value"] = False
    monkeypatch.setattr(runner.os, "killpg", stop)
    r = runner.bounded_mode(directory, "toy", p)
    assert r["passed"] is False and "cap" in r["failure"]
    assert killed == [(876543, runner.signal.SIGKILL)]
    assert set(r["files_sha256"]) == {"toy.stdout", "toy.stderr"}


def test_partial_attempt_validation_and_no_unlisted_file(monkeypatch, tmp_path):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    for suffix in ("stdout", "stderr"): (directory / f"toy.{suffix}").write_text("")
    payload = directory / "toy.payload"
    payload.mkdir()
    (payload / "inputs.json").write_text("partial retained bytes")
    arm = {"mode": "toy", "passed": False, "returncode": -9, "failure": "bounded synthetic interruption",
        "files_sha256": runner.mode_files(directory, "toy")}
    atomic_write_json(directory / "toy.json", arm)
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p), "modes": {"toy": arm}, "failure": None}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    assert runner.validate_attempt(directory, p) == record
    (payload / "unlisted.txt").write_text("not allowed")
    with pytest.raises(ValueError, match="unexpected"): runner.validate_attempt(directory, p)


def test_real_allocation_guard_rejects_absent_scheduler(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    with pytest.raises(ValueError, match="SLURM allocation"):
        c.check_allocation(c.PHASE, P)


def test_frozen_source_when_available():
    if not (ROOT / c.LOCK).is_file():
        pytest.skip("execution source not frozen yet")
    assert c.check_source(execution=False) == c.frozen_lock()


@pytest.mark.parametrize("damage", ["raw_value", "returned", "scaffold", "cleanup", "cad", "empty_mesh",
    "field", "option", "state_scope", "session", "active", "initial", "view_time", "point_request", "point_type"])
def test_rehashed_raw_probe_state_tampering_rejected(monkeypatch, tmp_path, damage):
    p, directory, _, _ = setup_synthetic(monkeypatch, tmp_path)
    result = synthetic_arm(monkeypatch, directory, "toy")["result"]
    payload = directory / "toy.payload"
    data = {name:c.read_json(payload / (name+".json")) for name in runner.NAMES}
    if damage == "raw_value": data["distance.view_after"]["data"]["values"][0][0] += .1
    if damage == "returned": data["size.view_after"]["returned_view"] += 1
    if damage == "scaffold": data["distance.scaffold"]["coordinates_mm"][0] += 1.
    if damage == "cleanup": data["size.cleanup"]["views"] = [99]
    if damage == "cad": data["probe_state_before"]["cad"]["0"][0]["tag"] += 99
    if damage == "empty_mesh": data["probe_state_before"]["mesh"]["node_tags"] = [999]
    if damage == "field": data["probe_state_before"]["fields"]["minimum"]["FieldsList"] = []
    if damage == "option": data["probe_state_before"]["options"]["Mesh.Algorithm"] = 6
    if damage == "state_scope": data["report"]["probe_original_state_unchanged"] = False
    if damage == "session": data["probe_state_before"]["session"]["models"].append(adapter.TEMP_MODEL)
    if damage == "active": data["distance.view_after"]["active"]["current_model"] = adapter.TEMP_MODEL
    if damage == "initial": data["size.view_before"]["values"][0][0] = 0.
    if damage == "view_time": data["size.view_after"]["data"]["time"] = 1.
    if damage == "point_request": data["distance.request"]["points_mm"][0][0] += .1
    if damage == "point_type": data["size.request"]["point_element_type"] = 1
    # Equal before/after alone is insufficient: both must match original CAD/fields.
    data["probe_state_after"] = copy.deepcopy(data["probe_state_before"])
    for name in runner.NAMES-{"report"}: atomic_write_json(payload / (name+".json"), data[name])
    report = data["report"]
    report["files_sha256"] = {name+".json":sha256_file(payload / (name+".json")) for name in runner.NAMES-{"report"}}
    atomic_write_json(payload / "report.json", report)
    result.update(report_sha256=sha256_file(payload / "report.json"), report_bytes=(payload / "report.json").stat().st_size)
    with pytest.raises(ValueError): runner.validate_result(result,"toy",p,"123",directory)


@pytest.mark.parametrize("damage", ["resource", "mode", "sizing", "tolerance", "cap", "scope", "scope_type", "retry", "adapter"])
def test_protocol_keeps_real_layout_contract(monkeypatch, damage):
    cfg = copy.deepcopy(P[c.PHASE])
    if damage == "resource": cfg["worker_timeout_s"] = 180
    if damage == "mode": cfg["modes"] = ["probe", "repeat"]
    if damage == "sizing": cfg["edge_plateau_half_width_mm"] = .1
    if damage == "tolerance": cfg["probe_rtol"] = .01
    if damage == "cap": cfg["planar_limits"]["planar_nodes_max"] += 1
    if damage == "scope": cfg["field_solver_executed"] = True
    if damage == "scope_type": cfg["field_solver_executed"] = 0
    if damage == "retry": cfg["automatic_retries"] = 1
    if damage == "adapter": cfg["probe_adapter_policy"] = "bypass"
    original = c.read_json
    monkeypatch.setattr(c, "read_json", lambda path:cfg if path == c.ROOT / c.PROTOCOL else original(path))
    with pytest.raises(ValueError): c.protocol()


def test_real_layout_limits_not_synthetic_api_limits():
    baseline = c.baseline.protocol()
    assert P["worker_limits"] == baseline["worker_limits"]
    assert P[c.PHASE]["modes"] == ["toy","local1","repeat1"]
    assert P["resources"][c.PHASE] == baseline["resources"][c.baseline.PHASE]
