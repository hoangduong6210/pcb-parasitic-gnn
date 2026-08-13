"""Contracts for the corpus-v4 high-resolution FEM convergence gate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"


def test_preflight_settings_and_finalizer_gate_are_predeclared() -> None:
    task = subprocess.run(
        [sys.executable, str(PROOFS / "experiments_corpus_v4_convergence_preflight.py"),
         "--validate-only"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    payload = json.loads(task.stdout)
    assert payload["n_tasks"] == 9
    assert payload["settings"] == [[2, 12.0], [2, 16.0], [3, 12.0], [3, 16.0]]
    finalizer = (
        PROOFS / "finalize_corpus_v4_convergence_preflight.py"
    ).read_text()
    assert 'default=2.0' in finalizer
    assert 'default=5.0' in finalizer
    assert '"gate_pass": gate_pass' in finalizer
    assert "production Cps setting rejected" in finalizer


def test_preflight_jobs_are_slurm_arrays_with_no_local_fallback() -> None:
    submit = (ROOT / "code/jobs/submit_corpus_v4_convergence_preflight.sh").read_text()
    finalize = (
        ROOT / "code/jobs/submit_finalize_corpus_v4_convergence_preflight.sh"
    ).read_text()
    assert "#SBATCH --array=0-8%9" in submit
    assert "#SBATCH --mem=96G" in submit
    assert "--timeout-s 7200" in submit
    assert "PCB_GNN_V4_CONVERGENCE_ARRAY_JOB_ID" in finalize
