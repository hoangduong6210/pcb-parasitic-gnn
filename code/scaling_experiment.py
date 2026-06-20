#!/usr/bin/env python3
"""
scaling_experiment.py — Honest wall-time scaling study for Topic 13.

The central hypothesis is an O(N) fast surrogate that beats O(N^2)-style
extraction at scale. The v1 training run showed the GNN is NOT faster than the
all-pairs PEEC reference at ~25 nodes (0.67x) BECAUSE the graph used all-pairs
edges, making the GNN itself O(N^2). This experiment tests the scaling honestly:

  For board sizes N (number of trace segments):
    * t_ref   = measured O(N^2) all-pairs PEEC reference time / sample
    * t_dense = GNN forward on the ALL-PAIRS graph (current arch, ~O(N^2) edges)
    * t_knn   = GNN forward on a SPARSE k-NN graph (k fixed -> ~O(N*k) edges)

  Report each curve and the crossover N where the sparse-kNN GNN forward first
  beats the all-pairs reference. Timing is weight-independent (a forward pass),
  so an untrained model of the trained config is valid for TIMING. Accuracy on
  k-NN graphs is a SEPARATE question (flagged as future work in the manuscript);
  this file measures wall time only and says so.

Runs via sbatch on a compute node (: never heavy on login).
"""
import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from gnn_baseline import PCBParasiticGNN, collate
from generate_synth import make_random_planar_layout
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs


def knn_sparsify(node_feat, k=8):
    """Build a symmetric k-NN edge set from node centroids (cols 0:3 = xyz).
    Returns (edge_index[2,E], edge_feat[E,7]) matching the dense featurizer's
    7-dim layout: [dist, overlap(=0 proxy), dx, dy, dz, is_cap, is_ind]."""
    xyz = node_feat[:, :3]
    n = xyz.shape[0]
    if n <= 1:
        return np.zeros((2, 0), dtype=np.int64), np.zeros((0, 7), dtype=np.float32)
    d = np.sqrt(((xyz[:, None, :] - xyz[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, np.inf)
    kk = min(k, n - 1)
    nn = np.argpartition(d, kk, axis=1)[:, :kk]
    src, dst, ef = [], [], []
    for i in range(n):
        for j in nn[i]:
            rel = xyz[j] - xyz[i]
            dist = float(np.linalg.norm(rel))
            src.append(i); dst.append(int(j))
            ef.append([dist, 0.0, rel[0], rel[1], rel[2], 0.0, 1.0])
    return (np.array([src, dst], dtype=np.int64),
            np.array(ef, dtype=np.float32))


def time_callable(fn, repeats=10):
    for _ in range(2):
        fn()
    ts = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return float(np.median(ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="../05_experiments/scaling_v1")
    ap.add_argument("--ckpt", type=str, default="../05_experiments/run_v1/gnn_checkpoint.pt")
    ap.add_argument("--sizes", type=int, nargs="+",
                    default=[10, 20, 40, 80, 160, 320, 640, 1280])
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = PCBParasiticGNN(node_dim=9, edge_dim=7, hidden=96, n_layers=4, n_targets=4).to(device)
    if Path(args.ckpt).exists():
        ck = torch.load(args.ckpt, map_location=device)
        try:
            model.load_state_dict(ck["state_dict"])
            ckpt_loaded = True
        except Exception as e:
            ckpt_loaded = f"config-mismatch ({e}); using fresh weights (timing is weight-independent)"
    else:
        ckpt_loaded = "no checkpoint; fresh weights (timing is weight-independent)"
    model.eval()

    rows = []
    rng = np.random.default_rng(args.seed)
    for N in args.sizes:
        # one representative layout with ~N trace segments
        seed = int(rng.integers(0, 1_000_000))
        layout = make_random_planar_layout(seed, n_layers=8, big=True)
        # force the trace count to N (n_pri = n_sec = N/2) by replicating pattern
        base = layout["traces"]
        if base:
            reps = (N + len(base) - 1) // len(base)
            layout["traces"] = (base * reps)[:N]
        g = build_graph_from_planar_layout(layout)
        nf, ef_dense, ei_dense = g.to_feature_matrices()
        n_nodes = nf.shape[0]

        # reference timing
        t_ref = time_callable(lambda: compute_reference_labels_allpairs(layout), repeats=8)

        # dense GNN forward
        dense_sample = {"node_feat": nf, "edge_feat": ef_dense, "edge_index": ei_dense,
                        "edge_dim": 7, "y": np.zeros(4, dtype=np.float32)}
        b_dense = collate([dense_sample], device=device)
        with torch.no_grad():
            t_dense = time_callable(lambda: model(b_dense), repeats=10)

        # sparse k-NN GNN forward
        ei_knn, ef_knn = knn_sparsify(nf, k=args.k)
        knn_sample = {"node_feat": nf, "edge_feat": ef_knn, "edge_index": ei_knn,
                      "edge_dim": 7, "y": np.zeros(4, dtype=np.float32)}
        b_knn = collate([knn_sample], device=device)
        with torch.no_grad():
            t_knn = time_callable(lambda: model(b_knn), repeats=10)

        rows.append({
            "N_traces": N,
            "n_nodes": int(n_nodes),
            "edges_dense": int(ei_dense.shape[1]),
            "edges_knn": int(ei_knn.shape[1]),
            "t_ref_ms": round(t_ref * 1000, 4),
            "t_gnn_dense_ms": round(t_dense * 1000, 4),
            "t_gnn_knn_ms": round(t_knn * 1000, 4),
            "knn_speedup_vs_ref_x": round(t_ref / t_knn, 3) if t_knn > 0 else None,
        })
        print(rows[-1])

    crossover = next((r["N_traces"] for r in rows if r["knn_speedup_vs_ref_x"] and
                      r["knn_speedup_vs_ref_x"] >= 1.0), None)
    out = {
        "experiment": "wall-time scaling: O(N^2) all-pairs PEEC vs GNN forward (dense vs k-NN)",
        "k": args.k,
        "device": device,
        "ckpt_loaded": ckpt_loaded,
        "timing_only_note": ("forward-pass wall time only; k-NN accuracy is separate "
                             "future work, not claimed here"),
        "rows": rows,
        "knn_beats_ref_at_N": crossover,
        "max_knn_speedup_x": max((r["knn_speedup_vs_ref_x"] or 0) for r in rows),
        "torch_version": torch.__version__,
        "hostname": platform.node(),
        "seed": args.seed,
    }
    (out_dir / "scaling.json").write_text(json.dumps(out, indent=2))
    print("=== SCALING SUMMARY ===")
    print(json.dumps(out, indent=2))
    print(f"Saved -> {out_dir/'scaling.json'}")


if __name__ == "__main__":
    main()
