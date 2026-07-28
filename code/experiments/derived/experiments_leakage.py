#!/usr/bin/env python3
"""
experiments_leakage.py — do the raw targets compose into a genuine PARASITIC?

`L_p` and `L_s` are air-core winding self-inductances, and `M` is the winding
mutual. None of the three is, on its own, a parasitic: with a ferrite core the
measured primary inductance is dominated by the magnetizing term. The quantity
that *is* unambiguously parasitic — it causes the ringing a snubber has to
absorb — is the LEAKAGE inductance, obtained from the same three numbers:

    k       = M / sqrt(L_p * L_s)            coupling coefficient
    L_leak  = L_p * (1 - k^2)                primary-referred leakage

This script derives both from the SAME field-grade model, corpus, and split as
`experiments_femcps.py`, and reports how accurately each is recovered.

The interesting risk is arithmetic, not physical. On these tightly interleaved
planar layouts k ~ 0.98, so `1 - k^2` ~ 0.03: `L_leak` is a small difference of
two large, strongly correlated numbers. First-order propagation gives

    d(1-k^2) = 2k*dk   ->   rel_err(L_leak) ~ (2k^2 / (1-k^2)) * rel_err(k)

i.e. a ~55x amplification at k=0.98. Whether the surrogate's correlated errors
partially cancel is an empirical question, which is why this is measured rather
than argued. Either outcome is reportable: a usable leakage prediction is a new
result; an unusable one is an honest limit that justifies reporting the raw
three.

Run (heavy — FEM + FastHenry per layout; use SLURM):
    python3 experiments_leakage.py --out ../results/run_leakage
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import torch.nn as nn

from planar_to_graph import build_graph_from_planar_layout
from fasthenry_ref import fasthenry_totals
from experiments_femcps import safe_fem_cps
from experiments_v5 import Norm, mk
from gnn_baseline import PCBParasiticGNN, collate
from pipeline import load_dataset

ROOT = Path(__file__).resolve().parents[3]
EPS = 1e-12


def coupling_and_leakage(lp, ls, m):
    """k and primary-referred leakage from the 2-port mutual-inductance model.

    `L_p`/`L_s` are per-net (self + intra-net mutual) sums and `M` the inter-net
    mutual sum, which is exactly a two-coil coupled-inductor description, so the
    textbook k / L_leak identities apply. k is clipped below 1: a physical
    coupling cannot exceed unity, and a *predicted* triple can violate that.
    """
    denom = np.sqrt(np.maximum(lp * ls, EPS))
    k = m / denom
    k_clipped = np.clip(k, -0.999999, 0.999999)
    l_leak = lp * (1.0 - k_clipped ** 2)
    return k, k_clipped, l_leak


def r2(a, b):
    return float(1 - np.sum((a - b) ** 2) / (np.sum((b - b.mean()) ** 2) + EPS))


def stats(pred, ref):
    rel = np.abs(pred - ref) / (np.abs(ref) + EPS) * 100
    return {
        "R2": round(r2(pred, ref), 4),
        "median_rel_err_pct": round(float(np.median(rel)), 2),
        "mean_rel_err_pct": round(float(np.mean(rel)), 2),
        "p90_rel_err_pct": round(float(np.percentile(rel, 90)), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "run_leakage"))
    ap.add_argument("--epochs", type=int, default=200)
    args = ap.parse_args()

    # ---- corpus: byte-identical selection to experiments_femcps -------------
    layouts, _, _ = load_dataset(ROOT / "datasets" / "synth_v2")
    cand = [r for r in layouts
            if any(t["net"] == "pri" for t in r["layout"]["traces"])
            and any(t["net"] == "sec" for t in r["layout"]["traces"])
            and len(r["layout"]["traces"]) <= 28][:346]
    print(f"[leak] field-grade labels on {len(cand)} candidate layouts", flush=True)

    samples = []
    t0 = time.time(); skip = 0
    for rec in cand:
        fh = fasthenry_totals(rec["layout"], 1e5)
        cps = safe_fem_cps(rec["layout"], refine=1, timeout=90)
        if not fh or fh.get("L_mut_nH", 0) <= 0 or cps is None or cps <= 0:
            skip += 1
            continue
        g = build_graph_from_planar_layout(rec["layout"])
        nf, ef, ei = g.to_feature_matrices()
        y = np.array([cps, fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]], np.float32)
        samples.append({"node_feat": nf.astype(np.float32),
                        "edge_feat": ef.astype(np.float32),
                        "edge_index": ei.astype(np.int64), "edge_dim": 7, "y": y})
    print(f"   built {len(samples)} samples ({skip} skipped, {time.time()-t0:.0f}s)",
          flush=True)
    if len(samples) < 40:
        print("[leak] too few samples, abort", flush=True)
        return 1

    # ---- split: byte-identical to experiments_femcps.py:67-69 --------------
    seed = 42
    torch.manual_seed(seed); np.random.seed(seed)
    n = len(samples)
    idx = np.random.permutation(n)
    tr, te = list(idx[:int(0.8 * n)]), list(idx[int(0.8 * n):])

    nrm = Norm(samples, tr)
    work = [mk(s, nrm) for s in samples]
    model = PCBParasiticGNN(node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
                            hidden=96, n_layers=4, n_targets=4)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    lf = nn.SmoothL1Loss(); order = list(tr)
    for _ in range(args.epochs):
        model.train(); np.random.shuffle(order)
        for i in range(0, len(order), 32):
            b = collate([work[j] for j in order[i:i + 32]])
            opt.zero_grad(); lf(model(b), b.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step()
        sch.step()

    model.eval()
    preds, ys = [], []
    with torch.no_grad():
        for j in te:
            preds.append(nrm.inv(model(collate([work[j]])).numpy()[0]))
            ys.append(samples[j]["y"])
    preds, ys = np.stack(preds), np.stack(ys)

    # columns: 0=Cps 1=L_pri 2=L_sec 3=L_mut
    k_p, k_pc, leak_p = coupling_and_leakage(preds[:, 1], preds[:, 2], preds[:, 3])
    k_r, k_rc, leak_r = coupling_and_leakage(ys[:, 1], ys[:, 2], ys[:, 3])

    raw = {t: stats(preds[:, i], ys[:, i])
           for i, t in enumerate(("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"))}

    # amplification predicted by first-order propagation, vs what we measured
    amp_theory = float(np.median(2 * k_rc ** 2 / (1 - k_rc ** 2)))
    rel_k = float(np.median(np.abs(k_p - k_r) / (np.abs(k_r) + EPS) * 100))
    rel_leak = float(np.median(np.abs(leak_p - leak_r) / (np.abs(leak_r) + EPS) * 100))

    out = {
        "note": ("Derived parasitics: coupling k and primary-referred leakage "
                 "L_leak = L_p(1-k^2), from the SAME field-grade model/corpus/"
                 "split as run_femcps. Tests whether the raw air-core triple "
                 "composes into a usable parasitic."),
        "host": platform.node(),
        "n_samples": len(samples), "n_test": len(te), "seed": seed,
        "raw_targets": raw,
        "k_reference": {
            "median": round(float(np.median(k_r)), 4),
            "min": round(float(k_r.min()), 4),
            "max": round(float(k_r.max()), 4),
            "n_unphysical_gt1_reference": int((k_r > 1.0).sum()),
            "n_unphysical_gt1_predicted": int((k_p > 1.0).sum()),
        },
        "derived": {
            "k": stats(k_pc, k_rc),
            "L_leak_nH": stats(leak_p, leak_r),
        },
        "leakage_fraction_of_Lp_pct": {
            "median": round(float(np.median(leak_r / (ys[:, 1] + EPS) * 100)), 2),
            "min": round(float((leak_r / (ys[:, 1] + EPS) * 100).min()), 2),
            "max": round(float((leak_r / (ys[:, 1] + EPS) * 100).max()), 2),
        },
        "error_amplification": {
            "median_k_rel_err_pct": round(rel_k, 3),
            "median_L_leak_rel_err_pct": round(rel_leak, 2),
            "measured_amplification": round(rel_leak / (rel_k + 1e-9), 1),
            "first_order_prediction_2k2_over_1mk2": round(amp_theory, 1),
        },
    }

    od = Path(args.out); od.mkdir(parents=True, exist_ok=True)
    (od / "results_leakage.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)
    print(f"\n[leak] k median={out['k_reference']['median']}  "
          f"L_leak is {out['leakage_fraction_of_Lp_pct']['median']}% of L_p", flush=True)
    print(f"[leak] rel-err  k={rel_k:.3f}%  ->  L_leak={rel_leak:.2f}%  "
          f"(amplification {out['error_amplification']['measured_amplification']}x, "
          f"first-order predicted {amp_theory:.1f}x)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
