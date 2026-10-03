"""No-meshing, no-solver tests; tiny array fingerprints and synthetic receipts."""
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
import tcad_cps_mesh_probe as contract
import run_tcad_cps_mesh_probe as runner
import tcad_cps_mesh_probe_worker as worker
from scientific_artifact import atomic_write_json, sha256_file, sha256_json
from test_tcad_cps_reference import scheduler_fixture

P = contract.protocol()


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def result(mode="toy"):
    layout_id, layout, arm = contract.mode_input(mode, P)
    policy = contract.expected_policy(mode, P)
    return {"mode": mode, "layout_id": layout_id, "arm": arm,
            "geometry_sha256": contract.geometry_sha256(layout), "mesh_policy": policy,
            "mesh_policy_sha256": sha256_json(policy), "mesh_nodes": 100, "mesh_tetrahedra": 300,
            "region_tetrahedra": {"dielectric": 200, "primary": 50, "secondary": 50},
            "mesh_fingerprint_schema": P["mesh_probe"]["mesh_fingerprint_schema"], "mesh_sha256": "a"*64,
            "native_log_options": copy.deepcopy(P["mesh_probe"]["native_log_options"]),
            "gmsh_build_options": "OpenCASCADE Hxt OpenMP", "stages": list(contract.STAGES),
            "field_solver_executed": False, "elapsed_s": 1., "peak_rss_gib": .1,
            "source_commit": "fixture", "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(P)}


def test_only_mesher_and_nonnumerical_logging_change():
    previous = contract.parent.protocol()
    assert {k: v for k, v in P["mesh"].items() if k != "gmsh_options"} == {k: v for k, v in previous["mesh"].items() if k != "gmsh_options"}
    assert P["mesh"]["gmsh_options"] == {**previous["mesh"]["gmsh_options"], "Mesh.Algorithm3D": 10}
    for key in ("physics", "runtime", "gates", "linear_solver", "recovery", "smoke"):
        assert P[key] == previous[key]
    assert P["worker_limits"]["toy"] == previous["resources"]["smoke"]
    assert P["worker_limits"]["local1"] == P["worker_limits"]["repeat1"] == previous["resources"]["feasibility"]
    assert sum(l["worker_timeout_s"] for l in P["worker_limits"].values()) == P["mesh_probe"]["worker_budget_s"] == 3000
    assert P["resources"]["mesh_probe"] == {**previous["resources"]["feasibility"], "time_limit": "00:55:00"}
    assert P["mesh_probe"]["modes"] == ["toy", "local1", "repeat1"]
    assert contract.mode_input("local1", P) == contract.mode_input("repeat1", P)
    with pytest.raises(ValueError):
        contract.mode_input("local2", P)


@pytest.mark.parametrize("mode", ["toy", "local1", "repeat1"])
def test_effective_policy_matches_frozen_field_helper(mode):
    options, values, ids = {}, {}, []
    def add(kind):
        ids.append(kind)
        return len(ids)
    fields = SimpleNamespace(add=add, setNumber=lambda i, k, v: values.setdefault(i, {}).update({k: v}),
                             setNumbers=Mock(), setAsBackgroundMesh=Mock())
    gmsh = SimpleNamespace(option=SimpleNamespace(setNumber=lambda k, v: options.update({k: v}), getNumber=options.get),
                           model=SimpleNamespace(mesh=SimpleNamespace(field=fields)))
    _, layout, arm = contract.mode_input(mode, P)
    observed = worker.apply_mesh_policy(gmsh, layout, arm, contract.parent.arm_protocol(P, arm))
    assert observed == contract.expected_policy(mode, P)
    assert observed["options"]["Mesh.Algorithm3D"] == 10
    assert observed["options"]["General.NumThreads"] == 1
    assert ids == ["Box"]*len(layout["traces"]) + ["Min"]
    assert contract.assess_result(result(mode), mode, P)


@pytest.mark.parametrize("key,value", [("mesh_nodes", 0), ("mesh_nodes", True), ("mesh_nodes", 300001),
    ("mesh_tetrahedra", 1500001), ("mesh_sha256", "invalid"), ("peak_rss_gib", 6.1),
    ("elapsed_s", 600.1), ("elapsed_s", float("nan")), ("field_solver_executed", True),
    ("gmsh_build_options", "No-Hxt"), ("mesh_fingerprint_schema", "wrong"), ("stages", []),
    ("region_tetrahedra", {"dielectric": 300, "primary": 0, "secondary": 0})])
def test_result_gates_fail_closed(key, value):
    value_result = result()
    value_result[key] = value
    assert not contract.assess_result(value_result, "toy", P)


@pytest.mark.parametrize("corruption", ["policy", "logging", "geometry", "field_result", "region_sum"])
def test_policy_geometry_and_mesh_only_boundary(corruption):
    value = result()
    if corruption == "policy":
        value["mesh_policy"]["options"]["Mesh.Algorithm3D"] = 1
        value["mesh_policy_sha256"] = sha256_json(value["mesh_policy"])
    elif corruption == "logging":
        value["native_log_options"]["General.Terminal"] = 0
    elif corruption == "geometry":
        value["geometry_sha256"] = "b"*64
    elif corruption == "field_result":
        value["cps_pf"] = 1.
    else:
        value["region_tetrahedra"]["dielectric"] = 201
    assert not contract.assess_result(value, "toy", P)


def test_tiny_array_hash_is_order_dtype_shape_and_region_bound():
    import numpy as np
    mesh = SimpleNamespace(p=np.arange(15, dtype=float).reshape(3, 5),
                           t=np.array([[0, 0, 1], [1, 2, 2], [2, 3, 3], [3, 4, 4]], dtype=np.int32))
    regions = np.array([0, 1, 2], dtype=np.int8)
    schema = P["mesh_probe"]["mesh_fingerprint_schema"]
    expected = worker.mesh_metadata(mesh, regions, schema)
    assert expected["mesh_nodes"] == 5 and expected["mesh_tetrahedra"] == 3
    assert expected["region_tetrahedra"] == {"dielectric": 1, "primary": 1, "secondary": 1}
    other = copy.deepcopy(mesh)
    other.p = np.asfortranarray(other.p)
    other.t = other.t.astype(np.int64)
    assert worker.mesh_metadata(other, regions, schema) == expected
    other.p[0, 0] += .1
    assert worker.mesh_metadata(other, regions, schema)["mesh_sha256"] != expected["mesh_sha256"]
    assert worker.mesh_metadata(mesh, regions[::-1], schema)["mesh_sha256"] != expected["mesh_sha256"]
    other = copy.deepcopy(mesh)
    other.t[0, 0] = 99
    with pytest.raises(ValueError, match="connectivity"):
        worker.mesh_metadata(other, regions, schema)
    with pytest.raises(ValueError, match="missing"):
        worker.mesh_metadata(mesh, np.zeros(3, dtype=np.int8), schema)
    other = copy.deepcopy(mesh)
    other.p[0, 0] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        worker.mesh_metadata(other, regions, schema)


def test_complete_negative_repeatability_is_not_mesh_feasibility():
    record = {"modes": {m: {"passed": True, "result": result(m)} for m in P["mesh_probe"]["modes"]}, "failure": None}
    assessed = contract.assessment(record, P)
    assert assessed["complete"] and assessed["mesh_feasible"] and assessed["repeatability_passed"]
    for key in ("field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible", "automatic_expansion"):
        assert assessed[key] is False
    record["modes"]["repeat1"]["result"]["mesh_sha256"] = "b"*64
    assessed = contract.assessment(record, P)
    assert assessed["complete"] and not assessed["mesh_feasible"] and not assessed["repeatability_passed"]
    record["modes"].pop("repeat1")
    assert not contract.assessment(record, P)["complete"]


def test_worker_and_parent_reject_login_before_numerical_imports(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "mesh_probe")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ValueError, match="login-node"):
        runner.main()
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    with pytest.raises(ValueError, match="login-node"):
        worker.main()
    tree = ast.parse((REPO / "code/solvers/tcad_cps_mesh_probe_worker.py").read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    guard = max(n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("check_allocation", "check_runtime"))
    imports = [n for n in main.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert all(n.lineno > guard for n in imports)
    fem = next(n for n in imports if isinstance(n, ast.ImportFrom) and n.module == "fem_capacitance_3d")
    assert [n.name for n in fem.names] == ["_build_mesh"]
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("assemble", "condense", "solve", "cg", "spsolve") for n in ast.walk(tree))


def test_single_compute_allocation_and_wrapper():
    record, env = scheduler_fixture("pilot")
    record.pop("ArrayJobId")
    record.pop("ArrayTaskId")
    record["TimeLimit"] = "00:55:00"
    env = {k: v for k, v in env.items() if not k.startswith("SLURM_ARRAY")}
    matches = contract.parent.support.original.allocation_matches
    assert matches(record, env, "a0126", "mesh_probe", P)
    for host in ("ascend-login01", "a0125"):
        assert not matches(record, env, host, "mesh_probe", P)
    for key, value in (("Requeue", "1"), ("Restarts", "1"), ("TimeLimit", "03:00:00"), ("ArrayJobId", "123")):
        assert not matches({**record, key: value}, env, "a0126", "mesh_probe", P)
    shell = (REPO / contract.WRAPPER).read_text()
    for value in ("--mem=160G", "--time=00:55:00", "--cpus-per-task=1", "--no-requeue", "PCB_TCAD_BATCH_PHASE=mesh_probe"):
        assert value in shell


@pytest.mark.parametrize("cause", ["time", "rss", "exit_time"])
def test_parent_enforces_limits_and_retains_raw_logs(monkeypatch, tmp_path, cause):
    process = Mock(pid=123, returncode=-9 if cause != "exit_time" else 0)
    process.poll.return_value = None if cause != "exit_time" else 0
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 1201, 1202] if cause != "exit_time" else [0, 1201])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if cause == "rss" else 0)
    p = copy.deepcopy(P)
    if cause == "rss":
        p["worker_limits"]["local1"]["worker_timeout_s"] = 9999
    receipt = runner.bounded_mode(tmp_path, "local1", p)
    assert not receipt["passed"] and receipt["failure"]
    assert set(receipt["files_sha256"]) == {"local1.stdout", "local1.stderr"}
    if cause != "exit_time":
        kill.assert_called_once_with(123, runner.signal.SIGKILL)


def setup_attempt(monkeypatch, tmp_path, *, fail=False, mismatch=False):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit": "fixture"})
    directory = contract.attempt_directory("123", create=True)
    record = {"source_commit": "fixture", "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(P), "modes": {}, "failure": None}
    for mode in P["mesh_probe"]["modes"][:2 if fail else 3]:
        passed = not fail or mode == "toy"
        value = result(mode)
        if mismatch and mode == "repeat1":
            value["mesh_sha256"] = "b"*64
        (directory / f"{mode}.stdout").write_text("Info : Meshing\nRESULT=" + json.dumps(value) + "\n" if passed else "Info : Meshing\n")
        (directory / f"{mode}.stderr").write_text("")
        arm = {"mode": mode, "passed": passed, "returncode": 0 if passed else -9, "failure": None if passed else "worker wall-time cap exceeded",
               "elapsed_s": 1 if passed else 1200.5, "observed_peak_rss_gib": .1,
               "files_sha256": {f"{mode}.{s}": sha256_file(directory / f"{mode}.{s}") for s in ("stdout", "stderr")}}
        if passed:
            arm["result"] = value
        record["modes"][mode] = arm
        atomic_write_json(directory / f"{mode}.json", arm)
    record.update(contract.assessment(record, P))
    atomic_write_json(directory / "attempt.json", record)
    return directory, record


@pytest.mark.parametrize("outcome", ["pass", "negative", "incomplete"])
def test_terminal_review_preserves_all_three_outcomes(monkeypatch, tmp_path, outcome):
    directory, record = setup_attempt(monkeypatch, tmp_path, fail=outcome == "incomplete", mismatch=outcome == "negative")
    assert runner.validate_attempt(directory, P) == record
    row = {"JobID": "123", "State": "FAILED" if outcome == "incomplete" else "COMPLETED",
           "ExitCode": "2:0" if outcome == "incomplete" else "0:0", "Restarts": "0"}
    monkeypatch.setattr(runner, "accounting", lambda _: ("fixture", [row]))
    review = runner.terminal_review("123", P)
    assert review["complete"] == (outcome != "incomplete")
    assert review["mesh_feasible"] == (outcome == "pass")
    assert not review["reference_qualified"]
    row["State"] = "RUNNING"
    with pytest.raises(ValueError, match="terminal"):
        runner.terminal_review("123", P)


@pytest.mark.parametrize("corruption", ["source", "job", "runtime", "raw", "coverage", "flag", "numeric_flag", "extra", "symlink", "skip_failed", "parent_cap"])
def test_receipt_corruption_rejected(monkeypatch, tmp_path, corruption):
    directory, record = setup_attempt(monkeypatch, tmp_path)
    if corruption == "source":
        record["source_commit"] = "other"
    elif corruption == "job":
        record["scheduler"]["JobId"] = "124"
    elif corruption == "runtime":
        record["runtime"]["threads"]["OMP_NUM_THREADS"] = "2"
    elif corruption == "raw":
        (directory / "toy.stdout").write_text("changed")
    elif corruption == "coverage":
        record["modes"].pop("toy")
    elif corruption == "flag":
        record["reference_qualified"] = True
    elif corruption == "numeric_flag":
        record["reference_qualified"] = 0
    elif corruption == "extra":
        (directory / "extra.json").write_text("{}")
    elif corruption == "symlink":
        (directory / "toy.stdout").rename(directory / "target")
        (directory / "toy.stdout").symlink_to(directory / "target")
    elif corruption == "skip_failed":
        record["modes"]["toy"]["passed"] = False
    elif corruption == "parent_cap":
        record["modes"]["toy"]["elapsed_s"] = 601
        atomic_write_json(directory / "toy.json", record["modes"]["toy"])
    atomic_write_json(directory / "attempt.json", record)
    with pytest.raises(ValueError):
        runner.validate_attempt(directory, P)


def test_parent_stops_after_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit": "fixture"})
    monkeypatch.setattr(runner, "check_source", lambda: None)
    monkeypatch.setattr(runner, "validate_attempt", lambda *args: None)
    arm = Mock(return_value={"mode": "toy", "passed": False})
    monkeypatch.setattr(runner, "bounded_mode", arm)
    assert not runner.run(P, {"JobId": "123"}, runner.expected_runtime(P))
    assert arm.call_count == 1
    record = contract.read_json(contract.attempt_directory("123") / "attempt.json")
    assert set(record["modes"]) == {"toy"} and not record["complete"]


def test_attempts_exclusive_and_symlink_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    path = contract.attempt_directory("123", create=True)
    with pytest.raises(FileExistsError):
        contract.attempt_directory("123", create=True)
    with pytest.raises(ValueError):
        contract.attempt_directory("../escape")
    (path.parent / "job_124").symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        contract.attempt_directory("124")


def test_source_closure_after_freeze():
    if not (REPO / contract.LOCK).exists():
        pytest.skip("pre-freeze validation")
    lock = contract.check_source(execution=False)
    assert set(contract.SOURCES).issubset(lock["files_sha256"])
    assert str(contract.ARCHIVE) in lock["files_sha256"]


@pytest.mark.parametrize("corruption", [None, "bytes", "root", "commit", "external_lock", "wrapper", "phase", "untracked"])
def test_execution_source_guards(monkeypatch, tmp_path, corruption):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    (tmp_path / contract.LOCK).parent.mkdir(parents=True)
    wrapper = tmp_path / contract.WRAPPER
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("frozen wrapper")
    lock = {"files_sha256": {contract.WRAPPER: sha256_file(wrapper)}}
    atomic_write_json(tmp_path / contract.LOCK, lock)
    monkeypatch.setattr(contract, "frozen_lock", lambda: lock if corruption != "bytes" else {})
    env = {"PCB_TCAD_EXECUTION_ROOT": str(tmp_path), "PCB_TCAD_SOURCE_COMMIT": "fixture",
           "PCB_TCAD_LOCK_SHA256": sha256_file(tmp_path / contract.LOCK),
           "PCB_TCAD_BATCH_PHASE": "mesh_probe", "PCB_TCAD_EXECUTED_BATCH_SCRIPT": str(wrapper)}
    replacements = {"root": ("PCB_TCAD_EXECUTION_ROOT", str(tmp_path.parent)),
                    "commit": ("PCB_TCAD_SOURCE_COMMIT", "other"),
                    "external_lock": ("PCB_TCAD_LOCK_SHA256", "other"),
                    "phase": ("PCB_TCAD_BATCH_PHASE", "feasibility")}
    if corruption in replacements:
        key, value = replacements[corruption]
        env[key] = value
    if corruption == "wrapper":
        other = tmp_path / "other.sh"
        other.write_text("different wrapper")
        env["PCB_TCAD_EXECUTED_BATCH_SCRIPT"] = str(other)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    def command(args):
        if args[1] == "rev-parse":
            return "fixture"
        if args[1] == "diff":
            return ""
        assert args[1] == "ls-files"
        return "" if corruption == "untracked" else "\n".join([contract.WRAPPER, str(contract.LOCK)])
    monkeypatch.setattr(contract.parent.support.original, "command", command)
    if corruption is None:
        assert contract.check_source() == lock
    else:
        with pytest.raises(ValueError):
            contract.check_source()
