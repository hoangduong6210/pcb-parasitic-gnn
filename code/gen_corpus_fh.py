#!/usr/bin/env python3
"""
gen_corpus_fh.py — corpus v2 for the panel round-3 push:
  * LARGER boards (more traces) so large-N accuracy is MEASURED, not extrapolated.
  * mutual-inductance label L_m from the multi-filament (FastHenry-style) partial
    -element method instead of the Grover closed form (which the panel showed is
    ~63% off). C_ps and the self/intra-net L_p,L_s keep the analytical path
    (honestly noted; L_m is the dominant inductive coupling and the one fixed).

Heavy (all-pairs filament over many larger layouts) -> Runs on a compute cluster.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from generate_synth import make_random_planar_layout
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from fem_inductance_ref import fem_pair_mutual_nh


def filament_total_Lm(layout, nw=5, nt=2):
    trs = layout["traces"]
    pri = [t for t in trs if t["net"] == "pri"]
    sec = [t for t in trs if t["net"] == "sec"]
    tot = 0.0
    for a in pri:
        for b in sec:
            h = abs(b.get("z_mm", 0.3) - a.get("z_mm", 0.1))
            ov = min(a["length_mm"], b["length_mm"])
            tot += fem_pair_mutual_nh(a["width_mm"], b["width_mm"],
                                      a.get("thick_mm", 0.07), h, ov, nw=nw, nt=nt)
    return tot


def big_layout(seed, max_per_net):
    """Like make_random_planar_layout but with a configurable larger trace count."""
    rng = np.random.default_rng(seed)
    lay = make_random_planar_layout(seed, n_layers=8, big=True)
    # extend: resample n_pri/n_sec up to max_per_net and rebuild trace list
    n_pri = int(rng.integers(4, max_per_net))
    n_sec = int(rng.integers(4, max_per_net))
    base = lay["traces"]
    pri = [t for t in base if t["net"] == "pri"]
    sec = [t for t in base if t["net"] == "sec"]
    def grow(lst, n):
        if not lst:
            return lst
        out = []
        for i in range(n):
            t = dict(lst[i % len(lst)])
            t["x0"] = float(rng.uniform(2, 8))
            t["layer"] = int((i % 4) * 2 + (0 if t["net"] == "pri" else 1))
            out.append(t)
        return out
    lay["traces"] = grow(pri, n_pri) + grow(sec, n_sec)
    return lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--out", default="../03_datasets/synth_v2")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max_per_net", type=int, default=36)   # up to ~70 traces
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    layouts, labels = [], []
    t0 = time.time()
    for i in range(args.n):
        lay = big_layout(args.seed + i, args.max_per_net)
        g = build_graph_from_planar_layout(lay)
        nf, ef, ei = g.to_feature_matrices()
        ana = compute_reference_labels_allpairs(lay)      # C, L_p, L_s (analytical)
        lm_fil = filament_total_Lm(lay)                   # L_m (filament)
        layouts.append({"id": i, "layout": lay,
                        "n_nodes": int(nf.shape[0]), "n_edges": int(ef.shape[0]),
                        "node_feat": nf.tolist(), "edge_feat": ef.tolist(),
                        "edge_index": ei.tolist() if ei.size else []})
        labels.append({"id": i, "Cps_pF": ana["Cps_pF"], "L_pri_nH": ana["L_pri_nH"],
                       "L_sec_nH": ana["L_sec_nH"], "L_mut_nH": lm_fil,
                       "L_mut_nH_grover": ana["L_mut_nH"]})
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{args.n}  ({time.time()-t0:.0f}s)")

    with open(out / "layouts.jsonl", "w") as f:
        for r in layouts:
            f.write(json.dumps(r) + "\n")
    json.dump(labels, open(out / "labels.json", "w"))
    nodes = [r["n_nodes"] for r in layouts]
    meta = {"n_samples": args.n, "label_Lm": "filament_fasthenry_5x2",
            "avg_nodes": float(np.mean(nodes)), "max_nodes": int(np.max(nodes)),
            "min_nodes": int(np.min(nodes)), "max_per_net": args.max_per_net,
            "freq_points": 21}
    json.dump(meta, open(out / "meta.json", "w"), indent=2)
    print(f"Generated {args.n} -> {out}; nodes avg {meta['avg_nodes']:.1f} "
          f"max {meta['max_nodes']} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
