"""Synthetic checks for validation replay diagnostics; no corpus is opened."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SOURCE = Path(__file__).resolve().parents[1] / "code/experiments/proofs/diagnose_strict_e3_validation_replay_v1.py"
SPEC = importlib.util.spec_from_file_location("e3_replay_diagnostic", SOURCE)
assert SPEC is not None and SPEC.loader is not None
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def test_metric_paths_and_gate_match_frozen_direction() -> None:
    stored = {"C_ps": {"bias": 1.000000015, "counts": [4, 0]}, "r2": None}
    replay = {"C_ps": {"bias": 1.0, "counts": [4, 0]}, "r2": None}
    rows = {row["metric"]: row for row in diag.differences(stored, replay)}
    row = rows["C_ps.bias"]
    assert row["absolute_difference"] == abs(1.000000015 - 1.0)
    assert row["original_gate_limit"] == 1e-10 + 1e-8
    assert row["original_gate_passed"] == bool(np.isclose(1.000000015, 1.0, rtol=1e-8, atol=1e-10))
    assert rows["C_ps.counts[0]"]["original_gate_passed"]
    assert rows["r2"]["equal"]


@pytest.mark.parametrize("stored,replay", [({"a": 1}, {"b": 1}), ([1], []), (float("nan"), 1), (1, float("inf")), (1, True), ("x", "y")])
def test_invalid_metrics_fail_closed(stored: object, replay: object) -> None:
    with pytest.raises(ValueError):
        diag.differences(stored, replay)


def test_zero_reference_is_json_safe_and_retains_absolute_difference() -> None:
    row = diag.differences(1.0, 0.0)[0]
    assert row["relative_difference_to_replay"] is None
    assert row["absolute_difference"] == 1.0
    assert row["original_gate_passed"] is False
    assert diag.differences(0.0, 0.0)[0]["relative_difference_to_replay"] == 0.0


def test_canonical_file_accepts_only_regular_in_tree_path(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    target.write_text("{}")
    assert diag.real_file(tmp_path, "checkpoint.json") == target
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    for name in ("missing.json", "linked.json", str(target), "../checkpoint.json", "."):
        with pytest.raises(ValueError):
            diag.real_file(tmp_path, name)


def test_scheduler_rejects_non_slurm_before_contacting_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    def forbidden(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("controller must not be queried without an allocation")
    monkeypatch.setattr(diag.subprocess, "check_output", forbidden)
    with pytest.raises(ValueError):
        diag.scheduler()


SCHEDULER_RECORD = "JobId=123 JobState=RUNNING Requeue=0 Restarts=0 Partition=nextgen Account=pgs0407 TimeLimit=00:30:00 NumTasks=1 MinMemoryNode=48G ReqTRES=cpu=8,mem=48G,node=1 AllocTRES=cpu=13,mem=48G,node=1 NumCPUs=13 CPUs/Task=13"


def test_scheduler_accepts_site_memory_driven_cpu_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "13")
    monkeypatch.setattr(diag.subprocess, "check_output", lambda *_args, **_kwargs: SCHEDULER_RECORD)
    assert diag.scheduler()["scontrol"]["CPUs/Task"] == "13"


@pytest.mark.parametrize("old,new", [
    ("Requeue=0", "Requeue=1"), ("Restarts=0", "Restarts=1"),
    ("JobId=123", "JobId=124"), ("ReqTRES=cpu=8", "ReqTRES=cpu=4"),
    ("NumCPUs=13", "NumCPUs=8"), ("Partition=nextgen", "Partition=other"),
    ("TimeLimit=00:30:00", "TimeLimit=04:00:00"),
])
def test_scheduler_rejects_wrong_execution_profile(monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "13")
    monkeypatch.setattr(diag.subprocess, "check_output", lambda *_args, **_kwargs: SCHEDULER_RECORD.replace(old, new))
    with pytest.raises(ValueError):
        diag.scheduler()
