from __future__ import annotations

import importlib.util
import json
import sys
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "code/operations/corpus_v4_fem_v2_controller.py"
SPEC = importlib.util.spec_from_file_location("corpus_v4_fem_v2_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


FIXED_NOW = datetime(2026, 8, 23, 3, 0, tzinfo=timezone.utc)


class FakeRunner:
    """Pure in-memory SLURM boundary used by every controller test."""

    def __init__(
        self,
        *,
        live_ids: Sequence[str] = (),
        sbatch_ids: Sequence[str] = (),
        accounting: dict[str, str] | None = None,
    ) -> None:
        self.live_ids = list(live_ids)
        self.sbatch_ids = deque(sbatch_ids)
        self.accounting = accounting or {}
        self.calls: list[list[str]] = []

    def run(self, command: Sequence[str]) -> controller.CommandResult:
        argv = list(command)
        self.calls.append(argv)
        if argv[0] == "squeue":
            stdout = "".join(f"{job_id}\n" for job_id in self.live_ids)
            return controller.CommandResult(0, stdout, "")
        if argv[0] == "sbatch":
            if not self.sbatch_ids:
                raise AssertionError("unexpected sbatch call")
            return controller.CommandResult(0, self.sbatch_ids.popleft() + "\n", "")
        if argv[0] == "sacct":
            job_id = argv[argv.index("-j") + 1]
            return controller.CommandResult(0, self.accounting.get(job_id, ""), "")
        raise AssertionError(f"unexpected command: {argv}")


class ForbiddenRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command: Sequence[str]) -> controller.CommandResult:
        self.calls.append(list(command))
        raise AssertionError("dry-run must not call a scheduler command")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _command_exports(command: Sequence[str]) -> dict[str, str]:
    raw = next(
        token.removeprefix("--export=")
        for token in command
        if token.startswith("--export=")
    )
    return dict(item.split("=", 1) for item in raw.split(","))


def _build_execution_root(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "run"
    protocol = root / controller.PROTOCOL_RELATIVE
    lock = root / controller.LOCK_RELATIVE
    plan_path = root / controller.PLAN_RELATIVE
    protocol.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text('{"lock":"test"}\n', encoding="utf-8")

    artifact_sha256: dict[str, str] = {}
    for expected in controller._expected_wave_layout():
        dispatch = {
            "entries": [
                {
                    "geometry_sha256": f"{task_index:064x}"[-64:],
                    "layout_id": task_index,
                    "task_index": task_index,
                }
                for task_index in expected["indices"]
            ],
            "fidelity_id": expected["fidelity_id"],
            "schema": "pcb-gnn.corpus-v4-fem-v2-production-dispatch.v1",
        }
        dispatch_path = plan_path.parent / expected["dispatch"]
        _write_json(dispatch_path, dispatch)
        artifact_sha256[expected["dispatch"]] = controller.sha256_file(dispatch_path)

    _write_json(
        plan_path,
        {
            "artifact_sha256": artifact_sha256,
            "counts": {"geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198},
            "schema": "pcb-gnn.corpus-v4-fem-v2-production-plan.v1",
        },
    )
    for relative in (
        controller.CONTROLLER_SOURCE_RELATIVE,
        controller.R3_WRAPPER_RELATIVE,
        controller.R4_WRAPPER_RELATIVE,
        controller.FINALIZER_WRAPPER_RELATIVE,
    ):
        wrapper = root / relative
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")

    _write_json(
        protocol,
        {
            "computational_sources": {
                relative: controller.sha256_file(root / relative)
                for relative in (
                    controller.CONTROLLER_SOURCE_RELATIVE,
                    controller.R3_WRAPPER_RELATIVE,
                    controller.R4_WRAPPER_RELATIVE,
                    controller.FINALIZER_WRAPPER_RELATIVE,
                )
            }
        },
    )

    pins = {
        "lock": controller.sha256_file(lock),
        "plan": controller.sha256_file(plan_path),
        "protocol": controller.sha256_file(protocol),
    }
    return root, pins


def _config(root: Path, pins: dict[str, str], **changes: object) -> controller.ControllerConfig:
    config = controller.ControllerConfig(
        execution_root=root,
        state_path=Path(controller.STATE_RELATIVE),
        source_commit="a" * 40,
        protocol_sha256=pins["protocol"],
        plan_sha256=pins["plan"],
        lock_sha256=pins["lock"],
        username="researcher",
    )
    return replace(config, **changes)


def _source_accounting(
    job_id: str,
    tasks: int,
    *,
    memory: str,
    allocated_cpu: int,
    time_limit: str,
) -> str:
    rows = []
    for task in range(tasks):
        component = f"{job_id}_{task}"
        rows.append(
            "|".join(
                (
                    component,
                    component,
                    "COMPLETED",
                    "0:0",
                    controller.ACCOUNT,
                    controller.PARTITION,
                    time_limit,
                    "a0100",
                    "0",
                    "500",
                    f"billing=1,cpu=1,mem={memory},node=1",
                    f"billing={allocated_cpu},cpu={allocated_cpu},mem={memory},node=1",
                )
            )
            + "\n"
        )
    return "".join(rows)


def _finalizer_accounting(job_id: str) -> str:
    return (
        "|".join(
            (
                job_id,
                job_id,
                "COMPLETED",
                "0:0",
                controller.ACCOUNT,
                controller.PARTITION,
                "00:30:00",
                "a0101",
                "0",
                "5",
                "billing=2,cpu=2,mem=16G,node=1",
                "billing=5,cpu=5,mem=16G,node=1",
            )
        )
        + "\n"
    )


def _prior_admission(
    root: Path, pins: dict[str, str], *, wave_id: int = 0
) -> tuple[Path, str]:
    path = (
        root
        / "results/corpus_v4/cps_reference_v2/production/v1/waves/r3"
        / f"wave_{wave_id:03d}/admission/source_set_test/finalizer_job_8003"
        / "FINAL_ADMISSION.json"
    )
    _write_json(
        path,
        {
            "admission_eligible": True,
            "artifact_stage": "postterminal_wave_admission",
            "decision": {
                "coverage_complete": False,
                "dataset_finalize_may_start": False,
                "retry_may_start": True,
                "scientific_outcome": "INDETERMINATE",
                "terminal_negative": False,
            },
            "fidelity_id": "cps_fem_r3_p16_t1_v2",
            "roots": {
                "execution_lock_sha256": pins["lock"],
                "plan_sha256": pins["plan"],
                "protocol_sha256": pins["protocol"],
                "source_git_head": "a" * 40,
            },
            "schema": "pcb-gnn.corpus-v4-fem-v2-production-wave-admission.v1",
            "wave_id": wave_id,
        },
    )
    return path, controller.sha256_file(path)


def test_dispatch_authentication_freezes_r4_then_four_r3_waves(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    specs = controller.build_wave_specs(_config(root, pins))
    assert [spec.wave_id for spec in specs] == [
        "r4_000",
        "r3_000",
        "r3_001",
        "r3_002",
        "r3_003",
    ]
    assert [spec.expected_tasks for spec in specs] == [198, 400, 400, 400, 300]
    assert [spec.throttle for spec in specs] == [2, 8, 8, 8, 8]
    assert [spec.package_wave_id for spec in specs] == [0, 0, 1, 2, 3]


def test_dispatch_hash_drift_fails_before_scheduler_access(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    dispatch = root / Path(controller.PLAN_RELATIVE).parent / "r4_dispatch_000.json"
    dispatch.write_text(dispatch.read_text(encoding="utf-8") + " ", encoding="utf-8")
    runner = ForbiddenRunner()
    with pytest.raises(controller.ControllerError, match="dispatch SHA-256"):
        controller.FemV2Controller(_config(root, pins), runner, now=lambda: FIXED_NOW)
    assert runner.calls == []


def test_dry_run_is_offline_and_previews_r4_before_r3(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = ForbiddenRunner()
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    state = instance.tick(dry_run=True, assumed_live_count=0)
    assert runner.calls == []
    actions = state["last_dry_run"]["actions"]
    assert [(row["wave_id"], row["kind"]) for row in actions] == [
        ("r4_000", "source"),
        ("r4_000", "finalizer"),
        ("r3_000", "source"),
        ("r3_000", "finalizer"),
    ]
    assert "--array=0-197%2" in actions[0]["command"]
    assert "--dependency=afterany:<SOURCE_JOB_ID>" in actions[1]["command"]
    assert "--array=0-399%8" in actions[2]["command"]
    assert state["last_dry_run"]["capacity"]["projected_live_expanded_elements"] == 600
    assert state["operator_admission_required"] is True
    r4_final_exports = _command_exports(actions[1]["command"])
    assert r4_final_exports["PCB_GNN_V4_FEM_V2_WAVE_ID"] == "0"
    assert r4_final_exports["PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS"].startswith(
        "<SOURCE_JOB_ID>|results/corpus_v4/cps_reference_v2/production/v1/plan/"
        "r4_dispatch_000.json|"
    )
    assert "PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID" not in r4_final_exports
    source_export = next(
        token for token in actions[0]["command"] if token.startswith("--export=")
    )
    assert not source_export.startswith("--export=ALL,")


def test_soft_capacity_allows_r4_but_blocks_r3_at_750_live_elements(
    tmp_path: Path,
) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(
        live_ids=[f"7000_{index}" for index in range(750)],
        sbatch_ids=["8000", "8001"],
    )
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    state = instance.tick()
    sbatch = [command for command in runner.calls if command[0] == "sbatch"]
    assert len(sbatch) == 2
    assert "--array=0-197%2" in sbatch[0]
    assert "--dependency=afterany:8000" in sbatch[1]
    assert state["waves"]["r3_000"]["source"]["status"] == "CAPACITY_BLOCKED"
    assert state["capacity"]["projected_after_tick"] == 949


def test_soft_ceiling_blocks_r4_pair_without_any_submission(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(live_ids=[f"7000_{index}" for index in range(752)])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    state = instance.tick()
    assert [command for command in runner.calls if command[0] == "sbatch"] == []
    decision = state["capacity"]["last_source_decision"]
    assert decision["wave_id"] == "r4_000"
    assert decision["projected_expanded_elements"] == 951
    assert decision["allowed"] is False


def test_hard_qos_limit_cannot_be_configured_above_1000(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    with pytest.raises(controller.ControllerError, match="capacity ceilings"):
        controller.FemV2Controller(
            _config(root, pins, soft_ceiling=1001, hard_limit=1001),
            ForbiddenRunner(),
            now=lambda: FIXED_NOW,
        )


def test_real_tick_submits_exact_source_finalizer_pairs_in_order(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(sbatch_ids=["8000", "8001", "8002", "8003"])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    state = instance.tick()
    sbatch = [command for command in runner.calls if command[0] == "sbatch"]
    assert "--array=0-197%2" in sbatch[0]
    assert "--dependency=afterany:8000" in sbatch[1]
    assert "--array=0-399%8" in sbatch[2]
    assert "--dependency=afterany:8002" in sbatch[3]
    assert [state["waves"][wave][kind]["job_id"] for wave, kind in (
        ("r4_000", "source"),
        ("r4_000", "finalizer"),
        ("r3_000", "source"),
        ("r3_000", "finalizer"),
    )] == ["8000", "8001", "8002", "8003"]
    assert state["capacity"]["projected_after_tick"] == 600
    assert not any("admit" in token for command in runner.calls for token in command)


def test_terminal_sacct_is_exactly_hashed_and_atomically_persisted(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(sbatch_ids=["8000", "8001", "8002", "8003"])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    instance.tick()
    r4_raw = _source_accounting(
        "8000", 198, memory="160G", allocated_cpu=41, time_limit="03:00:00"
    )
    r3_raw = _source_accounting(
        "8002", 400, memory="48G", allocated_cpu=13, time_limit="02:00:00"
    )
    runner.accounting = {
        "8000": r4_raw,
        "8001": _finalizer_accounting("8001"),
        "8002": r3_raw,
        "8003": _finalizer_accounting("8003"),
    }
    state = instance.tick()
    persisted = json.loads(instance.state_path.read_text(encoding="utf-8"))
    assert persisted == state
    evidence = state["waves"]["r4_000"]["source"]["accounting"]
    assert evidence["row_count"] == 198
    assert evidence["raw_stdout"] == r4_raw
    assert evidence["raw_stdout_sha256"] == controller.sha256_bytes(r4_raw.encode())
    expected_rows = sorted(controller._parse_sacct(r4_raw), key=lambda row: row["JobID"])
    assert evidence["canonical_rows_sha256"] == controller.sha256_bytes(
        controller.canonical_json_bytes(expected_rows)
    )
    assert evidence["contract_pass"] is True
    assert evidence["terminal_success"] is True
    assert list(instance.state_path.parent.glob(".status.json.*.tmp")) == []


def test_next_r3_wave_requires_manual_release_after_prior_finalizer(
    tmp_path: Path,
) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(sbatch_ids=["8000", "8001", "8002", "8003"])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    instance.tick()
    runner.accounting = {
        "8000": _source_accounting(
            "8000", 198, memory="160G", allocated_cpu=41, time_limit="03:00:00"
        ),
        "8001": _finalizer_accounting("8001"),
        "8002": _source_accounting(
            "8002", 400, memory="48G", allocated_cpu=13, time_limit="02:00:00"
        ),
        "8003": _finalizer_accounting("8003"),
    }
    instance.tick()

    runner.sbatch_ids.extend(("8010", "8011"))
    admission, admission_sha = _prior_admission(root, pins)
    state = instance.tick(
        release_r3_through=1,
        prior_admission=admission,
        prior_admission_sha256=admission_sha,
    )
    assert state["waves"]["r3_001"]["source"]["job_id"] == "8010"
    assert state["waves"]["r3_001"]["finalizer"]["job_id"] == "8011"
    assert state["releases"]["events"][-1]["type"] == "operator_release"
    assert state["releases"]["events"][-1]["prior_admission"]["sha256"] == admission_sha
    final_exports = _command_exports(
        next(
            command
            for command in runner.calls
            if command[0] == "sbatch" and "--dependency=afterany:8010" in command
        )
    )
    assert final_exports["PCB_GNN_V4_FEM_V2_WAVE_ID"] == "1"
    assert final_exports["PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256"] == admission_sha

    with pytest.raises(controller.ControllerError, match="prior R3 finalizer"):
        instance.tick(release_r3_through=2)


def test_nonterminal_or_incomplete_sacct_remains_pending(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(sbatch_ids=["8000", "8001", "8002", "8003"])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    instance.tick()
    runner.accounting = {
        "8000": _source_accounting(
            "8000", 197, memory="160G", allocated_cpu=41, time_limit="03:00:00"
        ),
        "8001": _finalizer_accounting("8001"),
        "8002": "",
        "8003": "",
    }
    state = instance.tick()
    source = state["waves"]["r4_000"]["source"]
    assert source["status"] == "ACCOUNTING_PENDING"
    assert source.get("accounting") is None
    assert source["last_accounting_probe"]["expected_rows"] == 198
    assert source["last_accounting_probe"]["observed_rows"] == 197


def test_missing_finalizer_wrapper_fails_closed(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    (root / controller.FINALIZER_WRAPPER_RELATIVE).unlink()
    with pytest.raises(controller.ControllerError, match="finalizer wrapper"):
        controller.FemV2Controller(
            _config(root, pins), ForbiddenRunner(), now=lambda: FIXED_NOW
        )


def test_state_finalizer_and_runtime_exports_are_restricted(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    alternate = root / "code/jobs/alternate.sh"
    alternate.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    with pytest.raises(controller.ControllerError, match="canonical status path"):
        controller.FemV2Controller(
            _config(root, pins, state_path=Path("protocols/overwrite.json")),
            ForbiddenRunner(),
            now=lambda: FIXED_NOW,
        )
    with pytest.raises(controller.ControllerError, match="canonical frozen finalizer"):
        controller.FemV2Controller(
            _config(root, pins, finalizer_script=alternate),
            ForbiddenRunner(),
            now=lambda: FIXED_NOW,
        )
    with pytest.raises(controller.ControllerError, match="runtime-control export"):
        controller.FemV2Controller(
            _config(root, pins, extra_exports={"BASH_ENV": "/tmp/unsafe"}),
            ForbiddenRunner(),
            now=lambda: FIXED_NOW,
        )


def test_next_r3_release_requires_postterminal_admission(tmp_path: Path) -> None:
    root, pins = _build_execution_root(tmp_path)
    runner = FakeRunner(sbatch_ids=["8000", "8001", "8002", "8003"])
    instance = controller.FemV2Controller(
        _config(root, pins), runner, now=lambda: FIXED_NOW
    )
    instance.tick()
    runner.accounting = {
        "8000": _source_accounting(
            "8000", 198, memory="160G", allocated_cpu=41, time_limit="03:00:00"
        ),
        "8001": _finalizer_accounting("8001"),
        "8002": _source_accounting(
            "8002", 400, memory="48G", allocated_cpu=13, time_limit="02:00:00"
        ),
        "8003": _finalizer_accounting("8003"),
    }
    instance.tick()
    with pytest.raises(controller.ControllerError, match="postterminal admission"):
        instance.tick(release_r3_through=1)
