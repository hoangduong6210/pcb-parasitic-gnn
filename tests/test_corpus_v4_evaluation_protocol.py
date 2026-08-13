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
    final = validate(
        "finalize_corpus_v4_latency.py", "--source-array-job-id", "validate"
    )
    assert task == {
        "schema": "pcb-gnn.corpus-v4-paired-latency-task.v1",
        "status": "validation-ok",
        "array_tasks": 100,
    }
    assert final["schema"] == "pcb-gnn.corpus-v4-paired-latency-final.v1"
    worker = (PROOFS / "experiments_corpus_v4_latency_task.py").read_text()
    submit = (ROOT / "code/jobs/submit_corpus_v4_latency.sh").read_text()
    assert "FEM_REFINE = 2" in worker
    assert "DOMAIN_PAD_MM = 12.0" in worker
    assert "#SBATCH --array=0-99%50" in submit
    assert "--fem-timeout-s 3600" in submit


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
