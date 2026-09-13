"""Solver-free encoded-graph E(3) coordinate-update ablation.

Scalar metadata and topology are held fixed under the group action. This is
not a claim about rotating a raw layout and rebuilding its axis-aligned graph.
"""
from __future__ import annotations

import hashlib
import random
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch import nn

from gnn_baseline import GraphBatch, _scatter_max, _scatter_mean, _scatter_sum

EDGE_COLUMNS = (1, 5, 6)
ARM_NAMES = ("strict96", "fixed96", "fixed_matched")


def parameter_count(hidden: int, update_coordinates: bool, n_layers: int = 4) -> int:
    """Analytic four-target parameter count; does not consume random state."""
    if hidden < 1 or n_layers < 1:
        raise ValueError("hidden and n_layers must be positive")
    base = (5 + 6 * n_layers) * hidden**2 + (21 + 10 * n_layers) * hidden + 7
    return base + ((n_layers - 1) * (hidden**2 + 2 * hidden + 1) if update_coordinates else 0)


def matched_width(strict_hidden: int = 96, n_layers: int = 4) -> int:
    """Nearest fixed-coordinate parameter budget, lower width breaks ties."""
    target = parameter_count(strict_hidden, True, n_layers)
    return min(range(1, 2 * strict_hidden + 1), key=lambda h: (abs(parameter_count(h, False, n_layers) - target), h))


class DistanceLayer(nn.Module):
    def __init__(self, hidden: int, update_coordinates: bool):
        super().__init__()
        self.msg = nn.Sequential(nn.Linear(2 * hidden + 4, hidden), nn.SiLU(), nn.Linear(hidden, hidden), nn.SiLU())
        self.upd = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.SiLU(), nn.Linear(hidden, hidden))
        self.norm = nn.LayerNorm(hidden)
        self.coord = nn.Sequential(nn.Linear(hidden, hidden), nn.SiLU(), nn.Linear(hidden, 1)) if update_coordinates else None

    def forward(self, h: torch.Tensor, x: torch.Tensor, edge_index: torch.Tensor, e: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        aggregate = torch.zeros_like(h)
        if edge_index.shape[1]:
            src, dst = edge_index
            relative = x[src] - x[dst]
            d2 = relative.square().sum(-1, keepdim=True)
            messages = self.msg(torch.cat((h[src], h[dst], d2, e), dim=-1))
            aggregate = _scatter_mean(messages, dst, h.shape[0])
            if self.coord is not None:
                # vector_norm has a defined zero-vector gradient, unlike sqrt(d2).
                bounded = relative / (torch.linalg.vector_norm(relative, dim=-1, keepdim=True) + 1.0)
                weight = 0.1 * torch.tanh(self.coord(messages))
                x = x + _scatter_mean(bounded * weight, dst, h.shape[0])
        return self.norm(h + self.upd(torch.cat((h, aggregate), dim=-1))), x


class ScalarDistanceModel(nn.Module):
    def __init__(self, hidden: int = 96, update_coordinates: bool = False, n_layers: int = 4):
        super().__init__()
        parameter_count(hidden, update_coordinates, n_layers)
        self.hidden, self.update_coordinates, self.n_layers = hidden, update_coordinates, n_layers
        self.node_enc = nn.Sequential(nn.Linear(6, hidden), nn.SiLU(), nn.Linear(hidden, hidden))
        self.edge_enc = nn.Sequential(nn.Linear(3, hidden), nn.SiLU(), nn.Linear(hidden, 3))
        # The final coordinate branch cannot affect scalar predictions: omit it.
        self.layers = nn.ModuleList(DistanceLayer(hidden, update_coordinates and i < n_layers - 1) for i in range(n_layers))
        self.head = nn.Sequential(nn.Linear(3 * hidden, hidden), nn.SiLU(), nn.Linear(hidden, hidden), nn.SiLU(), nn.Linear(hidden, 4))

    def forward_states(self, batch: GraphBatch) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        x = batch.node_feat[:, :3].clone()
        h = self.node_enc(batch.node_feat[:, 3:])
        edges = self.edge_enc(batch.edge_feat) if batch.edge_feat.shape[0] else batch.edge_feat
        for layer in self.layers:
            h, x = layer(h, x, batch.edge_index, edges)
        total = _scatter_sum(h, batch.batch_index, batch.n_graphs)
        pooled = torch.cat((_scatter_mean(h, batch.batch_index, batch.n_graphs), _scatter_max(h, batch.batch_index, batch.n_graphs), total.sign() * total.abs().log1p()), dim=-1)
        return self.head(pooled), h, x

    def forward(self, batch: GraphBatch) -> torch.Tensor:
        return self.forward_states(batch)[0]


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_arms(seed: int, strict_hidden: int = 96, n_layers: int = 4) -> tuple[dict[str, ScalarDistanceModel], dict[str, Any]]:
    """Seed before construction and explicitly pair all shared-width tensors.

    Factory construction resets global Python, NumPy and Torch RNGs. Training
    must independently seed each arm's batch-order generator.
    """
    models: dict[str, ScalarDistanceModel] = {}
    for name, width, moving in ((ARM_NAMES[0], strict_hidden, True), (ARM_NAMES[1], strict_hidden, False), (ARM_NAMES[2], matched_width(strict_hidden, n_layers), False)):
        _seed(seed)
        models[name] = ScalarDistanceModel(width, moving, n_layers)
    fixed_state = models["fixed96"].state_dict()
    strict_state = models["strict96"].state_dict()
    with torch.no_grad():
        for key, value in fixed_state.items():
            strict_state[key].copy_(value)
    hashes = {key: hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest() for key, value in sorted(fixed_state.items())}
    return models, {"seed": seed, "shared_tensor_sha256": hashes, "paired_arms": ["strict96", "fixed96"], "arms": {name: {"hidden": model.hidden, "parameters": parameter_count(model.hidden, model.update_coordinates, n_layers)} for name, model in models.items()}}


class SymmetryNormalizer:
    """Float64 train-only statistics; all coordinates share one scalar scale."""
    def __init__(self, samples: Mapping[int, Mapping[str, Any]], train_ids: Sequence[int]):
        if not train_ids or len(set(train_ids)) != len(train_ids):
            raise ValueError("training IDs must be nonempty and unique")
        nodes, edges, distances, targets = [], [], [], []
        for index in train_ids:
            sample = samples[index]
            node, edge, ei = self._features(sample)
            target = np.asarray(sample["reference_r3"], dtype=np.float64)
            if target.shape != (4,) or not np.isfinite(target).all() or np.any(target <= 0):
                raise ValueError("training references must be four finite positive targets")
            nodes.append(node[:, 3:])
            targets.append(target)
            if len(edge):
                edges.append(edge[:, EDGE_COLUMNS])
                distances.append(np.sum((node[ei[0], :3] - node[ei[1], :3])**2, axis=1))
        node_values = np.concatenate(nodes)
        edge_values = np.concatenate(edges) if edges else np.zeros((1, 3), dtype=np.float64)
        logged = np.log1p(np.stack(targets))
        self.node_mean, self.node_scale = node_values.mean(0), np.maximum(node_values.std(0), 1e-6)
        self.edge_mean, self.edge_scale = edge_values.mean(0), np.maximum(edge_values.std(0), 1e-6)
        self.target_mean, self.target_scale = logged.mean(0), np.maximum(logged.std(0), 1e-8)
        self.coordinate_scale = max(float(np.sqrt(np.concatenate(distances).mean())), 1e-6) if distances else 1.0
        if any(not np.isfinite(value).all() for value in self.arrays().values()):
            raise ValueError("nonfinite fitted normalization")

    @staticmethod
    def _features(sample: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        node, edge = np.asarray(sample["node_feat"], dtype=np.float64), np.asarray(sample["edge_feat"], dtype=np.float64)
        ei = np.asarray(sample["edge_index"])
        if node.ndim != 2 or node.shape[1] != 9 or not len(node) or edge.ndim != 2 or edge.shape[1] != 7:
            raise ValueError("expected nonempty N by 9 nodes and E by 7 edges")
        if ei.shape != (2, len(edge)) or not np.issubdtype(ei.dtype, np.integer) or (ei.size and (ei.min() < 0 or ei.max() >= len(node))):
            raise ValueError("invalid edge indices")
        if not np.isfinite(node).all() or not np.isfinite(edge).all():
            raise ValueError("nonfinite graph features")
        return node, edge, ei.astype(np.int64)

    def arrays(self) -> dict[str, np.ndarray]:
        return {"norm.node_mean": np.asarray(self.node_mean), "norm.node_scale": np.asarray(self.node_scale), "norm.edge_mean": np.asarray(self.edge_mean), "norm.edge_scale": np.asarray(self.edge_scale), "norm.target_log1p_mean": np.asarray(self.target_mean), "norm.target_log1p_scale": np.asarray(self.target_scale), "norm.coordinate_scale": np.asarray([self.coordinate_scale], dtype=np.float64)}

    def transform(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        node, edge, ei = self._features(sample)
        transformed = {"node_feat": np.concatenate((node[:, :3] / self.coordinate_scale, (node[:, 3:] - self.node_mean) / self.node_scale), axis=1).astype(np.float32), "edge_feat": ((edge[:, EDGE_COLUMNS] - self.edge_mean) / self.edge_scale).astype(np.float32), "edge_index": ei, "edge_dim": 3, "y": np.zeros(4, dtype=np.float32)}
        if "reference_r3" in sample:
            target = np.asarray(sample["reference_r3"], dtype=np.float64)
            if target.shape != (4,) or not np.isfinite(target).all() or np.any(target <= 0):
                raise ValueError("references must be four finite positive targets")
            transformed["y"] = ((np.log1p(target) - self.target_mean) / self.target_scale).astype(np.float32)
        if not np.isfinite(transformed["node_feat"]).all() or not np.isfinite(transformed["edge_feat"]).all():
            raise ValueError("normalization overflow")
        return transformed

    def inverse(self, normalized: np.ndarray) -> np.ndarray:
        return np.expm1(np.asarray(normalized, dtype=np.float64) * self.target_scale + self.target_mean)
