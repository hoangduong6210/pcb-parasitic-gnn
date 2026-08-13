"""Lightweight contracts for full refined-Cps corpus generation."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v4_jobs_are_array_gated_and_refined() -> None:
    submit = (ROOT / "code/jobs/submit_corpus_v4_refined_cps.sh").read_text()
    finalize = (ROOT / "code/jobs/submit_finalize_corpus_v4.sh").read_text()
    assert "#SBATCH --array=0-149%50" in submit
    assert "--chunk-size 10" in submit
    assert "--timeout-s 3600" in submit
    assert "PCB_GNN_V4_REFINEMENT_ARRAY_JOB_ID" in finalize


def test_v4_uses_highest_validated_fem_setting() -> None:
    worker = (
        ROOT / "code/experiments/proofs/experiments_corpus_v4_refined_cps.py"
    ).read_text()
    finalizer = (ROOT / "code/experiments/proofs/finalize_corpus_v4.py").read_text()
    assert "FEM_REFINE = 2" in worker
    assert "DOMAIN_PAD_MM = 12.0" in worker
    assert "EXPECTED_REFINE = 2" in finalizer
    assert "EXPECTED_PAD_MM = 12.0" in finalizer


def test_v4_finalizer_checks_identity_and_content_hashes() -> None:
    finalizer = (ROOT / "code/experiments/proofs/finalize_corpus_v4.py").read_text()
    for contract in (
        "array-task mismatch",
        "task ranges are not exact and contiguous",
        "do not match the requested source corpus",
        "geometry hash mismatch",
        "task_artifacts_sha256",
    ):
        assert contract in finalizer
    worker = (
        ROOT / "code/experiments/proofs/experiments_corpus_v4_refined_cps.py"
    ).read_text()
    assert "requirements-proof.txt" in worker
    assert "package_versions" in worker
