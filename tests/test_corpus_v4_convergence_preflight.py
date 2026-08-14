"""Contracts for the corpus-v4 high-resolution FEM convergence gate."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"
sys.path.insert(0, str(ROOT / "code"))

from experiments.proofs import experiments_corpus_v4_convergence_preflight as preflight  # noqa: E402
from experiments.proofs.finalize_corpus_v4_convergence_preflight import (  # noqa: E402
    validate_task_set,
)


def test_preflight_settings_and_finalizer_gate_are_predeclared() -> None:
    task = subprocess.run(
        [sys.executable, str(PROOFS / "experiments_corpus_v4_convergence_preflight.py"),
         "--validate-only"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    payload = json.loads(task.stdout)
    assert payload["n_tasks"] == 9
    assert payload["settings"] == [[2, 12.0], [2, 16.0], [3, 12.0], [3, 16.0]]
    assert payload["linear_solver"] == "amg_cg"
    assert payload["solver_rtol"] == 1e-10
    assert payload["residual_tolerance"] == 1e-9
    task_source = (
        PROOFS / "experiments_corpus_v4_convergence_preflight.py"
    ).read_text()
    assert "atomic_write(path, payload)" in task_source
    assert 'result.get("linear_solver") == "pyamg_smoothed_aggregation_cg"' in task_source
    finalizer = (
        PROOFS / "finalize_corpus_v4_convergence_preflight.py"
    ).read_text()
    assert 'default=2.0' in finalizer
    assert 'default=5.0' in finalizer
    assert 'EXPECTED_SOLVER = "pyamg_smoothed_aggregation_cg"' in finalizer
    assert 'RESIDUAL_TOLERANCE = 1e-9' in finalizer
    assert '"gate_pass": gate_pass' in finalizer
    assert "production Cps setting rejected" in finalizer
    changed_tolerance = subprocess.run(
        [
            sys.executable,
            str(PROOFS / "finalize_corpus_v4_convergence_preflight.py"),
            "--source-array-job-id",
            "0",
            "--median-tolerance-pct",
            "3.0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert changed_tolerance.returncode != 0
    assert "tolerances are fixed" in changed_tolerance.stderr


def test_preflight_jobs_are_slurm_arrays_with_no_local_fallback() -> None:
    submit = (ROOT / "code/jobs/submit_corpus_v4_convergence_preflight.sh").read_text()
    finalize = (
        ROOT / "code/jobs/submit_finalize_corpus_v4_convergence_preflight.sh"
    ).read_text()
    assert "#SBATCH --array=0-8%9" in submit
    assert "#SBATCH --mem=96G" in submit
    assert "--timeout-s 18000" in submit
    assert "PCB_GNN_EXECUTED_BATCH_SCRIPT" in submit
    assert "PCB_GNN_GMSH_THREADS" in submit
    assert "OPENBLAS_NUM_THREADS=1" in submit
    assert "PCB_GNN_V4_CONVERGENCE_ARRAY_JOB_ID" in finalize
    assert "PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT" in finalize


def test_setting_gate_fails_closed() -> None:
    valid = {
        "linear_solver": "pyamg_smoothed_aggregation_cg",
        "relative_residual": 1e-10,
        "input_system_sha256": "a" * 64,
    }
    assert preflight.setting_result_passes(valid)
    for mutation in (
        {"linear_solver": "scipy_superlu_direct"},
        {"relative_residual": 1.1e-9},
        {"relative_residual": float("nan")},
        {"input_system_sha256": ""},
    ):
        rejected = {**valid, **mutation}
        assert not preflight.setting_result_passes(rejected)
    assert not preflight.setting_result_passes(None)


def test_failed_setting_is_checkpointed_before_exception(tmp_path: Path) -> None:
    path = tmp_path / "task.json"
    payload = {"settings": []}
    failed = {"refine": 3, "pad_mm": 12.0, "success": False}
    with pytest.raises(RuntimeError, match="inspect task artifact"):
        preflight.checkpoint_setting(path, payload, failed)
    assert json.loads(path.read_text())["settings"] == [failed]


def test_worker_timeout_and_malformed_native_output_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = tmp_path / "worker.py"
    worker.write_text("# mocked worker\n")
    monkeypatch.setattr(preflight, "fem_cps_diagnostic_worker_path", lambda: worker)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="", stderr="")

    monkeypatch.setattr(preflight.subprocess, "run", timeout)
    timed_out = preflight.solve({}, 3, 12.0, 1)
    assert timed_out["timed_out"] is True
    assert timed_out["success"] is False

    malformed = subprocess.CompletedProcess(
        args=[], returncode=-11, stdout='STAGE={"stage":', stderr="native crash"
    )
    monkeypatch.setattr(preflight.subprocess, "run", lambda *args, **kwargs: malformed)
    crashed = preflight.solve({}, 3, 12.0, 1)
    assert crashed["success"] is False
    assert crashed["signal"] == "SIGSEGV"
    assert crashed["telemetry_parse_errors"]
    assert crashed["stderr_tail"] == ["native crash"]


def test_diagnostic_summary_is_cryptographically_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker = ROOT / "code/solvers/fem_cps_diagnostic_worker.py"
    source_hashes = {
        "requirements-proof.txt": preflight.file_sha256(ROOT / "requirements-proof.txt"),
        "code/solvers/fem_capacitance_3d.py": preflight.file_sha256(
            ROOT / "code/solvers/fem_capacitance_3d.py"
        ),
        "code/solvers/fem_cps_diagnostic_worker.py": preflight.file_sha256(worker),
    }
    summary = {
        "schema": preflight.DIAGNOSTIC_SUMMARY_SCHEMA,
        "pass": True,
        "array_job_id": "6832704",
        "task_artifacts_sha256": {"task_00.json": "a", "task_01.json": "b"},
        "task_gates": {
            "0": {
                "pass": True,
                "identical_system": True,
                "cps_relative_difference": 1e-16,
            },
            "1": {"pass": True, "relative_residual": 1e-10},
        },
        "common_provenance": {"file_sha256": dict(source_hashes)},
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="not the trusted artifact"):
        preflight.validate_diagnostic_summary(path, worker)
    monkeypatch.setattr(
        preflight, "EXPECTED_DIAGNOSTIC_SUMMARY_SHA256", preflight.file_sha256(path)
    )
    evidence = preflight.validate_diagnostic_summary(path, worker)
    assert evidence["array_job_id"] == "6832704"
    assert len(evidence["sha256"]) == 64

    summary["array_job_id"] = "wrong-job"
    path.write_text(json.dumps(summary))
    monkeypatch.setattr(
        preflight, "EXPECTED_DIAGNOSTIC_SUMMARY_SHA256", preflight.file_sha256(path)
    )
    with pytest.raises(ValueError, match="untrusted array job"):
        preflight.validate_diagnostic_summary(path, worker)

    summary["array_job_id"] = "6832704"
    summary["common_provenance"]["file_sha256"][
        "code/solvers/fem_capacitance_3d.py"
    ] = "wrong"
    path.write_text(json.dumps(summary))
    monkeypatch.setattr(
        preflight, "EXPECTED_DIAGNOSTIC_SUMMARY_SHA256", preflight.file_sha256(path)
    )
    with pytest.raises(ValueError, match="source mismatch"):
        preflight.validate_diagnostic_summary(path, worker)

    summary["common_provenance"]["file_sha256"] = source_hashes
    summary["task_gates"]["1"]["relative_residual"] = float("nan")
    path.write_text(json.dumps(summary))
    monkeypatch.setattr(
        preflight, "EXPECTED_DIAGNOSTIC_SUMMARY_SHA256", preflight.file_sha256(path)
    )
    with pytest.raises(ValueError, match="scientific gates"):
        preflight.validate_diagnostic_summary(path, worker)


def _valid_task_set() -> list[dict]:
    settings = [
        {
            "refine": refine,
            "pad_mm": pad,
            "success": True,
            "linear_solver": "pyamg_smoothed_aggregation_cg",
            "requested_linear_solver": "amg_cg",
            "relative_residual": 1e-10,
            "input_system_sha256": "a" * 64,
            "cps_pf": 4.0,
        }
        for refine, pad in ((2, 12.0), (2, 16.0), (3, 12.0), (3, 16.0))
    ]
    tasks = []
    for task_id in range(9):
        tasks.append(
            {
                "schema": "pcb-gnn.corpus-v4-convergence-preflight-task.v2",
                "provenance": {
                    "slurm_array_job_id": "123",
                    "slurm_array_task_id": task_id,
                    "git_head": "b" * 40,
                    "git_dirty_paths": [],
                    "source_stable": True,
                    "file_sha256": {
                        "code/jobs/submit_corpus_v4_convergence_preflight.sh": "c"
                    },
                    "executed_batch_script": {"sha256": "c"},
                    "corpus_artifacts_sha256": {"layouts.jsonl": "d"},
                    "python": "3.9.21",
                    "package_versions": {"pyamg": "5.3.0"},
                    "thread_environment": {"OMP_NUM_THREADS": "1"},
                    "native_solver_diagnostic": {"sha256": "e"},
                },
                "selection": {"geometry_sha256": f"geometry-{task_id}"},
                "settings": copy.deepcopy(settings),
                "task_pass": True,
            }
        )
    return tasks


def test_finalizer_rejects_partial_wrong_solver_and_mixed_source_tasks() -> None:
    tasks = _valid_task_set()
    validate_task_set(tasks, "123", "b" * 40)

    partial = copy.deepcopy(tasks)
    partial[0]["settings"].pop()
    with pytest.raises(ValueError, match="settings mismatch"):
        validate_task_set(partial, "123", "b" * 40)

    wrong_solver = copy.deepcopy(tasks)
    wrong_solver[0]["settings"][0]["linear_solver"] = "scipy_superlu_direct"
    with pytest.raises(ValueError, match="invalid AMG-CG"):
        validate_task_set(wrong_solver, "123", "b" * 40)

    high_residual = copy.deepcopy(tasks)
    high_residual[0]["settings"][0]["relative_residual"] = 2e-9
    with pytest.raises(ValueError, match="invalid AMG-CG"):
        validate_task_set(high_residual, "123", "b" * 40)

    nan_residual = copy.deepcopy(tasks)
    nan_residual[0]["settings"][0]["relative_residual"] = float("nan")
    with pytest.raises(ValueError, match="invalid AMG-CG"):
        validate_task_set(nan_residual, "123", "b" * 40)

    mixed_source = copy.deepcopy(tasks)
    mixed_source[0]["provenance"]["file_sha256"]["extra.py"] = "different"
    with pytest.raises(ValueError, match="mixed source"):
        validate_task_set(mixed_source, "123", "b" * 40)

    duplicate_geometry = copy.deepcopy(tasks)
    duplicate_geometry[1]["selection"] = duplicate_geometry[0]["selection"]
    with pytest.raises(ValueError, match="not unique"):
        validate_task_set(duplicate_geometry, "123", "b" * 40)
