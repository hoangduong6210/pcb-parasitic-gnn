"""Verified loader and split registry for finalized corpus v3 artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from geometry_contract import geometry_sha256, validate_layout, validate_passive_labels
from planar_to_graph import build_graph_from_planar_layout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_final_corpus(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    directory = directory.resolve()
    summary_path = directory / "summary.json"
    layouts_path = directory / "layouts.jsonl"
    labels_path = directory / "labels.jsonl"
    summary = json.loads(summary_path.read_text())
    required_gates = (
        "geometry_valid", "all_labels_passive", "all_array_tasks_clean_and_source_identical",
    )
    if any(summary["gates"].get(gate) is not True for gate in required_gates):
        raise ValueError("corpus finalizer gates are not all true")
    for path in (layouts_path, labels_path):
        if sha256(path) != summary["artifacts_sha256"][path.name]:
            raise ValueError(f"artifact hash mismatch: {path.name}")
    layouts = [json.loads(line) for line in layouts_path.read_text().splitlines() if line]
    labels = [json.loads(line) for line in labels_path.read_text().splitlines() if line]
    if len(layouts) != len(labels) or len(layouts) != summary["gates"]["n_layouts"]:
        raise ValueError("layout/label cardinality mismatch")

    samples: list[dict[str, Any]] = []
    for layout_record, label_record in zip(layouts, labels):
        if layout_record["layout_id"] != label_record["layout_id"]:
            raise ValueError("layout/label ID mismatch")
        if layout_record["geometry_sha256"] != label_record["geometry_sha256"]:
            raise ValueError("layout/label geometry hash mismatch")
        layout = layout_record["layout"]
        validate_layout(layout)
        if geometry_sha256(layout) != layout_record["geometry_sha256"]:
            raise ValueError("recomputed geometry hash mismatch")
        label = {name: float(label_record[name]) for name in (
            "Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH",
        )}
        validate_passive_labels(label)
        graph = build_graph_from_planar_layout(layout)
        node_feat, edge_feat, edge_index = graph.to_feature_matrices()
        samples.append({
            "layout_id": int(layout_record["layout_id"]),
            "geometry_sha256": layout_record["geometry_sha256"],
            "family": [
                sum(trace["net"] == "pri" for trace in layout["traces"]),
                sum(trace["net"] == "sec" for trace in layout["traces"]),
            ],
            "layout": layout,
            "node_feat": node_feat.astype(np.float32),
            "edge_feat": edge_feat.astype(np.float32),
            "edge_index": edge_index.astype(np.int64),
            "edge_dim": 7,
            "y": np.asarray([label[name] for name in (
                "Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH",
            )], dtype=np.float32),
        })
    return samples, summary


def split_indices(samples: list[dict[str, Any]], seed: int, kind: str) -> tuple[list[int], list[int]]:
    rng = np.random.default_rng(seed)
    if kind == "random":
        indices = np.arange(len(samples))
        rng.shuffle(indices)
        cut = int(0.8 * len(indices))
        return indices[:cut].tolist(), indices[cut:].tolist()
    if kind != "family":
        raise ValueError(f"unsupported split kind: {kind}")
    families = sorted({tuple(sample["family"]) for sample in samples})
    rng.shuffle(families)
    test_family_count = max(1, int(np.ceil(0.2 * len(families))))
    test_families = set(families[:test_family_count])
    train = [index for index, sample in enumerate(samples) if tuple(sample["family"]) not in test_families]
    test = [index for index, sample in enumerate(samples) if tuple(sample["family"]) in test_families]
    if not train or not test:
        raise ValueError("family-disjoint split is empty")
    return train, test
