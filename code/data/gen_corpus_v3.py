#!/usr/bin/env python3
"""Generate geometry-valid v3 active-leg layouts without computing labels.

Each winding is represented by co-directed series-connected active legs.  Return
paths, vias, core windows, and terminals remain outside this geometry scope and
must not be inferred from the corpus.  Conductors occupy distinct volumes, obey
board bounds and same-layer clearance, and share one canonical stackup mapping.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from geometry_contract import GEOMETRY_SCHEMA, geometry_sha256, validate_layout


def _winding_traces(
    rng: np.random.Generator,
    net: str,
    count: int,
    layers: list[int],
    board_w_mm: float,
    board_h_mm: float,
    net_phase_mm: float,
) -> list[dict]:
    assignments = {layer: [] for layer in layers}
    for turn_index in range(count):
        assignments[layers[turn_index % len(layers)]].append(turn_index)

    traces = []
    edge_margin = 2.0
    for layer in layers:
        turns = assignments[layer]
        if not turns:
            continue
        lane_pitch = (board_h_mm - 2 * edge_margin) / len(turns)
        for lane, turn_index in enumerate(turns):
            width_limit = max(0.7, lane_pitch - 0.6)
            width = float(rng.uniform(0.7, min(2.4, width_limit)))
            lane_center = edge_margin + (lane + 0.5) * lane_pitch
            jitter_limit = max(0.0, (lane_pitch - width - 0.4) / 2)
            y_center = lane_center + float(rng.uniform(-jitter_limit, jitter_limit))
            y0 = y_center - width / 2
            length = float(rng.uniform(30.0, 47.0))
            x_room = board_w_mm - length - 2 * edge_margin
            x0 = edge_margin + float(rng.uniform(0.0, max(0.0, x_room)))
            x0 = min(x0 + net_phase_mm, board_w_mm - edge_margin - length)
            x0 = max(edge_margin, x0)
            traces.append({
                "trace_id": f"{net}-t{turn_index:02d}",
                "net": net,
                "turn_index": turn_index,
                "segment_role": "active_leg",
                "current_sign": 1,
                "layer": layer,
                "x0": round(float(x0), 9),
                "y0": round(float(y0), 9),
                "length_mm": round(length, 9),
                "width_mm": round(width, 9),
                "thick_mm": 0.07,
            })
    return traces


def make_layout_v3(seed: int, n_layers: int = 8, max_per_net: int = 14) -> dict:
    if n_layers != 8:
        raise ValueError("v3 predeclared corpus uses exactly eight layers")
    if not 4 <= max_per_net <= 14:
        raise ValueError("max_per_net must stay within the validated 4..14 range")
    rng = np.random.default_rng(seed)
    board_w_mm = 55.0
    board_h_mm = 55.0
    n_pri = int(rng.integers(4, max_per_net + 1))
    n_sec = int(rng.integers(4, max_per_net + 1))
    pri = _winding_traces(rng, "pri", n_pri, [0, 2, 4, 6], board_w_mm, board_h_mm, 0.0)
    sec = _winding_traces(
        rng, "sec", n_sec, [1, 3, 5, 7], board_w_mm, board_h_mm,
        float(rng.uniform(-1.0, 1.0)),
    )
    layout = {
        "geometry_schema": GEOMETRY_SCHEMA,
        "model_scope": "co-directed series-connected active legs; returns and vias excluded",
        "seed": int(seed),
        "n_layers": n_layers,
        "board_w_mm": board_w_mm,
        "board_h_mm": board_h_mm,
        "stackup": {"layer_pitch_mm": 0.18, "layer_z0_mm": 0.05},
        "design_rules": {"same_layer_clearance_mm": 0.20, "board_edge_margin_mm": 2.0},
        "eps_r": 4.2,
        "cu_oz": 2.0,
        "traces": sorted(pri + sec, key=lambda trace: (trace["layer"], trace["net"], trace["turn_index"])),
        "freqs_hz": np.logspace(4, 8, 21).tolist(),
    }
    validate_layout(layout)
    return layout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42000)
    parser.add_argument("--max-per-net", type=int, default=14)
    parser.add_argument("--out", type=Path, default=Path("datasets/synth_v3/layouts.jsonl"))
    args = parser.parse_args()
    if args.n <= 0:
        raise SystemExit("--n must be positive")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    corpus_hashes = []
    counts = []
    minimum_clearances = []
    with args.out.open("w") as handle:
        for layout_id in range(args.n):
            layout = make_layout_v3(args.seed + layout_id, max_per_net=args.max_per_net)
            audit = validate_layout(layout)
            digest = geometry_sha256(layout)
            record = {"layout_id": layout_id, "geometry_sha256": digest, "layout": layout}
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            corpus_hashes.append(digest)
            counts.append(audit["n_traces"])
            if audit["minimum_same_layer_clearance_mm"] is not None:
                minimum_clearances.append(audit["minimum_same_layer_clearance_mm"])
    meta = {
        "schema": "pcb-planar-corpus.v3",
        "geometry_schema": GEOMETRY_SCHEMA,
        "n_layouts": args.n,
        "seed_start": args.seed,
        "max_per_net": args.max_per_net,
        "geometry_sequence_sha256": __import__("hashlib").sha256("\n".join(corpus_hashes).encode()).hexdigest(),
        "min_traces": min(counts), "max_traces": max(counts),
        "mean_traces": float(np.mean(counts)),
        "minimum_same_layer_clearance_mm": min(minimum_clearances),
        "labels": "none; field labels are produced only after the geometry gate",
    }
    (args.out.parent / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, sort_keys=True))


if __name__ == "__main__":
    main()
