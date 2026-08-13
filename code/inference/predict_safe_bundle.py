#!/usr/bin/env python3
"""Run four-target inference from the state-dict-only NumPy bundle."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
for _directory in (CODE / "models/gnn", CODE / "core"):
    sys.path.insert(0, str(_directory))

from gnn_baseline import PCBParasiticGNN, collate
from planar_to_graph import build_graph_from_planar_layout


def load_bundle(bundle: Path) -> tuple[PCBParasiticGNN, dict[str, np.ndarray], dict[str, Any]]:
    metadata = json.loads((bundle / "metadata.json").read_text())
    archive = np.load(bundle / "weights_and_norm.npz", allow_pickle=False)
    config = metadata["architecture"]
    model = PCBParasiticGNN(**config)
    state = {
        key.removeprefix("state__"): torch.from_numpy(archive[key].copy())
        for key in archive.files if key.startswith("state__")
    }
    model.load_state_dict(state, strict=True)
    model.eval()
    normalization = {key: archive[f"norm_{key}"].copy() for key in ("ym", "ys", "nfm", "nfs", "efm", "efs")}
    archive.close()
    return model, normalization, metadata


def predict_layout(model: PCBParasiticGNN, norm: dict[str, np.ndarray], layout: dict[str, Any]) -> np.ndarray:
    graph = build_graph_from_planar_layout(layout)
    node, edge, edge_index = graph.to_feature_matrices()
    node = ((node.astype(np.float32) - norm["nfm"]) / norm["nfs"]).astype(np.float32)
    edge = edge.astype(np.float32)
    if edge.size:
        edge = ((edge - norm["efm"]) / norm["efs"]).astype(np.float32)
    sample = {
        "node_feat": node, "edge_feat": edge,
        "edge_index": edge_index.astype(np.int64), "edge_dim": 7,
        "y": np.zeros(4, dtype=np.float32),
    }
    with torch.no_grad():
        standardized = model(collate([sample])).numpy()[0]
    logged = standardized * norm["ys"] + norm["ym"]
    return np.sign(logged) * np.expm1(np.abs(logged))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("layouts", type=Path, help="JSONL rows containing layout or {layout: ...}")
    args = parser.parse_args()
    model, norm, metadata = load_bundle(args.bundle)
    for line in args.layouts.read_text().splitlines():
        row = json.loads(line)
        layout = row.get("layout", row)
        prediction = predict_layout(model, norm, layout)
        print(json.dumps({
            "layout_id": row.get("layout_id"),
            "targets": dict(zip(metadata["targets"], map(float, prediction))),
        }))


if __name__ == "__main__":
    main()
