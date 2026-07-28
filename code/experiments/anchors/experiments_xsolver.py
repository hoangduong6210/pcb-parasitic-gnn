#!/usr/bin/env python3
"""
experiments_xsolver.py — Q3 cross-solver validation (GNN trained on FastHenry L labels
from the field-grade femcps setup, validated on independent multi-filament Neumann
free-space L on the exact held-out 20%).

Proves GNN learns physics (agreement within inter-solver gap) not FastHenry idiosyncrasy.
HARD RULE: Neumann (and FH label) solves execute only inside SLURM jobs on compute nodes.
"""
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from pipeline import load_dataset, TARGETS
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
from fasthenry_ref import fasthenry_totals
from fem_inductance_ref import neumann_totals
from experiments_v5 import Norm, mk

ROOT = Path(__file__).resolve().parents[3]


def main():
    layouts, _, _ = load_dataset(ROOT / "datasets" / "synth_v2")
    cand = [r for r in layouts
            if any(t["net"] == "pri" for t in r["layout"]["traces"])
            and any(t["net"] == "sec" for t in r["layout"]["traces"])
            and len(r["layout"]["traces"]) <= 28][:346]

    print("[xsolver] field-grade FastHenry L + Neumann independent on held-out; n_cand=%d" % len(cand), flush=True)
    samples = []
    t0 = time.time()
    skip = 0
    for rec in cand:
        fh = fasthenry_totals(rec["layout"], 1e5)
        if not fh or fh.get("L_mut_nH", 0) <= 0:
            skip += 1
            continue
        ana = compute_reference_labels_allpairs(rec["layout"])
        # y uses ana Cps + FastHenry L (L supervision is field-grade; Cps only for multi-task compatibility)
        y = np.array([ana["Cps_pF"], fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]], np.float32)
        g = build_graph_from_planar_layout(rec["layout"])
        nf, ef, ei = g.to_feature_matrices()
        samples.append({
            "node_feat": nf.astype(np.float32),
            "edge_feat": ef.astype(np.float32),
            "edge_index": ei.astype(np.int64),
            "edge_dim": 7,
            "y": y,
            "layout": rec["layout"],
        })
    print("   %d samples (%d fh-skipped, %.0fs)" % (len(samples), skip, time.time() - t0), flush=True)

    seed = 42
    torch.manual_seed(seed)
    np.random.seed(seed)
    n = len(samples)
    idx = np.random.permutation(n)
    tr = list(idx[: int(0.8 * n)])
    te = list(idx[int(0.8 * n):])
    nrm = Norm(samples, tr)
    work = [mk(s, nrm) for s in samples]

    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    torch.set_num_threads(4)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=80)
    lf = nn.SmoothL1Loss()
    order = list(tr)
    for ep in range(80):
        model.train()
        np.random.shuffle(order)
        for i in range(0, len(order), 32):
            b = collate([work[j] for j in order[i:i + 32]])
            opt.zero_grad()
            lf(model(b), b.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
        sch.step()
        if (ep + 1) % 20 == 0 or ep == 0:
            print("    train ep %d/%d (%.0fs so far)" % (ep+1, 80, time.time()-t0), flush=True)
    model.eval()

    gnn_preds = []
    fh_ys = []
    neum_ys = []
    with torch.no_grad():
        for j in te:
            gnn_p = nrm.inv(model(collate([work[j]])).numpy()[0])
            gnn_preds.append(gnn_p)
            fh_ys.append(samples[j]["y"])
            lay = samples[j]["layout"]
            ne = neumann_totals(lay, nw=5, nt=2)
            # align order [Cps, Lp, Ls, Lm]; use ana C for consistency with train y
            ana_c = samples[j]["y"][0]
            yneu = np.array([ana_c, ne["L_pri_nH"], ne["L_sec_nH"], ne["L_mut_nH"]], np.float32)
            neum_ys.append(yneu)
    gnn_preds = np.stack(gnn_preds)
    fh_ys = np.stack(fh_ys)
    neum_ys = np.stack(neum_ys)

    r2 = lambda a, b: float(1 - np.sum((a - b)**2) / (np.sum((b - b.mean())**2) + 1e-12))

    out = {
        "note": "Q3 xsolver: GNN trained on FastHenry L (field-grade femcps setup) vs independent Neumann multi-filament; also FastHenry vs Neumann gap on held-out 20%",
        "host": platform.node(),
        "n_samples": len(samples),
        "n_test": len(te),
        "nw_nt_filament": [5, 2],
        "seed": 42,
    }
    LMAP = {"L_pri_nH": 1, "L_sec_nH": 2, "L_mut_nH": 3}
    for t in ["L_pri_nH", "L_sec_nH", "L_mut_nH"]:
        k = LMAP[t]
        g = gnn_preds[:, k]
        neu = neum_ys[:, k]
        fh = fh_ys[:, k]
        rel_gn = np.abs(g - neu) / (np.abs(neu) + 1e-9) * 100.0
        rel_fn = np.abs(fh - neu) / (np.abs(neu) + 1e-9) * 100.0
        out[f"GNN_vs_Neumann_{t}"] = {
            "R2": round(r2(g, neu), 4),
            "median_rel_err_pct": round(float(np.median(rel_gn)), 2),
        }
        out[f"FastHenry_vs_Neumann_{t}"] = {
            "R2": round(r2(fh, neu), 4),
            "median_rel_err_pct": round(float(np.median(rel_fn)), 2),
        }

    od = ROOT / "results" / "run_xsolver"
    od.mkdir(parents=True, exist_ok=True)
    (od / "results_xsolver.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    print("=== xsolver DONE ->", od / "results_xsolver.json", flush=True)


if __name__ == "__main__":
    main()
