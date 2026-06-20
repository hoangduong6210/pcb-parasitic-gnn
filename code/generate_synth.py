#!/usr/bin/env python3
"""
generate_synth.py — Synthetic planar PCB trace dataset generator (low RAM).

Generates random multi-layer rectangular trace layouts for planar magnetics
(LLC-style interleaving) and labels using the improved trace_peec models.

Usage (light):
  python generate_synth.py --n 200 --out ../03_datasets/synth_v0 --seed 42

Heavy runs: submit via sbatch (see submit_research13.sh).
"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

from planar_to_graph import (
    build_graph_from_planar_layout,
    compute_improved_labels,
    compute_reference_labels_allpairs,
)

def make_random_planar_layout(seed: int, n_layers: int = 8, big: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    traces = []
    # `big` widens the trace-count range so graphs span a realistic size
    # distribution (and the O(N^2) reference labeler is genuinely non-trivial).
    hi = 22 if big else 12
    n_pri = rng.integers(4, hi)
    n_sec = rng.integers(4, hi)

    board_w = 55.0
    board_h = 55.0
    trace_len = rng.uniform(35, 48)
    base_width = rng.uniform(1.2, 3.5)

    layer_spacing = 0.18  # mm between layer centers approx

    # Simple P-S-P-S interleaving pattern
    for i in range(max(n_pri, n_sec)):
        # Primary traces
        if i < n_pri:
            layer = (i % (n_layers // 2)) * 2
            w = base_width * rng.uniform(0.9, 1.15)
            x0 = rng.uniform(2, 8)
            traces.append({
                "net": "pri",
                "layer": int(layer),
                "x0": float(x0),
                "y0": 0.0,
                "length_mm": float(trace_len),
                "width_mm": float(w),
                "thick_mm": 0.07,
                "z_mm": layer * layer_spacing + 0.05,
            })
        # Secondary traces
        if i < n_sec:
            layer = (i % (n_layers // 2)) * 2 + 1
            w = base_width * rng.uniform(0.9, 1.15)
            x0 = rng.uniform(2, 8)
            traces.append({
                "net": "sec",
                "layer": int(layer),
                "x0": float(x0),
                "y0": 0.0,
                "length_mm": float(trace_len),
                "width_mm": float(w),
                "thick_mm": 0.07,
                "z_mm": layer * layer_spacing + 0.05,
            })

    freqs = np.logspace(4, 8, 21).tolist()

    return {
        "n_layers": int(n_layers),
        "board_w_mm": board_w,
        "board_h_mm": board_h,
        "eps_r": 4.2,
        "cu_oz": 2.0,
        "traces": traces,
        "freqs_hz": freqs,
        "seed": int(seed),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200, help="number of samples")
    parser.add_argument("--out", type=str, default="../03_datasets/synth_v0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n_layers", type=int, default=8)
    parser.add_argument("--big", action="store_true",
                        help="wider trace-count range (larger graphs)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    import time
    layouts = []
    all_labels = []
    ref_total_s = 0.0   # wall time spent in the O(N^2) all-pairs reference

    for i in range(args.n):
        seed = args.seed + i
        layout = make_random_planar_layout(seed, n_layers=args.n_layers, big=args.big)
        graph = build_graph_from_planar_layout(layout)

        # representative-pair shortcut (kept for the old-baseline comparison)
        labels = compute_improved_labels(layout)
        # full O(N^2) all-pairs PEEC reference = the GNN target vector (timed)
        _t0 = time.perf_counter()
        ref = compute_reference_labels_allpairs(layout)
        ref_total_s += time.perf_counter() - _t0

        # Store compact: only summary stats + graph feature matrices for training
        node_feat, edge_feat, edge_index = graph.to_feature_matrices()

        rec = {
            "id": i,
            "layout": layout,
            "n_nodes": int(node_feat.shape[0]),
            "n_edges": int(edge_feat.shape[0]),
            "node_feat": node_feat.tolist(),
            "edge_feat": edge_feat.tolist(),
            "edge_index": edge_index.tolist() if edge_index.size else [],
        }
        layouts.append(rec)
        all_labels.append({
            "id": i,
            # GNN targets = full all-pairs reference (the honest "ground truth")
            "Cps_pF": ref["Cps_pF"],
            "L_pri_nH": ref["L_pri_nH"],
            "L_sec_nH": ref["L_sec_nH"],
            "L_mut_nH": ref["L_mut_nH"],
            # representative-pair shortcut (for old-baseline error reference)
            "Cps_pF_repr": float(np.mean(labels["Cps_pF"])),
        })

    # Write compact jsonl + meta
    with open(out_dir / "layouts.jsonl", "w") as f:
        for r in layouts:
            f.write(json.dumps(r) + "\n")

    with open(out_dir / "labels.json", "w") as f:
        json.dump(all_labels, f, indent=2)

    meta = {
        "n_samples": args.n,
        "n_layers": args.n_layers,
        "seed": args.seed,
        "freq_points": len(layouts[0]["layout"]["freqs_hz"]) if layouts else 0,
        "avg_nodes": float(np.mean([r["n_nodes"] for r in layouts])) if layouts else 0,
        "avg_edges": float(np.mean([r["n_edges"] for r in layouts])) if layouts else 0,
        "ref_allpairs_total_s": round(ref_total_s, 4),
        "ref_allpairs_ms_per_sample": round(ref_total_s / max(1, args.n) * 1000, 4),
        "generated_on": str(np.datetime64('now')),
    }
    with open(out_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Generated {args.n} samples -> {out_dir}")
    print(f"Avg nodes: {np.mean([r['n_nodes'] for r in layouts]):.1f}")
    print(f"All-pairs reference: {meta['ref_allpairs_ms_per_sample']:.4f} ms/sample")

if __name__ == "__main__":
    main()
