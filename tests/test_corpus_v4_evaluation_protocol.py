"""Contracts for the corpus-v4 evaluation and paired-latency pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"


def validate(script: str, *arguments: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(PROOFS / script), *arguments, "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def test_v4_evaluator_schemas_are_explicit() -> None:
    assert validate(
        "experiments_corpus_v3_accuracy.py", "--series", "corpus_v4"
    )["schema"] == "pcb-gnn.corpus-v4-accuracy-task.v1"
    assert validate(
        "finalize_corpus_v3_accuracy.py", "--source-array-job-id", "validate",
        "--series", "corpus_v4",
    )["schema"] == "pcb-gnn.corpus-v4-accuracy-final.v1"
    assert validate(
        "experiments_corpus_v3_strict_e3.py", "--series", "corpus_v4"
    )["schema"] == "pcb-gnn.corpus-v4-strict-e3-task.v1"
    assert validate(
        "finalize_corpus_v3_strict_e3.py", "--source-array-job-id", "validate",
        "--series", "corpus_v4",
    )["schema"] == "pcb-gnn.corpus-v4-strict-e3-final.v1"
    assert validate(
        "experiments_corpus_v3_trees.py", "--series", "corpus_v4"
    )["schema"] == "pcb-gnn.corpus-v4-trees-task.v1"
    assert validate(
        "finalize_corpus_v3_trees.py", "--source-array-job-id", "validate",
        "--series", "corpus_v4",
    )["schema"] == "pcb-gnn.corpus-v4-trees-final.v1"


def test_series_parameter_preserves_archival_v3_schemas() -> None:
    assert validate(
        "experiments_corpus_v3_accuracy.py"
    )["schema"] == "pcb-gnn.corpus-v3-accuracy-task.v1"
    assert validate(
        "experiments_corpus_v3_trees.py"
    )["schema"] == "pcb-gnn.corpus-v3-trees-task.v1"


def test_v4_latency_is_paired_array_at_reference_setting() -> None:
    task = validate("experiments_corpus_v4_latency_task.py")
    final = validate("finalize_corpus_v4_latency.py")
    assert task["schema"] == "pcb-gnn.corpus-v4-paired-latency-task.v2"
    assert task["status"] == "validation-ok"
    assert task["array_tasks"] == 306
    assert task["fem_fidelity_id"] == "cps_fem_r3_p16"
    assert task["timing_boundary"] == "in-memory-raw-json-record-to-four-output"
    assert task["warmups"] == 50
    assert task["timed_repetitions"] == 200
    assert final["schema"] == "pcb-gnn.corpus-v4-paired-latency-final.v2"
    assert final["bootstrap_cluster"] == "family"
    assert final["bootstrap_resamples"] == 10_000
    protocol = json.loads(
        (ROOT / "protocols/corpus_v4_latency_v1.json").read_text(encoding="utf-8")
    )
    assert protocol["solver_workflow"]["capacitance"] == {
        "fidelity_id": "cps_fem_r3_p16",
        "linear_solver": "pyamg_smoothed_aggregation_cg",
        "pad_mm": 16.0,
        "refine": 3,
        "target": "Cps_pF",
        "timeout_s": 1800,
    }
    assert protocol["gnn_timing"]["measurement_blocks"] == [
        "100 repetitions before the solver workflow",
        "100 repetitions after the solver workflow",
    ]
    submit = (ROOT / "code/jobs/submit_corpus_v4_latency.sh").read_text()
    assert "#SBATCH --array=0-305%8" in submit
    assert "#SBATCH --cpus-per-task=25" in submit
    assert "#SBATCH --mem=48G" in submit
    assert "#SBATCH --time=02:00:00" in submit


def test_v4_analytical_audit_has_no_login_node_fallback() -> None:
    result = validate("experiments_corpus_v4_analytical_audit.py")
    assert result["schema"] == "pcb-gnn.corpus-v4-analytical-audit.v1"
    script = (PROOFS / "experiments_corpus_v4_analytical_audit.py").read_text()
    assert "SLURM_JOB_ID" in script
    assert "compute_reference_labels_allpairs" in script
    assert "median_relative_error_pct" in script


def test_v4_jobs_never_relabel_outputs_as_v3() -> None:
    jobs = (
        "submit_corpus_v4_accuracy.sh",
        "submit_corpus_v4_strict_e3.sh",
        "submit_corpus_v4_trees.sh",
        "submit_corpus_v4_cross_solver.sh",
    )
    for name in jobs:
        text = (ROOT / "code/jobs" / name).read_text()
        assert "--series corpus_v4" in text
        assert "PCB_GNN_V4_" in text


def test_legacy_fem_worker_accepts_explicit_domain_padding() -> None:
    worker = (ROOT / "code/solvers/fem_cps_worker.py").read_text()
    assert "pad_mm = float(sys.argv[3])" in worker
    assert "pad_mm=pad_mm" in worker
