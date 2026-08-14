#!/usr/bin/env python3
"""Isolated one-layout FEM worker that emits C_ps and mesh diagnostics."""
from __future__ import annotations

import faulthandler
import json
import resource
import sys

from fem_capacitance_3d import fem_cps_3d_diagnostics


if __name__ == "__main__":
    faulthandler.enable(all_threads=True)
    layout = json.load(open(sys.argv[1]))
    refine = int(sys.argv[2])
    pad_mm = float(sys.argv[3])
    linear_solver = sys.argv[4] if len(sys.argv) > 4 else "direct"

    def progress(stage: str, payload: dict) -> None:
        print(
            "STAGE=" + json.dumps(
                {
                    "stage": stage,
                    "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    **payload,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    result = fem_cps_3d_diagnostics(
        layout,
        eps_r=4.2,
        refine=refine,
        pad_mm=pad_mm,
        linear_solver=linear_solver,
        progress=progress,
        strict=True,
    )
    if result is None or result["cps_pf"] <= 0:
        raise RuntimeError("FEM returned no positive capacitance result")
    print("RESULT=" + json.dumps(result, sort_keys=True), flush=True)
