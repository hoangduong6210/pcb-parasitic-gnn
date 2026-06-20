#!/usr/bin/env python3
"""Subprocess worker: solve ONE layout's FEM-3D Cps and print it. Isolated so a
gmsh C-level segfault kills only this process (the caller skips it)."""
import sys, json
from fem_capacitance_3d import fem_cps_3d

if __name__ == "__main__":
    layout = json.load(open(sys.argv[1]))
    refine = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    try:
        c = fem_cps_3d(layout, eps_r=4.2, refine=refine)
        if c is not None and c > 0:
            print("CPS=%.6f" % c)
    except Exception:
        pass
