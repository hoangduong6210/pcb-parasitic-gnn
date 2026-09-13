"""Small structural checks for the SLURM qualification; no fitting or corpus."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("e3_qualification", ROOT / "code/experiments/proofs/qualify_strict_e3_model_v1.py")
QUAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUAL)


def test_qualification_refuses_login_before_any_model_execution(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["qualification", "--expected-source-commit", "unused", "--expected-protocol-sha256", "unused"])
    with pytest.raises(ValueError, match="requires a non-array SLURM job"):
        QUAL.main()


def test_residual_fails_nonfinite_and_shape_mismatch():
    with pytest.raises(ValueError):
        QUAL.residual(np.array([np.nan]), np.array([1.]))
    with pytest.raises(ValueError):
        QUAL.residual(np.ones((1, 1)), np.ones(1))
    assert QUAL.residual(np.array([4.]), np.array([2.])) == 1.


def test_protocol_is_initialized_only_and_inputs_are_synthetic():
    protocol = json.loads((ROOT / QUAL.SOURCES[-1]).read_text())
    assert protocol["seeds"] == [40, 41, 42, 43, 44]
    assert protocol["transforms_per_seed"] == 40
    assert protocol["relative_tolerance"] == 2e-5
    assert protocol["training_may_start"] is False
    assert protocol["claim_eligible"] is False
    records = QUAL.fixtures()
    assert len(records) == 2
    assert records[1]["edge_index"].shape == (2, 0)
    for item in QUAL.SOURCES:
        assert (ROOT / item).is_file()


def test_worker_excludes_training_and_corpus_loaders():
    import ast
    tree = ast.parse((ROOT / QUAL.SOURCES[2]).read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not imported.intersection({"pipeline", "v3_dataset", "fasthenry_ref", "fem_capacitance_3d"})
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls.intersection({"fit", "backward", "step"})
    wrapper = (ROOT / QUAL.SOURCES[3]).read_text()
    assert "/usr/bin/env -i" in wrapper
    assert "--no-requeue" in wrapper
    assert "PYTHONNOUSERSITE=1" in wrapper


def test_committed_receipt_is_initialized_only_and_complete():
    import hashlib
    path = ROOT / "results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "07cd5b4ba54b688c5aac25bb8d07a05b14a7a0d4f57ea1e6b9f1427881c005b3"
    data = json.loads(path.read_text())
    assert data["passed"] is True
    assert data["training_started"] is data["corpus_bytes_opened"] is data["claim_eligible"] is False
    assert len(data["results"]) == 15
    assert {(r["seed"], r["arm"]) for r in data["results"]} == {(s, a) for s in range(40, 45) for a in ("strict96", "fixed96", "fixed_matched")}
    assert data["protocol"]["transforms_per_seed"] == 40
    for row in data["results"]:
        assert row["passed"] is True
        assert all(value <= 2e-5 for value in row["max_relative_residual"].values())
    for name, sha in data["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
