"""Synthetic model-backed adapter integration; never initialize actual Gmsh."""
import builtins
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"),str(ROOT / "code/solvers")]
import tcad_cps_field_probe_api as c
import tcad_cps_field_probe_worker as worker
import run_tcad_cps_field_probe_api as runner
import tcad_cps_column_cad as cad
from scientific_artifact import atomic_write_json,sha256_file,sha256_json
from test_tcad_cps_model_field_probe import fake_native

P = c.protocol()


@pytest.fixture(autouse=True)
def clean_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def setup_synthetic(monkeypatch,tmp_path):
    p = copy.deepcopy(P)
    monkeypatch.setattr(c,"ROOT",tmp_path)
    monkeypatch.setattr(c,"protocol",lambda:p)
    monkeypatch.setattr(c,"check_allocation",lambda *a:{"JobId":"123"})
    monkeypatch.setattr(c,"check_source",lambda **kwargs:{})
    monkeypatch.setattr(c,"check_runtime",lambda *a:runner.expected_runtime(p))
    monkeypatch.setattr(c,"identity",lambda:{"source_commit":"synthetic","lock_sha256":"0"*64,"protocol_sha256":"1"*64})
    monkeypatch.setattr(cad,"snapshot",lambda native,*args,**kwargs:{"synthetic_rectangles":copy.deepcopy(native.fixture_state["models"][native.fixture_state["current"]]["rectangles"])})
    monkeypatch.setenv("SLURM_JOB_ID","123")
    native,state = fake_native(original=None)
    monkeypatch.setitem(sys.modules,"gmsh",native)
    return p,c.attempt_directory("123",create=True),native,state


def arm(monkeypatch,directory,mode):
    monkeypatch.setattr(sys,"argv",["worker","--mode",mode])
    output = io.StringIO()
    with redirect_stdout(output): worker.main()
    (directory / f"{mode}.stdout").write_text(output.getvalue())
    (directory / f"{mode}.stderr").write_text("")
    result = json.loads(output.getvalue().split("RESULT=")[1])
    receipt = {"mode":mode,"passed":True,"returncode":0,"failure":None,"elapsed_s":1.,"observed_peak_rss_gib":.1,
        "files_sha256":runner.mode_files(directory,mode),"result":result}
    atomic_write_json(directory / f"{mode}.json",receipt)
    return receipt


@pytest.mark.parametrize("entry",["build","worker","runner"])
@pytest.mark.parametrize("guard",["check_allocation","check_source","check_runtime"])
def test_all_guards_precede_native_import(monkeypatch,tmp_path,entry,guard):
    p,directory,native,_ = setup_synthetic(monkeypatch,tmp_path)
    monkeypatch.setattr(c,guard,Mock(side_effect=ValueError("guard failure")))
    original = builtins.__import__
    def block(name,*args,**kwargs):
        if name in ("gmsh","numpy","scipy","skfem"): raise AssertionError("native import before guard")
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",block)
    monkeypatch.setattr(sys,"argv",["worker","--mode","probe"])
    with pytest.raises(ValueError,match="guard failure"):
        if entry == "build": worker.build("probe",directory / "probe.payload")
        else: (worker if entry == "worker" else runner).main()
    native.initialize.assert_not_called()


@pytest.mark.parametrize("mode",["probe","repeat"])
def test_synthetic_full_adapter_and_non_native_terminal_review(monkeypatch,tmp_path,mode):
    p,directory,native,state = setup_synthetic(monkeypatch,tmp_path)
    result = arm(monkeypatch,directory,mode)["result"]
    native.initialize.assert_called_once_with([],readConfigFiles=False,run=False)
    native.finalize.assert_called_once()
    native.model.mesh.generate.assert_not_called()
    assert state["plugin_calls"] == ["tcad_field_probe_fixture"]*2
    original = builtins.__import__
    def block(name,*args,**kwargs):
        if name in ("gmsh","numpy","scipy","skfem"): raise AssertionError("native import during terminal review")
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",block)
    runner.validate_result(result,mode,p,"123",directory)
    assert all(result[k] is False for k in c.CLOSED)


@pytest.mark.parametrize("damage",["plugin","nonfinite","original","numeric"])
def test_partial_raw_evidence_and_main_after_state_survive_failure(monkeypatch,tmp_path,damage):
    p,directory,native,state = setup_synthetic(monkeypatch,tmp_path)
    if damage == "numeric": state["error"] = .1
    else: state["failure"] = damage
    with pytest.raises(ValueError): worker.build("probe",directory / "probe.payload")
    payload = directory / "probe.payload"
    assert (payload / "after.json").is_file() and (payload / "distance.cleanup.json").is_file()
    assert not (payload / "report.json").exists()
    if damage == "nonfinite":
        assert c.read_json(payload / "distance.view_after.json")["data"]["values"][0][0] == {"nonfinite":"nan"}
    if damage == "numeric": assert (payload / "comparison.json").is_file()
    native.finalize.assert_called_once()
    native.model.mesh.generate.assert_not_called()


@pytest.mark.parametrize("damage",["raw_value","scope","returned","scaffold","cleanup","fixture","cad","expected","tolerance","field","time","resource"])
def test_rehashed_payload_tampering_rejected(monkeypatch,tmp_path,damage):
    p,directory,_,_ = setup_synthetic(monkeypatch,tmp_path)
    result = arm(monkeypatch,directory,"probe")["result"]
    payload = directory / "probe.payload"
    data = {name:c.read_json(payload / (name+".json")) for name in runner.NAMES}
    if damage == "raw_value": data["distance.view_after"]["data"]["values"][0][0] += .1
    if damage == "scope": data["report"]["field_solver_executed"] = True
    if damage == "returned": data["distance.view_after"]["returned_view"] += 1
    if damage == "scaffold": data["distance.scaffold"]["coordinates_mm"][0] += 1
    if damage == "cleanup": data["distance.cleanup"]["views"] = [99]
    if damage == "fixture": data["fixture"]["boxes_mm"][0][0] += .1
    if damage == "cad": data["after"]["cad"] = {}
    if damage == "expected": data["comparison"]["points"][0]["expected_distance_mm"] += .1
    if damage == "tolerance": data["comparison"]["rtol"] = 1.
    if damage == "field": data["before"]["fields"]["minimum"]["FieldsList"] = []
    if damage == "time": data["size.view_after"]["data"]["time"] = 1.
    if damage == "resource": result["elapsed_s"] = 10000
    for name in runner.NAMES-{"report"}: atomic_write_json(payload / (name+".json"),data[name])
    report = data["report"]
    report["comparison_sha256"] = sha256_json(data["comparison"])
    report["files_sha256"] = {name+".json":sha256_file(payload / (name+".json")) for name in runner.NAMES-{"report"}}
    atomic_write_json(payload / "report.json",report)
    result.update(report_sha256=sha256_file(payload / "report.json"),report_bytes=(payload / "report.json").stat().st_size)
    with pytest.raises(ValueError): runner.validate_result(result,"probe",p,"123",directory)


def test_partial_attempt_closure_and_no_overwrite(monkeypatch,tmp_path):
    p,directory,native,_ = setup_synthetic(monkeypatch,tmp_path)
    for suffix in ("stdout","stderr"): (directory / ("probe."+suffix)).write_text("")
    payload = directory / "probe.payload"; payload.mkdir()
    (payload / "distance.request.json").write_text("preserved partial")
    with pytest.raises(FileExistsError): worker.build("probe",payload)
    native.initialize.assert_not_called()
    receipt = {"mode":"probe","passed":False,"failure":"synthetic partial","files_sha256":runner.mode_files(directory,"probe")}
    atomic_write_json(directory / "probe.json",receipt)
    record = {**c.identity(),"scheduler":{"JobId":"123"},"runtime":runner.expected_runtime(p),"modes":{"probe":receipt},"failure":None}
    record.update(c.assessment(record,p)); atomic_write_json(directory / "attempt.json",record)
    assert runner.validate_attempt(directory,p) == record
    (payload / "unexpected").write_text("preserved")
    with pytest.raises(ValueError): runner.validate_attempt(directory,p)


@pytest.mark.parametrize("failure",[False,True])
def test_runner_sequence_and_exact_repeat_requirement(monkeypatch,tmp_path,failure):
    p,directory,_,_ = setup_synthetic(monkeypatch,tmp_path)
    directory.rmdir()
    visited = []
    def mode(directory,name,p):
        visited.append(name)
        return {"passed":not failure,"result":{"report_sha256":"same"}}
    monkeypatch.setattr(runner,"bounded_mode",mode)
    monkeypatch.setattr(runner,"validate_attempt",lambda *args:{})
    assert runner.run(p,{"JobId":"123"},runner.expected_runtime(p)) is not failure
    assert visited == (["probe"] if failure else ["probe","repeat"])
    record = {"modes":{m:{"passed":True,"result":{"report_sha256":m}} for m in p[c.PHASE]["modes"]},"failure":None}
    assert c.assessment(record,p)["diagnostic_passed"] is False


@pytest.mark.parametrize("gate",["time","rss"])
def test_parent_watchdog_stops_process_group_and_preserves_logs(monkeypatch,tmp_path,gate):
    p,directory,_,_ = setup_synthetic(monkeypatch,tmp_path)
    alive = {"value":True}
    process = SimpleNamespace(pid=876543,returncode=-9,poll=lambda:None if alive["value"] else -9,wait=lambda:-9)
    monkeypatch.setattr(runner.subprocess,"Popen",lambda *args,**kwargs:process)
    ticks = iter([0.,1000. if gate == "time" else 1.,1001. if gate == "time" else 2.])
    monkeypatch.setattr(runner.time,"monotonic",lambda:next(ticks))
    monkeypatch.setattr(runner,"rss_gib",lambda pid:100. if gate == "rss" else .1)
    stopped = []
    def kill(pid,sig): stopped.append((pid,sig)); alive["value"] = False
    monkeypatch.setattr(runner.os,"killpg",kill)
    result = runner.bounded_mode(directory,"probe",p)
    assert result["passed"] is False and "cap" in result["failure"]
    assert stopped == [(876543,runner.signal.SIGKILL)]
    assert set(result["files_sha256"]) == {"probe.stdout","probe.stderr"}


def test_full_repeat_payload_identity_and_attempt_closure(monkeypatch,tmp_path):
    p,directory,_,_ = setup_synthetic(monkeypatch,tmp_path)
    record = {**c.identity(),"scheduler":{"JobId":"123"},"runtime":runner.expected_runtime(p),"modes":{},"failure":None}
    for mode in p[c.PHASE]["modes"]:
        native,_ = fake_native(original=None)
        monkeypatch.setitem(sys.modules,"gmsh",native)
        record["modes"][mode] = arm(monkeypatch,directory,mode)
    record.update(c.assessment(record,p))
    atomic_write_json(directory / "attempt.json",record)
    assert runner.validate_attempt(directory,p) == record
    assert record["diagnostic_passed"] and record["repeatability_passed"]
    assert all(record[k] is False for k in c.CLOSED)


def test_no_scheduler_means_no_native_execution(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID",raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE",c.PHASE)
    with pytest.raises(ValueError,match="SLURM allocation"): c.check_allocation(c.PHASE,P)


@pytest.mark.parametrize("damage",["fixture","policy","resource","retry","cap","scope"])
def test_protocol_rejects_changed_frozen_definition(monkeypatch,damage):
    cfg = copy.deepcopy(P[c.PHASE])
    if damage == "fixture": cfg["fixture"]["boxes_mm"][0][0] += .1
    if damage == "policy": cfg["policy"]["near_size_mm"] = .2
    if damage == "resource": cfg["worker_timeout_s"] = 1000
    if damage == "retry": cfg["automatic_retries"] = 1
    if damage == "cap": cfg["fixture_points_max"] = 100000
    if damage == "scope": cfg["field_solver_executed"] = True
    original = c.read_json
    monkeypatch.setattr(c,"read_json",lambda path:cfg if path == c.ROOT / c.PROTOCOL else original(path))
    with pytest.raises(ValueError): c.protocol()


def test_frozen_source_when_present():
    if not (ROOT / c.LOCK).exists(): pytest.skip("native API execution source not frozen yet")
    assert c.check_source(execution=False) == c.frozen_lock()
