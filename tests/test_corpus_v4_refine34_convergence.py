"""Contracts for the frozen nine-layout refine-3/refine-4 gate."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"
sys.path.insert(0, str(PROOFS))
sys.path.insert(0, str(ROOT / "code/core"))
sys.path.insert(0, str(ROOT / "code/data"))
sys.path.insert(0, str(ROOT / "code/solvers"))

import experiments_corpus_v4_refine34_convergence as experiment  # noqa: E402
import finalize_corpus_v4_refine34_convergence as finalizer  # noqa: E402


def test_protocol_is_frozen_before_submission() -> None:
    completed = subprocess.run(
        [sys.executable, str(PROOFS / "experiments_corpus_v4_refine34_convergence.py"),
         "--validate-only"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["n_tasks"] == 9
    assert payload["settings"] == [[3, 12.0], [3, 16.0], [4, 16.0]]
    assert payload["median_tolerance_pct"] == 2.0
    assert payload["max_tolerance_pct"] == 5.0
    assert len(payload["layouts"]) == 9
    assert len({row[1] for row in payload["layouts"]}) == 9
    assert payload["layouts"] == [list(row) for row in experiment.LAYOUTS]
    assert {
        "code/core/runtime_paths.py",
        "code/core/planar_to_graph.py",
        "code/core/pcb_graph.py",
        "code/core/trace_peec.py",
    }.issubset(experiment.SOURCE_NAMES)


def test_jobs_are_slurm_only_and_resource_bounded() -> None:
    submit = (ROOT / "code/jobs/submit_corpus_v4_refine34_convergence.sh").read_text()
    finalize = (
        ROOT / "code/jobs/submit_finalize_corpus_v4_refine34_convergence.sh"
    ).read_text()
    assert "#SBATCH --array=0-8%2" in submit
    assert "#SBATCH --cpus-per-task=25" in submit
    assert "#SBATCH --mem=160G" in submit
    assert "#SBATCH --time=07:00:00" in submit
    assert "--timeout-s 7200" in submit
    assert "PCB_GNN_MAX_RSS_KB=125829120" in submit
    assert "PCB_GNN_EXECUTED_BATCH_SCRIPT" in submit
    assert "PCB_GNN_V4_REFINE34_ARRAY_JOB_ID" in finalize
    assert "PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT" in finalize


def _valid_tasks() -> list[dict]:
    tasks = []
    source = {name: f"source-{index}" for index, name in enumerate(experiment.SOURCE_NAMES)}
    source["code/jobs/submit_corpus_v4_refine34_convergence.sh"] = "batch-sha"
    for task_id, (layout_id, geometry_sha) in enumerate(experiment.LAYOUTS):
        settings = []
        for refine, pad_mm in experiment.SETTINGS:
            setting = {
                "refine": refine,
                "pad_mm": pad_mm,
                "success": True,
                "linear_solver": "pyamg_smoothed_aggregation_cg",
                "maxiter": 500,
                "rtol": 1e-10,
                "relative_residual": 1e-10,
                "cps_pf": 4.0,
                "input_system_sha256": "b" * 64,
                "system_sha256": "b" * 64,
                "solver_info": 0,
                "telemetry_parse_errors": [],
                "mesh_nodes": 9_000_000,
                "mesh_tetrahedra": 55_000_000,
                "operator_complexity": 1.1,
                "iterations": 30,
                "wall_ms": 3_000_000.0,
                "stages": [{"max_rss_kb": 90 * 1048576}],
            }
            setting["resource_gate"] = experiment.evaluate_gates(setting)
            settings.append(setting)
        tasks.append({
            "schema": experiment.SCHEMA,
            "provenance": {
                "slurm_array_job_id": "123",
                "slurm_array_task_id": task_id,
                "git_head": "c" * 40,
                "final_git_head": "c" * 40,
                "git_dirty_paths": [],
                "final_git_dirty_paths": [],
                "final_untracked_code": [],
                "source_stable": True,
                "file_sha256": source,
                "final_file_sha256": source,
                "executed_batch_script": {"sha256": "batch-sha"},
                "corpus_artifacts_sha256": experiment.EXPECTED_CORPUS_SHA256,
                "python": "3.9.21",
                "platform": "Linux-test",
                "package_versions": {
                    name: "test" for name in finalizer.PACKAGE_NAMES
                },
                "thread_environment": {
                    name: "1" for name in experiment.THREAD_NAMES
                },
                "prior_final": {
                    "sha256": experiment.PRIOR_FINAL_SHA256,
                    "source_array_job_id": experiment.PRIOR_ARRAY_JOB_ID,
                    "task_artifacts_sha256": experiment.PRIOR_TASK_SHA256,
                },
                "refine4_feasibility": {
                    str(layout_id): {
                        "sha256": experiment.FEASIBILITY[layout_id]["sha256"],
                        "slurm_job_id": experiment.FEASIBILITY[layout_id]["slurm_job_id"],
                    }
                    for layout_id in (149, 407)
                },
            },
            "selection": {
                "layout_id": layout_id,
                "geometry_sha256": geometry_sha,
            },
            "settings": settings,
            "task_pass": True,
        })
    return tasks


def test_finalizer_fails_closed_on_partial_mixed_or_invalid_tasks() -> None:
    tasks = _valid_tasks()
    finalizer.validate_task_set(tasks, "123", "c" * 40)

    partial = copy.deepcopy(tasks)
    partial[0]["settings"].pop()
    with pytest.raises(ValueError, match="settings mismatch"):
        finalizer.validate_task_set(partial, "123", "c" * 40)

    wrong_geometry = copy.deepcopy(tasks)
    wrong_geometry[1]["selection"]["geometry_sha256"] = "wrong"
    with pytest.raises(ValueError, match="geometry mismatch"):
        finalizer.validate_task_set(wrong_geometry, "123", "c" * 40)

    high_residual = copy.deepcopy(tasks)
    high_residual[2]["settings"][2]["relative_residual"] = 2e-9
    with pytest.raises(ValueError, match="invalid FEM setting"):
        finalizer.validate_task_set(high_residual, "123", "c" * 40)

    forged_gate = copy.deepcopy(tasks)
    forged_gate[2]["settings"][2]["mesh_nodes"] = 10_000_001
    with pytest.raises(ValueError, match="invalid FEM setting"):
        finalizer.validate_task_set(forged_gate, "123", "c" * 40)

    mixed_source = copy.deepcopy(tasks)
    mixed_source[3]["provenance"]["file_sha256"] = dict(
        mixed_source[3]["provenance"]["file_sha256"]
    )
    changed_name = experiment.SOURCE_NAMES[0]
    mixed_source[3]["provenance"]["file_sha256"][changed_name] = "changed"
    mixed_source[3]["provenance"]["final_file_sha256"] = dict(
        mixed_source[3]["provenance"]["file_sha256"]
    )
    with pytest.raises(ValueError, match="mixed source"):
        finalizer.validate_task_set(mixed_source, "123", "c" * 40)

    truncated_source = copy.deepcopy(tasks)
    truncated_source[0]["provenance"]["file_sha256"].pop(next(iter(experiment.SOURCE_NAMES)))
    with pytest.raises(ValueError, match="closure is incomplete"):
        finalizer.validate_task_set(truncated_source, "123", "c" * 40)

    changed_final_source = copy.deepcopy(tasks)
    changed_final_source[0]["provenance"]["final_file_sha256"] = {}
    with pytest.raises(ValueError, match="closure is incomplete"):
        finalizer.validate_task_set(changed_final_source, "123", "c" * 40)

    wrong_evidence = copy.deepcopy(tasks)
    wrong_evidence[0]["provenance"]["refine4_feasibility"]["149"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="feasibility evidence mismatch"):
        finalizer.validate_task_set(wrong_evidence, "123", "c" * 40)


def test_task_directory_rejects_missing_and_extra_artifacts(tmp_path: Path) -> None:
    expected = [tmp_path / f"task_{task_id:02d}.json" for task_id in range(9)]
    for path in expected:
        path.write_text("{}")
    assert finalizer.task_artifact_paths(tmp_path) == expected
    extra = tmp_path / "task_09.json"
    extra.write_text("{}")
    with pytest.raises(ValueError, match="contains extras"):
        finalizer.task_artifact_paths(tmp_path)
    extra.unlink()
    expected[0].unlink()
    with pytest.raises(ValueError, match="incomplete"):
        finalizer.task_artifact_paths(tmp_path)


def test_delta_uses_right_hand_reference() -> None:
    tasks = _valid_tasks()
    for task in tasks:
        task["settings"][0]["cps_pf"] = 9.0
        task["settings"][1]["cps_pf"] = 10.0
    result = finalizer.delta(tasks, (3, 12.0), (3, 16.0))
    assert result["median_relative_difference_pct"] == pytest.approx(10.0)
    assert result["max_relative_difference_pct"] == pytest.approx(10.0)


def test_tolerances_cannot_be_changed() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(PROOFS / "finalize_corpus_v4_refine34_convergence.py"),
            "--source-array-job-id", "0",
            "--median-tolerance-pct", "3.0",
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode != 0
    assert "tolerances are fixed" in completed.stderr


def test_canonical_feasibility_artifacts_are_cryptographically_bound() -> None:
    prior = (
        ROOT
        / "results/corpus_v4/convergence_preflight/final/job_6833716"
        / "results_corpus_v4_convergence_preflight.json"
    )
    stage_a = ROOT / "results/corpus_v4/refine4_feasibility/jobs/job_6834616/layout_0149.json"
    stage_b = ROOT / "results/corpus_v4/refine4_feasibility/jobs/job_6837051/layout_0407.json"
    source_hashes = {
        name: experiment.file_sha256(ROOT / name)
        for name in experiment.FEASIBILITY_COMPARABLE_SOURCES
    }
    stage_a_payload = json.loads(stage_a.read_text())
    environment = {
        "python": stage_a_payload["provenance"]["python"],
        "package_versions": stage_a_payload["provenance"]["package_versions"],
        "thread_environment": stage_a_payload["provenance"]["thread_environment"],
    }
    evidence = experiment.validate_prior_and_feasibility(
        prior, {149: stage_a, 407: stage_b}, source_hashes, environment
    )
    assert (
        evidence["refine4_feasibility"]["149"]["sha256"]
        == experiment.FEASIBILITY[149]["sha256"]
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        experiment.validate_prior_and_feasibility(
            ROOT / "README.md", {149: stage_a, 407: stage_b}, source_hashes, environment
        )
