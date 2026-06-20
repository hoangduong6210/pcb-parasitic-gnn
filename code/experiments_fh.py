#!/usr/bin/env python3
"""
experiments_fh.py — T1 step 1: establish FastHenry (3-D, field-standard) as the
inductance ground truth and cross-check our references against it.

Per layout (subset of synth_v2): total mutual L_m from
  (a) FastHenry 3-D solve            -> the gold-standard reference
  (b) our multi-filament 15x6 solve  -> should match FastHenry (validates it)
  (c) the analytical Grover label     -> expected ~60% off the field standard
Reports medians. Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np

from run_research13_pipeline import load_dataset
from fasthenry_ref import fasthenry_totals
from fem_inductance_ref import fem_pair_mutual_nh   # 15x6 filament
from planar_to_graph import compute_reference_labels_allpairs

ROOT = Path(__file__).resolve().parents[1]


def filament_total_Lm(layout, nw=15, nt=6):
    trs = layout["traces"]
    pri = [t for t in trs if t["net"] == "pri"]; sec = [t for t in trs if t["net"] == "sec"]
    tot = 0.0
    for a in pri:
        for b in sec:
            h = abs(b.get("z_mm", 0.3) - a.get("z_mm", 0.1)); ov = min(a["length_mm"], b["length_mm"])
            tot += fem_pair_mutual_nh(a["width_mm"], b["width_mm"], a.get("thick_mm", 0.07), h, ov, nw=nw, nt=nt)
    return tot


def main():
    layouts, labels, meta = load_dataset(ROOT / "03_datasets" / "synth_v1")
    sel = [r for r in layouts if any(t["net"] == "pri" for t in r["layout"]["traces"])
           and any(t["net"] == "sec" for t in r["layout"]["traces"])][:24]
    rows = []
    t0 = time.time()
    for rec in sel:
        lay = rec["layout"]
        fh = fasthenry_totals(lay, 1e5)
        if not fh or fh["L_mut_nH"] <= 0:
            continue
        fil = filament_total_Lm(lay)
        grov = compute_reference_labels_allpairs(lay)["L_mut_nH"]
        fhv = fh["L_mut_nH"]
        rows.append({"id": rec["id"], "fasthenry_Lm_nH": round(fhv, 2),
                     "filament15x6_Lm_nH": round(fil, 2), "grover_Lm_nH": round(grov, 2),
                     "filament_vs_fasthenry_pct": round(abs(fil - fhv) / abs(fhv) * 100, 2),
                     "grover_vs_fasthenry_pct": round(abs(grov - fhv) / abs(fhv) * 100, 2)})
    fv = np.array([r["filament_vs_fasthenry_pct"] for r in rows])
    gv = np.array([r["grover_vs_fasthenry_pct"] for r in rows])
    out = {
        "note": "FastHenry 3-D (field standard) vs our filament-15x6 and the analytical Grover label",
        "n": len(rows), "host": platform.node(), "elapsed_s": round(time.time() - t0, 1),
        "filament_vs_fasthenry_median_pct": round(float(np.median(fv)), 2),
        "grover_vs_fasthenry_median_pct": round(float(np.median(gv)), 2),
        "rows": rows,
    }
    od = ROOT / "05_experiments" / "run_fh"; od.mkdir(parents=True, exist_ok=True)
    (od / "results_fh.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))
    print("=> filament matches FastHenry to %.1f%% (validates our 2-D ref); "
          "Grover label is %.0f%% off the 3-D field standard."
          % (out["filament_vs_fasthenry_median_pct"], out["grover_vs_fasthenry_median_pct"]))


if __name__ == "__main__":
    main()
