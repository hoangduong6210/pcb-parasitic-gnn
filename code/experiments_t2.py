#!/usr/bin/env python3
"""
T2 — E(n)-equivariant + physics-informed GNN vs the invariant MPNN baseline.

Three comparisons (the novelty evidence):
  (A) full-data accuracy: equivariant vs MPNN (R2 per target).
  (B) SAMPLE EFFICIENCY: train both on 200 / 500 / 1500 samples; the equivariant
      inductive bias should generalise better with less data.
  (C) EQUIVARIANCE check: apply a random 3-D rotation to every layout's node
      coordinates and edge relative-vectors; the equivariant model's prediction
      must be (near-)unchanged. Demonstrates the built-in E(3) symmetry.
Runs on a compute cluster.
"""
import json, math, platform, time
from pathlib import Path
import numpy as np
import torch, torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from gnn_equivariant import PCBEquivariantGNN, count_params
from run_research13_pipeline import load_dataset, build_samples, TARGETS
from experiments_v5 import Norm, split, mk

ROOT = Path(__file__).resolve().parents[1]


def train_eval(model_class, samples, seed, epochs, n_train_cap=None, phys=True):
    torch.manual_seed(seed); np.random.seed(seed)
    tr, te = split(samples, seed, False)
    if n_train_cap:
        tr = tr[:n_train_cap]
    nrm = Norm(samples, tr)
    work = [mk(s, nrm) for s in samples]
    node_dim = samples[0]["node_feat"].shape[1]
    model = model_class(node_dim=node_dim, edge_dim=7, hidden=96, n_layers=4, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    lossf = nn.SmoothL1Loss(); rng = np.random.default_rng(seed)
    for ep in range(epochs):
        model.train(); order = tr.copy(); rng.shuffle(order)
        for i in range(0, len(order), 32):
            b = collate([work[j] for j in order[i:i+32]])
            opt.zero_grad(); pred = model(b)
            loss = lossf(pred, b.y)
            if phys:   # physics-informed: penalise predicted-negative parasitics
                yphys = nrm.inv(pred.detach().cpu().numpy())
                loss = loss + 0.01 * torch.relu(-pred).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
        sch.step()
    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for j in te:
            preds.append(nrm.inv(model(collate([work[j]])).numpy()[0])); ys.append(samples[j]["y"])
    preds, ys = np.stack(preds), np.stack(ys)
    r2 = lambda a, b: float(1 - np.sum((a-b)**2)/(np.sum((b-b.mean())**2)+1e-12))
    per = {t: round(r2(preds[:,k], ys[:,k]), 4) for k, t in enumerate(TARGETS)}
    return model, nrm, work, te, per


def rotate_layout_feats(work_item, R):
    """Apply 3-D rotation R to node xyz (cols 0:3) and edge rel-vec (cols 2:5)."""
    w = dict(work_item)
    nf = w["node_feat"].copy()
    nf[:, :3] = nf[:, :3] @ R.T
    w["node_feat"] = nf
    ef = w["edge_feat"].copy()
    if ef.size:
        ef[:, 2:5] = ef[:, 2:5] @ R.T
        w["edge_feat"] = ef
    return w


EPOCHS = 150

def _save(res):
    od = ROOT / "05_experiments" / "run_t2"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t2.json").write_text(json.dumps(res, indent=2)); print("   [saved]", flush=True)

def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v2")
    samples = build_samples(layouts, labels)
    res = {"meta": {"host": platform.node(), "n": len(samples)}}

    # (A) full-data accuracy
    print("[A] full-data: equivariant vs MPNN", flush=True)
    m_eq, nrm_eq, work_eq, te_eq, per_eq = train_eval(PCBEquivariantGNN, samples, 42, EPOCHS)
    _, _, _, _, per_mp = train_eval(PCBParasiticGNN, samples, 42, EPOCHS)
    res["full_data"] = {"equivariant_r2": per_eq, "mpnn_r2": per_mp,
                        "equivariant_params": count_params(m_eq)}
    print("   eq:", per_eq, "\n   mp:", per_mp, flush=True); _save(res)

    # (B) sample efficiency (cap=1500 ~= full, so just 200/800)
    print("[B] sample efficiency (cap train set)", flush=True)
    se = {}
    for cap in [200, 800]:
        _, _, _, _, pe = train_eval(PCBEquivariantGNN, samples, 42, EPOCHS, n_train_cap=cap)
        _, _, _, _, pm = train_eval(PCBParasiticGNN, samples, 42, EPOCHS, n_train_cap=cap)
        se[str(cap)] = {"equivariant_Lp_r2": pe["L_pri_nH"], "mpnn_Lp_r2": pm["L_pri_nH"],
                        "equivariant_Lm_r2": pe["L_mut_nH"], "mpnn_Lm_r2": pm["L_mut_nH"]}
        print(f"   cap={cap}: eq Lp/Lm={pe['L_pri_nH']}/{pe['L_mut_nH']}  mp={pm['L_pri_nH']}/{pm['L_mut_nH']}", flush=True)
        res["sample_efficiency"] = se; _save(res)

    # (C) equivariance check on the equivariant model (rotate test layouts)
    print("[C] equivariance check (random 3-D rotation)")
    rng = np.random.default_rng(0)
    A = rng.standard_normal((3, 3)); Q, _ = np.linalg.qr(A)
    if np.linalg.det(Q) < 0: Q[:, 0] = -Q[:, 0]
    R = Q.astype(np.float32)
    drifts = []
    with torch.no_grad():
        for j in te_eq[:40]:
            base = nrm_eq.inv(m_eq(collate([work_eq[j]])).numpy()[0])
            rot = nrm_eq.inv(m_eq(collate([rotate_layout_feats(work_eq[j], R)])).numpy()[0])
            drifts.append(float(np.median(np.abs(rot - base) / (np.abs(base) + 1e-9) * 100)))
    res["equivariance_check"] = {"median_pred_drift_under_rotation_pct": round(float(np.median(drifts)), 4),
                                 "note": "equivariant model output should be ~invariant to board rotation"}
    print("   median prediction drift under rotation: %.4f%%" % res["equivariance_check"]["median_pred_drift_under_rotation_pct"])

    od = ROOT / "05_experiments" / "run_t2"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t2.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "meta"}, indent=2))


if __name__ == "__main__":
    main()
