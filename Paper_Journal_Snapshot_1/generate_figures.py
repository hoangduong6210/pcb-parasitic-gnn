#!/usr/bin/env python3
"""Generate deterministic monochrome figures for journal snapshot 1."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
DATA = json.loads((ROOT / "figure_data.json").read_text())["claims"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.2,
    "axes.labelsize": 8.2,
    "axes.titlesize": 9.0,
    "legend.fontsize": 8.0,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
    "axes.linewidth": 0.7,
    "lines.linewidth": 1.2,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
})


def save(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        OUT / f"{name}.pdf",
        metadata={
            "Creator": "Paper_Journal_Snapshot_1/generate_figures.py",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    fig.savefig(
        OUT / f"{name}.png",
        dpi=300,
        metadata={"Software": "Paper_Journal_Snapshot_1/generate_figures.py"},
    )
    plt.close(fig)


def pipeline() -> None:
    fig, ax = plt.subplots(figsize=(7.15, 2.15))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    boxes = [
        (0.01, 0.26, 0.14, "Geometry-valid\nlayouts", "1,500\nlayouts"),
        (0.18, 0.26, 0.14, "Shared\ntopology", "graph and\nsolvers"),
        (0.35, 0.26, 0.14, "Numerical\nreferences", "four\ntargets"),
        (0.52, 0.26, 0.14, "Family-split\nmodels", "5 by 5\ngrid"),
        (0.69, 0.26, 0.14, "Accepted\nsurrogate", "four\noutputs"),
        (0.86, 0.26, 0.13, "Scoped\ndecision", "screening\nonly"),
    ]
    shades = [0.93, 0.86, 0.78, 0.70, 0.60, 0.48]
    for (x, y, w, title, subtitle), shade in zip(boxes, shades):
        patch = FancyBboxPatch((x, y), w, 0.46, boxstyle="round,pad=0.012",
                               facecolor=str(shade), edgecolor="black", linewidth=0.8)
        ax.add_patch(patch)
        ax.text(x + w / 2, y + 0.29, title, ha="center", va="center", weight="bold")
        ax.text(x + w / 2, y + 0.11, subtitle, ha="center", va="center", fontsize=8.0)
    for i in range(len(boxes) - 1):
        x1 = boxes[i][0] + boxes[i][2]
        x2 = boxes[i + 1][0]
        ax.add_patch(FancyArrowPatch((x1 + 0.004, 0.49), (x2 - 0.004, 0.49),
                                     arrowstyle="-|>", mutation_scale=10, color="black"))
    ax.text(0.50, 0.91, "Evidence path and claim boundary", ha="center", weight="bold", fontsize=9.5)
    ax.text(0.50, 0.08, "Synthetic numerical-reference agreement; no fabricated-board or arbitrary-PCB claim",
            ha="center", va="center", style="italic", fontsize=8.0)
    save(fig, "hoang1_pipeline")


def geometry_scope() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.55), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    layers = [0.9, 1.8, 3.6, 4.5]
    styles = [("Primary", "0.25", "///"), ("Secondary", "0.72", "\\\\")]
    for i, y in enumerate(layers):
        label, shade, hatch = styles[i % 2]
        ax.add_patch(Rectangle((1.0 + 0.3 * (i % 2), y), 7.3, 0.36,
                               facecolor=shade, edgecolor="black", hatch=hatch, linewidth=0.8))
        ax.text(8.65, y + 0.18, f"{label} layer", va="center", fontsize=8.0)
    ax.add_patch(Rectangle((0.55, 0.45), 8.75, 4.85, fill=False, edgecolor="black", linewidth=1.0))
    ax.annotate("lateral offset", xy=(1.55, 3.78), xytext=(3.9, 3.0),
                arrowprops={"arrowstyle": "->", "lw": 0.8}, ha="center")
    ax.annotate("inter-layer spacing", xy=(7.5, 2.5), xytext=(7.5, 3.25),
                arrowprops={"arrowstyle": "<->", "lw": 0.8}, ha="center", fontsize=8.0)
    ax.set_title("(a) Modeled co-directed active-leg abstraction", pad=2)
    ax = axes[1]
    ax.axis("off")
    included = ["rectangular copper\ntraces", "layer and net\nidentity", "dielectric\nspacing", "overlap and\noffsets"]
    excluded = ["routed returns\nand vias", "terminals and\nplanes", "core window /\nferrite", "fabrication\nvariability"]
    ax.text(0.03, 0.92, "Included", weight="bold", transform=ax.transAxes)
    ax.text(0.59, 0.92, "Excluded", weight="bold", transform=ax.transAxes)
    for i, value in enumerate(included):
        ax.text(0.03, 0.78 - 0.18 * i, f"+ {value}", transform=ax.transAxes, fontsize=8.0, va="top")
    for i, value in enumerate(excluded):
        ax.text(0.59, 0.78 - 0.18 * i, f"- {value}", transform=ax.transAxes, fontsize=8.0, va="top")
    ax.text(0.50, 0.06, "(b) Scope contract", ha="center", transform=ax.transAxes, weight="bold")
    save(fig, "hoang2_geometry_scope")


def fem_fidelity() -> None:
    gates = DATA["fem_gates"]
    disc = DATA["fidelity_discrepancy"]
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.65), gridspec_kw={"width_ratios": [1.1, 1]})
    ax = axes[0]
    x = np.arange(2)
    med = [gates["domain_median_pct"], gates["mesh_median_pct"]]
    mx = [gates["domain_max_pct"], gates["mesh_max_pct"]]
    ax.bar(x - 0.18, med, width=0.36, color="0.82", edgecolor="black", hatch="///", label="Median")
    ax.bar(x + 0.18, mx, width=0.36, color="0.42", edgecolor="black", hatch="...", label="Maximum")
    ax.hlines([2, 5], -0.55, 1.55, colors=["0.2", "0.2"], linestyles=["--", ":"], linewidths=1)
    ax.text(-0.48, 14.7, "Gates: median 2%; maximum 5%", ha="left", fontsize=8.0,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
    ax.set_xticks(x, ["Domain\n12 vs 16 mm", "Mesh\nR3 vs R4"])
    ax.set_ylabel("Relative difference (%)")
    ax.set_ylim(0, 15.5)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("(a) Frozen nine-layout gates")
    ax = axes[1]
    labels = ["Min", "Median", "Mean", "P90", "P95", "Max"]
    vals = [disc["min_pct"], disc["median_pct"], disc["mean_pct"], disc["p90_pct"], disc["p95_pct"], disc["max_pct"]]
    y = np.arange(len(labels))
    ax.barh(y, vals, color=["0.88", "0.68", "0.62", "0.48", "0.38", "0.24"], edgecolor="black")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("R3-to-R4 discrepancy (%)")
    ax.set_xlim(0, 19)
    for yi, value in zip(y, vals):
        ax.text(value + 0.25, yi, f"{value:.3f}", va="center", fontsize=8.0)
    ax.set_title("(b) Deterministic 198-layout registry")
    fig.tight_layout(w_pad=1.2)
    save(fig, "hoang3_fem_fidelity")


def accuracy() -> None:
    data = DATA["accuracy"]
    y = np.arange(4)
    mean = np.asarray(data["mean_mape_pct"])
    low = np.asarray(data["interval_low_pct"])
    high = np.asarray(data["interval_high_pct"])
    archived = np.asarray(data["archived_mean_mape_pct"])
    fig, ax = plt.subplots(figsize=(3.5, 2.65))
    ax.errorbar(mean, y, xerr=np.vstack([mean - low, high - mean]), fmt="o", color="black",
                mfc="black", capsize=3, label="FEM-v2 target package")
    ax.scatter(archived, y, marker="x", s=32, color="0.45", label="Archived target package")
    ax.set_yticks(y, data["targets"])
    ax.invert_yaxis()
    ax.set_xlabel("Family-macro MAPE (%)")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Version-scoped family-held-out accuracy")
    save(fig, "hoang4_accuracy")


def baselines() -> None:
    data = DATA["baselines"]
    values = np.asarray(data["mean_mape_pct"])
    x = np.arange(4)
    width = 0.15
    shades = ["0.12", "0.88", "0.70", "0.52", "0.34"]
    hatches = ["", "//", "\\\\", "..", "xx"]
    fig, ax = plt.subplots(figsize=(7.15, 2.75))
    for i, (name, shade, hatch) in enumerate(zip(data["models"], shades, hatches)):
        ax.bar(x + (i - 2) * width, values[i], width, color=shade, edgecolor="black",
               linewidth=0.6, hatch=hatch, label=name)
    ax.set_xticks(x, data["targets"])
    ax.set_ylabel("Mean family-macro MAPE (%)")
    ax.set_ylim(0, 78)
    ax.legend(frameon=False, ncol=5, loc="upper center")
    ax.grid(axis="y", color="0.90", linewidth=0.6)
    ax.set_title("GNN and frozen pooled-feature procedures")
    save(fig, "hoang5_baselines")


def coordinate_ablation() -> None:
    abl = DATA["coordinate_ablation"]
    sym = DATA["symmetry"]
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 3.05), gridspec_kw={"width_ratios": [1.45, 1]})
    ax = axes[0]
    offsets = [-0.10, 0.10]
    markers = ["o", "s"]
    for ci, control in enumerate(abl["controls"]):
        for ti, target in enumerate(abl["targets"]):
            y = 3 - ti + offsets[ci]
            mean = abl["difference_pp"][ci][ti]
            lo = abl["interval_low_pp"][ci][ti]
            hi = abl["interval_high_pp"][ci][ti]
            ax.errorbar(mean, y, xerr=[[mean - lo], [hi - mean]], fmt=markers[ci],
                        color="black" if ci == 0 else "0.45", mfc="white" if ci else "black",
                        capsize=2.5, label=control if ti == 0 else None)
    ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_yticks(np.arange(4), list(reversed(abl["targets"])))
    ax.set_xlabel("Coordinate-update minus control (percentage points)")
    ax.set_xlim(-1.15, 1.75)
    ax.grid(axis="x", color="0.90", linewidth=0.6)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("(a) Paired descriptive sensitivity intervals")
    ax = axes[1]
    residuals = np.asarray(sym["residuals"])
    y = np.arange(len(residuals))
    ax.barh(y, residuals, color=["0.82", "0.70", "0.58", "0.46", "0.34"], edgecolor="black")
    ax.axvline(sym["tolerance"], color="black", linestyle="--", linewidth=1, label="Tolerance")
    ax.set_xscale("log")
    ax.set_yticks(y, sym["labels"])
    ax.invert_yaxis()
    ax.set_xlabel("Maximum residual")
    ax.set_xlim(1e-8, 6e-5)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("(b) Encoded-graph symmetry checks")
    fig.tight_layout(w_pad=1.0)
    save(fig, "hoang6_coordinate_symmetry")


def latency() -> None:
    data = DATA["latency"]
    fig, ax = plt.subplots(figsize=(3.5, 2.75))
    y = np.arange(4)
    values = np.asarray(data["seconds"])
    ax.barh(y, values, color=["0.20", "0.48", "0.70", "0.38"], edgecolor="black",
            hatch=["//", "..", "xx", ""])
    ax.set_yticks(y, data["components"])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Median elapsed time per design (s, log scale)")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.set_title("Paired four-target timing boundary")
    ax.text(0.98, 0.05,
            f"Median paired ratio: {data['primary_ratio']:,.0f}x\n"
            f"Family-cluster interval: {data['interval_low']:,.0f}-{data['interval_high']:,.0f}x",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.0,
            bbox={"facecolor": "white", "edgecolor": "black", "pad": 3})
    save(fig, "hoang7_latency")


def main() -> None:
    pipeline()
    geometry_scope()
    fem_fidelity()
    accuracy()
    baselines()
    coordinate_ablation()
    latency()


if __name__ == "__main__":
    main()
