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
import tcad_cps_column_feasibility as c
import tcad_cps_column_builder as builder
import tcad_cps_column_worker as worker
import run_tcad_cps_column_feasibility as runner
import tcad_cps_dielectric_cad_metadata as original_cad
from scientific_artifact import sha256_file, sha256_json, atomic_write_json
from test_tcad_cps_column_mesh import BOXES, DOMAIN, report_fixture, fake_native, fake_reader
from test_tcad_cps_column_planning import POLICY

P = c.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def native_fixture():
    report = report_fixture()
    state = {"initialized": False, "next_rectangle": 0, "fields": {}, "numbers": {}}
    native = SimpleNamespace(model=fake_reader(report["before"]).model)
    def initialize(*args, **kwargs): state["initialized"] = True
    def finalize(): state["initialized"] = False
    native.initialize, native.finalize = Mock(side_effect=initialize), Mock(side_effect=finalize)
    native.isInitialized = lambda: state["initialized"]
    native.option = SimpleNamespace(setNumber=lambda k,v: state["numbers"].__setitem__(k,v),
        getNumber=lambda k: state["numbers"][k], getString=lambda k: "synthetic native API; no actual meshing")
    def add_field(kind):
        tag = len(state["fields"])+1
        state["fields"][tag] = {"kind": kind}
        return tag
    field = SimpleNamespace(list=lambda: list(state["fields"]), add=add_field,
        setNumber=lambda t,k,v: state["fields"][t].__setitem__(k,v), getNumber=lambda t,k: state["fields"][t][k],
        setNumbers=lambda t,k,v: state["fields"][t].__setitem__(k,v), getNumbers=lambda t,k: state["fields"][t][k],
        getType=lambda t: state["fields"][t]["kind"], setAsBackgroundMesh=Mock())
    def rectangle(*args):
        state["next_rectangle"] += 1
        return state["next_rectangle"]
    reader = native.model.occ.getMass
    occ = SimpleNamespace(addRectangle=Mock(side_effect=rectangle), synchronize=Mock(), getMass=reader)
    def fragment(objects, tools, **kwargs):
        assert objects == [(2,1)] and tools == [(2,2),(2,3)]
        assert kwargs == {"tag": -1, "removeObject": True, "removeTool": True}
        native.model = fake_native().model
        occ.getMass = native.model.occ.getMass
        native.model.occ = occ
        native.model.mesh.field = field
        native.model.mesh.generate = state["generate"]
        return [(2,1),(2,2)], [[(2,1),(2,2)],[(2,2)],[(2,2)]]
    occ.fragment = Mock(side_effect=fragment)
    state["generate"] = Mock()
    native.model.occ = occ
    native.model.add = Mock()
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
