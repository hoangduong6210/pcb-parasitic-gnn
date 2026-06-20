#!/usr/bin/env python3
"""
Decision-consequence demo: does the surrogate CHANGE the layout decision, or just
reproduce a solver faster? For each design family (a base + interleaving variants)
the engineer picks the interleaving with the LOWEST inter-winding C_ps (lowest
common-mode coupling). We compare three screeners choosing that pick:
  - analytical PEEC  (fast, 0.78 ms, but position-blind / 52-267% off)
  - GNN              (fast, 1.17 ms, field-grade + rho=0.93 ranking)
  - FEM-3D C_ps      (the truth, ~2 s/design)
and measure the REGRET of each pick = how much higher the picked design's TRUE
(FEM) C_ps is than the family's true-optimal. A good screener picks the (near-)best
interleaving; a position-blind one picks wrong. Family-disjoint. SLURM.
"""
import json, platform, time, copy, subprocess, os, tempfile
from pathlib import Path
import numpy as np
import torch, torch.nn as nn
from scipy.stats import spearmanr

from gnn_baseline import PCBParasiticGNN, collate
from run_research13_pipeline import load_dataset
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from experiments_v5 import Norm, mk

ROOT = Path(__file__).resolve().parents[1]


def safe_fem_cps(layout, refine=0, timeout=90):
    fd, p = tempfile.mkstemp(suffix=".json"); os.close(fd)
    try:
        json.dump(layout, open(p, "w"))
        r = subprocess.run(["/usr/bin/python3", "fem_cps_worker.py", p, str(refine)],
                           capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "PYTHONPATH": "."})
        for line in r.stdout.splitlines():
            if line.startswith("CPS="):
                return float(line[4:])
        return None
    except Exception:
        return None
    finally:
        try: os.remove(p)
        except Exception: pass


def variants(base, n, rng):
    out = []
    for _ in range(n):
        lay = copy.deepcopy(base); perm = rng.permutation(8)
        for t in lay["traces"]:
            t["layer"] = int(perm[t["layer"] % 8]); t["z_mm"] = t["layer"] * 0.18 + 0.05
        out.append(lay)
    return out


def graph_of(lay):
    g = build_graph_from_planar_layout(lay); nf, ef, ei = g.to_feature_matrices()
    return {"node_feat": nf.astype(np.float32), "edge_feat": ef.astype(np.float32),
            "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": np.zeros(1, np.float32)}


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    bases = [r["layout"] for r in layouts
             if any(t["net"] == "pri" for t in r["layout"]["traces"])
             and any(t["net"] == "sec" for t in r["layout"]["traces"])
             and len(r["layout"]["traces"]) <= 20][:120]
    rng = np.random.default_rng(21)

    print("[decision] build families: FEM-3D truth + analytical PEEC + graph", flush=True)
    fams = []; t0 = time.time()
    for b in bases:
        recs = []
        for lay in variants(b, 8, rng):
            fem = safe_fem_cps(lay, refine=0, timeout=90)
            if fem and fem > 0:
                peec = compute_reference_labels_allpairs(lay)["Cps_pF"]
                recs.append({"g": graph_of(lay), "fem": fem, "peec": peec})
        fem_vals = [r["fem"] for r in recs]
        if len(recs) >= 4 and (max(fem_vals) / min(fem_vals) > 1.15):
            fams.append(recs)
    print("   %d usable families (%.0fs)" % (len(fams), time.time() - t0), flush=True)

    nf_tr = int(0.7 * len(fams)); train_f, test_f = fams[:nf_tr], fams[nf_tr:]
    allg = [r["g"] for fam in train_f for r in fam]
    nrm = Norm([{**g, "y": np.zeros(1, np.float32)} for g in allg], list(range(len(allg))))
    def work(g): return mk({**g, "y": np.zeros(1, np.float32)}, nrm)

    torch.manual_seed(0)
    model = PCBParasiticGNN(node_dim=allg[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=1)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    margin = nn.MarginRankingLoss(margin=1.0); rng2 = np.random.default_rng(1)
    for ep in range(120):
        model.train(); order = list(range(len(train_f))); rng2.shuffle(order)
        for fi in order:
            fam = train_f[fi]
            sc = model(collate([work(r["g"]) for r in fam])).squeeze(-1)
            fem = torch.tensor([r["fem"] for r in fam], dtype=torch.float32)
            i, j = torch.triu_indices(len(fam), len(fam), offset=1)
            sign = torch.sign(fem[i] - fem[j]); keep = sign != 0
            if keep.sum() == 0:
                continue
            loss = margin(sc[i][keep], sc[j][keep], sign[keep])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
    model.eval()

    # decision comparison on family-disjoint test
    def regret(pick_idx, fem_vals):
        best = min(fem_vals)
        return (fem_vals[pick_idx] - best) / best * 100.0
    peec_reg, gnn_reg, rand_reg = [], [], []
    peec_hit, gnn_hit = 0, 0; rho_peec, rho_gnn = [], []
    with torch.no_grad():
        for fam in test_f:
            fem = np.array([r["fem"] for r in fam])
            peec = np.array([r["peec"] for r in fam])
            sc = model(collate([work(r["g"]) for r in fam])).squeeze(-1).numpy()
            true_best = int(np.argmin(fem))
            peec_pick = int(np.argmin(peec))     # PEEC picks lowest-PEEC-Cps
            gnn_pick = int(np.argmin(sc))         # GNN ranking picks lowest-score (lowest Cps)
            peec_reg.append(regret(peec_pick, fem)); gnn_reg.append(regret(gnn_pick, fem))
            rand_reg.append(np.mean([regret(k, fem) for k in range(len(fem))]))
            peec_hit += (peec_pick == true_best); gnn_hit += (gnn_pick == true_best)
            r1, _ = spearmanr(peec, fem); r2, _ = spearmanr(sc, fem)
            if not np.isnan(r1): rho_peec.append(r1)
            if not np.isnan(r2): rho_gnn.append(r2)
    n = len(test_f)
    out = {"note": "decision-consequence: which screener picks the best interleaving",
           "host": platform.node(), "n_families": len(fams), "n_test_families": n,
           "peec_mean_regret_pct": round(float(np.mean(peec_reg)), 1),
           "gnn_mean_regret_pct": round(float(np.mean(gnn_reg)), 1),
           "random_mean_regret_pct": round(float(np.mean(rand_reg)), 1),
           "peec_median_regret_pct": round(float(np.median(peec_reg)), 1),
           "gnn_median_regret_pct": round(float(np.median(gnn_reg)), 1),
           "peec_top1_hit_rate": round(peec_hit / n, 2),
           "gnn_top1_hit_rate": round(gnn_hit / n, 2),
           "peec_rank_spearman": round(float(np.mean(rho_peec)), 2),
           "gnn_rank_spearman": round(float(np.mean(rho_gnn)), 2)}
    od = ROOT / "05_experiments" / "run_decision"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_decision.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    print("=> picking the best interleaving: PEEC regret %.1f%% (hit %.0f%%) vs GNN regret %.1f%% (hit %.0f%%)"
          % (out["peec_mean_regret_pct"], 100*out["peec_top1_hit_rate"],
             out["gnn_mean_regret_pct"], 100*out["gnn_top1_hit_rate"]), flush=True)


if __name__ == "__main__":
    main()
