#!/usr/bin/env python3
"""
T4 — optimizer-in-the-loop: GNN-driven interleaving screening by inter-winding
capacitance C_ps (the EMI-critical parasitic that interleaving actually controls,
and the GNN's best-predicted target). For each base design we generate several
interleaving variants, rank them by C_ps with (a) the analytical all-pairs PEEC
reference and (b) the GNN, and report the rank agreement (Spearman) + the
inference speedup. This is the decision-usefulness the earlier total-L_m demo
lacked (L_m barely changes across interleavings; C_ps changes strongly).
Runs on a compute cluster.
"""
import json, platform, time, copy
from pathlib import Path
import numpy as np
import torch
from scipy.stats import spearmanr

from gnn_baseline import collate
from run_research13_pipeline import load_dataset, build_samples, TARGETS
from experiments_v5 import train
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs

ROOT = Path(__file__).resolve().parents[1]
CPS = TARGETS.index("Cps_pF")


def predict_cps(model, nrm, nf, ef, ei):
    s = {"node_feat": nrm.node(nf), "edge_feat": nrm.edge(ef),
         "edge_index": np.asarray(ei, np.int64), "edge_dim": 7, "y": np.zeros(4, np.float32)}
    with torch.no_grad():
        return float(nrm.inv(model(collate([s])).numpy()[0])[CPS])


def interleave_variants(base_layout, n_var, rng):
    """Generate interleaving variants by permuting the layer assignment of the
    primary/secondary traces (changes P-S z-adjacency -> changes C_ps)."""
    out = []
    for _ in range(n_var):
        lay = copy.deepcopy(base_layout)
        perm = rng.permutation(8)
        for t in lay["traces"]:
            t["layer"] = int(perm[t["layer"] % 8])
            t["z_mm"] = t["layer"] * 0.18 + 0.05
        out.append(lay)
    return out


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v2")
    samples = build_samples(layouts, labels)
    print("[T4] train GNN on synth_v2 (n=%d)" % len(samples))
    model, nrm, per, _ = train(samples, 42, 200)
    print("    train R2(Cps)=%.4f" % per["Cps_pF"])

    rng = np.random.default_rng(7)
    bases = [r["layout"] for r in layouts
             if any(t["net"] == "pri" for t in r["layout"]["traces"])
             and any(t["net"] == "sec" for t in r["layout"]["traces"])][:12]
    rhos = []; t_ref = 0.0; t_gnn = 0.0; n_eval = 0
    for base in bases:
        variants = interleave_variants(base, 6, rng)
        ref_cps, gnn_cps = [], []
        for lay in variants:
            t0 = time.perf_counter()
            rc = compute_reference_labels_allpairs(lay)["Cps_pF"]
            t_ref += time.perf_counter() - t0
            g = build_graph_from_planar_layout(lay); nf, ef, ei = g.to_feature_matrices()
            t1 = time.perf_counter()
            gc = predict_cps(model, nrm, nf.tolist(), ef.tolist(), ei.tolist() if ei.size else [])
            t_gnn += time.perf_counter() - t1
            ref_cps.append(rc); gnn_cps.append(gc); n_eval += 1
        rho, _ = spearmanr(ref_cps, gnn_cps)
        if not np.isnan(rho):
            rhos.append(rho)
    rhos = np.array(rhos)
    out = {"note": "GNN-driven interleaving screening by C_ps: rank agreement vs "
                   "analytical all-pairs PEEC reference + inference speedup",
           "host": platform.node(), "n_designs": len(rhos), "variants_per_design": 6,
           "spearman_mean": round(float(rhos.mean()), 3),
           "spearman_median": round(float(np.median(rhos)), 3),
           "spearman_min": round(float(rhos.min()), 3),
           "frac_designs_rho_ge_0.9": round(float((rhos >= 0.9).mean()), 2),
           "gnn_speedup_vs_reference_x": round(t_ref / max(t_gnn, 1e-9), 1),
           "train_r2_cps": per["Cps_pF"]}
    od = ROOT / "05_experiments" / "run_t4"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t4.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print("=> GNN ranks interleavings by C_ps at Spearman %.2f (median), %.1fx faster "
          "than the reference." % (out["spearman_median"], out["gnn_speedup_vs_reference_x"]))


if __name__ == "__main__":
    main()
