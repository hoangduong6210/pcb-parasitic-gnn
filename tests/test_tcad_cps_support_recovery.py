"""No-solver regression suite for the bounded support-recovery chain."""
import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_support_recovery as recovery
import run_tcad_cps_support_recovery as runner
import tcad_cps_reference as original
from archive_tcad_cps_pilot_v1 import check_archive
from tcad_cps_reference_worker import apply_mesh_policy
from test_tcad_cps_reference import scheduler_fixture
P = recovery.protocol()


def test_original_source_and_terminal_archive_remain_intact():
    original.check_source(execution=False)
    manifest = check_archive()
    assert len(manifest["files_sha256"]) == 59
    assert len(manifest["accounting"]) == 4


def test_only_mesh_support_changes_not_physics_or_caps():
    parent = original.read_json(ROOT / original.PROTOCOL)
    for key in ("physics", "linear_solver", "runtime", "gates", "geometry", "selection"):
        assert P[key] == parent[key]
    assert P["mesh"]["near_sizes_mm"] == parent["mesh"]["near_sizes_mm"]
    expected = {k: v for k, v in parent["resources"]["pilot"].items() if not k.startswith("array_")}
    assert P["resources"]["feasibility"] == expected
    assert P["resources"]["smoke"] == parent["resources"]["smoke"]
    assert P["resources"]["finalize"] == parent["resources"]["finalize"]
    assert P["recovery"]["layout_id"] == 597
    assert len(P["recovery"]["recovery_arms"]) == 7
    assert not P["recovery"]["resource_caps_may_increase"]


def test_half_gap_support_keeps_nearest_overlapping_layer_gap_fully_covered():
    from geometry_contract import trace_box
    layout = recovery.target(P)["layout"]
    boxes = [trace_box(layout, t) for t in layout["traces"]]
    expansion = P["recovery"]["compact_support"]["box_expansion_mm"]
    checked = 0
    for i, a in enumerate(boxes):
        for b in boxes[i+1:]:
            if min(a[1], b[1]) <= max(a[0], b[0]) or min(a[3], b[3]) <= max(a[2], b[2]):
                continue
            lower, upper = sorted((a, b), key=lambda box: box[4])
            gap = upper[4] - lower[5]
            if abs(gap - .11) < 1e-12:
                assert lower[5] + expansion >= upper[4] - expansion - 1e-12
                checked += 1
    assert checked > 0


def test_support_arm_is_fresh_old_support_at_intermediate_level():
    arm = P["recovery"]["recovery_arms"][-1]
    assert arm["name"] == "support1" and arm["level"] == 1
    p = recovery.arm_protocol(P, arm)
    assert p["mesh"] == original.read_json(ROOT / original.PROTOCOL)["mesh"]
    assert P["mesh"]["box_expansion_mm"] == .055  # No in-place mutation.
    assert not P["recovery"]["reuse_old_results_as_new_arms"]


def test_compact_field_recipe_without_importing_or_running_gmsh():
    options, values, ids = {}, {}, []
    def add(kind):
        ids.append(kind)
        return len(ids)
    fields = SimpleNamespace(add=add, setNumber=lambda i, n, v: values.setdefault(i, {}).update({n: v}),
                             setNumbers=Mock(), setAsBackgroundMesh=Mock())
    gmsh = SimpleNamespace(option=SimpleNamespace(setNumber=lambda n, v: options.update({n: v}), getNumber=options.get),
                           model=SimpleNamespace(mesh=SimpleNamespace(field=fields)))
    observed = apply_mesh_policy(gmsh, P["smoke"]["layout"], P["smoke"]["arm"], P)
    assert values[1]["XMin"] == 1.945
    assert values[1]["Thickness"] == .5
    assert observed["near_size_mm"] == .12
    assert observed["options"]["Mesh.MeshSizeExtendFromBoundary"] == 0


def test_singleton_allocation_rejects_login_node_and_wrong_resources():
    record, env = scheduler_fixture("pilot")
    record.pop("ArrayJobId")
    record.pop("ArrayTaskId")
    env = {k: v for k, v in env.items() if not k.startswith("SLURM_ARRAY")}
    assert original.allocation_matches(record, env, "a0126", "feasibility", P)
    assert not original.allocation_matches(record, env, "login01", "feasibility", P)
    assert not original.allocation_matches({**record, "Requeue": "1"}, env, "a0126", "feasibility", P)


def test_missing_allocation_fails_before_numerical_worker(monkeypatch):
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", "feasibility")
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ValueError, match="login-node"):
        recovery.check_allocation("feasibility", P)


def synthetic_record():
    result = {"cps_pf": 100., "relative_residual": 1e-11, "system_sha256": "a"*64,
              "mesh_nodes": 2000, "mesh_tetrahedra": 10000, "operator_complexity": 1.1, "peak_rss_gib": .1}
    return {"passed": True, "layout_id": 597,
            "arms": {a["name"]: {"passed": True, "arm": a, "result": copy.deepcopy(result)} for a in P["recovery"]["recovery_arms"]}}


def test_single_layout_pass_never_implies_three_layout_qualification():
    summary = recovery.assess_feasibility(synthetic_record(), P)
    assert summary["complete"] and summary["feasibility_passed"]
    for key in ("three_sentinel_qualification", "claim_eligible", "training_may_start", "automatic_expansion", "continuum_convergence_established"):
        assert summary[key] is False


@pytest.mark.parametrize("mode", ["missing", "failure", "nonfinite", "wrong_layout", "repeat_hash", "support_sensitivity"])
def test_incomplete_or_negative_feasibility_is_not_accepted(mode):
    record = synthetic_record()
    if mode == "missing":
        record["arms"].pop("support1")
    elif mode == "failure":
        record["arms"]["local2"]["passed"] = False
    elif mode == "nonfinite":
        record["arms"]["local2"]["result"]["cps_pf"] = float("nan")
    elif mode == "wrong_layout":
        record["layout_id"] = 874
    elif mode == "repeat_hash":
        record["arms"]["repeat2"]["result"]["system_sha256"] = "b"*64
    else:
        record["arms"]["support1"]["result"]["cps_pf"] = 106
    assert not recovery.assess_feasibility(record, P)["feasibility_passed"]


def test_unsupported_output_paths_and_overwrite_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "ROOT", tmp_path)
    recovery.attempt_directory("feasibility", "123", create=True)
    with pytest.raises(FileExistsError):
        recovery.attempt_directory("feasibility", "123", create=True)
    with pytest.raises(ValueError):
        recovery.attempt_directory("../escape", "123")
    with pytest.raises(ValueError):
        recovery.attempt_directory("feasibility", "../123")


@pytest.mark.parametrize("failure", ["time", "rss"])
def test_recovery_worker_resource_stop_retains_raw_logs(monkeypatch, tmp_path, failure):
    fake = Mock(pid=123, returncode=-9)
    fake.poll.return_value = None
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=fake))
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    ticks = iter([0, 1201, 1202])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(runner, "rss_gib", lambda _: 121 if failure == "rss" else 0)
    p = copy.deepcopy(P)
    if failure == "rss":
        p["resources"]["feasibility"]["worker_timeout_s"] = 9999
    record = runner.bounded_arm(tmp_path, "feasibility", p["recovery"]["recovery_arms"][0], p)
    kill.assert_called_once_with(123, runner.signal.SIGKILL)
    assert record["passed"] is False and record["failure"]
    assert set(record["files_sha256"]) == {"local0.stdout", "local0.stderr"}


def test_recovery_lock_when_frozen():
    if not (ROOT / recovery.LOCK).exists():
        pytest.skip("pre-freeze validation")
    assert recovery.check_source(execution=False) == recovery.frozen_lock()


def test_finalizer_retains_failed_attempt_binding(monkeypatch, tmp_path):
    phase_root = tmp_path / "final"
    attempt_root = tmp_path / "feasibility"
    attempt_root.mkdir()
    (attempt_root / "attempt.json").write_text('{"passed": false}\n')
    def directory(phase, job, create=False):
        path = phase_root if phase == "finalize" else attempt_root
        if create:
            path.mkdir()
        return path
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "attempt_directory", directory)
    monkeypatch.setattr(runner, "identity", lambda: {"source_commit": "test"})
    monkeypatch.setattr(runner, "check_source", lambda: None)
    monkeypatch.setenv("SLURM_JOB_ID", "124")
    monkeypatch.setenv("PCB_TCAD_FEASIBILITY_JOB_ID", "123")
    monkeypatch.setattr(runner, "accounting", lambda _: ("123|FAILED|2:0|0", [{"JobID": "123", "State": "FAILED", "ExitCode": "2:0", "Restarts": "0"}]))
    monkeypatch.setattr(runner, "accepted_smoke", lambda _: {"attempt_sha256": "smoke"})
    record = {"scheduler": {"JobId": "123"}, "smoke": {"attempt_sha256": "smoke"},
              "arms": {"local2": {"passed": False, "failure": "cap exceeded"}}}
    monkeypatch.setattr(runner, "validate_attempt", lambda *args: record)
    assert runner.finalize(P, {}, {}) is False
    saved = json.loads((phase_root / "summary.json").read_text())
    assert saved["attempt_sha256"] == recovery.sha256_file(attempt_root / "attempt.json")
    assert saved["observed_arms"]["local2"]["failure"] == "cap exceeded"
    assert saved["errors"] and not saved["complete"] and not saved["feasibility_passed"]


def test_result_from_old_protocol_cannot_be_admitted_as_new(monkeypatch):
    monkeypatch.setattr(runner, "identity", lambda: {"protocol_sha256": "new-protocol"})
    arm = P["recovery"]["recovery_arms"][0]
    with pytest.raises(ValueError, match="arm/source"):
        runner.validate_result({"arm": arm, "protocol_sha256": "old-protocol"}, "feasibility", arm, P)
