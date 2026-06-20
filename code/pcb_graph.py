"""
PCB Graph representation for GNN parasitic extraction (Topic 13).

Nodes = trace segments, plane patches, vias.
Edges = inductive/capacitive couplings (geometric proximity + electrical).

Designed to be E(3)-ready: positions are explicit 3D, relative vectors will be
used in equivariant layers.

This module is pure (numpy + dataclasses) so it can be used for label generation
without torch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np


@dataclass
class Node:
    """A mesh element on the PCB: trace rect, plane fragment, or via."""
    id: int
    kind: str                  # "trace", "plane", "via"
    layer: int                 # 0-based stackup index (0 = bottom)
    center_mm: np.ndarray      # (x, y, z) true-scale centroid
    dims_mm: np.ndarray        # (width, length, thickness) or (r, h, 0) for via
    material: str              # "copper", "fr4", "rogers4350", ...
    sigma_s_m: float           # conductivity
    eps_r: float = 1.0         # relative permittivity of surrounding
    mu_r: float = 1.0


@dataclass
class Edge:
    """Coupling between two nodes."""
    src: int
    dst: int
    kind: str                  # "inductive", "capacitive", "resistive", "via"
    dist_mm: float
    overlap_area_mm2: float = 0.0
    rel_vec_mm: Optional[np.ndarray] = None   # dst.center - src.center (for equivariance)


@dataclass
class PCBGraph:
    """
    A full board representation ready for GNN.

    nodes: list of Node
    edges: list of Edge
    freqs_hz: log-spaced frequencies for which we want RLGC(f)
    globals: stackup description, board size, etc.
    """
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    freqs_hz: np.ndarray = field(default_factory=lambda: np.array([]))
    globals: Dict = field(default_factory=dict)
    node_id_to_idx: Dict[int, int] = field(default_factory=dict)

    def add_node(self, node: Node) -> int:
        idx = len(self.nodes)
        self.node_id_to_idx[node.id] = idx
        self.nodes.append(node)
        return idx

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def to_feature_matrices(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns:
            node_feat: [N, D_node]
            edge_feat: [E, D_edge]
            edge_index: [2, E] (src, dst)
        """
        if not self.nodes:
            return np.zeros((0, 8)), np.zeros((0, 5)), np.zeros((2, 0), dtype=int)

        # Node features (invariant scalars + coords for later equivariant use)
        # [x, y, z, w, l, t, log_sigma, eps_r, layer_norm]
        feats = []
        for n in self.nodes:
            cx, cy, cz = n.center_mm
            w, l, t = n.dims_mm
            log_sigma = np.log10(max(n.sigma_s_m, 1e-12))
            layer_norm = n.layer / max(1, self.globals.get("n_layers", 16) - 1)
            feats.append([cx, cy, cz, w, l, t, log_sigma, n.eps_r, layer_norm])
        node_feat = np.array(feats, dtype=np.float32)

        # Edge features
        efeats = []
        eidx = []
        for e in self.edges:
            rel = e.rel_vec_mm if e.rel_vec_mm is not None else np.zeros(3)
            efeats.append([
                e.dist_mm,
                e.overlap_area_mm2,
                *rel[:3],
                1.0 if e.kind == "capacitive" else 0.0,
                1.0 if e.kind == "inductive" else 0.0,
            ])
            src_i = self.node_id_to_idx[e.src]
            dst_i = self.node_id_to_idx[e.dst]
            eidx.append([src_i, dst_i])
        edge_feat = np.array(efeats, dtype=np.float32) if efeats else np.zeros((0, 7), dtype=np.float32)
        edge_index = np.array(eidx, dtype=np.int64).T if eidx else np.zeros((2, 0), dtype=np.int64)

        return node_feat, edge_feat, edge_index

    def summary(self) -> str:
        return (f"PCBGraph: {len(self.nodes)} nodes, {len(self.edges)} edges, "
                f"{len(self.freqs_hz)} freqs, globals={list(self.globals.keys())}")
