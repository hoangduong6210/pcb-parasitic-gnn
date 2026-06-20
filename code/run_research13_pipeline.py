#!/usr/bin/env python3
"""
run_research13_pipeline.py — GNN training + honest evaluation for Topic 13.

Replaces the v0 Ridge-on-aggregates proof-of-concept with a REAL geometry-aware
message-passing GNN (engine in gnn_baseline.py) that predicts the four-element
graph-level parasitic vector [Cps, L_pri, L_sec, L_mut] against the full
O(N^2) all-pairs PEEC reference labels.

Honesty contract (every number below is measured, none hand-typed):
  * accuracy  : per-target RMSE and R^2 on a held-out 20% test split, in
                physical units (pF / nH).
  * old base  : the simplified single parallel-plate `peec_cps`-style scalar,
                scored against the SAME reference -> the accuracy-improvement
                factor is reference-anchored, not GNN-vs-GNN.
  * speedup   : measured GNN forward time per sample (median of repeated runs)
                vs the measured all-pairs reference time per sample
                (meta.ref_allpairs_ms_per_sample from generate_synth). If the
                GNN is NOT faster, the reported factor is < 1 and we say so.
  * provenance: hostname, device, torch version, n_params, seed written out.

Intended to run via sbatch on a compute node (: never heavy on login).
"""
import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from gnn_baseline import PCBParasiticGNN, collate, count_params


TARGETS = ["Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"]


def load_dataset(data_dir: Path):
    layouts = []
    with open(data_dir / "layouts.jsonl") as f:
        for line in f:
            layouts.append(json.loads(line))
    with open(data_dir / "labels.json") as f:
        labels = json.load(f)
    meta = {}
    meta_p = data_dir / "meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text())
    return layouts, labels, meta


def old_peec_cps_baseline(n_pri, n_sec, mlt_mm, inter_tape_mm=0.1, eps_r=3.4):
    """Simplified parallel-plate scalar (spirit of engine/peec_cps.py) — the
    pre-GNN baseline. One overlap-area estimate, no all-pairs accumulation."""
    layer_h = 0.8
    overlap = mlt_mm * layer_h * min(n_pri, n_sec) / max(4, 1)
    n_pairs = max(2, int((n_pri + n_sec) / 4))
    return 8.854e-3 * eps_r * overlap / inter_tape_mm * n_pairs   # pF


def build_samples(layouts, labels):
    by_id = {lab["id"]: lab for lab in labels}
    samples = []
    for rec in layouts:
        lab = by_id[rec["id"]]
        y = np.array([lab[t] for t in TARGETS], dtype=np.float32)
        samples.append({
            "node_feat": np.asarray(rec["node_feat"], dtype=np.float32),
            "edge_feat": np.asarray(rec["edge_feat"], dtype=np.float32),
            "edge_index": np.asarray(rec["edge_index"], dtype=np.int64),
            "edge_dim": 7,
            "y": y,
            "layout": rec["layout"],
            "Cps_ref": lab["Cps_pF"],
        })
    return samples


def iterate_minibatches(samples, idx, batch_size, device, shuffle, rng):
    order = idx.copy()
    if shuffle:
        rng.shuffle(order)
    for i in range(0, len(order), batch_size):
        sel = order[i:i + batch_size]
        yield collate([samples[j] for j in sel], device=device)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default="../03_datasets/synth_v0")
    ap.add_argument("--out", type=str, default="../05_experiments/run_v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--hidden", type=int, default=96)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-3)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] {data_dir}")
    layouts, labels, meta = load_dataset(data_dir)
    samples = build_samples(layouts, labels)
    n = len(samples)
    print(f"[load] {n} samples, device={device}")

    # --- target standardization (log1p for the heavy-tailed extensive sums) ---
    Y = np.stack([s["y"] for s in samples])                  # [n, 4], physical units
    Ylog = np.sign(Y) * np.log1p(np.abs(Y))
    y_mean = Ylog.mean(0)
    y_std = Ylog.std(0) + 1e-8

    def to_norm(y_phys):
        yl = np.sign(y_phys) * np.log1p(np.abs(y_phys))
        return (yl - y_mean) / y_std

    def from_norm(y_norm):
        yl = y_norm * y_std + y_mean
        return np.sign(yl) * np.expm1(np.abs(yl))

    for s in samples:
        s["y"] = to_norm(s["y"]).astype(np.float32)

    # --- split, then node/edge feature standardization (fit on train only) ---
    idx = np.arange(n)
    rng.shuffle(idx)
    n_test = max(1, int(0.2 * n))
    test_idx, train_idx = idx[:n_test], idx[n_test:]

    nf_all = np.concatenate([samples[j]["node_feat"] for j in train_idx], 0)
    nf_mean = nf_all.mean(0)
    nf_std = nf_all.std(0) + 1e-6
    ef_train = [samples[j]["edge_feat"] for j in train_idx if samples[j]["edge_feat"].size]
    ef_all = np.concatenate(ef_train, 0) if ef_train else np.zeros((1, 7))
    ef_mean = ef_all.mean(0)
    ef_std = ef_all.std(0) + 1e-6
    for s in samples:
        s["node_feat"] = ((s["node_feat"] - nf_mean) / nf_std).astype(np.float32)
        if s["edge_feat"].size:
            s["edge_feat"] = ((s["edge_feat"] - ef_mean) / ef_std).astype(np.float32)

    node_dim = samples[0]["node_feat"].shape[1]
    model = PCBParasiticGNN(node_dim=node_dim, edge_dim=7, hidden=args.hidden,
                            n_layers=args.layers, n_targets=len(TARGETS)).to(device)
    n_params = count_params(model)
    print(f"[model] PCBParasiticGNN params={n_params}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lossf = torch.nn.SmoothL1Loss()

    # --- training ---
    t_train0 = time.time()
    for ep in range(args.epochs):
        model.train()
        ep_loss = 0.0
        nb = 0
        for b in iterate_minibatches(samples, train_idx, args.batch_size, device, True, rng):
            opt.zero_grad()
            pred = model(b)
            loss = lossf(pred, b.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            ep_loss += loss.item()
            nb += 1
        sched.step()
        if (ep + 1) % 50 == 0 or ep == 0:
            print(f"[train] epoch {ep+1}/{args.epochs} loss={ep_loss/max(1,nb):.4f}")
    train_time = time.time() - t_train0

    # --- evaluation on held-out test set (physical units) ---
    model.eval()
    preds_norm, ys_norm = [], []
    with torch.no_grad():
        for j in test_idx:
            b = collate([samples[j]], device=device)
            preds_norm.append(model(b).cpu().numpy()[0])
            ys_norm.append(samples[j]["y"])
    preds_phys = np.stack([from_norm(p) for p in preds_norm])
    ys_phys = np.stack([from_norm(y) for y in ys_norm])

    def rmse(a, b):
        return float(np.sqrt(np.mean((a - b) ** 2)))

    def r2(a, b):
        ss_res = np.sum((a - b) ** 2)
        ss_tot = np.sum((b - b.mean()) ** 2) + 1e-12
        return float(1 - ss_res / ss_tot)

    per_target = {}
    for k, t in enumerate(TARGETS):
        per_target[t] = {
            "rmse": round(rmse(preds_phys[:, k], ys_phys[:, k]), 4),
            "r2": round(r2(preds_phys[:, k], ys_phys[:, k]), 4),
            "ref_mean": round(float(ys_phys[:, k].mean()), 4),
        }

    # --- old baseline (single parallel-plate scalar) vs reference Cps ---
    old_pred, ref_cps = [], []
    for j in test_idx:
        trs = samples[j]["layout"]["traces"]
        n_p = sum(1 for t in trs if t["net"] == "pri")
        n_s = sum(1 for t in trs if t["net"] == "sec")
        mlt = samples[j]["layout"]["board_w_mm"] * 0.7
        old_pred.append(old_peec_cps_baseline(n_p, n_s, mlt))
        ref_cps.append(samples[j]["Cps_ref"])
    old_pred = np.array(old_pred)
    ref_cps = np.array(ref_cps)
    old_rmse_cps = rmse(old_pred, ref_cps)
    gnn_rmse_cps = per_target["Cps_pF"]["rmse"]
    acc_improvement = round(old_rmse_cps / max(gnn_rmse_cps, 1e-9), 2)

    # --- honest inference timing (median of repeats) ---
    timing_batch = collate([samples[j] for j in test_idx], device=device)
    with torch.no_grad():
        for _ in range(3):                     # warmup
            _ = model(timing_batch)
        if device == "cuda":
            torch.cuda.synchronize()
        times = []
        for _ in range(20):
            t0 = time.perf_counter()
            _ = model(timing_batch)
            if device == "cuda":
                torch.cuda.synchronize()
            times.append(time.perf_counter() - t0)
    gnn_ms_per_sample = float(np.median(times) / len(test_idx) * 1000)
    ref_ms_per_sample = float(meta.get("ref_allpairs_ms_per_sample", 0.0))
    speedup = round(ref_ms_per_sample / gnn_ms_per_sample, 2) if gnn_ms_per_sample > 0 else None

    results = {
        "model": "PCBParasiticGNN (geometry-aware MPNN, pure-torch, PyG-free)",
        "n_params": n_params,
        "n_samples": n,
        "n_train": len(train_idx),
        "n_test": len(test_idx),
        "avg_nodes": meta.get("avg_nodes"),
        "avg_edges": meta.get("avg_edges"),
        "targets": TARGETS,
        "per_target": per_target,
        "old_baseline_rmse_Cps_pF": round(old_rmse_cps, 4),
        "gnn_rmse_Cps_pF": gnn_rmse_cps,
        "cps_accuracy_improvement_x": acc_improvement,
        "train_time_s": round(train_time, 2),
        "gnn_infer_ms_per_sample": round(gnn_ms_per_sample, 5),
        "ref_allpairs_ms_per_sample": round(ref_ms_per_sample, 5),
        "speedup_vs_ref_allpairs_x": speedup,
        "speedup_note": ("GNN forward (batched, median of 20) vs measured "
                         "O(N^2) all-pairs PEEC reference; <1 would mean slower."),
        "seed": args.seed,
        "epochs": args.epochs,
        "device": device,
        "torch_version": torch.__version__,
        "hostname": platform.node(),
    }

    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    torch.save({"state_dict": model.state_dict(),
                "node_norm": [nf_mean.tolist(), nf_std.tolist()],
                "edge_norm": [ef_mean.tolist(), ef_std.tolist()],
                "y_log_norm": [y_mean.tolist(), y_std.tolist()],
                "config": vars(args)}, out_dir / "gnn_checkpoint.pt")

    print("=== RESULTS ===")
    print(json.dumps(results, indent=2))
    print(f"Saved -> {out_dir/'results.json'} and gnn_checkpoint.pt")


if __name__ == "__main__":
    main()
