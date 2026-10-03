"""No real meshing/solving: fake native API, tiny arrays and source receipts."""
import ast
import copy
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code/experiments/proofs"), str(REPO / "code/solvers")]
import tcad_cps_hxt_postopt as contract
import run_tcad_cps_hxt_postopt as runner
import tcad_cps_hxt_postopt_worker as worker
import tcad_cps_hxt_postopt_mesh as builder
from test_tcad_cps_hxt_isolation import quality, result as old_result
from test_tcad_cps_reference import scheduler_fixture
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

P = contract.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def result(mode="toy"):
    value = old_result(mode)
    value.update(mesh_policy=contract.expected_policy(mode,P), stages=list(contract.STAGES),
        quality_before=quality(0.), quality_before_passed=False, nodes_before=100,
        optimizer=copy.deepcopy(P["hxt_postopt"]["optimizer"]), optimizer_calls=1)
    value["mesh_policy_sha256"] = sha256_json(value["mesh_policy"])
    return value


def test_new_protocol_preserves_geometry_quality_and_worker_caps():
    previous = contract.predecessor.protocol()
    for key in ("physics", "runtime", "gates", "linear_solver", "worker_limits", "hxt_isolation", "mesh_probe"):
        assert P[key] == previous[key]
    assert P["mesh"] == {**previous["mesh"], "gmsh_options": {
        **previous["mesh"]["gmsh_options"], "Mesh.Optimize":0, "Mesh.OptimizeNetgen":0, "Mesh.OptimizeThreshold":.3}}
    assert P["resources"] == {"hxt_postopt": previous["resources"]["hxt_isolation"]}
    assert P["hxt_postopt"]["optimizer"] == {"method":"", "force":False, "niter":1, "dimTags":[]}
    assert P["hxt_postopt"]["optimizer_calls"] == 1
    assert P["hxt_postopt"]["modes"] == ["toy", "local1", "repeat1"]


@pytest.mark.parametrize("before", [0., -.1, float("nan"), float("inf"), .2])
def test_before_invalid_is_an_observation_but_after_must_pass(before):
    value = result()
    value["quality_before"] = quality(before)
    value["quality_before_passed"] = before > 0 and before < 1
    json.dumps(value, allow_nan=False)
    assert contract.assess_result(value,"toy",P)
    value["mesh_quality"] = quality(0.)
    assert not contract.assess_result(value,"toy",P)


@pytest.mark.parametrize("case", ["nodes", "node_bool", "count", "regions", "nonpositive", "finite",
    "quantiles", "hash", "bins", "zero_finite", "before_flag", "stages", "optimizer", "calls", "bool_calls"])
def test_pre_observation_and_optimizer_corruption_rejected(case):
    value = result()
    q = value["quality_before"]
    stats = q["regions"]["primary"]["minSICN"]
    if case == "nodes": value["nodes_before"] = 300001
    elif case == "node_bool": value["nodes_before"] = True
    elif case == "count": q["element_count"] += 1
    elif case == "regions": q["regions"].pop("secondary")
    elif case == "nonpositive": stats["nonpositive_count"] = 301
    elif case == "finite": stats["finite_count"] = True
    elif case == "quantiles": stats["quantiles"][-1] = -.1
    elif case == "hash": q["arrays_sha256"] = "bad"
    elif case == "bins": q["regions"]["primary"]["sicn_below_threshold"]["0.1"] = 1000
    elif case == "zero_finite": stats["finite_count"] = 0
    elif case == "before_flag": value["quality_before_passed"] = True
    elif case == "stages": value["stages"] = contract.parent.STAGES
    elif case == "optimizer": value["optimizer"]["force"] = 0
    elif case == "calls": value["optimizer_calls"] = 2
    else: value["optimizer_calls"] = True
    assert not contract.assess_result(value,"toy",P)


def test_repeat_binds_before_and_after_but_opens_no_scientific_claim():
    record = {"failure":None, "modes":{m:{"passed":True,"result":result(m)} for m in P["hxt_postopt"]["modes"]}}
    assessment = contract.assessment(record,P)
    assert assessment["complete"] and assessment["diagnostic_passed"]
    for key in ("mesh_feasible","numerical_quality_qualified","field_solver_executed","reference_qualified","training_may_start","claim_eligible"):
        assert assessment[key] is False
    record["modes"]["repeat1"]["result"]["quality_before"]["arrays_sha256"] = "b"*64
    assert contract.assessment(record,P)["complete"]
    assert not contract.assessment(record,P)["diagnostic_passed"]


def test_login_guards_precede_numerical_imports(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "hxt_postopt")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ValueError, match="login-node"): runner.main()
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="login-node"): worker.main()
    tree = ast.parse((REPO / "code/solvers/tcad_cps_hxt_postopt_worker.py").read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    guards = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("check_allocation", "check_source", "check_runtime")]
    first_import = min(n.lineno for n in main.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    assert first_import > sorted(guards)[2]
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("solve", "assemble", "cg", "spsolve") for n in ast.walk(tree))


def test_allocation_and_wrapper():
    record, env = scheduler_fixture("pilot")
    record.pop("ArrayJobId"); record.pop("ArrayTaskId")
    record["TimeLimit"] = "00:55:00"
    env = {k:v for k,v in env.items() if not k.startswith("SLURM_ARRAY")}
    matches = contract.parent.parent.support.original.allocation_matches
    assert matches(record, env, "a0126", "hxt_postopt", P)
    assert not matches(record, env, "ascend-login01", "hxt_postopt", P)
    assert not matches({**record,"Requeue":"1"}, env, "a0126", "hxt_postopt", P)
    shell = (REPO / contract.WRAPPER).read_text()
    for item in ("--mem=160G", "--time=00:55:00", "--cpus-per-task=1", "--no-requeue", "PCB_TCAD_BATCH_PHASE=hxt_postopt"):
        assert item in shell


@pytest.mark.parametrize("cap", ["time", "rss"])
def test_parent_kills_process_group_and_retains_logs(monkeypatch, tmp_path, cap):
    process = Mock(pid=123, returncode=-9)
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock(); monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0,1201,1202] if cap == "time" else [0,1,2])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if cap == "rss" else 0)
    receipt = runner.bounded_mode(tmp_path, "local1", P)
    assert not receipt["passed"] and receipt["failure"]
    assert set(receipt["files_sha256"]) == {"local1.stdout", "local1.stderr"}
    kill.assert_called_once_with(123, runner.signal.SIGKILL)


def setup_attempt(monkeypatch, tmp_path, negative=False):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit":"fixture"})
    directory = contract.attempt_directory("123", create=True)
    record = {"source_commit":"fixture", "scheduler":{"JobId":"123"}, "runtime":runner.expected_runtime(P), "failure":None, "modes":{}}
    for mode in P["hxt_postopt"]["modes"]:
        value = result(mode)
        if negative and mode == "repeat1": value["mesh_quality"]["arrays_sha256"] = "b"*64
        (directory / f"{mode}.stdout").write_text("RESULT=" + json.dumps(value) + "\n")
        (directory / f"{mode}.stderr").write_text("")
        arm = {"mode":mode,"passed":True,"failure":None,"returncode":0,"elapsed_s":1.,"observed_peak_rss_gib":.1,"result":value,
               "files_sha256":{f"{mode}.{s}":sha256_file(directory / f"{mode}.{s}") for s in ("stdout","stderr")}}
        record["modes"][mode] = arm
        atomic_write_json(directory / f"{mode}.json", arm)
    record.update(contract.assessment(record,P))
    atomic_write_json(directory / "attempt.json",record)
    return directory,record


@pytest.mark.parametrize("negative", [False,True])
def test_receipt_and_terminal_review(monkeypatch, tmp_path, negative):
    directory,record = setup_attempt(monkeypatch,tmp_path,negative)
    assert runner.validate_attempt(directory,P) == record
    monkeypatch.setattr(runner,"accounting",lambda _: ("fixture",[{"JobID":"123","State":"COMPLETED","ExitCode":"0:0","Restarts":"0"}]))
    review = runner.terminal_review("123",P)
    assert review["complete"] and review["diagnostic_passed"] == (not negative)
    assert review["mesh_feasible"] is False
    (directory / "toy.stdout").write_text("changed\n")
    with pytest.raises(ValueError,match="hash"): runner.validate_attempt(directory,P)


def test_parent_stops_on_first_failure(monkeypatch,tmp_path):
    monkeypatch.setattr(contract,"ROOT",tmp_path); monkeypatch.setattr(runner,"ROOT",tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID","123")
    monkeypatch.setattr(runner,"identity",lambda: {"source_commit":"fixture"})
    monkeypatch.setattr(runner,"check_source",lambda: None)
    monkeypatch.setattr(runner,"validate_attempt",lambda *a: None)
    bounded = Mock(return_value={"passed":False,"failure":"fixture"})
    monkeypatch.setattr(runner,"bounded_mode",bounded)
    assert not runner.run(P,{"JobId":"123"},runner.expected_runtime(P))
    assert bounded.call_count == 1


def test_frozen_source_closure_when_present():
    if not (REPO / contract.LOCK).exists(): pytest.skip("pre-freeze validation")
    lock = contract.check_source(execution=False)
    assert set(contract.SOURCES).issubset(lock["files_sha256"])
    assert str(contract.ARCHIVE) in lock["files_sha256"]


@pytest.mark.parametrize("case", ["claim", "numeric_flag", "coverage", "extra", "symlink", "parent_cap"])
def test_attempt_fail_closed(monkeypatch,tmp_path,case):
    directory,record = setup_attempt(monkeypatch,tmp_path)
    if case == "claim": record["mesh_feasible"] = True
    elif case == "numeric_flag": record["numerical_quality_qualified"] = 0
    elif case == "coverage": record["modes"].pop("toy")
    elif case == "extra": (directory / "extra").write_text("")
    elif case == "symlink":
        (directory / "toy.stdout").rename(tmp_path / "target")
        (directory / "toy.stdout").symlink_to(tmp_path / "target")
    else:
        record["modes"]["toy"]["elapsed_s"] = 601
        atomic_write_json(directory / "toy.json",record["modes"]["toy"])
    atomic_write_json(directory / "attempt.json",record)
    with pytest.raises(ValueError): runner.validate_attempt(directory,P)


@pytest.mark.parametrize("case", [None,"bytes","root","commit","lock","wrapper","phase","untracked"])
def test_execution_source_binding(monkeypatch,tmp_path,case):
    monkeypatch.setattr(contract,"ROOT",tmp_path)
    wrapper = tmp_path / contract.WRAPPER
    wrapper.parent.mkdir(parents=True); wrapper.write_text("frozen")
    lock = {"files_sha256":{contract.WRAPPER:sha256_file(wrapper)}}
    atomic_write_json(tmp_path / contract.LOCK,lock)
    monkeypatch.setattr(contract,"frozen_lock",lambda: {} if case == "bytes" else lock)
    env = {"PCB_TCAD_EXECUTION_ROOT":str(tmp_path),"PCB_TCAD_SOURCE_COMMIT":"fixture",
           "PCB_TCAD_LOCK_SHA256":sha256_file(tmp_path / contract.LOCK),"PCB_TCAD_BATCH_PHASE":"hxt_postopt",
           "PCB_TCAD_EXECUTED_BATCH_SCRIPT":str(wrapper)}
    replacements = {"root":("PCB_TCAD_EXECUTION_ROOT",str(tmp_path.parent)),"commit":("PCB_TCAD_SOURCE_COMMIT","other"),
                    "lock":("PCB_TCAD_LOCK_SHA256","other"),"phase":("PCB_TCAD_BATCH_PHASE","mesh_probe")}
    if case in replacements:
        k,v = replacements[case]; env[k] = v
    if case == "wrapper":
        alternate = tmp_path / "alternate.sh"; alternate.write_text("different")
        env["PCB_TCAD_EXECUTED_BATCH_SCRIPT"] = str(alternate)
    for k,v in env.items(): monkeypatch.setenv(k,v)
    def command(args):
        if args[1] == "rev-parse": return "fixture"
        if args[1] == "diff": return ""
        assert args[1] == "ls-files"
        return "" if case == "untracked" else "\n".join([contract.WRAPPER,str(contract.LOCK)])
    monkeypatch.setattr(contract.parent.parent.support.original,"command",command)
    if case is None: assert contract.check_source() == lock
    else:
        with pytest.raises(ValueError): contract.check_source()


def test_builder_login_guard_and_preserved_geometry_source(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "hxt_postopt")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ValueError, match="login-node"):
        builder._build_mesh({})
    current = (REPO / "code/solvers/tcad_cps_hxt_postopt_mesh.py").read_text()
    original = (REPO / "code/solvers/fem_capacitance_3d.py").read_text()
    for start, end in (("    validate_layout(layout)", "        gmsh.model.mesh.generate(3)"),
                       ("        coords = np.asarray(node_coords)", "    return m, elem_region")):
        assert current[current.index(start):current.index(end)] == original[original.index(start):original.index(end)]
    tree = ast.parse(current)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_build_mesh")
    guards = [n.lineno for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
              and n.func.id in ("check_allocation","check_source","check_runtime")]
    assert min(n.lineno for n in function.body if isinstance(n,(ast.Import,ast.ImportFrom))) > max(guards)
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr == "optimize"]
    assert len(calls) == 1


def fake_native(monkeypatch, outcome="pass"):
    """Three synthetic volumes; optimizer changes coordinates AND connectivity."""
    import numpy as np
    _, layout, _ = contract.mode_input("toy",P)
    boxes = [builder.trace_box(layout,t) for t in layout["traces"]]
    centers = [[-100,-100,-100]] + [[(b[2*i]+b[2*i+1])/2 for i in range(3)] for b in boxes]
    state = {"initialized":False,"optimized":False,"events":[],"boxes":0,"fields":0,"options":{}}
    before = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], dtype=float)
    after = np.vstack((before, [1,1,1])); after[0,0] = .25
    def initialize(): state["initialized"] = True
    def finalize(): state["events"].append("finalize"); state["initialized"] = False
    def add_box(*args): state["boxes"] += 1; return state["boxes"]
    def add_field(*args): state["fields"] += 1; return state["fields"]
    def nodes():
        state["events"].append("nodes_after" if state["optimized"] else "nodes_before")
        coords = after if state["optimized"] else before
        return np.arange(1,len(coords)+1), coords.ravel(), []
    def elements(dim, tag):
        state["events"].append("elements_after" if state["optimized"] else "elements_before")
        return [4], [np.array([tag])], [np.array([1,2,3,5 if state["optimized"] else 4])]
    def optimize(**kwargs):
        assert kwargs == P["hxt_postopt"]["optimizer"]
        state["events"].append("optimize")
        if outcome == "optimizer_error": raise RuntimeError("synthetic optimizer failure")
        state["optimized"] = True
    def qualities(tags,metric):
        state["events"].append("quality_after" if state["optimized"] else "quality_before")
        value = 1. if metric == "minDetJac" else (.2 if state["optimized"] and outcome != "quality_failure" else 0.)
        return np.full(len(tags),value)
    occ = SimpleNamespace(addBox=add_box,synchronize=lambda: None,
        fuse=lambda *a: (a[0],[]),fragment=lambda *a: ([],[]),getCenterOfMass=lambda dim,tag: centers[tag-1])
    field = SimpleNamespace(add=add_field,setNumber=lambda *a: None,setNumbers=lambda *a: None,setAsBackgroundMesh=lambda *a: None)
    gmsh = SimpleNamespace(isInitialized=lambda: state["initialized"],initialize=initialize,finalize=finalize,
        option=SimpleNamespace(setNumber=lambda k,v: state["options"].update({k:v}),
            getNumber=state["options"].get,getString=lambda k: "OpenCASCADE Hxt OpenMP"),
        model=SimpleNamespace(add=lambda *a: None,occ=occ,getEntities=lambda dim: [(3,i) for i in (1,2,3)],
            mesh=SimpleNamespace(generate=lambda dim: state["events"].append("generate"),getNodes=nodes,
                getElements=elements,optimize=optimize,getElementQualities=qualities,field=field)))
    monkeypatch.setitem(sys.modules,"gmsh",gmsh)
    monkeypatch.setitem(sys.modules,"skfem",SimpleNamespace(MeshTet=lambda p,t: SimpleNamespace(p=p,t=t)))
    for module in (worker,builder):
        monkeypatch.setattr(module,"check_allocation",lambda *a: {"JobId":"123"})
        monkeypatch.setattr(module,"check_source",lambda: None)
        monkeypatch.setattr(module,"check_runtime",lambda p: runner.expected_runtime(p))
    return state, before, after


@pytest.mark.parametrize("outcome", ["pass","quality_failure","optimizer_error"])
def test_worker_with_real_builder_and_fake_native_api(monkeypatch,capsys,outcome):
    state, before, after = fake_native(monkeypatch,outcome)
    monkeypatch.setattr(sys,"argv",["worker","--mode","toy"])
    monkeypatch.setattr(worker,"identity",lambda: {"source_commit":"fixture"})
    if outcome == "pass": worker.main()
    else:
        with pytest.raises((ValueError,RuntimeError)): worker.main()
    output = capsys.readouterr().out
    assert state["events"].count("optimize") == 1
    assert state["events"].index("quality_before") < state["events"].index("optimize")
    assert not state["initialized"]
    assert state["options"]["Mesh.OptimizeThreshold"] == .3
    assert state["options"]["Mesh.Optimize"] == 0
    if outcome == "pass":
        value = json.loads(next(line[7:] for line in output.splitlines() if line.startswith("RESULT=")))
        assert contract.assess_result(value,"toy",P)
        assert value["nodes_before"] == 4 and value["mesh_nodes"] == 5
        assert value["quality_before_passed"] is False
        assert state["events"].index("optimize") < state["events"].index("nodes_after") < state["events"].index("quality_after")
        import numpy as np
        mesh = SimpleNamespace(p=after.T*1e-3,t=np.tile(np.array([0,1,2,4])[:,None],(1,3)))
        expected = worker.mesh_metadata(mesh,np.array([0,1,2]),P["mesh_probe"]["mesh_fingerprint_schema"])
        assert value["mesh_sha256"] == expected["mesh_sha256"]
    else:
        assert "RESULT=" not in output
        if outcome == "quality_failure": assert '"strict_quality_passed": false' in output
        else: assert "nodes_after" not in state["events"]


@pytest.mark.parametrize("stage", ["raw_mesh_generated","mesh_generated"])
def test_node_caps_precede_each_quality_calculation(monkeypatch,capsys,stage):
    state, _, _ = fake_native(monkeypatch)
    monkeypatch.setattr(sys,"argv",["worker","--mode","toy"])
    calls = []
    def build(layout,*,progress,**kwargs):
        progress(stage,{"n_nodes":300001})
    monkeypatch.setattr(builder,"_build_mesh",build)
    monkeypatch.setattr(worker,"collect_quality",lambda *a: calls.append(a))
    with pytest.raises(ValueError,match="mesh_nodes_max"): worker.main()
    assert not calls and "CAP_EVENT=" in capsys.readouterr().out


def test_parent_success_runs_new_worker_not_frozen_predecessor(monkeypatch,tmp_path):
    monkeypatch.setenv("SLURM_JOB_ID","123")
    process = Mock(pid=123,returncode=0); process.poll.return_value = 0
    value = result()
    def popen(command,**kwargs):
        assert command[-3:] == [str(REPO / "code/solvers/tcad_cps_hxt_postopt_worker.py"),"--mode","toy"]
        kwargs["stdout"].write("RESULT=" + json.dumps(value) + "\n")
        return process
    monkeypatch.setattr(runner.subprocess,"Popen",popen)
    monkeypatch.setattr(runner,"validate_result",lambda *a: None)
    assert runner.bounded_mode(tmp_path,"toy",P)["passed"] is True
