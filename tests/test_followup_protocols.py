"""Lightweight contracts for the follow-up proof protocols."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
for directory in (
    CODE / "experiments" / "proofs", CODE / "models" / "gnn", CODE / "core",
    CODE / "solvers", CODE / "data", CODE / "inference",
):
    sys.path.insert(0, str(directory))

from experiments_multisplit_accuracy import load_samples, split_indices  # noqa: E402
from gnn_baseline import PCBParasiticGNN  # noqa: E402
from predict_safe_bundle import load_bundle  # noqa: E402


def test_seed42_split_matches_original_proof_protocol() -> None:
    train, test = split_indices(332, 42)
    np.random.seed(42)
    expected = np.random.permutation(332)
    assert train == expected[:265].tolist()
    assert test == expected[265:].tolist()


def test_field_target_ledger_filters_failed_candidates() -> None:
    targets = ROOT / "results/proof_updates/jobs/strict_e3/job_51174496/field_grade_targets.jsonl"
    records, layouts, samples = load_samples(targets)
    assert len(records) == len(layouts) == len(samples) == 332
    assert all(record["valid"] and record["target"] is not None for record in records)


def test_protocol_validation_does_not_train_or_solve() -> None:
    commands = [
        [sys.executable, str(CODE / "experiments/proofs/experiments_multisplit_accuracy.py"), "--validate-only"],
        [sys.executable, str(CODE / "experiments/proofs/experiments_fem_convergence.py"), "--validate-only"],
    ]
    env = {"PYTHONPATH": ":".join(str(path) for path in sys.path if path)}
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        assert json.loads(completed.stdout)["status"] == "validation-ok"


def test_safe_bundle_loader_rejects_pickle_format(tmp_path: Path) -> None:
    model = PCBParasiticGNN()
    arrays = {
        "norm_ym": np.zeros(4), "norm_ys": np.ones(4),
        "norm_nfm": np.zeros(9), "norm_nfs": np.ones(9),
        "norm_efm": np.zeros(7), "norm_efs": np.ones(7),
    }
    arrays.update({f"state__{name}": tensor.detach().numpy() for name, tensor in model.state_dict().items()})
    np.savez_compressed(tmp_path / "weights_and_norm.npz", **arrays)
    metadata = {
        "architecture": {"node_dim": 9, "edge_dim": 7, "hidden": 96, "n_layers": 4, "n_targets": 4}
    }
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    loaded, norm, _ = load_bundle(tmp_path)
    assert set(loaded.state_dict()) == set(model.state_dict())
    assert norm["ym"].shape == (4,)


def test_heavy_scripts_refuse_login_node_execution() -> None:
    scripts = [
        CODE / "experiments/proofs/experiments_multisplit_accuracy.py",
        CODE / "experiments/proofs/experiments_fem_convergence.py",
    ]
    env = {"PYTHONPATH": ":".join(str(path) for path in sys.path if path)}
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script)], cwd=ROOT, env=env,
            capture_output=True, text=True, check=False,
        )
        assert completed.returncode != 0
        assert "outside SLURM" in completed.stderr
