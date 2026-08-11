from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code" / "core"))

from planar_to_graph import build_graph_from_planar_layout  # noqa: E402


def sample_layout() -> dict:
    return {
        "n_layers": 2,
        "eps_r": 4.2,
        "traces": [
            {
                "layer": 0,
                "x0": 0.0,
                "y0": 0.0,
                "length_mm": 20.0,
                "width_mm": 2.0,
                "net": "pri",
            },
            {
                "layer": 1,
                "x0": 1.0,
                "y0": 0.5,
                "length_mm": 18.0,
                "width_mm": 2.0,
                "net": "sec",
            },
        ],
    }


class GraphConstructionTests(unittest.TestCase):
    def test_layout_builds_bidirectional_graph(self) -> None:
        graph = build_graph_from_planar_layout(sample_layout())
        node_feat, edge_feat, edge_index = graph.to_feature_matrices()

        self.assertEqual(node_feat.shape, (2, 9))
        self.assertEqual(edge_feat.shape, (2, 7))
        self.assertEqual(edge_index.shape, (2, 2))
        self.assertTrue(np.isfinite(node_feat).all())
        self.assertTrue(np.isfinite(edge_feat).all())


if __name__ == "__main__":
    unittest.main()
