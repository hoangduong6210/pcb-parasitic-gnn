"""Lightweight contract tests. Never invoke meshing, solving or fitting here."""
import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_reference as contract
import plan_tcad_cps_reference as planner
import run_tcad_cps_reference as runner
spec = importlib.util.spec_from_file_location("tcad_worker", ROOT / "code/solvers/tcad_cps_reference_worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
PROTOCOL = contract.read_json(ROOT / contract.PROTOCOL)


def test_panel_reconstructs_and_ignores_labels_and_order():
    rows, _ = planner.load_verified_geometry_corpus(ROOT / PROTOCOL["geometry"]["directory"], PROTOCOL["geometry"])
    expected = planner.panel_from_records(rows, PROTOCOL)
    changed = [{**r, "cps_pf": -1e90, "targets": {"Cps": None}} for r in reversed(rows)]
    assert planner.panel_from_records(changed, PROTOCOL) == expected
    saved = contract.read_json(ROOT / contract.PANEL)
    assert saved == {**expected, "protocol_sha256": contract.sha256_file(ROOT / contract.PROTOCOL)}
    assert len(expected["rows"]) == 12
    assert expected["pilot_layout_ids"] == [874, 1369, 597]
    assert len(set(expected["pilot_layout_ids"])) == 3
    assert not expected["target_values_used"] and not expected["is_blind_model_test"]


def test_empty_selection_cell_fails():
    with pytest.raises(ValueError, match="empty"):
        planner.panel_from_records([], PROTOCOL)


def test_geometry_descriptors():
    value = planner.descriptors(PROTOCOL["smoke"]["layout"])
    assert value["n_conductors"] == 2
    assert value["opposite_net_overlap_mm2"] == 2
    assert value["no_same_layer_pairs"]
    assert value["same_layer_clearance_mm"] == pytest.approx(61**0.5)


def scheduler_fixture(phase="smoke"):
    p = PROTOCOL["resources"][phase]
    # OSC can grant more CPUs than requested to satisfy a memory request.
    allocated = 41 if phase == "pilot" else 3
    env = {"SLURM_JOB_ID": "123", "SLURMD_NODENAME": "a0126", "SLURM_CPUS_PER_TASK": str(allocated),
           "SLURM_MEM_PER_NODE": str(p["mem_gib"] * 1024)}
    record = {"JobId": "123", "UserId": f"test({os.getuid()})", "JobState": "RUNNING", "Account": p["account"],
              "Partition": p["partition"], "TimeLimit": p["time_limit"], "Requeue": "0", "Restarts": "0",
              "NumNodes": "1", "NumTasks": "1", "NodeList": "a0126", "BatchHost": "a0126",
              "NumCPUs": str(allocated), "CPUs/Task": str(allocated), "ReqTRES": f'cpu=1,mem={p["mem_gib"]}G',
              "TresPerTask": "cpu=1", "AllocTRES": f'cpu={allocated},mem={p["mem_gib"]}G', "MinMemoryNode": f'{p["mem_gib"]}G'}
    if phase == "pilot":
        env.update(SLURM_ARRAY_JOB_ID="120", SLURM_ARRAY_TASK_ID="0", SLURM_ARRAY_TASK_COUNT="3",
                   SLURM_ARRAY_TASK_MIN="0", SLURM_ARRAY_TASK_MAX="2")
        record.update(ArrayJobId="120", ArrayTaskId="0")
    return record, env


@pytest.mark.parametrize("phase", ["smoke", "pilot", "finalize"])
def test_actual_compute_host_and_resources_required(phase):
    record, env = scheduler_fixture(phase)
    assert contract.allocation_matches(record, env, "a0126.osc.edu", phase, PROTOCOL)
    assert not contract.allocation_matches(record, env, "ascend-login01", phase, PROTOCOL)
    assert not contract.allocation_matches(record, {}, "a0126", phase, PROTOCOL)
    for key, value in [("JobState", "PENDING"), ("Requeue", "1"), ("Restarts", "1"),
                       ("Partition", "other"), ("ReqTRES", "cpu=2,mem=8G"), ("NodeList", "a0125")]:
        assert not contract.allocation_matches({**record, key: value}, env, "a0126", phase, PROTOCOL)


def test_login_guard_does_not_query_scheduler(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "smoke")
    query = Mock(side_effect=AssertionError("must reject before scheduler query"))
    monkeypatch.setattr(contract, "command", query)
    with pytest.raises(ValueError, match="login-node"):
        contract.check_allocation("smoke", PROTOCOL)
    query.assert_not_called()


def test_mesh_policy_uses_expanded_boxes_and_disables_other_size_sources():
    options, values, ids = {}, {}, []
    def add(kind):
        ids.append(kind)
        return len(ids)
    fields = SimpleNamespace(add=add, setNumber=lambda i, n, v: values.setdefault(i, {}).update({n: v}),
                             setNumbers=Mock(), setAsBackgroundMesh=Mock())
    gmsh = SimpleNamespace(option=SimpleNamespace(setNumber=lambda n, v: options.update({n: v}), getNumber=options.get),
                           model=SimpleNamespace(mesh=SimpleNamespace(field=fields)))
    arm = PROTOCOL["smoke"]["arm"]
    observed = worker.apply_mesh_policy(gmsh, PROTOCOL["smoke"]["layout"], arm, PROTOCOL)
    assert ids == ["Box", "Box", "Min"]
    assert values[1]["XMin"] == 1.89 and values[1]["XMax"] == 4.11
    assert values[1]["ZMin"] == pytest.approx(-0.045)
    assert values[1]["VIn"] == 0.12 and values[1]["VOut"] == 1
    assert observed["options"]["Mesh.MeshSizeFromPoints"] == 0
    assert observed["options"]["Mesh.MeshSizeExtendFromBoundary"] == 0
    fields.setAsBackgroundMesh.assert_called_once_with(3)


def test_numpy_scalar_telemetry_remains_finite_json():
    # Scalar conversion only: no mesh, linear algebra or solver execution.
    import numpy as np
    encoded = json.dumps({"n_dofs": np.int32(2159), "nnz": np.int64(12336),
                          "value": np.float32(.25)}, allow_nan=False, default=worker.numeric_json)
    assert json.loads(encoded) == {"n_dofs": 2159, "nnz": 12336, "value": .25}
    with pytest.raises(ValueError):
        json.dumps({"value": np.float32("nan")}, allow_nan=False, default=worker.numeric_json)
    with pytest.raises(TypeError):
        json.dumps({"bad": object()}, default=worker.numeric_json)


def result():
    return {"cps_pf": 10., "relative_residual": 1e-11, "system_sha256": "a" * 64,
            "mesh_nodes": 1000, "mesh_tetrahedra": 2000, "operator_complexity": 1.1, "peak_rss_gib": .1}


@pytest.mark.parametrize("key,value", [("cps_pf", float("nan")), ("cps_pf", -1), ("relative_residual", 1e-5),
                                      ("peak_rss_gib", 121), ("operator_complexity", 2), ("mesh_nodes", 4000000)])
def test_bad_numerical_or_resource_results_fail(key, value):
    assert contract.assess_result(result(), PROTOCOL, "pilot")
    assert not contract.assess_result({**result(), key: value}, PROTOCOL, "pilot")


def test_backend_check_requires_same_matrix():
    record = {**result(), "comparison": result()}
    assert contract.assess_result(record, PROTOCOL, "smoke")
    record["comparison"]["system_sha256"] = "b" * 64
    assert not contract.assess_result(record, PROTOCOL, "smoke")


def synthetic_tasks():
    return [{"passed": True, "arms": {a["name"]: {"result": result()} for a in PROTOCOL["pilot_arms"]}} for _ in range(3)]


def test_finite_sensitivity_is_not_claim_or_training_authorization():
    summary = contract.sensitivity_summary(synthetic_tasks(), PROTOCOL)
    assert summary["pilot_passed"]
    assert not summary["claim_eligible"] and not summary["training_may_start"]
    assert not summary["continuum_convergence_established"]


def test_incomplete_coverage_and_repeat_system_change_fail():
    tasks = synthetic_tasks()
    assert not contract.sensitivity_summary(tasks[:2], PROTOCOL)["pilot_passed"]
    tasks[0]["arms"]["repeat2"]["result"]["system_sha256"] = "b" * 64
    assert not contract.sensitivity_summary(tasks, PROTOCOL)["pilot_passed"]


def test_maximum_failure_not_hidden_by_median():
    tasks = synthetic_tasks()
    tasks[0]["arms"]["pad20"]["result"]["cps_pf"] = 11
    summary = contract.sensitivity_summary(tasks, PROTOCOL)
    assert summary["complete"] and not summary["pilot_passed"]
    assert summary["comparisons"]["padding"]["median_pct"] == 0
    assert summary["comparisons"]["padding"]["max_pct"] == 10


def test_attempt_paths_reject_overwrite_symlink_and_non_id(monkeypatch, tmp_path):
    monkeypatch.setattr(contract, "ROOT", tmp_path)
    p = contract.attempt_directory("smoke", "123", create=True)
    with pytest.raises(FileExistsError):
        contract.attempt_directory("smoke", "123", create=True)
    with pytest.raises(ValueError):
        contract.attempt_directory("smoke", "../123")
    (p.parent / "job_124").symlink_to(p, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        contract.attempt_directory("smoke", "124")


def test_worker_log_requires_one_finite_terminal_result(tmp_path):
    p = tmp_path / "worker.stdout"
    p.write_text('STAGE={}\nRESULT={"cps_pf": NaN}\n')
    with pytest.raises(ValueError):
        runner.result_from_log(p)
    p.write_text('RESULT={}\nRESULT={}\n')
    with pytest.raises(ValueError):
        runner.result_from_log(p)


def test_terminal_accounting_rejects_missing_restarts_or_failed_job():
    row = {"JobID": "123_0", "State": "COMPLETED", "ExitCode": "0:0", "Restarts": "0"}
    assert runner.terminal_success([row], "123_0")
    assert not runner.terminal_success([{**row, "Restarts": "1"}], "123_0")
    assert not runner.terminal_success([row], "123_1")


@pytest.mark.parametrize("failure", ["time", "rss"])
def test_bounded_worker_kills_process_group_and_retains_logs(monkeypatch, tmp_path, failure):
    fake = Mock(pid=123, returncode=-9)
    fake.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=fake))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 1201, 1202])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if failure == "rss" else 0)
    protocol = copy.deepcopy(PROTOCOL)
    if failure == "rss":
        protocol["resources"]["pilot"]["worker_timeout_s"] = 9999
    arm = runner.bounded_arm(tmp_path, "pilot", PROTOCOL["pilot_arms"][0], protocol)
    kill.assert_called_once_with(123, runner.signal.SIGKILL)
    assert not arm["passed"] and arm["failure"]
    assert (tmp_path / "local0.stdout").exists() and (tmp_path / "local0.stderr").exists()


def test_frozen_source_lock_when_present():
    if not (ROOT / contract.LOCK).exists():
        pytest.skip("pre-freeze source validation")
    assert contract.check_source(execution=False) == contract.frozen_lock()
