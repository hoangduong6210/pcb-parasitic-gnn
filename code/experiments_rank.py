#!/usr/bin/env python3
"""
Fix the rho=0.27 interleaving-ranking failure with a PAIRWISE RANKING objective.
The earlier failure was an objective mismatch: a pointwise regressor with global
R^2=0.95 has an absolute error floor that rivals the small WITHIN-family C_ps
spread, so it cannot order interleavings. A pairwise (RankNet/margin) loss
optimises ORDER directly and is not bounded by the absolute error floor.

Labels are FEM-3D C_ps (geometry-correct, so interleaving variants now have
genuinely different C_ps). Evaluation is FAMILY-DISJOINT (train families vs unseen
test families). Compares the ranking model to the regression baseline (rho~0.27).
Runs on a compute cluster.
"""
import json, platform, time, copy, subprocess, os, tempfile
from pathlib import Path
import numpy as np
import torch, torch.nn as nn
from scipy.stats import spearmanr

from gnn_baseline import PCBParasiticGNN, collate
from run_research13_pipeline import load_dataset
from planar_to_graph import build_graph_from_planar_layout
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
             and len(r["layout"]["traces"]) <= 20][:110]
    rng = np.random.default_rng(13)

    print("[rank] build %d families x 8 interleaving variants, FEM-3D Cps" % len(bases), flush=True)
    fams = []; t0 = time.time()
    for b in bases:
        vs = variants(b, 8, rng); recs = []
        for lay in vs:
            c = safe_fem_cps(lay, refine=0, timeout=90)
            if c and c > 0:
                recs.append((graph_of(lay), c))
        if len(recs) >= 4 and (max(r[1] for r in recs) / min(r[1] for r in recs) > 1.15):
            fams.append(recs)            # keep families with real within-family Cps spread
    print("   %d usable families (%.0fs)" % (len(fams), time.time() - t0), flush=True)

    nf_tr = int(0.7 * len(fams)); train_f, test_f = fams[:nf_tr], fams[nf_tr:]
    # standardize node/edge feats on the training graphs
    allg = [g for fam in train_f for (g, _) in fam]
    nrm = Norm([{**g, "y": np.zeros(1, np.float32)} for g in allg], list(range(len(allg))))
    def work(g): return mk({**g, "y": np.zeros(1, np.float32)}, nrm)

    torch.manual_seed(0)
    model = PCBParasiticGNN(node_dim=allg[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=1)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    margin = nn.MarginRankingLoss(margin=1.0)
    rng2 = np.random.default_rng(1)
    for ep in range(120):
        model.train(); order = list(range(len(train_f))); rng2.shuffle(order)
        for fi in order:
            fam = train_f[fi]
            gs = collate([work(g) for (g, _) in fam])
            scores = model(gs).squeeze(-1)            # one score per variant
            cps = torch.tensor([c for (_, c) in fam], dtype=torch.float32)
            # all within-family pairs
            i, j = torch.triu_indices(len(fam), len(fam), offset=1)
            si, sj = scores[i], scores[j]
            sign = torch.sign(cps[i] - cps[j])        # +1 if cps_i>cps_j
            keep = sign != 0
            if keep.sum() == 0:
                continue
            loss = margin(si[keep], sj[keep], sign[keep])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
    model.eval()

    rhos = []
    with torch.no_grad():
        for fam in test_f:
            sc = model(collate([work(g) for (g, _) in fam])).squeeze(-1).numpy()
            cps = np.array([c for (_, c) in fam])
            rho, _ = spearmanr(sc, cps)
            if not np.isnan(rho):
                rhos.append(rho)
    rhos = np.array(rhos)
    out = {"note": "pairwise-ranking GNN for interleaving order (FEM-3D Cps, family-disjoint)",
           "host": platform.node(), "n_families": len(fams), "n_test_families": len(rhos),
           "variants_per_family": 8,
           "spearman_mean": round(float(rhos.mean()), 3),
           "spearman_median": round(float(np.median(rhos)), 3),
           "spearman_min": round(float(rhos.min()), 3),
           "frac_families_rho_ge_0.7": round(float((rhos >= 0.7).mean()), 2),
           "baseline_regression_rho": 0.27}
    od = ROOT / "05_experiments" / "run_rank"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_rank.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    print("=> pairwise-ranking Spearman %.2f (median) vs regression baseline 0.27"
          % out["spearman_median"], flush=True)


if __name__ == "__main__":
    main()
