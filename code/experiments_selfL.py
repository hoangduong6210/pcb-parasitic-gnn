#!/usr/bin/env python3
"""
Self-inductance label audit (reviewer ask): the mutual-L Grover label was 56% off
FastHenry 3-D; are the SELF-inductance labels (L_pri, L_sec) the analytical
generator ships also biased? Compare the analytical all-pairs label against the
FastHenry 3-D solve, per net, on held-out layouts. Honest outcome either way:
if off -> a finding + must regenerate; if close -> the self labels are validated.
Runs on a compute cluster.
"""
import json, platform, time
from pathlib import Path
import numpy as np

from run_research13_pipeline import load_dataset
from planar_to_graph import compute_reference_labels_allpairs
from fasthenry_ref import fasthenry_totals

ROOT = Path(__file__).resolve().parents[1]


def main():
    layouts, _, _ = load_dataset(ROOT / "03_datasets" / "synth_v2")
    sel = [r for r in layouts
           if any(t["net"] == "pri" for t in r["layout"]["traces"])
           and any(t["net"] == "sec" for t in r["layout"]["traces"])][-40:]
    rows = []; t0 = time.time()
    for rec in sel:
        fh = fasthenry_totals(rec["layout"], 1e5)
        if not fh:
            continue
        ana = compute_reference_labels_allpairs(rec["layout"])
        for tgt in ("L_pri_nH", "L_sec_nH", "L_mut_nH"):
            a, f = ana.get(tgt), fh.get(tgt)
            if a and f and f > 0:
                rows.append({"id": rec["id"], "target": tgt,
                             "analytical_nH": round(float(a), 2), "fasthenry_nH": round(float(f), 2),
                             "rel_err_pct": round(abs(a - f) / abs(f) * 100, 2)})
    out = {"note": "analytical Grover self/mutual L label vs FastHenry 3-D",
           "host": platform.node(), "elapsed_s": round(time.time() - t0, 1)}
    for tgt in ("L_pri_nH", "L_sec_nH", "L_mut_nH"):
        e = np.array([r["rel_err_pct"] for r in rows if r["target"] == tgt])
        if len(e):
            out[tgt] = {"median_rel_err_pct": round(float(np.median(e)), 1),
                        "mean_rel_err_pct": round(float(e.mean()), 1), "n": len(e)}
    od = ROOT / "05_experiments" / "run_selfL"; od.mkdir(parents=True, exist_ok=True)
    out["rows"] = rows
    (od / "results_selfL.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2), flush=True)
    for tgt in ("L_pri_nH", "L_sec_nH", "L_mut_nH"):
        if tgt in out:
            print("  %s: analytical-vs-FastHenry median %.1f%%" % (tgt, out[tgt]["median_rel_err_pct"]), flush=True)


if __name__ == "__main__":
    main()
