#!/usr/bin/env python3
"""
experiments_v2.py — the rigor pass for this work.

Adds, in one SLURM job:
  (A) Independent FEM ground truth: 2-D electrostatic scikit-fem capacitance vs
      the analytical Cps label on a subset -> validates the silver labels.
  (B) Multi-seed dense GNN (seeds 42/43/44) -> mean±std on all targets.
  (C) k-NN-graph GNN actually TRAINED + evaluated -> the sparse model that wins
      on speed now has a measured accuracy (closes the "untrained winner" gap).
  (D) Non-strawman baselines on the SAME reference:
        - MLP on pooled node-feature statistics (no message passing)
        - geometry-ablated GNN (spatial coords / edge geometry zeroed)
        - shallow GNN (2 layers) depth ablation
Writes 05_experiments/run_v2/results_v2.json.

Runs via sbatch on a compute node. No login-node compute.
"""
import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

from gnn_baseline import PCBParasiticGNN, collate
from scaling_experiment import knn_sparsify
from run_research13_pipeline import load_dataset, build_samples, old_peec_cps_baseline, TARGETS


# ----------------------------------------------------------------------------
def _standardize_fit(arrs):
    allv = np.concatenate([a for a in arrs if a.size], 0)
    return allv.mean(0), allv.std(0) + 1e-6


def prepare(samples, *, seed, edges="dense", ablate_geom=False, knn_k=8,
            size_split=False):
    """Return (work_samples, split) with edges/features per the experiment knobs.
    size_split=True => train on the SMALLER graphs, test on the LARGER ones
    (generalization / extrapolation to bigger boards), instead of a random split."""
    work = []
    for s in samples:
        nf = s["node_feat"].copy()
        if edges == "knn":
            ei, ef = knn_sparsify(nf, k=knn_k)
        else:
            ei, ef = s["edge_index"].copy(), s["edge_feat"].copy()
        if ablate_geom:
            nf[:, :3] = 0.0                      # zero node xyz
            if ef.size:
                ef[:, [0, 2, 3, 4]] = 0.0        # zero edge dist + rel-vec
        work.append({"node_feat": nf, "edge_feat": ef, "edge_index": ei,
                     "edge_dim": 7, "y_phys": s["y"].copy(), "layout": s["layout"],
                     "Cps_ref": s["Cps_ref"]})
    n = len(work)
    # targets: log1p standardize on all
    Y = np.stack([w["y_phys"] for w in work])
    Ylog = np.sign(Y) * np.log1p(np.abs(Y))
    y_mean, y_std = Ylog.mean(0), Ylog.std(0) + 1e-8
    # split
    if size_split:
        order = np.argsort([w["node_feat"].shape[0] for w in work])  # small -> large
        nte = max(1, int(0.2 * n))
        train_idx = order[:n - nte]      # smaller graphs
        test_idx = order[n - nte:]       # largest graphs (extrapolation)
    else:
        rng = np.random.default_rng(seed)
        idx = np.arange(n); rng.shuffle(idx)
        nte = max(1, int(0.2 * n)); test_idx, train_idx = idx[:nte], idx[nte:]
    # feature standardize on train
    nf_mean, nf_std = _standardize_fit([work[j]["node_feat"] for j in train_idx])
    ef_mean, ef_std = _standardize_fit([work[j]["edge_feat"] for j in train_idx] or [np.zeros((1, 7))])
    for w in work:
        w["node_feat"] = ((w["node_feat"] - nf_mean) / nf_std).astype(np.float32)
        if w["edge_feat"].size:
            w["edge_feat"] = ((w["edge_feat"] - ef_mean) / ef_std).astype(np.float32)
        yl = (np.sign(w["y_phys"]) * np.log1p(np.abs(w["y_phys"])) - y_mean) / y_std
        w["y"] = yl.astype(np.float32)
    return work, train_idx, test_idx, (y_mean, y_std)


def _from_norm(yn, y_mean, y_std):
    yl = yn * y_std + y_mean
    return np.sign(yl) * np.expm1(np.abs(yl))


class PooledMLP(nn.Module):
    """Baseline: pool node features (mean⊕max⊕sum), NO message passing."""
    def __init__(self, node_dim=9, hidden=128, n_targets=4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(3 * node_dim, hidden), nn.SiLU(),
            nn.Linear(hidden, hidden), nn.SiLU(),
            nn.Linear(hidden, n_targets))

    def forward(self, b):
        from gnn_baseline import _scatter_mean, _scatter_max, _scatter_sum
        h = b.node_feat
        gm = _scatter_mean(h, b.batch_index, b.n_graphs)
        gx = _scatter_max(h, b.batch_index, b.n_graphs)
        gs = _scatter_sum(h, b.batch_index, b.n_graphs)
        gs = torch.sign(gs) * torch.log1p(gs.abs())
        return self.net(torch.cat([gm, gx, gs], -1))


def train_eval(samples, *, seed, epochs, edges="dense", ablate_geom=False,
               model_kind="gnn", layers=4, hidden=96, lr=2e-3, batch_size=32,
               knn_k=8, size_split=False):
    torch.manual_seed(seed); np.random.seed(seed)
    work, train_idx, test_idx, (y_mean, y_std) = prepare(
        samples, seed=seed, edges=edges, ablate_geom=ablate_geom, knn_k=knn_k,
        size_split=size_split)
    node_dim = work[0]["node_feat"].shape[1]
    if model_kind == "mlp":
        model = PooledMLP(node_dim=node_dim, hidden=128, n_targets=4)
    else:
        model = PCBParasiticGNN(node_dim=node_dim, edge_dim=7, hidden=hidden,
                                n_layers=layers, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    lossf = nn.SmoothL1Loss()
    rng = np.random.default_rng(seed)
    for ep in range(epochs):
        model.train()
        order = train_idx.copy(); rng.shuffle(order)
        for i in range(0, len(order), batch_size):
            sel = order[i:i + batch_size]
            b = collate([work[j] for j in sel])
            opt.zero_grad()
            loss = lossf(model(b), b.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
        sched.step()
    # eval
    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for j in test_idx:
            preds.append(_from_norm(model(collate([work[j]])).numpy()[0], y_mean, y_std))
            ys.append(work[j]["y_phys"])
    preds, ys = np.stack(preds), np.stack(ys)

    def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))
    def r2(a, b):
        return float(1 - np.sum((a - b) ** 2) / (np.sum((b - b.mean()) ** 2) + 1e-12))

    per = {t: {"rmse": round(rmse(preds[:, k], ys[:, k]), 4),
               "r2": round(r2(preds[:, k], ys[:, k]), 4)}
           for k, t in enumerate(TARGETS)}
    # old baseline cps on same test
    old = []
    for j in test_idx:
        trs = work[j]["layout"]["traces"]
        n_p = sum(1 for t in trs if t["net"] == "pri"); n_s = sum(1 for t in trs if t["net"] == "sec")
        old.append(old_peec_cps_baseline(n_p, n_s, work[j]["layout"]["board_w_mm"] * 0.7))
    old_rmse = rmse(np.array(old), ys[:, 0])
    test_nodes = [int(work[j]["node_feat"].shape[0]) for j in test_idx]
    train_nodes = [int(work[j]["node_feat"].shape[0]) for j in train_idx]
    return {"per_target": per, "cps_r2": per["Cps_pF"]["r2"],
            "cps_rmse": per["Cps_pF"]["rmse"], "old_cps_rmse": round(old_rmse, 4),
            "n_params": sum(p.numel() for p in model.parameters()),
            "test_nodes_min": min(test_nodes), "test_nodes_max": max(test_nodes),
            "train_nodes_max": max(train_nodes)}


def fem_ground_truth(layouts, n_subset=24):
    """Independent FEM vs analytical Cps on a representative pri-sec pair."""
    from fem_capacitance_ref import fem_pair_capacitance_pf
    from trace_peec import Trace, trace_capacitance_pf
    rels = []
    done = 0
    for rec in layouts:
        if done >= n_subset:
            break
        trs = rec["layout"]["traces"]
        pri = next((t for t in trs if t["net"] == "pri"), None)
        sec = next((t for t in trs if t["net"] == "sec"), None)
        if not pri or not sec:
            continue
        h = abs(sec.get("z_mm", 0.3) - pri.get("z_mm", 0.1))
        ov = min(pri["length_mm"], sec["length_mm"])
        eps_r = rec["layout"].get("eps_r", 4.2)
        c_fem = fem_pair_capacitance_pf(pri["width_mm"], sec["width_mm"],
                                        pri.get("thick_mm", 0.07), h, ov, eps_r)
        tp = Trace(0, 0, pri.get("z_mm", 0.1), pri["length_mm"], pri["width_mm"], pri.get("thick_mm", 0.07), "pri")
        tsx = Trace(0, 0, sec.get("z_mm", 0.3), sec["length_mm"], sec["width_mm"], sec.get("thick_mm", 0.07), "sec")
        c_ana = trace_capacitance_pf(tp, tsx, eps_r)
        if c_fem > 0 and c_ana > 0:
            rels.append(abs(c_ana - c_fem) / c_fem * 100.0)
            done += 1
    rels = np.array(rels)
    return {"n": int(len(rels)),
            "mean_abs_rel_err_pct": round(float(rels.mean()), 2),
            "median_abs_rel_err_pct": round(float(np.median(rels)), 2),
            "max_abs_rel_err_pct": round(float(rels.max()), 2),
            "note": "analytical Cps label vs independent 2-D scikit-fem electrostatic solve, representative pri-sec pair"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../03_datasets/synth_v1")
    ap.add_argument("--out", default="../05_experiments/run_v2")
    ap.add_argument("--epochs", type=int, default=200)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    layouts, labels, meta = load_dataset(Path(args.data))
    samples = build_samples(layouts, labels)
    print(f"[v2] {len(samples)} samples")

    res = {"meta": {"epochs": args.epochs, "device": "cpu",
                    "torch": torch.__version__, "host": platform.node(),
                    "n_samples": len(samples)}}

    # (A) FEM ground truth
    print("[A] FEM ground-truth cross-check ...")
    t0 = time.time()
    res["fem_ground_truth"] = fem_ground_truth(layouts, n_subset=24)
    print("    ", res["fem_ground_truth"], f"({time.time()-t0:.1f}s)")

    # (B) multi-seed dense GNN
    print("[B] multi-seed dense GNN ...")
    seeds = [42, 43, 44]
    runs = [train_eval(samples, seed=s, epochs=args.epochs) for s in seeds]
    def agg(key_fn):
        v = np.array([key_fn(r) for r in runs]); return round(float(v.mean()), 4), round(float(v.std()), 4)
    res["dense_gnn_multiseed"] = {
        "seeds": seeds,
        "n_params": runs[0]["n_params"],
        "per_target_r2_mean_std": {t: {"mean": agg(lambda r, t=t: r["per_target"][t]["r2"])[0],
                                       "std": agg(lambda r, t=t: r["per_target"][t]["r2"])[1]}
                                   for t in TARGETS},
        "per_target_rmse_mean_std": {t: {"mean": agg(lambda r, t=t: r["per_target"][t]["rmse"])[0],
                                         "std": agg(lambda r, t=t: r["per_target"][t]["rmse"])[1]}
                                     for t in TARGETS},
        "cps_acc_improvement_x_mean": round(float(np.mean([r["old_cps_rmse"]/max(r["cps_rmse"],1e-9) for r in runs])), 2),
        "runs": runs,
    }
    print("    dense R2(Cps) mean/std:", res["dense_gnn_multiseed"]["per_target_r2_mean_std"]["Cps_pF"])

    # (C) k-NN trained GNN
    print("[C] k-NN-graph GNN (trained) ...")
    res["knn_gnn"] = train_eval(samples, seed=42, epochs=args.epochs, edges="knn")
    print("    knn R2(Cps):", res["knn_gnn"]["cps_r2"])

    # (D) baselines / ablations
    print("[D] baselines + ablations ...")
    res["baseline_pooled_mlp"] = train_eval(samples, seed=42, epochs=args.epochs, model_kind="mlp")
    res["ablation_no_geometry"] = train_eval(samples, seed=42, epochs=args.epochs, ablate_geom=True)
    res["ablation_shallow_2layer"] = train_eval(samples, seed=42, epochs=args.epochs, layers=2)
    print("    mlp R2(Cps):", res["baseline_pooled_mlp"]["cps_r2"],
          "| no-geom R2(Cps):", res["ablation_no_geometry"]["cps_r2"],
          "| 2-layer R2(Cps):", res["ablation_shallow_2layer"]["cps_r2"])

    (out / "results_v2.json").write_text(json.dumps(res, indent=2))
    print("=== DONE -> ", out / "results_v2.json")
    print(json.dumps({k: (v if not isinstance(v, dict) else "...") for k, v in res.items()}, indent=2))


if __name__ == "__main__":
    main()
