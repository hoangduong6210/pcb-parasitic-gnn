#!/usr/bin/env python3
"""
experiments_v4.py — panel round-1 response experiments.

(A) Independent INDUCTANCE validation: total mutual inductance L_m (sum over all
    primary-secondary pairs) from an independent multi-filament (FastHenry-style) Neumann solve vs the
    analytical PEEC label AND the trained GNN prediction. Mirrors the existing
    capacitance FEM validation, for the inductive output (panel CRITICAL).

(B) GENERALIZATION (size extrapolation): train on the SMALLER graphs, test on the
    LARGEST ones, reporting R^2 on the held-out large boards -- the regime the
    speedup story targets but never previously validated for accuracy.

Runs on a compute cluster.
"""
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from gnn_baseline import PCBParasiticGNN, collate
from fem_inductance_ref import fem_pair_mutual_nh
from run_research13_pipeline import load_dataset, build_samples, TARGETS
from experiments_v2 import train_eval

ROOT = Path(__file__).resolve().parents[1]


def fem_total_mutual(layout):
    trs = layout["traces"]
    pri = [t for t in trs if t["net"] == "pri"]
    sec = [t for t in trs if t["net"] == "sec"]
    tot = 0.0
    for a in pri:
        for b in sec:
            h = abs(b.get("z_mm", 0.3) - a.get("z_mm", 0.1))
            ov = min(a["length_mm"], b["length_mm"])
            tot += fem_pair_mutual_nh(a["width_mm"], b["width_mm"],
                                      a.get("thick_mm", 0.07), h, ov)
    return tot


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v1")
    samples = build_samples(layouts, labels)
    labmap = {d["id"]: d for d in labels}
    res = {"meta": {"host": platform.node(), "torch": torch.__version__,
                    "n_samples": len(samples)}}

    # ---- (A) independent inductance validation ----
    print("[A] independent multi-filament (FastHenry-style) L_m validation")
    ck = torch.load(ROOT / "05_experiments" / "run_v1" / "gnn_checkpoint.pt", map_location="cpu")
    nf_mean, nf_std = (np.array(x) for x in ck["node_norm"])
    ef_mean, ef_std = (np.array(x) for x in ck["edge_norm"])
    y_mean, y_std = (np.array(x) for x in ck["y_log_norm"])
    model = PCBParasiticGNN(node_dim=9, edge_dim=7, hidden=ck["config"]["hidden"],
                            n_layers=ck["config"]["layers"], n_targets=4)
    model.load_state_dict(ck["state_dict"]); model.eval()
    LM_IDX = TARGETS.index("L_mut_nH")

    sel = [r for r in layouts if any(t["net"] == "pri" for t in r["layout"]["traces"])
           and any(t["net"] == "sec" for t in r["layout"]["traces"])][-12:]
    rows = []
    for rec in sel:
        fem = fem_total_mutual(rec["layout"])
        peec = labmap[rec["id"]]["L_mut_nH"]
        nf = ((np.asarray(rec["node_feat"], np.float32) - nf_mean) / nf_std).astype(np.float32)
        ef = np.asarray(rec["edge_feat"], np.float32)
        ef = ((ef - ef_mean) / ef_std).astype(np.float32) if ef.size else ef
        s = {"node_feat": nf, "edge_feat": ef,
             "edge_index": np.asarray(rec["edge_index"], np.int64), "edge_dim": 7,
             "y": np.zeros(4, np.float32)}
        with torch.no_grad():
            yl = model(collate([s])).numpy()[0] * y_std + y_mean
        gnn = float((np.sign(yl) * np.expm1(np.abs(yl)))[LM_IDX])
        if fem > 0:
            rows.append({"id": rec["id"], "fem_Lm_nH": round(fem, 2),
                         "peec_Lm_nH": round(peec, 2), "gnn_Lm_nH": round(gnn, 2),
                         "peec_vs_fem_pct": round(abs(peec - fem) / fem * 100, 2),
                         "gnn_vs_fem_pct": round(abs(gnn - fem) / fem * 100, 2)})
    pv = np.array([r["peec_vs_fem_pct"] for r in rows])
    gv = np.array([r["gnn_vs_fem_pct"] for r in rows])
    res["inductance_fem_validation"] = {
        "n_layouts": len(rows),
        "peec_vs_fem_median_pct": round(float(np.median(pv)), 2),
        "gnn_vs_fem_median_pct": round(float(np.median(gv)), 2),
        "note": "total mutual L_m vs independent multi-filament (FastHenry-style) Neumann-integral solve",
        "rows": rows}
    print("   ", res["inductance_fem_validation"]["peec_vs_fem_median_pct"],
          res["inductance_fem_validation"]["gnn_vs_fem_median_pct"])

    # ---- (B) generalization: train small, test large ----
    print("[B] generalization: train on small graphs, test on largest")
    gen = train_eval(samples, seed=42, epochs=200, size_split=True)
    res["generalization_size_split"] = {
        "train_nodes_max": gen["train_nodes_max"],
        "test_nodes_min": gen["test_nodes_min"], "test_nodes_max": gen["test_nodes_max"],
        "per_target_r2": {t: gen["per_target"][t]["r2"] for t in TARGETS},
        "per_target_rmse": {t: gen["per_target"][t]["rmse"] for t in TARGETS}}
    print("   train<=%d nodes, test %d-%d nodes, R2:" % (
        gen["train_nodes_max"], gen["test_nodes_min"], gen["test_nodes_max"]),
        res["generalization_size_split"]["per_target_r2"])

    # also a random-split reference at same epochs for apples-to-apples
    ref = train_eval(samples, seed=42, epochs=200, size_split=False)
    res["random_split_reference"] = {
        "per_target_r2": {t: ref["per_target"][t]["r2"] for t in TARGETS}}

    out = ROOT / "05_experiments" / "run_v4"; out.mkdir(parents=True, exist_ok=True)
    (out / "results_v4.json").write_text(json.dumps(res, indent=2))
    print("=== DONE ->", out / "results_v4.json")


if __name__ == "__main__":
    main()
