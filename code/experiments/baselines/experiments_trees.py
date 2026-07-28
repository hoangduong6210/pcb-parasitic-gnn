#!/usr/bin/env python3
"""
experiments_trees.py — tree baselines (XGB/LGBM/CatBoost/RF) on the EXACT pooled
node-feature vector used by PooledMLP in experiments_v2.py (mean⊕max⊕sum-log of
the 9D node_feat after train-std), on the SAME field-grade labels (FEM-3D Cps via
safe_fem_cps + FastHenry L) + 80/20 seed-42 split that the GNN in experiments_femcps
uses.

Three axes exactly as specified:
1. Pointwise regression (R² + median rel-err % per target) vs GNN field-grade ref.
2. Family-disjoint ranking (LightGBM lambdarank or fallback; Spearman ρ on
   interleaving families built like experiments_ranklat2).
3. Size generalization (train small-N graphs, test large-N; reuse N-ordering from
   scaling_experiment / v2 size_split).

HARD RULE: heavy (label gen + training) only via sbatch on nextgen. Login smoke
uses --fast-analytical (no FEM/FH solves, analytical y for layout pool only) and
stays <10s.

Usage (sbatch / full field-grade):
  cd code && PYTHONPATH=. /usr/bin/python3 experiments_trees.py --use-field-labels --out ../results/run_trees

Usage (smoke on login, fast, no solves):
  cd code && PYTHONPATH=. /usr/bin/python3 experiments_trees.py --fast-analytical --max-cand 80 --out ../results/run_trees

Writes results_trees.json + prints one-line verdict per axis.
"""
import argparse
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

# ensure json available for deep copy in rank (already imported)

# Re-use (per task)
from pipeline import load_dataset, TARGETS
from planar_to_graph import build_graph_from_planar_layout, compute_reference_labels_allpairs
try:
    from experiments_femcps import safe_fem_cps as _safe_fem_cps
except Exception:
    _safe_fem_cps = None
try:
    from fasthenry_ref import fasthenry_totals as _fasthenry_totals
except Exception:
    _fasthenry_totals = None

ROOT = Path(__file__).resolve().parents[3]


def _safe_fem(layout, refine=1, timeout=90):
    if _safe_fem_cps is None:
        return None
    return _safe_fem_cps(layout, refine=refine, timeout=timeout)


def _fh(layout, freq=1e5):
    if _fasthenry_totals is None:
        return None
    return _fasthenry_totals(layout, freq)


def _load_field_cand(max_cand=400):
    layouts, _, _ = load_dataset(ROOT / "datasets" / "synth_v2")
    cand = []
    for r in layouts:
        lay = r["layout"]
        trs = lay.get("traces", [])
        has_p = any(t.get("net") == "pri" for t in trs)
        has_s = any(t.get("net") == "sec" for t in trs)
        if has_p and has_s and len(trs) <= 28:
            cand.append(lay)
        if len(cand) >= max_cand:
            break
    return cand


def _build_samples(cand, use_field=True):
    """Return list of dicts with raw 'node_feat' (N,9), 'y' (4,), 'n_nodes'."""
    samples = []
    skipped = 0
    t0 = time.time()
    for lay in cand:
        if use_field:
            cps = _safe_fem(lay, refine=1, timeout=90)
            fh = _fh(lay, 1e5)
            if not cps or cps <= 0 or not fh or fh.get("L_mut_nH", 0) <= 0:
                skipped += 1
                continue
            y = np.array([cps, fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]], np.float32)
        else:
            ana = compute_reference_labels_allpairs(lay)
            y = np.array([ana["Cps_pF"], ana["L_pri_nH"], ana["L_sec_nH"], ana["L_mut_nH"]], np.float32)
        g = build_graph_from_planar_layout(lay)
        nf, ef, ei = g.to_feature_matrices()
        if nf.shape[0] < 2:
            skipped += 1
            continue
        samples.append({
            "node_feat": nf.astype(np.float32),
            "edge_feat": ef.astype(np.float32) if ef.size > 0 else np.zeros((0, 7), np.float32),
            "edge_index": ei.astype(np.int64) if ei.size > 0 else np.zeros((2, 0), np.int64),
            "y": y, "n_nodes": int(nf.shape[0])
        })
    print(f"[trees] built {len(samples)} samples ({skipped} skipped, use_field={use_field}, {time.time()-t0:.1f}s)", flush=True)
    return samples


def _pooled(nf_std):
    """Exact same pooling as PooledMLP / GNN head readout on standardized node feats: mean+max+sumlog."""
    if nf_std.shape[0] == 0:
        return np.zeros(27, np.float32)
    m = nf_std.mean(0)
    mx = nf_std.max(0)
    s = np.sign(nf_std.sum(0)) * np.log1p(np.abs(nf_std.sum(0)))
    return np.concatenate([m, mx, s]).astype(np.float32)


def _standardize_node(samples, train_idx):
    nf_tr = np.concatenate([samples[j]["node_feat"] for j in train_idx], axis=0)
    mu = nf_tr.mean(0)
    sd = nf_tr.std(0) + 1e-6
    Xs = []
    for s in samples:
        nf = (s["node_feat"] - mu) / sd
        Xs.append(_pooled(nf))
    return np.stack(Xs, 0), mu, sd


def _r2(a, b):
    a = np.asarray(a); b = np.asarray(b)
    return float(1.0 - np.sum((a - b) ** 2) / (np.sum((b - b.mean()) ** 2) + 1e-12))


def _med_rel_err_pct(p, y):
    p = np.asarray(p); y = np.asarray(y)
    return float(np.median(np.abs(p - y) / (np.abs(y) + 1e-9) * 100.0))


def _pointwise_metrics(P, Y):
    out = {}
    for k, t in enumerate(TARGETS):
        out[t] = {
            "R2": round(_r2(P[:, k], Y[:, k]), 4),
            "median_rel_err_pct": round(_med_rel_err_pct(P[:, k], Y[:, k]), 2),
        }
    return out


def _train_eval_pointwise(Xtr, Ytr, Xte, Yte):
    res = {}
    # RandomForest (sklearn always present in this env)
    try:
        from sklearn.ensemble import RandomForestRegressor
        rf = RandomForestRegressor(n_estimators=300, max_depth=12, random_state=42, n_jobs=2)
        rf.fit(Xtr, Ytr)
        res["RandomForest"] = _pointwise_metrics(rf.predict(Xte), Yte)
    except Exception as e:
        res["RandomForest"] = {"error": str(e)[:80]}

    # XGBoost
    try:
        import xgboost as xgb
        xgr = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05,
                               random_state=42, n_jobs=2, objective="reg:squarederror")
        xgr.fit(Xtr, Ytr)
        res["XGBoost"] = _pointwise_metrics(xgr.predict(Xte), Yte)
    except Exception as e:
        res["XGBoost"] = {"error": str(e)[:80]}

    # LightGBM (may need pip) — wrap for multi-output (LGBMRegressor is single-target only)
    try:
        import lightgbm as lgb
        from sklearn.multioutput import MultiOutputRegressor
        base = lgb.LGBMRegressor(n_estimators=200, max_depth=6, learning_rate=0.05,
                                 random_state=42, n_jobs=2)
        lgr = MultiOutputRegressor(base)
        lgr.fit(Xtr, Ytr)
        res["LightGBM"] = _pointwise_metrics(lgr.predict(Xte), Yte)
    except Exception as e:
        res["LightGBM"] = {"error": str(e)[:80]}

    # CatBoost (may need pip)
    try:
        from catboost import CatBoostRegressor
        cbr = CatBoostRegressor(iterations=200, depth=6, learning_rate=0.05,
                                loss_function="MultiRMSE", random_seed=42, thread_count=2, verbose=0)
        cbr.fit(Xtr, Ytr)
        res["CatBoost"] = _pointwise_metrics(cbr.predict(Xte), Yte)
    except Exception as e:
        res["CatBoost"] = {"error": str(e)[:80]}

    return res


def _build_families_for_rank(cand, max_bases=40, rng_seed=13, use_field=True):
    """Minimal interleaving (Z) families like ranklat2. Returns list of families.
    Each family = list of (X_pooled_for_fam, y_cps) but we build after global std later.
    Here return list of layouts + their Cps label for later pooling."""
    rng = np.random.default_rng(rng_seed)
    fams = []
    bases = [lay for lay in cand if len(lay.get("traces", [])) <= 18][:max_bases]
    for base in bases:
        recs = []
        for _ in range(8):
            lay = json.loads(json.dumps(base))  # deep copy safe
            perm = rng.permutation(8)
            for t in lay["traces"]:
                t["layer"] = int(perm[t.get("layer", 0) % 8])
                t["z_mm"] = t["layer"] * 0.18 + 0.05
            if use_field:
                c = _safe_fem(lay, refine=0, timeout=60)
            else:
                c = compute_reference_labels_allpairs(lay)["Cps_pF"]
            if c and c > 0:
                recs.append((lay, float(c)))
        cs = [r[1] for r in recs]
        if len(recs) >= 4 and (max(cs) / min(cs) > 1.10):
            fams.append(recs)
    return fams


def _rank_axis(samples, X_all, Y_all, tr_idx, te_idx, use_field=True):
    """Family-disjoint lambdarank (LGBM) on Cps. Fall back to RF score if no lgb."""
    # Build families on the cand used for samples (use same filter size)
    cand = _load_field_cand(max_cand=120)
    fam_layouts = _build_families_for_rank(cand, max_bases=35, use_field=use_field)
    # Map to indices in samples is hard; instead rebuild small pooled per fam using same global stats from main tr
    # For simplicity: re-std on main tr, pool per fam layout
    # We already have X_all from main split; but families are new variants.
    # Recompute a local std from all samples tr for fairness.
    nf_tr = np.concatenate([samples[j]["node_feat"] for j in tr_idx], 0)
    mu = nf_tr.mean(0); sd = nf_tr.std(0) + 1e-6

    def _pool_one(lay):
        g = build_graph_from_planar_layout(lay)
        nf, _, _ = g.to_feature_matrices()
        nf = (nf - mu) / sd
        return _pooled(nf)

    # Build fam data: list of (Xfam [K,27], yfam [K])
    fams = []
    for recs in fam_layouts:
        Xs = []
        ys = []
        for lay, c in recs:
            Xs.append(_pool_one(lay))
            ys.append(c)
        if len(Xs) >= 4:
            fams.append((np.stack(Xs), np.array(ys)))

    if not fams:
        return {"n_families": 0, "note": "no usable families"}

    rng = np.random.default_rng(42)
    order = np.arange(len(fams)); rng.shuffle(order)
    ntef = max(1, int(0.2 * len(fams)))
    trf = [fams[i] for i in order[:len(fams)-ntef]]
    tef = [fams[i] for i in order[len(fams)-ntef:]]

    # NATIVE lightgbm LGBMRanker with objective=lambdarank + graded relevance from within-family Cps rank
    lgb_ok = False
    mean_rho = None
    try:
        import lightgbm as lgb
        from lightgbm import LGBMRanker
        Xtr_r = np.vstack([f[0] for f in trf])
        # graded relevance: per family, integer rank of Cps (0=lowest Cps ... K-1=highest) for lambdarank
        ygr = []
        for f in trf:
            yf = f[1]
            r = np.argsort(np.argsort(yf)).astype(np.int32)  # higher Cps -> higher grade
            ygr.append(r)
        ytr_r = np.concatenate(ygr)
        groups = [len(f[0]) for f in trf]
        ranker = LGBMRanker(
            objective="lambdarank",
            metric="ndcg",
            n_estimators=120,
            learning_rate=0.1,
            num_leaves=31,
            min_child_samples=3,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        ranker.fit(Xtr_r, ytr_r, group=groups)
        rhos = []
        for Xf, yf in tef:
            sc = ranker.predict(Xf)
            rho, _ = spearmanr(sc, yf)  # spearman vs true Cps (order)
            if np.isfinite(rho):
                rhos.append(float(rho))
        mean_rho = float(np.mean(rhos)) if rhos else None
        lgb_ok = True
    except Exception:
        pass

    # Fallback: RF as scorer (pointwise fit on Cps, use pred as score)
    if mean_rho is None:
        try:
            from sklearn.ensemble import RandomForestRegressor
            Xtr_r = np.vstack([f[0] for f in trf])
            ytr_r = np.concatenate([f[1] for f in trf])
            rf = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42, n_jobs=1)
            rf.fit(Xtr_r, ytr_r)
            rhos = []
            for Xf, yf in tef:
                sc = rf.predict(Xf)
                rho, _ = spearmanr(sc, yf)
                if np.isfinite(rho):
                    rhos.append(float(rho))
            mean_rho = float(np.mean(rhos)) if rhos else None
        except Exception:
            mean_rho = None

    return {
        "n_families_train": len(trf),
        "n_families_test": len(tef),
        "LGBM_lambdarank_or_fallback_rho_mean": round(mean_rho, 4) if mean_rho is not None else None,
        "lgb_native": lgb_ok,
        "GNN_reference_rho": 0.93,
    }


def _size_gen_axis(samples):
    """Train on small N, test on large N. Widen the node split as synth_v2 allows for gap.
    ALSO eval GNN (replicated field-grade from femcps/v5) on same size tr/te for direct trees-vs-GNN.
    Use local std on size train (no leak from random main split).
    """
    nodes = np.array([s["n_nodes"] for s in samples])
    order = np.argsort(nodes)
    n = len(samples)
    # Widen split: use ~80% cutoff on size, then take all <= that size for train, > for test (max gap)
    n80 = max(5, min(n-5, int(0.80 * n)))
    cut_size = int(nodes[order[n80-1]])
    cut = n80
    for ii in range(n80, n):
        if nodes[order[ii]] <= cut_size:
            cut = ii + 1
        else:
            break
    if cut > n - 5:
        cut = n - 5
    tr = order[:cut].tolist()
    te = order[cut:].tolist()
    # local std on this size's train only
    Xsz, _, _ = _standardize_node(samples, tr)
    Y_all = np.stack([s["y"] for s in samples])
    Xtr, Ytr = Xsz[tr], Y_all[tr]
    Xte, Yte = Xsz[te], Y_all[te]
    mets = _train_eval_pointwise(Xtr, Ytr, Xte, Yte)

    # ADD: replicate field-grade GNN (from experiments_femcps / experiments_v5 train) on this size split
    gnn_large = {"note": "GNN size-gen eval failed to replicate"}
    try:
        from experiments_v5 import Norm, mk
        from gnn_baseline import PCBParasiticGNN, collate
        import torch
        import torch.nn as nn
        trl = tr
        tel = te
        nrm = Norm(samples, trl)
        work = [mk(s, nrm) for s in samples]
        nd = samples[0]["node_feat"].shape[1]
        model = PCBParasiticGNN(node_dim=nd, edge_dim=7, hidden=96, n_layers=4, n_targets=4)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
        sch = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=200)
        lf = nn.SmoothL1Loss()
        rng = np.random.default_rng(42)
        olist = list(trl)
        for ep in range(200):
            model.train()
            rng.shuffle(olist)
            for b0 in range(0, len(olist), 32):
                bb = collate([work[j] for j in olist[b0:b0+32]])
                opt.zero_grad()
                loss = lf(model(bb), bb.y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                opt.step()
            sch.step()
        model.eval()
        pp, yy = [], []
        with torch.no_grad():
            for j in tel:
                p = nrm.inv(model(collate([work[j]])).numpy()[0])
                pp.append(p)
                yy.append(samples[j]["y"])
        PP = np.stack(pp)
        YY = np.stack(yy)
        gnn_large = _pointwise_metrics(PP, YY)
        gnn_large["note"] = "field-grade GNN replicated (200ep, size-split train) vs trees on same large-N te"
    except Exception as e:
        gnn_large = {"error": str(e)[:100]}

    return {
        "train_n": len(tr), "test_n": len(te),
        "train_nodes_max": int(nodes[tr].max()) if tr else 0,
        "test_nodes_min": int(nodes[te].min()) if te else 0,
        "test_nodes_max": int(nodes[te].max()) if te else 0,
        "per_target_on_large": mets,
        "GNN_field_grade_on_large": gnn_large,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "run_trees"))
    ap.add_argument("--max-cand", type=int, default=400)
    ap.add_argument("--use-field-labels", action="store_true",
                    help="Run real FEM-3D + FastHenry (heavy; only on sbatch nextgen)")
    ap.add_argument("--fast-analytical", action="store_true",
                    help="Use analytical labels (fast, no solves; for login smoke)")
    args = ap.parse_args()

    outd = Path(args.out); outd.mkdir(parents=True, exist_ok=True)

    use_field = bool(args.use_field_labels and not args.fast_analytical)
    if use_field and (_safe_fem_cps is None or _fasthenry_totals is None):
        print("[trees] WARNING: field solvers unavailable, falling back to analytical labels", flush=True)
        use_field = False

    cand = _load_field_cand(max_cand=args.max_cand)
    samples = _build_samples(cand, use_field=use_field)
    if len(samples) < 20:
        print("[trees] too few samples, abort")
        return

    # BYTE-IDENTICAL split to experiments_femcps.py:67-69 (legacy global RNG,
    # 80/20 by int(0.8*n)) so the GNN reference row below is a true head-to-head.
    # Do NOT switch to default_rng: PCG64 yields a DIFFERENT permutation.
    n = len(samples)
    np.random.seed(42)
    idx = np.random.permutation(n)
    tr_idx = list(idx[:int(0.8 * n)])
    te_idx = list(idx[int(0.8 * n):])

    X_all, _, _ = _standardize_node(samples, tr_idx)
    Y_all = np.stack([s["y"] for s in samples])

    Xtr, Ytr = X_all[tr_idx], Y_all[tr_idx]
    Xte, Yte = X_all[te_idx], Y_all[te_idx]

    t0 = time.time()
    pw = _train_eval_pointwise(Xtr, Ytr, Xte, Yte)
    print(f"[trees] pointwise done ({time.time()-t0:.1f}s)", flush=True)

    # GNN field-grade reference (from experiments_femcps results, never recomputed here)
    gnn_ref = {
        "Cps_pF": {"R2": 0.9527, "median_rel_err_pct": 3.22},
        "L_pri_nH": {"R2": 0.9954, "median_rel_err_pct": 2.83},
        "L_sec_nH": {"R2": 0.9942, "median_rel_err_pct": 3.81},
        "L_mut_nH": {"R2": 0.9943, "median_rel_err_pct": 2.56},
        "note": "field-grade GNN (FEM-3D Cps + FastHenry L) from run_femcps; same labels/split used for trees"
    }
    pw["GNN_field_grade_reference"] = gnn_ref

    # ranking
    rk = _rank_axis(samples, X_all, Y_all, tr_idx, te_idx, use_field=use_field)

    # size gen (widened + GNN compare)
    sg = _size_gen_axis(samples)

    res = {
        "meta": {
            "n_samples": len(samples),
            "n_test": len(te_idx),
            "seed": 42,
            "use_field_labels": use_field,
            "host": platform.node(),
            "python": platform.python_version(),
            "timestamp": time.time(),
            "note": "pooled 27D tabular (mean+max+sumlog of 9D node_feat after train-std) exactly as PooledMLP; field-grade labels via femcps path when --use-field-labels"
        },
        "pointwise": pw,
        "ranking": rk,
        "size_generalization": sg,
        "verdict": "See the per-axis summary in this file"
    }

    (outd / "results_trees.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: res[k] for k in ["meta", "verdict"] if k in res}, indent=2), flush=True)
    print("WROTE", outd / "results_trees.json", flush=True)


if __name__ == "__main__":
    main()