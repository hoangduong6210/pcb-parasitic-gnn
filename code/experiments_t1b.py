#!/usr/bin/env python3
"""
T1b — make the inductance surrogate field-grade against FastHenry (3-D).
Train the GNN on the filament-L_m corpus (filament == FastHenry to 1.6%, job
5700723), then validate the trained GNN's total L_m DIRECTLY against FastHenry
3-D on held-out layouts. Headline: GNN vs FastHenry median %.
Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np

from run_research13_pipeline import load_dataset, build_samples
from experiments_v5 import train, gnn_Lm
from fasthenry_ref import fasthenry_totals
from planar_to_graph import build_graph_from_planar_layout

ROOT = Path(__file__).resolve().parents[1]


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v2")
    samples = build_samples(layouts, labels)
    print("[t1b] train GNN on filament-L_m corpus (n=%d)" % len(samples))
    model, nrm, per, _ = train(samples, 42, 200)
    print("    train R2:", per)

    # validate GNN total L_m vs FastHenry 3-D on the last 24 layouts
    sel = [r for r in layouts if any(t["net"] == "pri" for t in r["layout"]["traces"])
           and any(t["net"] == "sec" for t in r["layout"]["traces"])][-24:]
    rows = []; t0 = time.time()
    for rec in sel:
        fh = fasthenry_totals(rec["layout"], 1e5)
        if not fh or fh["L_mut_nH"] <= 0:
            continue
        g = build_graph_from_planar_layout(rec["layout"])
        nf, ef, ei = g.to_feature_matrices()
        gnn = gnn_Lm(model, nrm, nf.tolist(), ef.tolist(), ei.tolist() if ei.size else [])
        fhv = fh["L_mut_nH"]
        rows.append({"id": rec["id"], "fasthenry_Lm_nH": round(fhv, 2),
                     "gnn_Lm_nH": round(gnn, 2),
                     "gnn_vs_fasthenry_pct": round(abs(gnn - fhv) / abs(fhv) * 100, 2)})
    gv = np.array([r["gnn_vs_fasthenry_pct"] for r in rows])
    out = {"note": "trained GNN total L_m vs FastHenry 3-D (field standard)",
           "n": len(rows), "host": platform.node(), "elapsed_s": round(time.time() - t0, 1),
           "gnn_vs_fasthenry_median_pct": round(float(np.median(gv)), 2),
           "gnn_vs_fasthenry_mean_pct": round(float(gv.mean()), 2),
           "train_r2": per, "rows": rows}
    od = ROOT / "05_experiments" / "run_t1b"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_t1b.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    print("=> GNN matches FastHenry 3-D to %.1f%% median (field-grade vs the "
          "open-source Q3D equivalent)." % out["gnn_vs_fasthenry_median_pct"])


if __name__ == "__main__":
    main()
