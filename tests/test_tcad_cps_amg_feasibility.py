"""No-solver tests for the separately versioned seven-arm AMG study."""
import ast
import copy
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_amg_feasibility as contract
import run_tcad_cps_amg_feasibility as runner
import tcad_cps_amg_feasibility_worker as worker
import tcad_cps_amg_diagnostic as diagnostic
import tcad_cps_support_recovery as support
from archive_tcad_cps_amg_diagnostic_v1 import check_archive, safe_path, collect
import archive_tcad_cps_amg_diagnostic_v1 as archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json
from test_tcad_cps_reference import scheduler_fixture
P = contract.protocol()


def test_prior_sources_and_nine_file_diagnostic_archive_are_intact():
    diagnostic.check_source(execution=False)
    archive = check_archive()
    assert len(archive["files_sha256"]) == 9
    assert archive["accounting"][0]["State"] == "COMPLETED"


def test_archive_refuses_overwrite_and_unsafe_paths(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / archive.DIRECTORY).mkdir(parents=True)
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    monkeypatch.setattr(archive, "review", lambda _: None)
    monkeypatch.setattr(archive, "accounting", lambda _: ("", [{"JobID": archive.JOB, "State": "COMPLETED", "ExitCode": "0:0", "Restarts": "0"}]))
    with pytest.raises(ValueError, match="overwrite"):
        collect(source)
    with pytest.raises(ValueError, match="unsafe"):
        safe_path(tmp_path, "../escape")
    (tmp_path / "alias").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        safe_path(tmp_path, "alias/result.json")


def test_unchanged_physics_mesh_caps_arm_order_and_sensitivity_gates():
    parent = support.protocol()
    for key in ("physics", "mesh", "linear_solver", "resources", "runtime", "gates", "recovery", "smoke"):
        assert P[key] == parent[key]
    assert P["diagnostic"] == diagnostic.protocol()["diagnostic"]
    assert [a["name"] for a in contract.arms_for("feasibility", P)] == ["local0", "local1", "local2", "repeat2", "pad20", "far2", "support1"]
    for phase in ("smoke", "feasibility"):
        for arm in contract.arms_for(phase, P):
            layout_id, _, actual = contract.inputs(phase, arm["name"], P)
            assert actual == arm and layout_id == ("smoke" if phase == "smoke" else 597)
    for phase, name in (("finalize", "local0"), ("smoke", "local0"), ("feasibility", "local3")):
        with pytest.raises(ValueError):
            contract.inputs(phase, name, P)


def test_runtime_metadata_cannot_mutate_frozen_protocol():
    expected = copy.deepcopy(P["runtime"])
    metadata = runner.expected_runtime(P)
    metadata["threads"]["OMP_NUM_THREADS"] = "99"
    metadata["packages"]["pyamg"] = "other"
    assert P["runtime"] == expected


def synthetic_result(phase="feasibility", name="local0"):
    layout_id, layout, arm = contract.inputs(phase, name, P)
    anchor = P["diagnostic"]["expected_systems"]["toy" if phase == "smoke" else "local0"]
    return {"n_free": 477, "nnz": 5595, **anchor, "input_system_sha256": anchor["system_sha256"],
            "candidate": copy.deepcopy(P["diagnostic"]["candidate"]), "solver_info": 0, "iterations": 20,
            "cps_pf": 100., "relative_residual": 1e-11, "operator_complexity": 1.1,
            "peak_rss_gib": .1, "elapsed_s": 10., "arm": copy.deepcopy(arm), "layout_id": layout_id,
            "geometry_sha256": runner.geometry_sha256(layout), "mesh_policy": {}, "mesh_policy_sha256": sha256_json({}),
            "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(P), "source_commit": "test",
            "solution_relative_l2": 1e-10,
            "comparison": {"cps_pf": 100., "relative_residual": 1e-14, "system_sha256": anchor["system_sha256"],
                           "input_system_sha256": anchor["system_sha256"]}}


def synthetic_record():
    return {"passed": True, "layout_id": 597,
            "arms": {a["name"]: {"passed": True, "arm": a, "result": synthetic_result(name=a["name"])}
                     for a in contract.arms_for("feasibility", P)}}


def test_smoke_and_seven_arm_pass_do_not_qualify_reference():
    assert contract.assess_result(synthetic_result("smoke", "smoke"), P, "smoke")
    summary = contract.assess_feasibility(synthetic_record(), P)
    assert summary["complete"] and summary["feasibility_passed"]
    for flag in ("reference_qualified", "claim_eligible", "training_may_start", "automatic_expansion", "three_sentinel_qualification", "continuum_convergence_established"):
        assert summary[flag] is False


@pytest.mark.parametrize("key,value", [("operator_complexity", 1.26), ("relative_residual", 1e-8),
    ("cps_pf", float("nan")), ("elapsed_s", 1201), ("peak_rss_gib", 121), ("iterations", 501),
    ("solver_info", 1), ("solver_info", False), ("mesh_nodes", 3000001), ("input_system_sha256", "b"*64)])
def test_worker_numerical_resource_gates(key, value):
    result = synthetic_result()
    result[key] = value
    assert not contract.assess_result(result, P, "feasibility")


@pytest.mark.parametrize("case", ["missing", "old_candidate", "failed", "repeat", "support", "padding", "mesh", "far"])
def test_incomplete_and_negative_sensitivity_are_retained(case):
    record = synthetic_record()
    if case == "missing":
        record["arms"].pop("support1")
    elif case == "old_candidate":
        record["arms"]["local1"]["result"]["candidate"]["smooth"] = "jacobi"
    elif case == "failed":
        record["arms"]["local1"]["passed"] = False
    elif case == "repeat":
        record["arms"]["repeat2"]["result"]["system_sha256"] = "a"*64
        record["arms"]["repeat2"]["result"]["input_system_sha256"] = "a"*64
    else:
        name = {"support": "support1", "padding": "pad20", "mesh": "local1", "far": "far2"}[case]
        record["arms"][name]["result"]["cps_pf"] = 106
    summary = contract.assess_feasibility(record, P)
    assert not summary["feasibility_passed"]
    if case in ("support", "padding", "mesh", "far", "repeat"):
        assert summary["complete"]


def test_smoke_requires_direct_residual_vector_and_anchor_agreement():
    for case in ("residual", "vector", "anchor", "dimension"):
        result = synthetic_result("smoke", "smoke")
        if case == "residual":
            result["comparison"]["relative_residual"] = 1e-8
        elif case == "vector":
            result["solution_relative_l2"] = 1e-5
        elif case == "anchor":
            result["mesh_nodes"] += 1
        else:
            result["n_free"] = 25001
        assert not contract.assess_result(result, P, "smoke")


@pytest.mark.parametrize("phase", ["smoke", "feasibility", "finalize"])
def test_all_entrypoints_reject_login_before_numerical_work(monkeypatch, phase):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", phase)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["runner", "--phase", phase])
    with pytest.raises(ValueError, match="login-node"):
        runner.main()
    if phase != "finalize":
        monkeypatch.setattr(sys, "argv", ["worker", "--phase", phase, "--arm", contract.arms_for(phase, P)[0]["name"]])
        with pytest.raises(ValueError, match="login-node"):
            worker.main()


def test_actual_host_and_single_job_resource_contract():
    record, env = scheduler_fixture("pilot")
    record.pop("ArrayJobId")
    record.pop("ArrayTaskId")
    env = {k: v for k, v in env.items() if not k.startswith("SLURM_ARRAY")}
    matches = support.original.allocation_matches
    assert matches(record, env, "a0126", "feasibility", P)
    assert not matches(record, env, "login01", "feasibility", P)
    assert not matches({**record, "Requeue": "1"}, env, "a0126", "feasibility", P)
    assert not matches({**record, "ArrayJobId": "123"}, env, "a0126", "feasibility", P)


def test_worker_reuses_frozen_helpers_after_guards_without_monkeypatching():
    tree = ast.parse((ROOT / "code/solvers/tcad_cps_amg_feasibility_worker.py").read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    guard = min(n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "check_source")
    for node in main.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert node.lineno > guard
    helpers = next(n for n in main.body if isinstance(n, ast.ImportFrom) and n.module == "tcad_cps_amg_worker")
    assert {a.name for a in helpers.names} == {"assemble_system", "solve_candidate"}
    assert not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) for t in n.targets) for n in ast.walk(tree))


@pytest.mark.parametrize("cause", ["time", "rss"])
def test_bounded_arm_terminates_group_and_keeps_logs(monkeypatch, tmp_path, cause):
    process = Mock(pid=123, returncode=-9)
    process.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 1201, 1202])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if cause == "rss" else 0)
    p = copy.deepcopy(P)
    if cause == "rss":
        p["resources"]["feasibility"]["worker_timeout_s"] = 9999
    record = runner.bounded_arm(tmp_path, "feasibility", p["recovery"]["recovery_arms"][0], p)
    kill.assert_called_once_with(123, runner.signal.SIGKILL)
    assert record["failure"] and not record["passed"]
    assert set(record["files_sha256"]) == {"local0.stdout", "local0.stderr"}


def setup_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit": "test"})
    directory = contract.attempt_directory("smoke", "123", create=True)
    result = synthetic_result("smoke", "smoke")
    (directory / "smoke.stdout").write_text("RESULT="+json.dumps(result)+"\n")
    (directory / "smoke.stderr").write_text("")
    arm = {"arm": result["arm"], "passed": True, "failure": None, "returncode": 0,
           "elapsed_s": 10., "observed_peak_rss_gib": .1, "result": result,
           "files_sha256": {name: sha256_file(directory/name) for name in ("smoke.stdout", "smoke.stderr")}}
    atomic_write_json(directory / "smoke.json", arm)
    record = {"source_commit": "test", "phase": "smoke", "scheduler": {"JobId": "123"},
              "runtime": runner.expected_runtime(P), "layout_id": "smoke", "passed": True,
              "failure": None, "arms": {"smoke": arm}}
    atomic_write_json(directory / "attempt.json", record)
    return directory, record


@pytest.mark.parametrize("corruption", [None, "raw_log", "old_source", "job", "coverage", "runtime"])
def test_smoke_receipt_reconstruction_rejects_corruption(monkeypatch, tmp_path, corruption):
    directory, record = setup_attempt(monkeypatch, tmp_path)
    if corruption == "raw_log":
        (directory / "smoke.stdout").write_text("corrupt\n")
    elif corruption == "old_source":
        record["source_commit"] = "old"
    elif corruption == "job":
        record["scheduler"]["JobId"] = "124"
    elif corruption == "coverage":
        record["arms"]["local0"] = record["arms"].pop("smoke")
    elif corruption == "runtime":
        record["runtime"]["threads"]["OMP_NUM_THREADS"] = "2"
    if corruption:
        atomic_write_json(directory / "attempt.json", record)
        with pytest.raises(ValueError):
            runner.validate_attempt(directory, "smoke", P)
    else:
        assert runner.validate_attempt(directory, "smoke", P) == record


def test_terminal_smoke_required_and_failure_prevents_workers(monkeypatch, tmp_path):
    directory, record = setup_attempt(monkeypatch, tmp_path)
    monkeypatch.setenv("PCB_TCAD_SMOKE_JOB_ID", "123")
    monkeypatch.setattr(runner, "accounting", lambda _: ("", [{"JobID": "123", "State": "RUNNING", "ExitCode": "0:0", "Restarts": "0"}]))
    with pytest.raises(ValueError, match="terminal"):
        runner.accepted_smoke(P)
    monkeypatch.setenv("SLURM_JOB_ID", "124")
    bounded = Mock(side_effect=AssertionError("must not start a worker"))
    monkeypatch.setattr(runner, "bounded_arm", bounded)
    assert runner.run_phase("feasibility", P, {}, runner.expected_runtime(P)) is False
    saved = contract.read_json(contract.attempt_directory("feasibility", "124")/"attempt.json")
    assert not saved["arms"] and saved["failure"]
    bounded.assert_not_called()


def test_failed_first_worker_stops_later_arms(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setattr(runner, "identity", lambda: {})
    monkeypatch.setattr(runner, "check_source", lambda: None)
    monkeypatch.setattr(runner, "accepted_smoke", lambda _: {"attempt_sha256": "smoke"})
    bounded = Mock(return_value={"passed": False, "failure": "node cap"})
    monkeypatch.setattr(runner, "bounded_arm", bounded)
    assert runner.run_phase("feasibility", P, {}, {}) is False
    assert bounded.call_count == 1 and bounded.call_args.args[2]["name"] == "local0"


@pytest.mark.parametrize("complete", [False, True])
def test_finalizer_retains_failure_or_complete_negative(monkeypatch, tmp_path, complete):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "124")
    monkeypatch.setenv("PCB_TCAD_FEASIBILITY_JOB_ID", "123")
    directory = contract.attempt_directory("feasibility", "123", create=True)
    atomic_write_json(directory / "attempt.json", {"fixture": True})
    monkeypatch.setattr(runner, "identity", lambda: {})
    monkeypatch.setattr(runner, "check_source", lambda: None)
    monkeypatch.setattr(runner, "accepted_smoke", lambda _: {"attempt_sha256": "smoke"})
    record = synthetic_record() if complete else {"arms": {"local0": {"passed": False, "failure": "cap"}}}
    record.update(scheduler={"JobId": "123"}, smoke={"attempt_sha256": "smoke"})
    if complete:
        record["arms"]["support1"]["result"]["cps_pf"] = 106
        for arm in record["arms"].values():
            arm["failure"] = None
    monkeypatch.setattr(runner, "validate_attempt", lambda *args: record)
    rows = [{"JobID": "123", "State": "COMPLETED" if complete else "FAILED", "ExitCode": "0:0" if complete else "2:0", "Restarts": "0"}]
    monkeypatch.setattr(runner, "accounting", lambda _: ("accounting", rows))
    assert runner.finalize(P, {}, {}) is complete
    summary = contract.read_json(contract.attempt_directory("finalize", "124")/"summary.json")
    assert summary["attempt_sha256"] == sha256_file(directory/"attempt.json")
    assert summary["complete"] is complete and not summary["feasibility_passed"]
    assert summary["observed_arms"] and not summary["reference_qualified"]
    assert bool(summary["errors"]) is not complete


def test_output_path_and_overwrite_safety(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    contract.attempt_directory("feasibility", "123", create=True)
    with pytest.raises(FileExistsError):
        contract.attempt_directory("feasibility", "123", create=True)
    for phase, job in (("escape", "123"), ("smoke", "../123")):
        with pytest.raises(ValueError):
            contract.attempt_directory(phase, job)
    (tmp_path/contract.BASE/"smoke").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        contract.attempt_directory("smoke", "123")


def test_lock_when_frozen():
    if not (ROOT / contract.LOCK).exists():
        pytest.skip("pre-freeze validation")
    assert contract.check_source(execution=False) == contract.frozen_lock()
