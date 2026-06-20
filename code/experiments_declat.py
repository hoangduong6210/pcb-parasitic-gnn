#!/usr/bin/env python3
"""
Where does the GNN's ranking actually beat the analytical model? Map it cleanly by
ranking TWO kinds of design variation per base family:
  (Z) interleaving  - permute the P/S LAYER order (changes the z-gap). The analytical
                      Cps has z-distance in its formula, so PEEC SEES this.
  (XY) registration - shift the secondary laterally (changes the real x-y overlap).
                      The analytical overlap is min(L)*min(w), POSITION-BLIND, so PEEC
                      is blind to this - a real layout lever (P/S offset, spacing).
For each, compare the rank agreement vs the FEM-3D truth of the PEEC screener and the
GNN screener (family-disjoint). Expected: PEEC ranks Z well, XY poorly; GNN ranks both.
SLURM.
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


def z_variants(base, n, rng):
    """interleaving: permute layers (z-gap changes; PEEC sees this)."""
    out = []
    for _ in range(n):
        lay = copy.deepcopy(base); perm = rng.permutation(8)
        for t in lay["traces"]:
            t["layer"] = int(perm[t["layer"] % 8]); t["z_mm"] = t["layer"] * 0.18 + 0.05
        out.append(lay)
    return out


def xy_variants(base, n, rng):
    """registration: FIX layers, shift secondary laterally (x-y overlap changes;
    PEEC is position-blind to this)."""
    out = []
    for k in range(n):
        lay = copy.deepcopy(base)
        dx = float(rng.uniform(0.0, 32.0)); dy = float(rng.uniform(0.0, 4.0))
        for t in lay["traces"]:
            if t.get("net") == "sec":
                t["x0"] = t.get("x0", 0.0) + dx; t["y0"] = t.get("y0", 0.0) + dy
        out.append(lay)
    return out


def graph_of(lay):
    g = build_graph_from_planar_layout(lay); nf, ef, ei = g.to_feature_matrices()
    return {"node_feat": nf.astype(np.float32), "edge_feat": ef.astype(np.float32),
            "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": np.zeros(1, np.float32)}


def build_family(base, gen, rng):
    recs = []
    for lay in gen(base, 8, rng):
        fem = safe_fem_cps(lay, refine=0, timeout=90)
        if fem and fem > 0:
            recs.append({"g": graph_of(lay), "fem": fem,
                         "peec": compute_reference_labels_allpairs(lay)["Cps_pF"]})
    fem = [r["fem"] for r in recs]
    if len(recs) >= 4 and (max(fem) / min(fem) > 1.10):
        return recs
    return None


def _regret(pick, fem):
    return (fem[pick]-fem.min())/fem.min()*100.0


def decide(test_fams, model, work):
    pr, gr, rr = [], [], []
    with torch.no_grad():
        for fam in test_fams:
            fem = np.array([r["fem"] for r in fam]); peec = np.array([r["peec"] for r in fam])
            sc = model(collate([work(r["g"]) for r in fam])).squeeze(-1).numpy()
            pr.append(_regret(int(np.argmin(peec)), fem))
            gr.append(_regret(int(np.argmin(sc)), fem))
            rr.append(float(np.mean([_regret(k, fem) for k in range(len(fem))])))
    return {"peec_pick_regret_pct": round(float(np.mean(pr)),1),
            "gnn_pick_regret_pct": round(float(np.mean(gr)),1),
            "random_pick_regret_pct": round(float(np.mean(rr)),1), "n": len(test_fams)}


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    bases = [r["layout"] for r in layouts
             if any(t["net"] == "pri" for t in r["layout"]["traces"])
             and any(t["net"] == "sec" for t in r["layout"]["traces"])
             and len(r["layout"]["traces"]) <= 18][:90]
    rng = np.random.default_rng(31)
    print("[ranklat2] build Z (interleaving) + XY (registration) families", flush=True)
    zf, xyf = [], []; t0 = time.time()
    for b in bases:
        z = build_family(b, z_variants, rng); xy = build_family(b, xy_variants, rng)
        if z: zf.append(z)
        if xy: xyf.append(xy)
    print("   %d Z-families, %d XY-families (%.0fs)" % (len(zf), len(xyf), time.time()-t0), flush=True)

    # train one pairwise-ranking GNN on BOTH variation types (train split)
    nz = int(0.7*len(zf)); nxy = int(0.7*len(xyf))
    train_f = zf[:nz] + xyf[:nxy]
    allg = [r["g"] for fam in train_f for r in fam]
    nrm = Norm([{**g, "y": np.zeros(1, np.float32)} for g in allg], list(range(len(allg))))
    def work(g): return mk({**g, "y": np.zeros(1, np.float32)}, nrm)
    torch.manual_seed(0)
    model = PCBParasiticGNN(node_dim=allg[0]["node_feat"].shape[1], edge_dim=7, hidden=96, n_layers=4, n_targets=1)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    margin = nn.MarginRankingLoss(margin=1.0); rng2 = np.random.default_rng(1)
    for ep in range(120):
        model.train(); order = list(range(len(train_f))); rng2.shuffle(order)
        for fi in order:
            fam = train_f[fi]
            sc = model(collate([work(r["g"]) for r in fam])).squeeze(-1)
            fem = torch.tensor([r["fem"] for r in fam], dtype=torch.float32)
            i, j = torch.triu_indices(len(fam), len(fam), offset=1)
            sign = torch.sign(fem[i]-fem[j]); keep = sign != 0
            if keep.sum() == 0: continue
            loss = margin(sc[i][keep], sc[j][keep], sign[keep])
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
    model.eval()

    def eval_mode(test_fams):
        peec_r, gnn_r, peec_blind = [], [], 0
        with torch.no_grad():
            for fam in test_fams:
                fem = np.array([r["fem"] for r in fam]); peec = np.array([r["peec"] for r in fam])
                sc = model(collate([work(r["g"]) for r in fam])).squeeze(-1).numpy()
                if peec.max()-peec.min() < 1e-6: peec_blind += 1   # constant -> can't rank
                else:
                    rp,_ = spearmanr(peec, fem)
                    if not np.isnan(rp): peec_r.append(rp)
                rg,_ = spearmanr(sc, fem)
                if not np.isnan(rg): gnn_r.append(rg)
        return {"peec_rho_mean": round(float(np.mean(peec_r)),2) if peec_r else None,
                "peec_blind_frac": round(peec_blind/max(len(test_fams),1),2),
                "gnn_rho_mean": round(float(np.mean(gnn_r)),2) if gnn_r else None,
                "n": len(test_fams)}
    out = {"note": "GNN vs PEEC ranking by variation type (FEM-3D truth, family-disjoint)",
           "host": platform.node(),
           "Z_interleaving": eval_mode(zf[nz:]),
           "XY_registration": eval_mode(xyf[nxy:]),
           "XY_decision": decide(xyf[nxy:], model, work),
           "Z_decision": decide(zf[nz:], model, work)}
    od = ROOT / "05_experiments" / "run_declat"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_declat.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    z, xy = out["Z_interleaving"], out["XY_registration"]
    print("=> Z (interleaving): PEEC rho %s, GNN rho %s" % (z["peec_rho_mean"], z["gnn_rho_mean"]), flush=True)
    xyd = out["XY_decision"]; zd = out["Z_decision"]
    print("=> XY DECISION (pick lowest-Cps layout): PEEC-pick regret %.1f%% vs GNN-pick regret %.1f%% (random %.1f%%)"
          % (xyd["peec_pick_regret_pct"], xyd["gnn_pick_regret_pct"], xyd["random_pick_regret_pct"]), flush=True)
    print("=> Z DECISION: PEEC-pick regret %.1f%% vs GNN-pick regret %.1f%%" % (zd["peec_pick_regret_pct"], zd["gnn_pick_regret_pct"]), flush=True)
    print("=> XY (registration): PEEC rho %s (blind on %.0f%% of families), GNN rho %s"
          % (xy["peec_rho_mean"], 100*xy["peec_blind_frac"], xy["gnn_rho_mean"]), flush=True)


if __name__ == "__main__":
    main()
