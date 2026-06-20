#!/usr/bin/env python3
"""
make_figures.py — generate the support figures for this work from REAL
run artifacts (results.json, scaling.json, predictions.json). Light matplotlib
only (no compute); writes both PDF (for LaTeX) and PNG to 08_figures/.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "05_experiments"
FIG = ROOT / "08_figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 150, "savefig.bbox": "tight",
                     # IEEE PDF eXpress compliance: embed TrueType (Type 42),
                     # NEVER Type 3 (which PDF eXpress rejects).
                     "pdf.fonttype": 42, "ps.fonttype": 42})

results = json.loads((EXP / "run_v1" / "results.json").read_text())
scaling = json.loads((EXP / "scaling_v1" / "scaling.json").read_text())
pred_p = EXP / "run_v1" / "predictions.json"
preds = json.loads(pred_p.read_text()) if pred_p.exists() else None
v2_p = EXP / "run_v2" / "results_v2.json"
v2 = json.loads(v2_p.read_text()) if v2_p.exists() else None


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)
    print("wrote", name)


# ---- Fig 1: pipeline overview ------------------------------------------------
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(7.2, 1.9))
    ax.set_xlim(0, 10); ax.set_ylim(0.62, 3.18); ax.axis("off")
    boxes = [
        (0.6, "Planar PCB\nlayout\n(8-layer foils)", "#ededed"),
        (3.0, "PCB graph\nnodes=traces\nedges=couplings", "#d9d9d9"),
        (5.4, "Geometry-aware\nMPNN\n(275k params)", "#c2c2c2"),
        (7.8, "parasitic vector\n$C_{ps},L_{p},L_{s},L_{m}$", "#f2f2f2"),
    ]
    for x, txt, c in boxes:
        ax.add_patch(FancyBboxPatch((x, 0.9), 1.7, 1.25, boxstyle="round,pad=0.05",
                     fc=c, ec="#000000", lw=1.0))
        ax.text(x + 0.85, 1.52, txt, ha="center", va="center", fontsize=8.2)
    for x in (2.3, 4.7, 7.1):
        ax.add_patch(FancyArrowPatch((x, 1.52), (x + 0.7, 1.52),
                     arrowstyle="-|>", mutation_scale=14, color="#000000", lw=1.4))
    # inset: an actual little graph (nodes = traces) under the "PCB graph" box,
    # showing dense all-pairs vs sparse k-NN edges, so the figure carries content.
    rng = np.random.default_rng(3)
    gx = np.array([2.55, 3.05, 3.55, 2.7, 3.4, 3.0])
    gz = np.array([2.62, 2.78, 2.6, 2.42, 2.45, 2.92])
    # dense edges (light) — all pairs
    for i in range(len(gx)):
        for j in range(i + 1, len(gx)):
            ax.plot([gx[i], gx[j]], [gz[i], gz[j]], color="#b0b0b0", lw=0.4, zorder=1)
    # k-NN edges (bold green) — each node to 2 nearest
    for i in range(len(gx)):
        d = (gx - gx[i]) ** 2 + (gz - gz[i]) ** 2
        for j in np.argsort(d)[1:3]:
            ax.plot([gx[i], gx[j]], [gz[i], gz[j]], color="#000000", lw=1.2, zorder=2)
    ax.scatter(gx, gz, s=22, color="#000000", zorder=3, edgecolors="white", linewidths=0.5)
    ax.text(3.05, 3.02, "graph: nodes=traces", ha="center", fontsize=6.0, color="#222222")
    ax.text(5.0, 2.74, "edges: dense all-pairs (light)\nvs sparse $k$-NN (bold)",
            ha="left", fontsize=6.2, color="#222222")
    save(fig, "fig1_pipeline")


# ---- Fig 2: parity plots -----------------------------------------------------
def fig_parity():
    if preds is None:
        print("skip parity (no predictions.json yet)"); return
    ref = np.array(preds["ref"]); pr = np.array(preds["pred"])
    names = preds["targets"]; units = ["pF", "nH", "nH", "nH"]
    fig, axs = plt.subplots(1, 4, figsize=(7.2, 2.0), constrained_layout=True)
    for k, ax in enumerate(axs):
        r, p = ref[:, k], pr[:, k]
        ax.scatter(r, p, s=6, alpha=0.45, color="#454545", edgecolors="none")
        lo, hi = min(r.min(), p.min()), max(r.max(), p.max())
        ax.plot([lo, hi], [lo, hi], "k--", lw=0.9)
        ss_res = np.sum((p - r) ** 2); ss_tot = np.sum((r - r.mean()) ** 2) + 1e-12
        r2 = 1 - ss_res / ss_tot
        nice = {"Cps_pF": "$C_{ps}$", "L_pri_nH": "$L_p$", "L_sec_nH": "$L_s$", "L_mut_nH": "$L_m$"}.get(names[k], names[k])
        ax.set_title(f"{nice}  $R^2$={r2:.4f}", fontsize=8.5)
        ax.set_xlabel(f"PEEC ref ({units[k]})", fontsize=7.5)
        if k == 0:
            ax.set_ylabel("GNN prediction", fontsize=8)
        ax.tick_params(labelsize=6.5)
    save(fig, "fig2_parity")


# ---- Fig 3: baselines & ablations (grouped bar, per-target RMSE) -------------
def fig_baselines():
    if v2 is None:
        print("skip baselines (no results_v2.json)"); return
    tn = ["Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"]
    short = ["$C_{ps}$", "$L_p$", "$L_s$", "$L_m$"]
    models = [
        ("Dense GNN", v2["dense_gnn_multiseed"]["runs"][0]["per_target"], "#4d4d4d", ""),
        ("k-NN GNN", v2["knn_gnn"]["per_target"], "#8c8c8c", "///"),
        ("No rel-geom GNN", v2["ablation_no_geometry"]["per_target"], "#cccccc", "\\\\\\"),
        ("Pooled MLP", v2["baseline_pooled_mlp"]["per_target"], "#ffffff", "xxx"),
    ]
    x = np.arange(len(tn)); w = 0.2
    fig, ax = plt.subplots(figsize=(3.7, 2.7))
    for i, (name, per, c, hatch) in enumerate(models):
        vals = [per[t]["rmse"] for t in tn]
        ax.bar(x + (i - 1.5) * w, vals, w, label=name, color=c, hatch=hatch,
               edgecolor="black", linewidth=0.6)
    ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels(short)
    ax.set_ylabel("test RMSE (pF / nH, log)")
    ax.set_title("Baselines & ablations")
    # headroom so the legend never overlaps the tall MLP bars
    ymin, ymax = ax.get_ylim()
    ax.set_ylim(ymin, ymax * 6)
    ax.legend(fontsize=6.2, ncol=2, loc="upper left", framealpha=0.95)
    save(fig, "fig3_baselines")


# ---- Fig 4: wall-time scaling (the money figure) ----------------------------
def fig_scaling():
    rows = scaling["rows"]
    N = [r["N_traces"] for r in rows]
    ref = [r["t_ref_ms"] for r in rows]
    dense = [r["t_gnn_dense_ms"] for r in rows]
    knn = [r["t_gnn_knn_ms"] for r in rows]
    fig, ax = plt.subplots(figsize=(3.7, 2.8))
    ax.loglog(N, ref, marker="o", ls="-", color="k", mfc="white", label="all-pairs PEEC  (O($N^2$))")
    ax.loglog(N, dense, marker="s", ls="--", color="0.5", label="dense GNN")
    ax.loglog(N, knn, marker="^", ls="-.", color="k", lw=1.8, label="sparse k-NN GNN  ($\\approx$O($N$))")
    co = scaling["knn_beats_ref_at_N"]
    ax.axvline(co, color="k", ls=":", lw=0.8)
    ax.text(co*1.05, ax.get_ylim()[0]*2, f"crossover\nN={co}", fontsize=7, color="0.2")
    ax.set_xlabel("board size N (trace segments)")
    ax.set_ylabel("forward time / sample (ms)")
    ax.set_title("Wall-time scaling (timing only)")
    ax.legend(fontsize=6.6, loc="upper left")
    save(fig, "fig4_scaling")


if __name__ == "__main__":
    fig_pipeline()
    fig_baselines()
    fig_scaling()
    fig_parity()
    print("figures ->", FIG)
