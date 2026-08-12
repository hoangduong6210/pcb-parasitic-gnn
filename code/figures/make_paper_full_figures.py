#!/usr/bin/env python3
"""Generate Paper_Full vector figures from released proof-update results."""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "Paper_Full"
os.environ.setdefault("MPLCONFIGDIR", str(PAPER / ".mplconfig"))

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


OUT = PAPER / "figures"
OUT.mkdir(parents=True, exist_ok=True)
DATA = json.loads((REPO / "results" / "proof_updates" / "results.json").read_text())

# Neutral palette: every RGB triplet has equal channels, so figures remain
# unambiguous in grayscale print, photocopies, and color-blind workflows.
BLACK = "#111111"
DARK = "#444444"
MID = "#777777"
LIGHT = "#C8C8C8"
PALE = "#F2F2F2"
WHITE = "#FFFFFF"
GRID = "#D6D6D6"

SINGLE_COLUMN = 3.45
DOUBLE_COLUMN = 7.15

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.0,
    "axes.labelsize": 8.0,
    "axes.titlesize": 8.7,
    "axes.edgecolor": BLACK,
    "axes.labelcolor": BLACK,
    "axes.titlecolor": BLACK,
    "xtick.color": BLACK,
    "ytick.color": BLACK,
    "text.color": BLACK,
    "legend.fontsize": 7.2,
    "hatch.color": BLACK,
    "hatch.linewidth": 0.65,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
    "pdf.fonttype": 42,
})


def save(fig: plt.Figure, name: str) -> None:
    for suffix in ("pdf", "png"):
        # Remove wall-clock metadata so regenerated artifacts are byte-for-byte stable.
        metadata = (
            {"Creator": "code/figures/make_paper_full_figures.py", "CreationDate": None, "ModDate": None}
            if suffix == "pdf"
            else {"Software": "code/figures/make_paper_full_figures.py"}
        )
        fig.savefig(
            OUT / f"{name}.{suffix}",
            dpi=240 if suffix == "png" else None,
            metadata=metadata,
        )
    plt.close(fig)


def box(ax, xy, width, height, title, lines, facecolor=WHITE):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor=facecolor, edgecolor=BLACK, linewidth=1.25,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height * 0.72, title,
            ha="center", va="center", weight="bold", color=BLACK, fontsize=7.8)
    ax.text(xy[0] + width / 2, xy[1] + height * 0.34, lines,
            ha="center", va="center", color=BLACK, fontsize=7.3, linespacing=1.25)


def pipeline() -> None:
    fig, ax = plt.subplots(figsize=(DOUBLE_COLUMN, 2.35))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    xs = [0.02, 0.215, 0.41, 0.605, 0.80]
    titles = ["PCB layout", "Encoded graph", "Graph surrogate", "Four outputs", "Design decision"]
    lines = [
        "foil geometry\nnet and layer",
        "trace nodes\npair metadata",
        "distance messages\nshared weights",
        "$C_{ps}, L_p, L_s, M$\nsolver-supervised",
        "absolute estimate\nand pairwise rank",
    ]
    fills = [WHITE, PALE, WHITE, PALE, WHITE]
    for x, title, line, fill in zip(xs, titles, lines, fills):
        box(ax, (x, 0.35), 0.16, 0.34, title, line, fill)
    for left, right in zip(xs[:-1], xs[1:]):
        ax.add_patch(FancyArrowPatch((left + 0.16, 0.52), (right, 0.52),
                                    arrowstyle="-|>", mutation_scale=10,
                                    color=BLACK, linewidth=1.05))
    ax.plot([0.375, 0.375], [0.15, 0.82], linestyle=(0, (4, 2)), color=BLACK, linewidth=1.1)
    ax.text(0.375, 0.88, "strict $E(3)$ claim starts here", ha="center", color=BLACK, fontsize=8)
    ax.text(0.375, 0.10, "axis-aligned graph construction is outside the symmetry guarantee",
            ha="center", color=BLACK, fontsize=7.2)
    save(fig, "fig1_pipeline_scope")


def field_accuracy() -> None:
    field = DATA["field_accuracy_corpus"]
    targets = [r"$C_{ps}$", r"$L_p$", r"$L_s$", r"$M$"]
    analytical = [field["analytical_median_error_pct"][k] for k in ("Cps", "Lp", "Ls", "M")]
    gnn = [field["gnn_median_error_pct"][k] for k in ("Cps", "Lp", "Ls", "M")]
    x = np.arange(4); width = 0.36
    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN, 2.55), constrained_layout=True)
    ax.bar(
        x - width / 2,
        analytical,
        width,
        label="analytical label",
        color=MID,
        edgecolor=BLACK,
        linewidth=0.8,
        hatch="////",
    )
    ax.bar(
        x + width / 2,
        gnn,
        width,
        label="solver-supervised GNN",
        color=WHITE,
        edgecolor=BLACK,
        linewidth=0.8,
        hatch="....",
    )
    ax.set_yscale("log"); ax.set_ylabel("median relative error (%)")
    ax.set_ylim(1.2, 420)
    ax.set_xticks(x, targets); ax.grid(axis="y", which="both", color=GRID, linewidth=0.55)
    ax.legend(frameon=False, ncol=1, loc="upper right", handlelength=1.6)
    for xpos, value in zip(x - width/2, analytical):
        ax.text(xpos, value*1.11, f"{value:g}", ha="center", va="bottom", fontsize=7)
    for xpos, value in zip(x + width/2, gnn):
        ax.text(xpos, value*1.12, f"{value:.1f}", ha="center", va="bottom", fontsize=7)
    ax.set_title("Solver supervision reduces reference error", pad=5)
    save(fig, "fig2_field_accuracy")


def equivariance() -> None:
    strict = DATA["strict_e3"]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(DOUBLE_COLUMN, 2.65),
        gridspec_kw={"width_ratios": [1.05, 1.35]},
        constrained_layout=True,
    )
    ax = axes[0]
    effects = [strict["full_data_primary"]["relative_delta_pct"],
               strict["same_width_sensitivity"]["relative_delta_pct"]]
    lows = [strict["full_data_primary"]["ci95_pct"][0],
            strict["same_width_sensitivity"]["ci95_pct"][0]]
    highs = [strict["full_data_primary"]["ci95_pct"][1],
             strict["same_width_sensitivity"]["ci95_pct"][1]]
    y = np.array([1, 0])
    ax.errorbar(
        effects,
        y,
        xerr=[np.array(effects) - lows, np.array(highs) - effects],
        fmt="o",
        markerfacecolor=WHITE,
        markeredgecolor=BLACK,
        color=BLACK,
        ecolor=BLACK,
        capsize=3,
        markersize=5,
    )
    ax.axvline(0, color=BLACK, lw=0.8)
    ax.axvspan(-2, 2, color=LIGHT, alpha=0.55)
    ax.set_yticks(y, ["parameter-matched", "same width"])
    ax.set_xlabel("strict EGNN error change (%)\nnegative favors strict")
    ax.set_title("Accuracy effect (95% CI)")
    ax.set_ylim(-0.45, 1.55)
    ax.grid(axis="x", color=GRID, linewidth=0.55)
    ax.text(0, 1.34, r"predeclared $\pm2\%$ margin", color=BLACK,
            ha="center", va="bottom", fontsize=7.2)

    ax = axes[1]
    n = np.asarray(strict["learning_curve"]["n_train"])
    inv = np.asarray(strict["learning_curve"]["invariant_mean_error"])
    egnn = np.asarray(strict["learning_curve"]["strict_mean_error"])
    ax.plot(
        n,
        inv,
        marker="o",
        linestyle="-",
        color=BLACK,
        markerfacecolor=WHITE,
        label="invariant, matched budget",
    )
    ax.plot(n, egnn, marker="s", linestyle="--", color=MID, label="strict EGNN")
    ax.set_xscale("log", base=2); ax.set_yscale("log")
    ax.set_xticks(n, [str(v) for v in n])
    ax.set_xlabel("training designs"); ax.set_ylabel("mean absolute log error")
    ax.set_title("Sample-efficiency curve")
    ax.grid(color=GRID, linewidth=0.55, which="both"); ax.legend(frameon=False)
    save(fig, "fig3_strict_e3_ablation")


def latency() -> None:
    lat = DATA["latency"]
    labels = ["batch\nthroughput", "single\nforward", "raw-layout\nend to end", "paired field\nsolvers"]
    values = [lat["gnn_ms"]["precollated_batch_per_design"],
              lat["gnn_ms"]["single_forward"],
              lat["gnn_ms"]["raw_layout_end_to_end"],
              lat["paired_solver_ms"]["median"]]
    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN, 2.55), constrained_layout=True)
    bars = ax.bar(
        np.arange(4),
        values,
        color=[WHITE, LIGHT, MID, DARK],
        edgecolor=BLACK,
        linewidth=0.8,
        hatch=["....", "////", "\\\\", ""],
    )
    ax.set_yscale("log"); ax.set_ylabel("latency per design (ms)")
    ax.set_xticks(np.arange(4), labels, fontsize=6.8)
    ax.grid(axis="y", which="both", color=GRID, linewidth=0.55)
    ax.set_ylim(0.15, 12000)
    for bar, value in zip(bars, values):
        text = f"{value:.2f}" if value < 10 else f"{value/1000:.2f} s"
        ax.text(bar.get_x()+bar.get_width()/2, value*1.25, text, ha="center", fontsize=7.2)
    ax.set_title("Latency depends on the timed boundary", pad=5)
    save(fig, "fig4_latency_protocols")


def ranking() -> None:
    rank = DATA["ranking"]
    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE_COLUMN, 2.65), constrained_layout=True)
    ax = axes[0]
    methods = ["pointwise\nGNN", "pairwise\nGNN", "registration\nGNN"]
    rho = [rank["pointwise_rho"], rank["family_disjoint_pairwise_rho_median"], rank["xy_registration"]["gnn_rho"]]
    ax.bar(
        np.arange(3),
        rho,
        color=[MID, LIGHT, WHITE],
        edgecolor=BLACK,
        linewidth=0.8,
        hatch=["////", "\\\\", "...."],
    ); ax.set_ylim(0, 1.08)
    ax.set_xticks(np.arange(3), methods); ax.set_ylabel("Spearman $\\rho$")
    ax.set_title("Ranking requires the right objective")
    ax.grid(axis="y", color=GRID, linewidth=0.55)
    for i, value in enumerate(rho): ax.text(i, value+.035, f"{value:.2f}", ha="center", fontsize=7.2)
    ax = axes[1]
    labels = ["analytical", "random", "pairwise GNN"]
    regrets = [rank["xy_registration"]["analytical_pick_regret_pct"],
               rank["xy_registration"]["random_pick_regret_pct"],
               rank["xy_registration"]["gnn_pick_regret_pct"]]
    bars = ax.bar(
        np.arange(3),
        regrets,
        color=[DARK, MID, WHITE],
        edgecolor=BLACK,
        linewidth=0.8,
        hatch=["", "////", "...."],
    )
    ax.set_yscale("log"); ax.set_xticks(np.arange(3), labels)
    ax.set_ylabel("registration pick regret (%)")
    ax.set_title("The learned ranker changes the choice")
    ax.grid(axis="y", which="both", color=GRID, linewidth=0.55)
    ax.set_ylim(2.0, 3200)
    for bar, value in zip(bars, regrets):
        ax.text(bar.get_x()+bar.get_width()/2, value*1.12, f"{value:g}", ha="center", fontsize=7.2)
    save(fig, "fig5_ranking_decision")


def frequency() -> None:
    raw = json.loads((REPO / "results" / "run_t3" / "results_t3.json").read_text())
    f = np.asarray(raw["freqs_hz"])
    truth = np.asarray(raw["mean_true_curve"])
    pred = np.asarray(raw["mean_pred_curve"])
    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN, 2.55), constrained_layout=True)
    ax.plot(
        f,
        truth,
        marker="o",
        linestyle="-",
        color=BLACK,
        markerfacecolor=WHITE,
        markevery=2,
        label="field-solver mean",
    )
    ax.plot(f, pred, linestyle="--", color=MID, lw=1.7, label="GNN mean")
    ax.set_xscale("log"); ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel(r"$R_{ac}/R_{dc}$")
    ax.grid(color=GRID, linewidth=0.55, which="both"); ax.legend(frameon=False)
    ax.set_title("Frequency-resolved resistance extension", pad=5)
    save(fig, "fig6_frequency")


if __name__ == "__main__":
    pipeline(); field_accuracy(); equivariance(); latency(); ranking(); frequency()
    print(f"generated figures in {OUT}")
