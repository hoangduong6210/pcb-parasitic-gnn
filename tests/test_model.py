from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import torch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code" / "core"))
sys.path.insert(0, str(REPO_ROOT / "code" / "models" / "gnn"))

from gnn_baseline import PCBParasiticGNN, collate  # noqa: E402
from planar_to_graph import build_graph_from_planar_layout  # noqa: E402
from test_graph import sample_layout  # noqa: E402


class ModelSmokeTests(unittest.TestCase):
    def test_forward_shape_and_node_permutation_invariance(self) -> None:
        torch.manual_seed(7)
        graph = build_graph_from_planar_layout(sample_layout())
        node_feat, edge_feat, edge_index = graph.to_feature_matrices()
        target = np.zeros(4, dtype=np.float32)

        original = {
            "node_feat": node_feat,
            "edge_feat": edge_feat,
            "edge_index": edge_index,
            "edge_dim": 7,
            "y": target,
        }

        permutation = np.array([1, 0])
        inverse = np.empty_like(permutation)
        inverse[permutation] = np.arange(len(permutation))
        permuted = {
            "node_feat": node_feat[permutation],
            "edge_feat": edge_feat,
            "edge_index": inverse[edge_index],
            "edge_dim": 7,
            "y": target,
        }

        model = PCBParasiticGNN(hidden=16, n_layers=2)
        model.eval()
        with torch.no_grad():
            first = model(collate([original]))
            second = model(collate([permuted]))

        self.assertEqual(tuple(first.shape), (1, 4))
        torch.testing.assert_close(first, second, rtol=1e-5, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
