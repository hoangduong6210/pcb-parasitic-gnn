#!/usr/bin/env python3
"""Generate deterministic monochrome figures for journal snapshot 1."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figures"
DATA = json.loads((ROOT / "figure_data.json").read_text())["claims"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 7.8,
    "axes.labelsize": 7.8,
    "axes.titlesize": 8.4,
    "legend.fontsize": 7.3,
    "xtick.labelsize": 7.3,
    "ytick.labelsize": 7.3,
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
    fig, ax = plt.subplots(figsize=(7.15, 1.78))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    boxes = [
        (0.015, 0.29, 0.135, "Validated\ngeometry", "1,500 layouts"),
        (0.182, 0.29, 0.135, "Shared\ntopology", "graph + solvers"),
        (0.349, 0.29, 0.135, "Qualified\nreferences", "four targets"),
        (0.516, 0.29, 0.135, "Family-held\nout training", "5 x 5 grid"),
        (0.683, 0.29, 0.135, "Four-output\nsurrogate", "fixed checkpoint"),
        (0.850, 0.29, 0.135, "Scoped\ndecision", "screening only"),
    ]
    shades = [0.93, 0.86, 0.78, 0.70, 0.60, 0.48]
    fit_checks = []
    for (x, y, w, title, subtitle), shade in zip(boxes, shades):
        patch = FancyBboxPatch((x, y), w, 0.42, boxstyle="round,pad=0.009",
                               facecolor=str(shade), edgecolor="black", linewidth=0.8)
        ax.add_patch(patch)
        heading = ax.text(x + w / 2, y + 0.265, title, ha="center", va="center",
                          weight="bold", fontsize=7.7)
        body = ax.text(x + w / 2, y + 0.085, subtitle, ha="center", va="center",
                       fontsize=6.9)
        fit_checks.append((patch, heading, body))
    for i in range(len(boxes) - 1):
        x1 = boxes[i][0] + boxes[i][2]
        x2 = boxes[i + 1][0]
        ax.add_patch(FancyArrowPatch((x1 + 0.006, 0.50), (x2 - 0.006, 0.50),
                                     arrowstyle="-|>", mutation_scale=9, color="black", linewidth=0.8))
    ax.text(0.50, 0.91, "Evidence path and claim boundary", ha="center", weight="bold", fontsize=8.8)
    ax.text(0.50, 0.10, "Numerical-reference screening only: no fabricated-board or arbitrary-layout claim",
            ha="center", va="center", style="italic", fontsize=7.3)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for box, *labels in fit_checks:
        boundary = box.get_window_extent(renderer)
        for label in labels:
            extent = label.get_window_extent(renderer)
            assert boundary.contains(extent.x0, extent.y0)
            assert boundary.contains(extent.x1, extent.y1)
    save(fig, "hoang1_pipeline")


def geometry_scope() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.42), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    layers = [0.85, 1.75, 3.55, 4.45]
    styles = [("P", "0.25", "///"), ("S", "0.72", "\\\\")]
    for i, y in enumerate(layers):
        label, shade, hatch = styles[i % 2]
        ax.add_patch(Rectangle((1.05 + 0.32 * (i % 2), y), 7.15, 0.34,
                               facecolor=shade, edgecolor="black", hatch=hatch, linewidth=0.8))
        ax.text(0.76, y + 0.17, label, va="center", ha="center", weight="bold", fontsize=7.3)
    ax.add_patch(Rectangle((0.45, 0.12), 8.35, 5.1, fill=False, edgecolor="black", linewidth=0.9))
    ax.annotate("lateral registration", xy=(1.38, 3.72), xytext=(3.55, 3.02),
                arrowprops={"arrowstyle": "->", "lw": 0.8}, ha="center", fontsize=7.2)
    ax.annotate("layer spacing", xy=(7.42, 2.23), xytext=(7.42, 3.10),
                arrowprops={"arrowstyle": "<->", "lw": 0.8}, ha="center", fontsize=7.2)
    ax.text(1.10, 0.28, "P  primary net", fontsize=6.9)
    ax.text(4.45, 0.28, "S  secondary net", fontsize=6.9)
    ax.set_title("(a) Co-directed active-leg abstraction", pad=2)
    ax = axes[1]
    ax.axis("off")
    included = ["rectangular copper\ntraces", "layer and net\nidentity", "dielectric\nspacing", "overlap and\noffsets"]
    excluded = ["routed returns\nand vias", "terminals and\nplanes", "core window /\nferrite", "fabrication\nvariability"]
    ax.add_patch(Rectangle((0.01, 0.84), 0.46, 0.11, transform=ax.transAxes,
                           facecolor="0.82", edgecolor="black", linewidth=0.7))
    ax.add_patch(Rectangle((0.53, 0.84), 0.46, 0.11, transform=ax.transAxes,
                           facecolor="0.96", edgecolor="black", linewidth=0.7))
    ax.text(0.24, 0.895, "Included", weight="bold", ha="center", va="center", transform=ax.transAxes)
    ax.text(0.76, 0.895, "Excluded", weight="bold", ha="center", va="center", transform=ax.transAxes)
    for i, value in enumerate(included):
        ax.text(0.03, 0.76 - 0.18 * i, f"■  {value}", transform=ax.transAxes, fontsize=7.1, va="top")
    for i, value in enumerate(excluded):
        ax.text(0.55, 0.76 - 0.18 * i, f"□  {value}", transform=ax.transAxes, fontsize=7.1, va="top")
    ax.text(0.50, 0.035, "(b) Geometry scope contract", ha="center", transform=ax.transAxes, weight="bold")
    save(fig, "hoang2_geometry_scope")


def fem_fidelity() -> None:
    gates = DATA["fem_gates"]
    disc = DATA["fidelity_discrepancy"]
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.55), gridspec_kw={"width_ratios": [1.08, 1]})
    ax = axes[0]
    x = np.arange(2)
    med = [gates["domain_median_pct"], gates["mesh_median_pct"]]
    mx = [gates["domain_max_pct"], gates["mesh_max_pct"]]
    ax.bar(x - 0.18, med, width=0.36, color="0.82", edgecolor="black", hatch="///", label="Median")
    ax.bar(x + 0.18, mx, width=0.36, color="0.42", edgecolor="black", hatch="...", label="Maximum")
    ax.axhline(gates["domain_median_gate_pct"], color="black", linestyle="--", linewidth=0.9)
    ax.axhline(gates["domain_max_gate_pct"], color="black", linestyle=":", linewidth=1.0)
    ax.set_xticks(x, ["Domain\n12 vs 16 mm", "Mesh\nR3 vs R4"])
    ax.set_ylabel("Relative difference (%)")
    ax.set_ylim(0, 16.2)
    for xpos, values in ((x - 0.18, med), (x + 0.18, mx)):
        for xi, value in zip(xpos, values):
            ax.text(xi, value + 0.35, f"{value:.2f}", ha="center", va="bottom", fontsize=6.8)
    handles, labels = ax.get_legend_handles_labels()
    handles.extend([
        Line2D([0], [0], color="black", linestyle="--", linewidth=0.9),
        Line2D([0], [0], color="black", linestyle=":", linewidth=1.0),
    ])
    labels.extend(["Median gate (2%)", "Maximum gate (5%)"])
    ax.legend(handles, labels, frameon=False, loc="upper left", ncol=2,
              columnspacing=0.9, handlelength=1.8, fontsize=6.7)
    ax.set_title("(a) Nine-layout qualification gates")
    ax = axes[1]
    labels = ["Min", "Median", "Mean", "P90", "P95", "Max"]
    vals = [disc["min_pct"], disc["median_pct"], disc["mean_pct"], disc["p90_pct"], disc["p95_pct"], disc["max_pct"]]
    y = np.arange(len(labels))
    ax.barh(y, vals, color=["0.88", "0.68", "0.62", "0.48", "0.38", "0.24"], edgecolor="black")
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("R3-to-R4 discrepancy (%)")
    ax.set_xlim(0, 19.5)
    for yi, value in zip(y, vals):
        ax.text(value + 0.25, yi, f"{value:.3f}", va="center", fontsize=8.0)
    ax.set_title("(b) Selected 198-layout registry")
    fig.tight_layout(w_pad=1.2)
    save(fig, "hoang3_fem_fidelity")


def accuracy() -> None:
    data = DATA["accuracy"]
    y = np.arange(4)
    mean = np.asarray(data["mean_mape_pct"])
    low = np.asarray(data["interval_low_pct"])
    high = np.asarray(data["interval_high_pct"])
    archived = np.asarray(data["archived_mean_mape_pct"])
    fig, ax = plt.subplots(figsize=(3.5, 2.45))
    ax.errorbar(mean, y, xerr=np.vstack([mean - low, high - mean]), fmt="o", color="black",
                mfc="black", capsize=3, label="FEM-v2 target package")
    ax.scatter(archived, y, marker="x", s=32, color="0.45", label="Archived target package")
    ax.set_yticks(y, data["targets"])
    ax.invert_yaxis()
    ax.set_xlabel("Family-macro MAPE (%)")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.legend(frameon=False, loc="lower right", handletextpad=0.6)
    ax.set_title("Family-held-out accuracy by target package")
    save(fig, "hoang4_accuracy")


def baselines() -> None:
    data = DATA["baselines"]
    values = np.asarray(data["mean_mape_pct"])
    x = np.arange(4)
    width = 0.15
    shades = ["0.12", "0.88", "0.70", "0.52", "0.34"]
    hatches = ["", "//", "\\\\", "..", "xx"]
    fig, ax = plt.subplots(figsize=(7.15, 2.58))
    for i, (name, shade, hatch) in enumerate(zip(data["models"], shades, hatches)):
        ax.bar(x + (i - 2) * width, values[i], width, color=shade, edgecolor="black",
               linewidth=0.6, hatch=hatch, label=name)
    for xi, value in zip(x - 2 * width, values[0]):
        ax.text(xi, value + 1.1, f"{value:.1f}", ha="center", va="bottom", fontsize=6.7)
    ax.set_xticks(x, data["targets"])
    ax.set_ylabel("Mean family-macro MAPE (%)")
    ax.set_ylim(0, 78)
    ax.legend(frameon=False, ncol=5, loc="upper center", columnspacing=1.1, handletextpad=0.5)
    ax.grid(axis="y", color="0.90", linewidth=0.6)
    ax.set_title("Fixed-budget comparison with frozen pooled-feature procedures")
    save(fig, "hoang5_baselines")


def coordinate_ablation() -> None:
    abl = DATA["coordinate_ablation"]
    sym = DATA["symmetry"]
    fig, axes = plt.subplots(1, 2, figsize=(7.15, 2.82), gridspec_kw={"width_ratios": [1.42, 1]})
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
    ax.legend(frameon=False, loc="lower right", handletextpad=0.5)
    ax.set_title("(a) Paired descriptive sensitivity intervals")
    ax = axes[1]
    residuals = np.asarray(sym["residuals"])
    y = np.arange(len(residuals))
    ax.hlines(y, 1e-8, residuals, colors="0.65", linewidth=1.2)
    ax.scatter(residuals, y, s=32, marker="D", color=["0.82", "0.70", "0.58", "0.46", "0.34"],
               edgecolor="black", linewidth=0.7, zorder=3)
    ax.axvline(sym["tolerance"], color="black", linestyle="--", linewidth=1, label="Tolerance")
    ax.set_xscale("log")
    ax.set_yticks(y, sym["labels"])
    ax.invert_yaxis()
    ax.set_xlabel("Maximum residual")
    ax.set_xlim(1e-8, 6e-5)
    ax.legend([Line2D([0], [0], color="black", linestyle="--", linewidth=1)],
              ["Tolerance"], frameon=False, loc="upper right")
    ax.set_title("(b) Encoded-graph symmetry checks")
    fig.tight_layout(w_pad=1.0)
    save(fig, "hoang6_coordinate_symmetry")


def latency() -> None:
    data = DATA["latency"]
    fig, ax = plt.subplots(figsize=(3.5, 2.62))
    y = np.arange(4)
    values = np.asarray(data["seconds"])
    shades = ["0.20", "0.48", "0.70", "0.38"]
    markers = ["o", "s", "D", "^"]
    for yi, value, shade, marker in zip(y, values, shades, markers):
        ax.hlines(yi, 5e-3, value, color=shade, linewidth=2.1)
        ax.scatter(value, yi, s=34, color=shade, edgecolor="black", marker=marker, zorder=3)
    ax.set_yticks(y, data["components"])
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("Median elapsed time per design (s, log scale)")
    ax.grid(axis="x", color="0.88", linewidth=0.6)
    ax.set_xlim(4e-3, 2e3)
    long_solver_labels = []
    for yi, value in zip(y, values):
        label = f"{value * 1e3:.2f} ms" if value < 1 else f"{value:.2f} s"
        if value > 100:
            # Put the long-solver labels above their bars. Centering them on
            # the bars made the gray stroke run through the glyphs in print.
            annotation = ax.annotate(label, (value, yi), xytext=(-6, 10),
                                     textcoords="offset points", ha="right",
                                     va="bottom", fontsize=6.7)
            long_solver_labels.append((yi, value, annotation))
        else:
            ax.annotate(label, (value, yi), xytext=(5, 0), textcoords="offset points",
                        ha="left", va="center", fontsize=6.7)
    ax.set_title("Paired four-target timing boundary")
    ax.text(0.98, 0.98,
            f"median paired ratio  {data['primary_ratio']:,.0f}x\n"
            f"family-cluster interval  {data['interval_low']:,.0f}-{data['interval_high']:,.0f}x",
            transform=ax.transAxes, ha="right", va="top", fontsize=6.6,
            bbox={"facecolor": "white", "edgecolor": "0.35", "pad": 2.2})
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for yi, value, annotation in long_solver_labels:
        bar_y = ax.transData.transform((value, yi))[1]
        assert annotation.get_window_extent(renderer).y0 > bar_y + 2
    save(fig, "hoang7_latency")


def graph_contract() -> None:
    data = DATA["model_contract"]
    fig, ax = plt.subplots(figsize=(7.15, 2.45))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    stages = [
        (0.010, 0.22, 0.18, "Trace records", "net, layer\ndimensions, position\nmaterials"),
        (0.220, 0.22, 0.18, "Graph encoding", "trace nodes\npair edges\nrelative geometry"),
        (0.430, 0.22, 0.22, f"Message passing\n({data['message_layers']} layers)",
         f"scalar messages\ncoordinate updates\n(first {data['coordinate_update_layers']} layers)"),
        (0.680, 0.22, 0.14, "Pooling", "mean + max\nlog-sum"),
        (0.850, 0.22, 0.14, "Outputs", "$C_{ps}$\n$L_p, L_s, M$"),
    ]
    shades = [0.94, 0.86, 0.76, 0.66, 0.52]
    fit_checks = []
    for (x, y0, width, title, subtitle), shade in zip(stages, shades):
        box = FancyBboxPatch((x, y0), width, 0.47, boxstyle="round,pad=0.009",
                             facecolor=str(shade), edgecolor="black", linewidth=0.8)
        ax.add_patch(box)
        heading = ax.text(x + width / 2, y0 + 0.36, title, ha="center", va="center",
                          weight="bold", fontsize=6.8)
        body = ax.text(x + width / 2, y0 + 0.15, subtitle, ha="center", va="center",
                       fontsize=6.0)
        fit_checks.append((box, heading, body))
    for left, right in zip(stages[:-1], stages[1:]):
        ax.add_patch(FancyArrowPatch((left[0] + left[2] + 0.005, 0.455),
                                     (right[0] - 0.005, 0.455), arrowstyle="-|>",
                                     mutation_scale=9, color="black", linewidth=0.8))

    ax.text(0.50, 0.92, "Graph-surrogate and encoded-symmetry contract",
            ha="center", va="center", weight="bold", fontsize=8.8)
    ax.plot([0.430, 0.650], [0.14, 0.14], color="black", linewidth=0.8)
    ax.plot([0.430, 0.430], [0.14, 0.18], color="black", linewidth=0.8)
    ax.plot([0.650, 0.650], [0.14, 0.18], color="black", linewidth=0.8)
    ax.text(0.50, 0.065,
            "relative vectors rotate/reflect; scalar messages and pooled outputs remain invariant",
            ha="center", va="center", fontsize=6.7)
    ax.text(0.50, 0.79,
            "The checked symmetry begins after encoding; axis-aligned raw-layout metadata remains outside this guarantee.",
            ha="center", va="center", style="italic", fontsize=6.8)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for box, *labels in fit_checks:
        boundary = box.get_window_extent(renderer)
        for label in labels:
            extent = label.get_window_extent(renderer)
            assert boundary.contains(extent.x0, extent.y0)
            assert boundary.contains(extent.x1, extent.y1)
    save(fig, "hoang8_graph_contract")


def research_evolution() -> None:
    stages = DATA["research_evolution"]["stages"]
    fig, ax = plt.subplots(figsize=(7.15, 2.08))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    x_positions = np.linspace(0.015, 0.815, len(stages))
    width = 0.17
    shades = [0.95, 0.86, 0.76, 0.65, 0.52]
    fit_checks = []
    for x, stage, shade in zip(x_positions, stages, shades):
        box = FancyBboxPatch((x, 0.24), width, 0.52,
                             boxstyle="round,pad=0.009",
                             facecolor=str(shade), edgecolor="black", linewidth=0.8)
        ax.add_patch(box)
        heading = ax.text(x + width / 2, 0.65, stage["name"], ha="center", va="center",
                          fontsize=6.8, weight="bold")
        scope = ax.text(x + width / 2, 0.49, stage["scope"], ha="center", va="center",
                        fontsize=6.1)
        status = ax.text(x + width / 2, 0.33, stage["status"], ha="center", va="center",
                         fontsize=5.9, style="italic")
        fit_checks.append((box, heading, scope, status))
    for left, right in zip(x_positions[:-1], x_positions[1:]):
        ax.add_patch(FancyArrowPatch((left + width + 0.004, 0.50), (right - 0.004, 0.50),
                                     arrowstyle="-|>", mutation_scale=8.5,
                                     color="black", linewidth=0.8))
    ax.text(0.50, 0.91, "Research evolution and version boundaries",
            ha="center", va="center", fontsize=8.8, weight="bold")
    ax.text(0.50, 0.09,
            "Each stage retains its own evidence boundary; later stages extend rather than relabel earlier results.",
            ha="center", va="center", fontsize=7.0, style="italic")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for box, *labels in fit_checks:
        boundary = box.get_window_extent(renderer)
        for label in labels:
            extent = label.get_window_extent(renderer)
            assert boundary.contains(extent.x0, extent.y0)
            assert boundary.contains(extent.x1, extent.y1)
    save(fig, "hoang9_research_evolution")


def main() -> None:
    pipeline()
    geometry_scope()
    fem_fidelity()
    accuracy()
    baselines()
    coordinate_ablation()
    latency()
    graph_contract()
    research_evolution()


if __name__ == "__main__":
    main()
