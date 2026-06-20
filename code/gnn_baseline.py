"""
gnn_baseline.py — Geometry-aware message-passing GNN for PCB parasitic extraction.

Topic 13. License-clean (PyTorch BSD). NO torch-geometric dependency: the
batched message passing (concatenated graphs + scatter_add segment aggregation)
is hand-rolled so the research env only needs `torch`.

What this is (honest framing):
  - A real message-passing neural network (MPNN), NOT a Ridge/linear surrogate.
  - Geometry-aware & permutation-invariant: every node/edge feature fed to the
    network is a rotation/translation-INVARIANT scalar (distances, |rel_vec|,
    overlap, dims, layer index). We do not claim full E(3)-EQUIVARIANCE (no
    steerable/vector features); we claim invariance, which is what graph-level
    RLGC regression needs. The equivariant (EGNN/e3nn) upgrade is future work.
  - Predicts a graph-level target vector [Cps, L_pri, L_sec, L_mut] (the same
    quantities the analytical PEEC labeler produces), trained on standardized
    targets and inverted at report time.

Batching scheme (PyG-free):
  A "batch" is several graphs concatenated into one big graph. We track
  `batch_index[node] -> graph id` and offset each graph's edge_index by the
  running node count. Node->node messages use torch.scatter_add (segment sum)
  to the destination node; graph readout uses scatter over batch_index.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Batched-graph container
# ---------------------------------------------------------------------------
@dataclass
class GraphBatch:
    node_feat: torch.Tensor      # [N_total, D_node]
    edge_feat: torch.Tensor      # [E_total, D_edge]
    edge_index: torch.Tensor     # [2, E_total]  (src, dst) into concatenated nodes
    batch_index: torch.Tensor    # [N_total]     graph id per node
    y: torch.Tensor              # [B, D_target]
    n_graphs: int

    def to(self, device):
        return GraphBatch(
            self.node_feat.to(device), self.edge_feat.to(device),
            self.edge_index.to(device), self.batch_index.to(device),
            self.y.to(device), self.n_graphs,
        )


def collate(samples: List[dict], device="cpu") -> GraphBatch:
    """Concatenate a list of {node_feat, edge_feat, edge_index, y} into one batch."""
    nfs, efs, eis, bidx, ys = [], [], [], [], []
    offset = 0
    for gi, s in enumerate(samples):
        nf = torch.as_tensor(s["node_feat"], dtype=torch.float32)
        n = nf.shape[0]
        if n == 0:
            # guarantee at least 1 node so readout is well-defined
            nf = torch.zeros((1, nf.shape[1] if nf.ndim == 2 else 9), dtype=torch.float32)
            n = 1
        ei = torch.as_tensor(s["edge_index"], dtype=torch.long)
        if ei.numel() == 0:
            ei = torch.zeros((2, 0), dtype=torch.long)
        ef = torch.as_tensor(s["edge_feat"], dtype=torch.float32)
        if ef.numel() == 0:
            ef = torch.zeros((0, s.get("edge_dim", 7)), dtype=torch.float32)

        nfs.append(nf)
        efs.append(ef)
        eis.append(ei + offset)
        bidx.append(torch.full((n,), gi, dtype=torch.long))
        ys.append(torch.as_tensor(s["y"], dtype=torch.float32))
        offset += n

    return GraphBatch(
        node_feat=torch.cat(nfs, 0),
        edge_feat=torch.cat(efs, 0) if efs else torch.zeros((0, 7)),
        edge_index=torch.cat(eis, 1) if eis else torch.zeros((2, 0), dtype=torch.long),
        batch_index=torch.cat(bidx, 0),
        y=torch.stack(ys, 0),
        n_graphs=len(samples),
    ).to(device)


def _scatter_mean(src, index, dim_size):
    """Segment mean of src rows grouped by index -> [dim_size, F]."""
    out = torch.zeros((dim_size, src.shape[-1]), dtype=src.dtype, device=src.device)
    out.index_add_(0, index, src)
    cnt = torch.zeros(dim_size, dtype=src.dtype, device=src.device)
    cnt.index_add_(0, index, torch.ones(index.shape[0], dtype=src.dtype, device=src.device))
    cnt = cnt.clamp(min=1.0).unsqueeze(-1)
    return out / cnt


def _scatter_sum(src, index, dim_size):
    out = torch.zeros((dim_size, src.shape[-1]), dtype=src.dtype, device=src.device)
    out.index_add_(0, index, src)
    return out


def _scatter_max(src, index, dim_size):
    init = torch.full((dim_size, src.shape[-1]), -1e30, dtype=src.dtype, device=src.device)
    out = init.index_reduce(0, index, src, reduce="amax", include_self=True)
    # out-of-place reset for empty groups (in-place edit would break autograd)
    out = torch.where(out <= -1e29, torch.zeros_like(out), out)
    return out


# ---------------------------------------------------------------------------
# The MPNN
# ---------------------------------------------------------------------------
class MPNNLayer(nn.Module):
    """One round of edge-conditioned message passing with residual node update."""
    def __init__(self, hidden, edge_dim):
        super().__init__()
        self.msg = nn.Sequential(
            nn.Linear(2 * hidden + edge_dim, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden),
        )
        self.upd = nn.Sequential(
            nn.Linear(2 * hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden),
        )
        self.norm = nn.LayerNorm(hidden)

    def forward(self, h, edge_index, edge_attr):
        if edge_index.shape[1] == 0:
            agg = torch.zeros_like(h)
        else:
            src, dst = edge_index[0], edge_index[1]
            m = self.msg(torch.cat([h[src], h[dst], edge_attr], dim=-1))
            agg = _scatter_mean(m, dst, h.shape[0])
        h = h + self.upd(torch.cat([h, agg], dim=-1))   # residual
        return self.norm(h)


class PCBParasiticGNN(nn.Module):
    def __init__(self, node_dim=9, edge_dim=7, hidden=96, n_layers=4, n_targets=4):
        super().__init__()
        self.node_enc = nn.Sequential(
            nn.Linear(node_dim, hidden), nn.SiLU(), nn.Linear(hidden, hidden),
        )
        self.edge_enc = nn.Sequential(
            nn.Linear(edge_dim, hidden), nn.SiLU(), nn.Linear(hidden, edge_dim),
        )
        self.layers = nn.ModuleList([MPNNLayer(hidden, edge_dim) for _ in range(n_layers)])
        # readout: concat [mean, max, sum-log] pooled node states
        self.head = nn.Sequential(
            nn.Linear(3 * hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, n_targets),
        )

    def forward(self, b: GraphBatch):
        h = self.node_enc(b.node_feat)
        e = self.edge_enc(b.edge_feat) if b.edge_feat.shape[0] else b.edge_feat
        for layer in self.layers:
            h = layer(h, b.edge_index, e)
        g_mean = _scatter_mean(h, b.batch_index, b.n_graphs)
        g_max = _scatter_max(h, b.batch_index, b.n_graphs)
        g_sum = _scatter_sum(h, b.batch_index, b.n_graphs)
        g_sum = torch.sign(g_sum) * torch.log1p(g_sum.abs())   # log-compress extensive sum
        g = torch.cat([g_mean, g_max, g_sum], dim=-1)
        return self.head(g)


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters())
