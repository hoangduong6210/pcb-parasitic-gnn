#!/usr/bin/env python3
"""
T4b — fix the weak interleaving-screening result, three causes at once:
  (1) ERROR-FLOOR vs within-family spread: the global model's absolute Cps error
      (~70 pF) rivals the within-family std (~80 pF) for tight designs. Fix:
      AUGMENT training with interleaving FAMILIES (each base + its layer
      permutations, all labelled) so the network learns the fine z-dependence
      that distinguishes interleavings - the original corpus had only independent
      layouts and never saw "same traces, different layer order".
  (2) n=6 Spearman noise: evaluate with 30 variants per design.
  (3) no speedup at small N: also measure ranking speed on LARGE boards (N>80),
      above the GNN-vs-analytical crossover.
Evaluation bases are FAMILY-DISJOINT from training (held-out). Runs on a compute cluster.
"""
import json, platform, time, copy
from pathlib import Path
import numpy as np
import torch, torch.nn as nn
from scipy.stats import spearmanr

from gnn_baseline import PCBParasiticGNN, collate
from run_research13_pipeline import load_dataset, TARGETS
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from experiments_v5 import Norm, mk
from gen_corpus_fh import big_layout

ROOT = Path(__file__).resolve().parents[1]
CPS = TARGETS.index("Cps_pF")


def variants(base, n, rng):
    out = []
    for _ in range(n):
        lay = copy.deepcopy(base); perm = rng.permutation(8)
        for t in lay["traces"]:
            t["layer"] = int(perm[t["layer"] % 8]); t["z_mm"] = t["layer"] * 0.18 + 0.05
        out.append(lay)
    return out


def to_sample(lay):
    lab = compute_reference_labels_allpairs(lay)
    g = build_graph_from_planar_layout(lay); nf, ef, ei = g.to_feature_matrices()
    y = np.array([lab[t] for t in TARGETS], np.float32)
    return {"node_feat": nf.astype(np.float32), "edge_feat": ef.astype(np.float32),
            "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": y}


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    bases = [r["layout"] for r in layouts
             if any(t["net"] == "pri" for t in r["layout"]["traces"])
             and any(t["net"] == "sec" for t in r["layout"]["traces"])]
    rng = np.random.default_rng(11)
    train_bases, test_bases = bases[:160], bases[300:340]

    # (1) family-augmented training corpus: each base + 6 interleaving variants
    print("[T4b] build family-augmented corpus (%d bases x 6 variants)" % len(train_bases), flush=True)
    t0 = time.time(); train = []
    for b in train_bases:
        for lay in variants(b, 6, rng):
            train.append(to_sample(lay))
    print("   %d training samples (%.0fs)" % (len(train), time.time()-t0), flush=True)

    nrm = Norm(train, list(range(len(train))))
    work = [mk(s, nrm) for s in train]
    model = PCBParasiticGNN(node_dim=train[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=200)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=120)
    lf = nn.SmoothL1Loss(); idx = list(range(len(work)))
    tt = time.time()
    for ep in range(120):
        model.train(); rng.shuffle(idx)
        for i in range(0, len(idx), 32):
            b = collate([work[j] for j in idx[i:i+32]])
            opt.zero_grad(); lf(model(b), b.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
        sch.step()
        if ep % 30 == 0:
            print("   epoch %d (%.0fs)" % (ep, time.time()-tt), flush=True)
    model.eval()
    print("   trained (%.0fs)" % (time.time()-tt), flush=True)

    def gnn_cps(lay):
        g = build_graph_from_planar_layout(lay); nf, ef, ei = g.to_feature_matrices()
        s = {"node_feat": nrm.node(nf), "edge_feat": nrm.edge(ef),
             "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": np.zeros(4, np.float32)}
        with torch.no_grad():
            return float(nrm.inv(model(collate([s])).numpy()[0])[CPS])

    # (2) ranking on FAMILY-DISJOINT held-out bases, 30 variants each
    print("[T4b] rank eval on %d held-out bases x 30 variants" % len(test_bases), flush=True)
    rhos = []; t_ref = t_gnn = 0.0
    for b in test_bases:
        vs = variants(b, 30, rng)
        rc, gc = [], []
        for lay in vs:
            t1 = time.perf_counter(); rc.append(compute_reference_labels_allpairs(lay)["Cps_pF"]); t_ref += time.perf_counter()-t1
            t2 = time.perf_counter(); gc.append(gnn_cps(lay)); t_gnn += time.perf_counter()-t2
        rho, _ = spearmanr(rc, gc)
        if not np.isnan(rho):
            rhos.append(rho)
    rhos = np.array(rhos)
    od = ROOT / "05_experiments" / "run_t4b"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t4b.json").write_text(json.dumps({
        "partial": "ranking only (large-board pending)",
        "n_train": len(train), "n_test_designs": len(rhos), "variants_per_design": 30,
        "spearman_mean": round(float(rhos.mean()), 3),
        "spearman_median": round(float(np.median(rhos)), 3),
        "spearman_min": round(float(rhos.min()), 3),
        "frac_designs_rho_ge_0.9": round(float((rhos >= 0.9).mean()), 2),
        "small_board_speedup_x": round(t_ref / max(t_gnn, 1e-9), 2)}, indent=2))
    print("   [ranking saved] median rho=%.2f" % float(np.median(rhos)), flush=True)

    # (3) speedup on LARGE boards (N>80)
    print("[T4b] large-board speedup (N>80)", flush=True)
    big = [l for l in (big_layout(1000+i, 120) for i in range(12))
           if len(l["traces"]) > 80][:6]   # boards above the GNN-vs-analytical crossover
    bt_ref = bt_gnn = 0.0; nbig = []
    for lay in big:
        nbig.append(len(lay["traces"]))
        t1 = time.perf_counter(); compute_reference_labels_allpairs(lay); bt_ref += time.perf_counter()-t1
        t2 = time.perf_counter(); gnn_cps(lay); bt_gnn += time.perf_counter()-t2

    out = {"note": "T4b fixed interleaving screening: family-augmented training, "
                   "30 variants, family-disjoint eval, + large-board speedup",
           "host": platform.node(), "n_train": len(train), "n_test_designs": len(rhos),
           "variants_per_design": 30,
           "spearman_mean": round(float(rhos.mean()), 3),
           "spearman_median": round(float(np.median(rhos)), 3),
           "spearman_min": round(float(rhos.min()), 3),
           "frac_designs_rho_ge_0.9": round(float((rhos >= 0.9).mean()), 2),
           "small_board_speedup_x": round(t_ref / max(t_gnn, 1e-9), 2),
           "large_board_n_traces": nbig,
           "large_board_speedup_x": round(bt_ref / max(bt_gnn, 1e-9), 2)}
    od = ROOT / "05_experiments" / "run_t4b"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t4b.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    print("=> T4b: Spearman median %.2f (was 0.74), large-board speedup %.1fx (small %.2fx)"
          % (out["spearman_median"], out["large_board_speedup_x"], out["small_board_speedup_x"]), flush=True)


if __name__ == "__main__":
    main()
