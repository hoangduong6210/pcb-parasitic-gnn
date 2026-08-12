"""Lightweight contract tests for the strict-EGNN ablation (no solver/training)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
for directory in (CODE / "experiments" / "proofs", CODE / "models" / "gnn", CODE / "core", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from experiments_strict_egnn_ablation import (  # noqa: E402
    InvariantScalarMPNN,
    StrictScalarEGNN,
    SymmetryPreservingNorm,
    count_params,
    matched_baseline_hidden,
)
from gnn_baseline import collate  # noqa: E402


def synthetic_sample() -> dict:
    node_feat = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.4, 10.0, 0.035, 7.0, 4.1, 0.0],
            [1.0, 0.2, 0.5, 0.5, 9.0, 0.035, 7.0, 4.1, 1.0],
            [0.3, 1.4, 0.7, 0.6, 8.0, 0.035, 7.0, 4.1, 1.0],
        ],
        dtype=np.float32,
    )
    edge_index = np.asarray(
        [[0, 1, 1, 2, 2, 0], [1, 0, 2, 1, 0, 2]], dtype=np.int64
    )
    relative = node_feat[edge_index[0], :3] - node_feat[edge_index[1], :3]
    distance = np.linalg.norm(relative, axis=1, keepdims=True)
    overlap = np.full((6, 1), 0.25, dtype=np.float32)
    raw_vector = relative.astype(np.float32)
    flags = np.asarray(
        [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0], [1.0, 1.0], [1.0, 1.0]],
        dtype=np.float32,
    )
    return {
        "layout_id": "synthetic",
        "node_feat": node_feat,
        "edge_feat": np.concatenate([distance, overlap, raw_vector, flags], axis=1),
        "edge_index": edge_index,
        "edge_dim": 7,
        "y": np.asarray([1.0, 2.0, 3.0, 0.5], dtype=np.float32),
    }


def transformed_work() -> tuple[dict, dict, np.ndarray, np.ndarray]:
    raw = synthetic_sample()
    normalizer = SymmetryPreservingNorm([raw], [0])
    base = normalizer.transform(raw)
    orthogonal = np.asarray(
        [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]],
        dtype=np.float32,
    )
    translation = np.asarray([0.7, -1.3, 2.1], dtype=np.float32)
    changed = {key: value for key, value in base.items()}
    nodes = base["node_feat"].copy()
    nodes[:, :3] = nodes[:, :3] @ orthogonal.T + translation
    changed["node_feat"] = nodes
    return base, changed, orthogonal, translation


def test_strict_egnn_is_e3_equivariant() -> None:
    torch.manual_seed(7)
    model = StrictScalarEGNN(hidden=24).eval()
    base, changed, orthogonal, translation = transformed_work()
    with torch.no_grad():
        base_output, base_hidden, base_coordinates = model.forward_states(collate([base]))
        output, hidden, coordinates = model.forward_states(collate([changed]))
    expected_coordinates = base_coordinates @ torch.as_tensor(orthogonal).T
    expected_coordinates = expected_coordinates + torch.as_tensor(translation)
    torch.testing.assert_close(output, base_output, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(hidden, base_hidden, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(coordinates, expected_coordinates, rtol=2e-5, atol=2e-6)


def test_invariant_baseline_is_e3_invariant_and_does_not_move_coordinates() -> None:
    torch.manual_seed(11)
    model = InvariantScalarMPNN(hidden=24).eval()
    base, changed, _, _ = transformed_work()
    with torch.no_grad():
        base_output, base_hidden, base_coordinates = model.forward_states(collate([base]))
        output, hidden, coordinates = model.forward_states(collate([changed]))
    torch.testing.assert_close(output, base_output, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(hidden, base_hidden, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(base_coordinates, torch.as_tensor(base["node_feat"][:, :3]))
    torch.testing.assert_close(coordinates, torch.as_tensor(changed["node_feat"][:, :3]))


def test_normalizer_has_one_isotropic_coordinate_scale_and_three_edge_metadata() -> None:
    raw = synthetic_sample()
    normalizer = SymmetryPreservingNorm([raw], [0])
    work = normalizer.transform(raw)
    assert isinstance(normalizer.coordinate_scale, float)
    assert work["edge_feat"].shape[1] == 3
    assert work["edge_dim"] == 3


def test_matched_baseline_budget_is_within_two_percent() -> None:
    baseline_hidden, details = matched_baseline_hidden(96)
    baseline = InvariantScalarMPNN(baseline_hidden)
    strict = StrictScalarEGNN(96)
    relative = abs(count_params(baseline) - count_params(strict)) / count_params(strict)
    assert relative < 0.02, details
