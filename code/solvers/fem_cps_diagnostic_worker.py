#!/usr/bin/env python3
"""Isolated one-layout FEM worker that emits C_ps and mesh diagnostics."""
from __future__ import annotations

import json
import sys

from fem_capacitance_3d import fem_cps_3d_diagnostics


if __name__ == "__main__":
    layout = json.load(open(sys.argv[1]))
    refine = int(sys.argv[2])
    pad_mm = float(sys.argv[3])
    try:
        result = fem_cps_3d_diagnostics(layout, eps_r=4.2, refine=refine, pad_mm=pad_mm)
        if result is not None and result["cps_pf"] > 0:
            print("RESULT=" + json.dumps(result, sort_keys=True))
    except Exception:
        pass
