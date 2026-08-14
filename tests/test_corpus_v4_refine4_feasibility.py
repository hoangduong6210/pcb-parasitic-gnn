"""Contracts for the bounded refine-4 FEM feasibility probe."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
sys.path.insert(0, str(ROOT / "code/core"))
sys.path.insert(0, str(ROOT / "code/data"))
sys.path.insert(0, str(ROOT / "code/solvers"))

from experiments_corpus_v4_refine4_feasibility import (  # noqa: E402
    evaluate_gates,
    file_sha256,
    validate_computational_context,
    validate_prior_evidence,
    validate_stage_a,
)
from fem_cps_bounded_worker import enforce_resource_limits  # noqa: E402


def test_validate_only_predeclares_bounded_probe() -> None:
    script = (
        ROOT
        / "code/experiments/proofs/experiments_corpus_v4_refine4_feasibility.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["setting"] == {"refine": 4, "pad_mm": 16.0, "solver": "amg_cg"}
    assert set(payload["layouts"]) == {"149", "407"}
    assert payload["limits"]["worker_peak_rss_gib_max"] == 120.0
    assert payload["limits"]["relative_residual_max"] == 1e-9


def test_resource_gate_fails_closed() -> None:
    valid = {
        "success": True,
        "mesh_nodes": 9_000_000,
        "mesh_tetrahedra": 55_000_000,
        "operator_complexity": 1.15,
        "iterations": 30,
        "relative_residual": 1e-10,
        "wall_ms": 3_000_000.0,
        "stages": [{"max_rss_kb": 90 * 1048576}],
    }
    assert evaluate_gates(valid)["pass"]
    for key, value in (
        ("mesh_nodes", 10_000_001),
        ("mesh_tetrahedra", 65_000_001),
        ("operator_complexity", 1.26),
        ("iterations", 101),
        ("relative_residual", float("nan")),
        ("wall_ms", 7_200_001.0),
    ):
        rejected = {**valid, key: value}
        assert not evaluate_gates(rejected)["pass"]
    high_rss = {**valid, "stages": [{"max_rss_kb": 121 * 1048576}]}
    assert not evaluate_gates(high_rss)["pass"]


def test_bounded_worker_aborts_at_first_observable_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCB_GNN_MAX_MESH_NODES", "100")
    with pytest.raises(RuntimeError, match="n_nodes=101"):
        enforce_resource_limits({"n_nodes": 101}, max_rss_kb=1)
    monkeypatch.delenv("PCB_GNN_MAX_MESH_NODES")
    monkeypatch.setenv("PCB_GNN_MAX_OPERATOR_COMPLEXITY", "1.25")
    with pytest.raises(RuntimeError, match="operator_complexity"):
        enforce_resource_limits({"operator_complexity": 1.26}, max_rss_kb=1)


def test_prior_rejection_artifact_is_pinned() -> None:
    final = (
        ROOT
        / "results/corpus_v4/convergence_preflight/final/job_6833716"
        / "results_corpus_v4_convergence_preflight.json"
    )
    _, task, task_path = validate_prior_evidence(final, 149)
    assert task["selection"]["layout_id"] == 149
    assert task_path.name == "task_03.json"
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        validate_prior_evidence(ROOT / "README.md", 149)


def test_computational_context_matches_pinned_refine3() -> None:
    final = (
        ROOT
        / "results/corpus_v4/convergence_preflight/final/job_6833716"
        / "results_corpus_v4_convergence_preflight.json"
    )
    _, task, _ = validate_prior_evidence(final, 149)
    prior = task["provenance"]
    current_hashes = dict(prior["file_sha256"])
    current_paths = {
        "requirements-proof.txt": ROOT / "requirements-proof.txt",
        "code/experiments/proofs/experiments_corpus_v4_convergence_preflight.py": (
            ROOT / "code/experiments/proofs/experiments_corpus_v4_convergence_preflight.py"
        ),
        "code/data/v3_dataset.py": ROOT / "code/data/v3_dataset.py",
        "code/core/geometry_contract.py": ROOT / "code/core/geometry_contract.py",
        "code/solvers/fem_capacitance_3d.py": (
            ROOT / "code/solvers/fem_capacitance_3d.py"
        ),
        "code/solvers/fem_cps_diagnostic_worker.py": (
            ROOT / "code/solvers/fem_cps_diagnostic_worker.py"
        ),
    }
    current_hashes.update(
        {name: file_sha256(path) for name, path in current_paths.items()}
    )
    validate_computational_context(
        task,
        current_hashes,
        dict(prior["package_versions"]),
        dict(prior["thread_environment"]),
        prior["python"],
    )
    changed = dict(prior["file_sha256"])
    changed["code/solvers/fem_capacitance_3d.py"] = "wrong"
    with pytest.raises(ValueError, match="computational source differs"):
        validate_computational_context(
            task,
            changed,
            dict(prior["package_versions"]),
            dict(prior["thread_environment"]),
            prior["python"],
        )


def test_layout_407_requires_passing_layout_149_artifact(tmp_path: Path) -> None:
    sources = {
        "code/jobs/submit_corpus_v4_refine4_feasibility.sh": "batch-sha"
    }
    packages = {"pyamg": "5.3.0"}
    threads = {"PCB_GNN_GMSH_THREADS": "25"}
    setting = {
        "success": True,
        "mesh_nodes": 9_000_000,
        "mesh_tetrahedra": 55_000_000,
        "operator_complexity": 1.15,
        "iterations": 30,
        "relative_residual": 1e-10,
        "wall_ms": 3_000_000.0,
        "stages": [{"max_rss_kb": 90 * 1048576}],
    }
    gate = evaluate_gates(setting)
    path = tmp_path / "layout_0149.json"
    path.write_text(
        json.dumps(
            {
                "schema": "pcb-gnn.corpus-v4-refine4-feasibility.v1",
                "selection": {
                    "layout_id": 149,
                    "geometry_sha256": "0e2aef8a6ec688d3b271569091cd9a3d8ad786a1bc5f54bb3456ec292eda96b4",
                },
                "feasibility_pass": True,
                "resource_gate": gate,
                "refine4_pad16": setting,
                "scientific_acceptance_evaluated": False,
                "contraction_is_non_gating": True,
                "provenance": {
                    "source_stable": True,
                    "git_head": "a" * 40,
                    "final_git_head": "a" * 40,
                    "file_sha256": sources,
                    "final_file_sha256": sources,
                    "git_dirty_paths": [],
                    "final_git_dirty_paths": [],
                    "final_untracked_code": [],
                    "executed_batch_script": {"sha256": "batch-sha"},
                    "prior_final": {
                        "sha256": "d38b0f1f3b22d3dd2580a334f34e001aedae72707e1b298f1600d8cb68d4785b"
                    },
                    "prior_task": {
                        "sha256": "e82a1f0a7df7b4728cec9dbe7e3d06003779f32969db7fa87fcfdb64cdee0cfa"
                    },
                    "python": "3.9.21",
                    "package_versions": packages,
                    "thread_environment": threads,
                },
            }
        )
    )
    evidence = validate_stage_a(
        path, file_sha256(path), sources, packages, threads, "3.9.21", "a" * 40
    )
    assert evidence["sha256"] == file_sha256(path)
    failed = json.loads(path.read_text())
    failed["feasibility_pass"] = False
    path.write_text(json.dumps(failed))
    with pytest.raises(ValueError, match="did not pass"):
        validate_stage_a(
            path,
            file_sha256(path),
            sources,
            packages,
            threads,
            "3.9.21",
            "a" * 40,
        )


def test_slurm_probe_has_resource_headroom_and_no_local_fallback() -> None:
    submit = (ROOT / "code/jobs/submit_corpus_v4_refine4_feasibility.sh").read_text()
    assert "#SBATCH --mem=160G" in submit
    assert "#SBATCH --cpus-per-task=25" in submit
    assert "#SBATCH --time=03:00:00" in submit
    assert "--timeout-s 7200" in submit
    assert "PCB_GNN_EXECUTED_BATCH_SCRIPT" in submit
    assert "PCB_GNN_REFINE4_LAYOUT_ID" in submit
    assert "PCB_GNN_REFINE4_STAGE_A_149" in submit
    assert "PCB_GNN_REFINE4_STAGE_A_149_SHA256" in submit
    worker = (ROOT / "code/solvers/fem_cps_bounded_worker.py").read_text()
    assert "solver_rtol=1e-10" in worker
    assert "solver_maxiter=500" in worker
