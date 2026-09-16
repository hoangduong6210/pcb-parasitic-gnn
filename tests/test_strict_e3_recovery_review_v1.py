"""Independent synthetic recovery checks; never load a production checkpoint."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "code/experiments/proofs/recover_strict_e3_fem_v2_v1.py"
SPEC = importlib.util.spec_from_file_location("e3_recovery_review", SOURCE)
assert SPEC is not None and SPEC.loader is not None
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def protocol() -> dict:
    return json.loads((ROOT / "protocols/corpus_v4_strict_e3_fem_v2_recovery_v1.json").read_text())


def test_committed_recovery_protocol_is_accepted() -> None:
    recovery.validate_recovery_protocol(protocol())


@pytest.mark.parametrize("field,value", [
    ("frozen_commit", "0" * 40),
    ("frozen_protocol_sha256", "0" * 64),
    ("frozen_lock_sha256", "0" * 64),
    ("training_array", "7318064"),
    ("scientific_threads", 2),
    ("model_fitting_permitted", True),
    ("claim_eligible", True),
])
def test_recovery_rejects_scientific_scope_mutations(field: str, value: object) -> None:
    candidate = protocol()
    candidate[field] = value
    with pytest.raises(ValueError):
        recovery.validate_recovery_protocol(candidate)


@pytest.mark.parametrize("field,value", [
    ("cpus_per_task", 2), ("mem", "16G"), ("time", "04:00:00"),
    ("account", "other"), ("partition", "other"), ("requeue", True),
])
def test_recovery_rejects_resource_profile_mutations(field: str, value: object) -> None:
    candidate = protocol()
    candidate["resources"][field] = value
    with pytest.raises(ValueError):
        recovery.validate_recovery_protocol(candidate)


def test_recovery_requires_exact_task_grid_and_valid_hashes() -> None:
    original = protocol()
    for mutation in ("missing", "extra", "invalid_hash"):
        candidate = copy.deepcopy(original)
        if mutation == "missing":
            candidate["task_receipt_sha256"].pop("24")
        elif mutation == "extra":
            candidate["task_receipt_sha256"]["25"] = "f" * 64
        else:
            candidate["task_receipt_sha256"]["0"] = "not-a-sha256"
        with pytest.raises(ValueError):
            recovery.validate_recovery_protocol(candidate)


def test_unknown_protocol_field_fails_closed() -> None:
    candidate = protocol()
    candidate["relaxed_metric_tolerance"] = 1e-4
    with pytest.raises(ValueError):
        recovery.validate_recovery_protocol(candidate)


SCHEDULER = "JobId=123 JobState=RUNNING Requeue=0 Restarts=0 Partition=nextgen Account=pgs0407 TimeLimit=00:30:00 NumTasks=1 MinMemoryNode=48G ReqTRES=cpu=8,mem=48G,node=1 AllocTRES=cpu=13,mem=48G,node=1 NumCPUs=13 CPUs/Task=13 NodeList=a0102"


def scheduler_fixture(monkeypatch: pytest.MonkeyPatch, text: str = SCHEDULER) -> None:
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "13")
    for key in recovery.THREAD_ENV:
        monkeypatch.setenv(key, "8")
    monkeypatch.setattr(recovery.subprocess, "check_output", lambda *_a, **_k: text)


def test_scheduler_records_memory_driven_cpu_allocation(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler_fixture(monkeypatch)
    observed = recovery.scheduler()
    assert observed["scontrol"]["ReqTRES"].startswith("cpu=8,")
    assert observed["scontrol"]["NumCPUs"] == "13"


@pytest.mark.parametrize("name", recovery.THREAD_ENV)
def test_every_scientific_thread_env_is_enforced(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    scheduler_fixture(monkeypatch)
    monkeypatch.setenv(name, "2")
    with pytest.raises(ValueError):
        recovery.scheduler()


@pytest.mark.parametrize("old,new", [
    ("Requeue=0", "Requeue=1"), ("Restarts=0", "Restarts=1"),
    ("ReqTRES=cpu=8", "ReqTRES=cpu=2"),
    ("AllocTRES=cpu=13,mem=48G", "AllocTRES=cpu=13,mem=16G"),
    ("NumCPUs=13", "NumCPUs=8"), ("Account=pgs0407", "Account=other"),
    ("JobState=RUNNING", "JobState=PENDING"),
    ("TimeLimit=00:30:00", "TimeLimit=04:00:00"),
])
def test_scheduler_rejects_profile_drift(monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    scheduler_fixture(monkeypatch, SCHEDULER.replace(old, new))
    with pytest.raises(ValueError):
        recovery.scheduler()


def test_array_allocation_cannot_masquerade_as_finalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler_fixture(monkeypatch, SCHEDULER + " ArrayJobId=122 ArrayTaskId=0")
    with pytest.raises(ValueError):
        recovery.scheduler()


def test_output_refuses_overwrite_and_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(recovery, "ROOT", tmp_path)
    original = recovery.output_folder("admission", {"job_id": "123"})
    with pytest.raises(ValueError):
        recovery.output_folder("admission", {"job_id": "123"})
    original.with_name("job_124").symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError):
        recovery.output_folder("admission", {"job_id": "124"})


@pytest.mark.parametrize("failure", ["admission", "task_replay", "accepted_records"])
def test_heldout_is_never_opened_before_complete_admission(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    calls = []
    def forbidden(*_args, **_kwargs):
        calls.append("heldout")
        raise AssertionError("evaluation must remain closed")
    def admission(*_args):
        if failure == "admission":
            raise ValueError("admission invalid")
        return {"accepted": ["expected"]}
    def check_all(*_args):
        if failure == "task_replay":
            raise ValueError("checkpoint replay failed")
        return [], ["different"]
    monkeypatch.setattr(sys, "argv", [str(SOURCE), "--stage", "finalize", "--frozen-root", "/unused", "--expected-recovery-commit", "f" * 40, "--expected-recovery-protocol-sha256", "a" * 64, "--accepted-set", "/unused/accepted.json", "--expected-accepted-set-sha256", "b" * 64])
    monkeypatch.setattr(recovery, "scheduler", lambda: {})
    monkeypatch.setattr(recovery, "bootstrap", lambda _args: (SimpleNamespace(evaluate=forbidden), None, {}, {}, [], {}, {}))
    monkeypatch.setattr(recovery, "validate_admission", admission)
    monkeypatch.setattr(recovery, "check_all", check_all)
    with pytest.raises(ValueError):
        recovery.main()
    assert calls == []


def test_all_task_replay_stops_on_first_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    selected = protocol()
    root = tmp_path / recovery.BASE / "jobs" / f"job_{selected['training_array']}"
    for i in range(25):
        folder = root / f"task_{i:02d}"
        folder.mkdir(parents=True)
        (folder / "result.json").write_text("{}")
        selected["task_receipt_sha256"][str(i)] = recovery.sha(folder / "result.json")
    visited = []
    def check(_binding, _path, task_id, *_args):
        visited.append(task_id)
        if task_id == 4:
            raise ValueError("unchanged frozen tolerance failed")
        return {"scheduler": {"array_job_id": "7318063", "job_id": str(100 + task_id)}}
    module = SimpleNamespace(ROOT=tmp_path, check_task=check, terminal=lambda *_args: {"State": "COMPLETED"})
    with pytest.raises(ValueError, match="frozen tolerance"):
        recovery.check_all(module, None, {}, {}, [], selected)
    assert visited == list(range(5))


def provenance_fixture() -> dict:
    return {"recovery_commit": "a" * 40, "recovery_protocol_sha256": "b" * 64,
        "recovery_source_sha256": {"worker.py": recovery.hashlib.sha256(b"frozen-code").hexdigest()},
        "training_bindings": {"commit": "f" * 40}, "scientific_source_sha256": {"frozen.py": "c" * 64},
        "runtime": {"python": "3.10"}, "scientific_threads": 8}


def test_tracked_replay_allows_descendant_commit_with_same_recovery_source(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = provenance_fixture()
    current = copy.deepcopy(stored)
    current["recovery_commit"] = "d" * 40
    ancestry = []
    monkeypatch.setattr(recovery.subprocess, "run", lambda command, **_kw: ancestry.append(command))
    monkeypatch.setattr(recovery.subprocess, "check_output", lambda *_a, **_kw: b"frozen-code")
    recovery.validate_provenance(stored, current)
    assert ancestry[0][-2:] == [stored["recovery_commit"], current["recovery_commit"]]


def test_same_hash_declaration_cannot_hide_different_historical_source(monkeypatch: pytest.MonkeyPatch) -> None:
    value = provenance_fixture()
    monkeypatch.setattr(recovery.subprocess, "run", lambda *_a, **_kw: None)
    monkeypatch.setattr(recovery.subprocess, "check_output", lambda *_a, **_kw: b"changed-code")
    with pytest.raises(ValueError, match="source commit"):
        recovery.validate_provenance(value, copy.deepcopy(value))


@pytest.mark.parametrize("field,value", [("scientific_threads", 2), ("runtime", {}), ("training_bindings", {}), ("scientific_source_sha256", {})])
def test_provenance_rejects_scientific_drift(field: str, value: object) -> None:
    stored = provenance_fixture()
    current = copy.deepcopy(stored)
    current[field] = value
    with pytest.raises(ValueError):
        recovery.validate_provenance(stored, current)
