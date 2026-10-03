"""No-solver tests: contracts, failure retention and frozen assembly identity."""
import ast
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_amg_diagnostic as diagnostic
import run_tcad_cps_amg_diagnostic as runner
import tcad_cps_amg_worker as worker
import tcad_cps_support_recovery as recovery
from archive_tcad_cps_support_v1 import check_archive
from test_tcad_cps_reference import scheduler_fixture
P = diagnostic.protocol()


def test_original_and_support_closures_are_unchanged():
    recovery.check_source(execution=False)
    manifest = check_archive()
    assert len(manifest["files_sha256"]) == 10
    assert manifest["diagnosis"]["n_free"] == 18629
    assert manifest["diagnosis"]["operator_complexity"] > 1.25


def test_only_one_candidate_and_worker_caps_unchanged():
    parent = recovery.protocol()
    assert P["worker_limits"] == {"toy": parent["resources"]["smoke"], "local0": parent["resources"]["feasibility"]}
    for key in ("physics", "mesh", "linear_solver", "runtime", "gates", "geometry"):
        assert P[key] == parent[key]
    assert P["diagnostic"]["modes"] == ["toy", "local0"]
    assert diagnostic.candidate_kwargs(P) == {"smooth": None, "symmetry": "symmetric", "max_coarse": 50}
    candidate = diagnostic.candidate_kwargs(P)
    candidate["max_coarse"] = 100
    assert P["diagnostic"]["candidate"]["max_coarse"] == 50
    assert P["resources"]["diagnostic"]["time_limit"] == "00:45:00"
    for flag in ("automatic_feasibility_expansion", "training_may_start", "claim_eligible", "reference_qualified"):
        assert P["diagnostic"][flag] is False


def test_recorded_systems_and_direct_dimension_gate():
    for mode in P["diagnostic"]["modes"]:
        system = {"n_free": 100, **P["diagnostic"]["expected_systems"][mode]}
        diagnostic.check_system(system, mode, P)
        system["system_sha256"] = "0"*64
        with pytest.raises(ValueError, match="differs"):
            diagnostic.check_system(system, mode, P)
    with pytest.raises(ValueError, match="dimension cap"):
        diagnostic.check_system({**P["diagnostic"]["expected_systems"]["toy"], "n_free": 25001}, "toy", P)
    with pytest.raises(ValueError, match="unfrozen"):
        diagnostic.mode_input("local2", P)


def synthetic_result():
    system = P["diagnostic"]["expected_systems"]["local0"]
    return {**system, "input_system_sha256": system["system_sha256"],
            "candidate": diagnostic.candidate_kwargs(P), "solver_info": 0,
            "operator_complexity": 1.1, "iterations": 12, "relative_residual": 1e-11,
            "cps_pf": 100., "comparison": {"cps_pf": 100., "relative_residual": 1e-14,
                                           "input_system_sha256": system["system_sha256"]},
            "solution_relative_l2": 1e-10, "peak_rss_gib": 3., "elapsed_s": 500.}


def test_positive_same_matrix_candidate_assessment():
    assert diagnostic.assess_result(synthetic_result(), "local0", P)


@pytest.mark.parametrize("mode", ["complexity", "residual", "direct_residual", "capacitance", "vector",
                                 "hash", "geometry", "nan", "timeout", "rss", "candidate", "info"])
def test_negative_candidate_is_rejected(mode):
    r = synthetic_result()
    if mode == "complexity":
        r["operator_complexity"] = 1.2752039488745819
    elif mode == "residual":
        r["relative_residual"] = 1e-8
    elif mode == "direct_residual":
        r["comparison"]["relative_residual"] = 1e-8
    elif mode == "capacitance":
        r["cps_pf"] = 101
    elif mode == "vector":
        r["solution_relative_l2"] = 1e-5
    elif mode == "hash":
        r["comparison"]["input_system_sha256"] = "b"*64
    elif mode == "geometry":
        r["mesh_nodes"] += 1
    elif mode == "nan":
        r["cps_pf"] = float("nan")
    elif mode == "timeout":
        r["elapsed_s"] = 1201
    elif mode == "rss":
        r["peak_rss_gib"] = 121
    elif mode == "candidate":
        r["candidate"]["smooth"] = "jacobi"
    else:
        r["solver_info"] = 1
    assert not diagnostic.assess_result(r, "local0", P)


def test_allocation_rejects_login_array_requeue_and_wrong_time():
    record, env = scheduler_fixture("pilot")
    record.pop("ArrayJobId")
    record.pop("ArrayTaskId")
    record["TimeLimit"] = "00:45:00"
    env = {k: v for k, v in env.items() if not k.startswith("SLURM_ARRAY")}
    matches = recovery.original.allocation_matches
    assert matches(record, env, "a0126", "diagnostic", P)
    for host, changes in (("login01", {}), ("a0126", {"Requeue": "1"}),
                          ("a0126", {"ArrayJobId": "123"}), ("a0126", {"TimeLimit": "03:00:00"})):
        assert not matches({**record, **changes}, env, host, "diagnostic", P)


def test_entrypoints_reject_login_before_source_or_numerical_work(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "diagnostic")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "toy"])
    forbidden = Mock(side_effect=AssertionError("must not reach numerical work"))
    monkeypatch.setattr(worker, "assemble_system", forbidden)
    for entry in (worker.main, runner.main):
        with pytest.raises(ValueError, match="login-node"):
            entry()
    forbidden.assert_not_called()


def test_numerical_imports_follow_guards_and_copied_assembly_matches_source():
    tree = ast.parse((ROOT / "code/solvers/tcad_cps_amg_worker.py").read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    source_guard = next(n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "check_source")
    for node in main.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert node.lineno > source_guard
    original = ast.parse((ROOT / "code/solvers/fem_capacitance_3d.py").read_text())
    baseline = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == "fem_cps_3d_diagnostics")
    assembled = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "assemble_system")
    def recipes(function):
        return [ast.dump(n) for n in function.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id in {"basis", "K", "pri_nodes", "sec_nodes", "u", "D"}
                    or isinstance(t, ast.Subscript)
                    or isinstance(t, ast.Tuple) and isinstance(t.elts[0], ast.Name) and t.elts[0].id == "A"
                    for t in n.targets)]
    # The later solution/energy assignments are intentionally outside assembly.
    expected = recipes(baseline)
    observed = recipes(assembled)
    assert expected[:len(observed)] == observed
    def laplace(function):
        return ast.dump(next(n for n in function.body if isinstance(n, ast.FunctionDef) and n.name == "laplace"))
    assert laplace(baseline) == laplace(assembled)


def test_candidate_factory_and_complexity_stop_without_numerical_imports(monkeypatch):
    matrix = Mock(shape=(10, 10))
    matrix.tocsr.return_value = matrix
    hierarchy = Mock(levels=[1, 2])
    hierarchy.operator_complexity.return_value = 1.3
    factory = Mock(return_value=hierarchy)
    cg = Mock(side_effect=AssertionError("CG must not start above the frozen cap"))
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(ones=lambda shape: ("constant", shape)))
    monkeypatch.setitem(sys.modules, "pyamg", SimpleNamespace(smoothed_aggregation_solver=factory))
    monkeypatch.setitem(sys.modules, "scipy.sparse.linalg", SimpleNamespace(cg=cg))
    monkeypatch.setitem(sys.modules, "fem_capacitance_3d", SimpleNamespace(_sparse_system_sha256=lambda *args: "hash"))
    def progress(stage, payload):
        if payload.get("operator_complexity", 0) > 1.25:
            raise ValueError("frozen operator cap")
    with pytest.raises(ValueError, match="operator cap"):
        worker.solve_candidate(matrix, "rhs", P, progress)
    factory.assert_called_once_with(matrix, B=("constant", (10, 1)), smooth=None, symmetry="symmetric", max_coarse=50)
    cg.assert_not_called()


@pytest.mark.parametrize("reason", ["time", "rss"])
def test_bounded_worker_kills_process_group_and_retains_logs(monkeypatch, tmp_path, reason):
    fake = Mock(pid=123, returncode=-9)
    fake.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=fake))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 1201, 1202])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if reason == "rss" else 0)
    p = copy.deepcopy(P)
    if reason == "rss":
        p["worker_limits"]["local0"]["worker_timeout_s"] = 9999
    record = runner.bounded_mode(tmp_path, "local0", p)
    kill.assert_called_once_with(123, runner.signal.SIGKILL)
    assert record["failure"] and not record["passed"]
    assert set(record["files_sha256"]) == {"local0.stdout", "local0.stderr"}


def test_failed_toy_prevents_local0_and_no_claim_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "attempt_directory", lambda *args, **kwargs: tmp_path)
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit": "test"})
    monkeypatch.setattr(runner, "check_source", lambda: None)
    bounded = Mock(return_value={"passed": False, "failure": "cap"})
    monkeypatch.setattr(runner, "bounded_mode", bounded)
    assert runner.run(P, {}, {}) is False
    bounded.assert_called_once_with(tmp_path, "toy", P)
    saved = json.loads((tmp_path / "attempt.json").read_text())
    assert set(saved["modes"]) == {"toy"}
    for key in ("passed", "claim_eligible", "reference_qualified", "training_may_start", "automatic_feasibility_expansion"):
        assert saved[key] is False


def test_output_rejects_overwrite_path_traversal_and_symlinks(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostic, "ROOT", tmp_path)
    diagnostic.attempt_directory("123", create=True)
    with pytest.raises(FileExistsError):
        diagnostic.attempt_directory("123", create=True)
    with pytest.raises(ValueError):
        diagnostic.attempt_directory("../123")
    (tmp_path / diagnostic.BASE / "job_124").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        diagnostic.attempt_directory("124")


def test_old_result_identity_cannot_pass(monkeypatch):
    layout_id, layout, arm = diagnostic.mode_input("local0", P)
    result = {**synthetic_result(), "mode": "local0", "layout_id": layout_id, "arm": arm,
              "geometry_sha256": runner.geometry_sha256(layout), "protocol_sha256": "old"}
    monkeypatch.setattr(runner, "identity", lambda: {"protocol_sha256": "new"})
    with pytest.raises(ValueError, match="source mismatch"):
        runner.validate_result(result, "local0", P)


def test_lock_when_frozen():
    if not (ROOT / diagnostic.LOCK).exists():
        pytest.skip("pre-freeze validation")
    assert diagnostic.check_source(execution=False) == diagnostic.frozen_lock()
