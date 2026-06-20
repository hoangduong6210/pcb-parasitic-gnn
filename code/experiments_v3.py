#!/usr/bin/env python3
"""
experiments_v3.py — supplementary studies for this work.

(A) k-NN sparsity sweep: k in {4,8,16,32} -> accuracy (R^2 per target) and the
    mean edge count, to justify the k=8 operating point (accuracy vs sparsity).
(B) Capacity sweep: hidden width in {32,64,128} (layers=4) -> R^2, params, to
    show the model is not under/over-parameterised.

Reuses experiments_v2.train_eval. Runs on a compute cluster.
"""
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from run_research13_pipeline import load_dataset, build_samples, TARGETS
from scaling_experiment import knn_sparsify
from experiments_v2 import train_eval

ROOT = Path(__file__).resolve().parents[1]


def mean_knn_edges(samples, k):
    tot = 0
    for s in samples:
        ei, _ = knn_sparsify(s["node_feat"], k=k)
        tot += ei.shape[1]
    return tot / len(samples)


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v1")
    samples = build_samples(layouts, labels)
    epochs = 150
    res = {"meta": {"epochs": epochs, "host": platform.node(),
                    "torch": torch.__version__, "n_samples": len(samples)}}

    # (A) k-NN sparsity sweep
    print("[A] k-NN sparsity sweep")
    ksweep = []
    for k in [4, 8, 16, 32]:
        t0 = time.time()
        r = train_eval(samples, seed=42, epochs=epochs, edges="knn", knn_k=k)
        r["k"] = k
        r["mean_edges"] = round(mean_knn_edges(samples, k), 1)
        ksweep.append(r)
        print(f"   k={k}: edges~{r['mean_edges']}  R2(Cps)={r['per_target']['Cps_pF']['r2']}"
              f" R2(Lp)={r['per_target']['L_pri_nH']['r2']}  ({time.time()-t0:.0f}s)")
    res["knn_k_sweep"] = ksweep

    # (B) capacity sweep (hidden width, 4 layers)
    print("[B] capacity sweep (hidden width)")
    cap = []
    for h in [32, 64, 128]:
        t0 = time.time()
        r = train_eval(samples, seed=42, epochs=epochs, edges="dense", hidden=h, layers=4)
        r["hidden"] = h
        cap.append(r)
        print(f"   hidden={h}: params={r['n_params']}  R2(Cps)={r['per_target']['Cps_pF']['r2']}"
              f" R2(Lp)={r['per_target']['L_pri_nH']['r2']}  ({time.time()-t0:.0f}s)")
    res["capacity_sweep"] = cap

    out = ROOT / "05_experiments" / "run_v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results_v3.json").write_text(json.dumps(res, indent=2))
    print("=== DONE ->", out / "results_v3.json")


if __name__ == "__main__":
    main()
