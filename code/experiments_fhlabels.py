#!/usr/bin/env python3
"""
Field-grade ALL inductances: the self-L audit showed the analytical Grover labels
for L_pri/L_sec are ~50% off FastHenry 3-D (like the mutual). Honest fix: relabel
all three inductances with FastHenry 3-D, retrain, and validate the trained GNN
against held-out FastHenry. C_ps keeps its analytical/2-D-FEM label (screening).
Outcome: how many of the four targets are field-grade vs a 3-D field solver.
Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from run_research13_pipeline import load_dataset, TARGETS
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from fasthenry_ref import fasthenry_totals
from experiments_v5 import Norm, mk

ROOT = Path(__file__).resolve().parents[1]


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    cand = [r for r in layouts
            if any(t["net"] == "pri" for t in r["layout"]["traces"])
            and any(t["net"] == "sec" for t in r["layout"]["traces"])
            and len(r["layout"]["traces"]) <= 22][:550]

    print("[fhlabels] FastHenry 3-D relabel of L_pri/L_sec/L_mut on %d layouts" % len(cand), flush=True)
    samples = []; t0 = time.time(); skip = 0
    for rec in cand:
        fh = fasthenry_totals(rec["layout"], 1e5)
        if not fh or fh.get("L_mut_nH", 0) <= 0:
            skip += 1; continue
        ana = compute_reference_labels_allpairs(rec["layout"])
        g = build_graph_from_planar_layout(rec["layout"]); nf, ef, ei = g.to_feature_matrices()
        y = np.array([ana["Cps_pF"], fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]], np.float32)
        samples.append({"node_feat": nf.astype(np.float32), "edge_feat": ef.astype(np.float32),
                        "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": y})
    print("   %d samples (%d skipped, %.0fs)" % (len(samples), skip, time.time()-t0), flush=True)

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

    # validate GNN vs the FastHenry labels on held-out (field-grade if low %)
    preds, ys = [], []
    with torch.no_grad():
        for j in te:
            preds.append(nrm.inv(model(collate([work[j]])).numpy()[0])); ys.append(samples[j]["y"])
    preds, ys = np.stack(preds), np.stack(ys)
    r2 = lambda a, b: float(1 - np.sum((a-b)**2)/(np.sum((b-b.mean())**2)+1e-12))
    out = {"note": "GNN retrained on FastHenry-3D inductance labels, validated vs held-out FastHenry",
           "host": platform.node(), "n_samples": len(samples), "n_test": len(te)}
    for k, t in enumerate(TARGETS):
        rel = np.abs(preds[:, k] - ys[:, k]) / (np.abs(ys[:, k]) + 1e-9) * 100
        out[t] = {"R2": round(r2(preds[:, k], ys[:, k]), 4),
                  "median_rel_err_pct": round(float(np.median(rel)), 2),
                  "label_source": "fasthenry_3d" if t.startswith("L_") else "analytical_2dFEM"}
    od = ROOT / "05_experiments" / "run_fhlabels"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_fhlabels.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    for t in TARGETS:
        print("  %-9s R2=%.4f  vs FastHenry median %.2f%%  [%s]"
              % (t, out[t]["R2"], out[t]["median_rel_err_pct"], out[t]["label_source"]), flush=True)


if __name__ == "__main__":
    main()
