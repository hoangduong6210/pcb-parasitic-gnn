#!/usr/bin/env python3
"""
All four targets field-grade: relabel C_ps with FastCap 3-D and the three
inductances with FastHenry 3-D, retrain, validate the GNN against the held-out
3-D solvers. Also quantifies how far the analytical C_ps label (min-area overlap,
position-blind) is from the 3-D solver. Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from run_research13_pipeline import load_dataset, TARGETS
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from fasthenry_ref import fasthenry_totals
from fastcap_ref import fastcap_Cps
from experiments_v5 import Norm, mk

ROOT = Path(__file__).resolve().parents[1]


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    cand = [r for r in layouts
            if any(t["net"] == "pri" for t in r["layout"]["traces"])
            and any(t["net"] == "sec" for t in r["layout"]["traces"])
            and len(r["layout"]["traces"]) <= 28][:346]

    print("[allfield] FastCap C_ps + FastHenry L on %d layouts" % len(cand), flush=True)
    samples = []; ana_cps_err = []; t0 = time.time(); skip = 0
    for rec in cand:
        fh = fasthenry_totals(rec["layout"], 1e5)
        cps = fastcap_Cps(rec["layout"], nsub=2, order=2, timeout=90)
        if not fh or fh.get("L_mut_nH", 0) <= 0 or cps is None or cps <= 0:
            skip += 1; continue
        ana = compute_reference_labels_allpairs(rec["layout"])
        ana_cps_err.append(abs(ana["Cps_pF"] - cps) / cps * 100)
        g = build_graph_from_planar_layout(rec["layout"]); nf, ef, ei = g.to_feature_matrices()
        y = np.array([cps, fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]], np.float32)
        samples.append({"node_feat": nf.astype(np.float32), "edge_feat": ef.astype(np.float32),
                        "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": y})
    print("   %d samples (%d skipped, %.0fs); analytical-Cps vs FastCap median %.0f%%"
          % (len(samples), skip, time.time()-t0, np.median(ana_cps_err)), flush=True)

    seed = 42; torch.manual_seed(seed); np.random.seed(seed)
    n = len(samples); idx = np.random.permutation(n)
    tr, te = list(idx[:int(0.8*n)]), list(idx[int(0.8*n):])
    nrm = Norm(samples, tr); work = [mk(s, nrm) for s in samples]
    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=200)
    lf = nn.SmoothL1Loss(); order = list(tr)
    for ep in range(200):
        model.train(); np.random.shuffle(order)
        for i in range(0, len(order), 32):
            b = collate([work[j] for j in order[i:i+32]])
            opt.zero_grad(); lf(model(b), b.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
        sch.step()
    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for j in te:
            preds.append(nrm.inv(model(collate([work[j]])).numpy()[0])); ys.append(samples[j]["y"])
    preds, ys = np.stack(preds), np.stack(ys)
    r2 = lambda a, b: float(1 - np.sum((a-b)**2)/(np.sum((b-b.mean())**2)+1e-12))
    out = {"note": "all four targets field-grade: GNN vs FastCap-3D (Cps) + FastHenry-3D (L)",
           "host": platform.node(), "n_samples": len(samples), "n_test": len(te),
           "analytical_Cps_vs_fastcap_median_pct": round(float(np.median(ana_cps_err)), 1)}
    src = {"Cps_pF": "fastcap_3d", "L_pri_nH": "fasthenry_3d", "L_sec_nH": "fasthenry_3d", "L_mut_nH": "fasthenry_3d"}
    for k, t in enumerate(TARGETS):
        rel = np.abs(preds[:, k] - ys[:, k]) / (np.abs(ys[:, k]) + 1e-9) * 100
        out[t] = {"R2": round(r2(preds[:, k], ys[:, k]), 4),
                  "median_rel_err_pct": round(float(np.median(rel)), 2), "label_source": src[t]}
    od = ROOT / "05_experiments" / "run_allfield"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_allfield.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    for t in TARGETS:
        print("  %-9s R2=%.4f vs 3-D median %.2f%% [%s]" % (t, out[t]["R2"], out[t]["median_rel_err_pct"], out[t]["label_source"]), flush=True)


if __name__ == "__main__":
    main()
