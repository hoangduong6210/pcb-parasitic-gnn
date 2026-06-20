#!/usr/bin/env python3
"""
T3 — frequency-dependent prediction: the GNN predicts the primary-winding
R_ac/R_dc(f) curve (skin/proximity rise) from the layout, validated against a
FastHenry 3-D frequency sweep. Extends the lumped-scalar surrogate to a
frequency-resolved quantity, the AC loss EMI design actually needs.
Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from fasthenry_ref import fasthenry_Rac_curve
from run_research13_pipeline import load_dataset
from planar_to_graph import build_graph_from_planar_layout
from experiments_v5 import Norm, split, mk

ROOT = Path(__file__).resolve().parents[1]
FREQS = np.logspace(4, 8, 21)   # 10 kHz .. 100 MHz (FastHenry picks its grid)


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v2")
    # smaller layouts solve fast under filament subdivision; skin physics is the same
    cand = [r for r in layouts
            if any(t["net"] == "pri" for t in r["layout"]["traces"])
            and len(r["layout"]["traces"]) <= 20][:450]

    print("[T3] FastHenry R_ac/R_dc(f) sweep on %d small layouts" % len(cand))
    samples = []; grid = None; t0 = time.time(); skipped = 0
    for rec in cand:
        cur = fasthenry_Rac_curve(rec["layout"], FREQS, nhinc=2, nwinc=2, timeout=120)
        if cur is None:
            skipped += 1; continue
        fs, ratio = cur
        if grid is None:
            grid = fs
        if len(ratio) != len(grid):
            continue
        g = build_graph_from_planar_layout(rec["layout"])
        nf, ef, ei = g.to_feature_matrices()
        samples.append({"node_feat": nf.astype(np.float32),
                        "edge_feat": ef.astype(np.float32),
                        "edge_index": ei.astype(np.int64), "edge_dim": 7,
                        "y": ratio.astype(np.float32)})
    nT = len(grid)
    print("   built %d samples (%d skipped), %d freq points (%.0fs)" % (len(samples), skipped, nT, time.time()-t0))

    # train PCBParasiticGNN with nT curve outputs
    seed = 42; torch.manual_seed(seed); np.random.seed(seed)
    tr, te = split(samples, seed, False)
    nrm = Norm(samples, tr)
    work = [mk(s, nrm) for s in samples]
    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=nT)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=200)
    lf = nn.SmoothL1Loss(); rng = np.random.default_rng(seed)
    for ep in range(200):
        model.train(); order = tr.copy(); rng.shuffle(order)
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
    # per-point median relative error across the curve
    relerr = np.abs(preds - ys) / (np.abs(ys) + 1e-9) * 100
    r2 = lambda a, b: float(1 - np.sum((a-b)**2)/(np.sum((b-b.mean())**2)+1e-12))
    out = {"note": "GNN R_ac/R_dc(f) curve vs FastHenry 3-D sweep",
           "host": platform.node(), "n_samples": len(samples), "n_test": len(te),
           "n_freq_points": nT, "freqs_hz": [float(x) for x in grid],
           "curve_median_relerr_pct": round(float(np.median(relerr)), 3),
           "curve_r2": round(r2(preds.ravel(), ys.ravel()), 5),
           "mean_true_curve": [round(float(x), 3) for x in ys.mean(0)],
           "mean_pred_curve": [round(float(x), 3) for x in preds.mean(0)]}
    od = ROOT / "05_experiments" / "run_t3"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t3.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k not in ("freqs_hz",)}, indent=2))
    print("=> GNN predicts the FastHenry R_ac/R_dc(f) curve to %.1f%% median, R2=%.4f"
          % (out["curve_median_relerr_pct"], out["curve_r2"]))


if __name__ == "__main__":
    main()
