"""No meshing/solving: tiny quality arrays, fake Gmsh and metadata receipts."""
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
import tcad_cps_hxt_isolation as contract
import run_tcad_cps_hxt_isolation as runner
import tcad_cps_hxt_isolation_worker as worker
from test_tcad_cps_mesh_probe import result as old_result
from test_tcad_cps_reference import scheduler_fixture
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

P = contract.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def quality(sicn=.2, jacobian=1.):
    import numpy as np
    return worker.quality_metadata(np.arange(1, 301), np.array([0]*200+[1]*50+[2]*50),
        np.full(300, sicn), np.full(300, jacobian), P["hxt_isolation"]["quality"])


def result(mode="toy"):
    value = old_result(mode)
    value.update(mesh_policy=contract.expected_policy(mode, P), mesh_quality=quality(), numerical_quality_qualified=False)
    value["mesh_policy_sha256"] = sha256_json(value["mesh_policy"])
    return value


def test_only_optimization_changes_and_caps_are_unchanged():
    old = contract.parent.protocol()
    assert P["mesh"] == {**old["mesh"], "gmsh_options": {**old["mesh"]["gmsh_options"], "Mesh.Optimize": 0}}
    for key in ("physics", "runtime", "gates", "linear_solver", "worker_limits", "mesh_probe"):
        assert P[key] == old[key]
    assert P["resources"] == {"hxt_isolation": old["resources"]["mesh_probe"]}
    assert P["hxt_isolation"]["modes"] == ["toy", "local1", "repeat1"]
    assert sum(v["worker_timeout_s"] for v in P["worker_limits"].values()) == 3000
    assert contract.mode_input("local1", P) == contract.mode_input("repeat1", P)


def test_quality_fingerprint_is_canonical_and_value_bound():
    import numpy as np
    cfg = P["hxt_isolation"]["quality"]
    tags, regions = np.array([30, 10, 20], dtype=np.uint64), np.array([2, 0, 1], dtype=np.int8)
    sicn, jac = np.array([.3, .1, .2]), np.array([3., 1., 2.])
    observed = worker.quality_metadata(tags, regions, sicn, jac, cfg)
    assert observed == worker.quality_metadata(tags[::-1].astype(np.int64), regions[::-1], sicn[::-1], jac[::-1], cfg)
    assert observed["regions"]["primary"]["minSICN"]["quantiles"] == [.2]*7
    assert observed["arrays_sha256"] != worker.quality_metadata(tags, regions, sicn+.01, jac, cfg)["arrays_sha256"]
    assert observed["arrays_sha256"] != worker.quality_metadata(tags, regions, sicn, jac+1, cfg)["arrays_sha256"]


@pytest.mark.parametrize("case", ["duplicate", "zero_tag", "shape", "float_tags", "bad_region", "empty"])
def test_quality_structure_rejected(case):
    import numpy as np
    tags, regions, sicn, jac = np.array([1,2,3]), np.array([0,1,2]), np.ones(3), np.ones(3)
    if case == "duplicate": tags[2] = 1
    elif case == "zero_tag": tags[0] = 0
    elif case == "shape": sicn = sicn[:2]
    elif case == "float_tags": tags = tags.astype(float)
    elif case == "bad_region": regions[0] = 3
    else: tags, regions, sicn, jac = (a[:0] for a in (tags, regions, sicn, jac))
    with pytest.raises(ValueError):
        worker.quality_metadata(tags, regions, sicn, jac, P["hxt_isolation"]["quality"])


@pytest.mark.parametrize("sicn,jac", [(0.,1.),(-.1,1.),(float("nan"),1.),(.2,0.),(.2,-1.),(.2,float("inf")),(1.1,1.)])
def test_invalid_quality_is_serializable_but_rejected(sicn, jac):
    value = result()
    value["mesh_quality"] = quality(sicn, jac)
    json.dumps(value, allow_nan=False)
    assert not contract.assess_result(value, "toy", P)


def test_positive_slivers_do_not_qualify_for_field_solving():
    record = {"failure": None, "modes": {}}
    for mode in P["hxt_isolation"]["modes"]:
        value = result(mode)
        value["mesh_quality"] = quality(1e-8, 1e-15)
        assert contract.assess_result(value, mode, P)
        assert value["mesh_quality"]["regions"]["primary"]["sicn_below_threshold"]["0.01"] == 50
        record["modes"][mode] = {"passed": True, "result": value}
    assessment = contract.assessment(record, P)
    assert assessment["complete"] and assessment["diagnostic_passed"]
    for key in ("mesh_feasible", "numerical_quality_qualified", "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible"):
        assert assessment[key] is False
    record["modes"]["repeat1"]["result"]["mesh_quality"]["arrays_sha256"] = "b"*64
    assert not contract.assessment(record, P)["diagnostic_passed"]
    assert contract.assessment(record, P)["complete"]


@pytest.mark.parametrize("case", ["count", "region", "nonfinite_count", "numeric_count", "nonpositive", "quantiles", "bins", "hash", "units", "qualification"])
def test_quality_receipt_corruption(case):
    value = result()
    q = value["mesh_quality"]
    stats = q["regions"]["primary"]["minSICN"]
    if case == "count": q["element_count"] += 1
    elif case == "region": q["regions"].pop("secondary")
    elif case == "nonfinite_count": stats["finite_count"] -= 1
    elif case == "numeric_count": stats["nonpositive_count"] = False
    elif case == "nonpositive": stats["nonpositive_count"] = 1
    elif case == "quantiles": stats["quantiles"][0] = .5
    elif case == "bins": q["regions"]["primary"]["sicn_below_threshold"]["0.1"] = 51
    elif case == "hash": q["arrays_sha256"] = "bad"
    elif case == "units": q["metric_units"]["minDetJac"] = "m^3"
    else: value["numerical_quality_qualified"] = True
    assert not contract.assess_result(value, "toy", P)


def test_native_quality_collection_uses_all_regions_and_cap():
    import numpy as np
    _, layout, _ = contract.mode_input("toy", P)
    centers = [[-100,-100,-100]] + [[(b[0]+b[1])/2,(b[2]+b[3])/2,(b[4]+b[5])/2] for b in [worker.trace_box(layout,t) for t in layout["traces"]]]
    requests = []
    def qualities(tags, metric):
        requests.append(metric)
        return np.full(len(tags), .2 if metric == "minSICN" else 1.)
    mesh = SimpleNamespace(getElements=lambda dim, tag: ([4], [np.array([tag])], [[]]), getElementQualities=qualities)
    gmsh = SimpleNamespace(model=SimpleNamespace(mesh=mesh, getEntities=lambda dim: [(3,i) for i in (1,2,3)],
        occ=SimpleNamespace(getCenterOfMass=lambda dim, tag: centers[tag-1])))
    q = worker.collect_quality(gmsh, layout, P["hxt_isolation"]["quality"], P["worker_limits"]["toy"])
    assert [r["count"] for r in q["regions"].values()] == [1,1,1]
    assert requests == ["minSICN", "minDetJac"]
    requests.clear()
    with pytest.raises(ValueError, match="cap"):
        worker.collect_quality(gmsh, layout, P["hxt_isolation"]["quality"], {"mesh_tetrahedra_max": 2})
    assert not requests
    mesh.getElements = lambda dim, tag: ([11], [np.array([tag])], [[]])
    with pytest.raises(ValueError, match="first-order"):
        worker.collect_quality(gmsh, layout, P["hxt_isolation"]["quality"], P["worker_limits"]["toy"])


def test_login_guards_precede_numerical_imports(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "hxt_isolation")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ValueError, match="login-node"): runner.main()
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="login-node"): worker.main()
    tree = ast.parse((REPO / "code/solvers/tcad_cps_hxt_isolation_worker.py").read_text())
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
    assert matches(record, env, "a0126", "hxt_isolation", P)
    assert not matches(record, env, "ascend-login01", "hxt_isolation", P)
    assert not matches({**record,"Requeue":"1"}, env, "a0126", "hxt_isolation", P)
    shell = (REPO / contract.WRAPPER).read_text()
    for item in ("--mem=160G", "--time=00:55:00", "--cpus-per-task=1", "--no-requeue", "PCB_TCAD_BATCH_PHASE=hxt_isolation"):
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
    for mode in P["hxt_isolation"]["modes"]:
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
           "PCB_TCAD_LOCK_SHA256":sha256_file(tmp_path / contract.LOCK),"PCB_TCAD_BATCH_PHASE":"hxt_isolation",
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


@pytest.mark.parametrize("outcome", ["pass","quality_failure","node_cap"])
def test_worker_main_with_fake_mesh_builder(monkeypatch,capsys,outcome):
    import numpy as np
    monkeypatch.setattr(sys,"argv",["worker","--mode","toy"])
    monkeypatch.setattr(worker,"check_allocation",lambda *a: {"JobId":"123"})
    monkeypatch.setattr(worker,"check_source",lambda: None)
    monkeypatch.setattr(worker,"check_runtime",lambda p: runner.expected_runtime(p))
    monkeypatch.setattr(worker,"identity",lambda: {"source_commit":"fixture"})
    options = {}
    gmsh = SimpleNamespace(option=SimpleNamespace(setNumber=lambda k,v: options.update({k:v}),
                            getNumber=options.get,getString=lambda k:"OpenCASCADE Hxt OpenMP"))
    monkeypatch.setitem(sys.modules,"gmsh",gmsh)
    monkeypatch.setattr(worker,"apply_mesh_policy",lambda *a: contract.expected_policy("toy",P))
    q = worker.quality_metadata(np.arange(1,4),np.arange(3),np.full(3,0. if outcome == "quality_failure" else .2),np.ones(3),P["hxt_isolation"]["quality"])
    collect = Mock(return_value=q)
    monkeypatch.setattr(worker,"collect_quality",collect)
    mesh = SimpleNamespace(p=np.arange(15,dtype=float).reshape(3,5),t=np.array([[0,0,1],[1,2,2],[2,3,3],[3,4,4]]))
    def build(layout,*,eps_r,refine,pad_mm,progress):
        assert eps_r == 4.2 and refine == 0 and pad_mm == 2.
        for stage,payload in [("geometry_validated",{}),("occ_fragmented",{}),("mesh_generate_started",{}),
            ("mesh_generated",{"n_nodes":300001 if outcome == "node_cap" else 5}),
            ("mesh_extracted",{"n_tetrahedra":3}),("gmsh_finalized",{}),("skfem_mesh_created",{})]:
            progress(stage,payload)
        return mesh,np.arange(3,dtype=np.int8)
    monkeypatch.setitem(sys.modules,"fem_capacitance_3d",SimpleNamespace(_build_mesh=build))
    if outcome == "pass":
        worker.main()
        output = capsys.readouterr().out
        value = json.loads(next(line[7:] for line in output.splitlines() if line.startswith("RESULT=")))
        assert value["mesh_policy"]["options"]["Mesh.Optimize"] == 0
        assert contract.assess_result(value,"toy",P)
        assert value["numerical_quality_qualified"] is False
    else:
        with pytest.raises(ValueError): worker.main()
        output = capsys.readouterr().out
        assert "RESULT=" not in output
        if outcome == "node_cap":
            assert "CAP_EVENT=" in output and "300001" in output
            collect.assert_not_called()
        else:
            assert '"mesh_quality"' in output and '"nonpositive_count": 1' in output
