"""
inductance_ref.py — INDEPENDENT multi-filament mutual-inductance reference
(FastHenry-style Neumann double-integral), used to check the GNN's inductive
output against something other than the analytical Grover/PEEC label
as an independent cross-solver reference.

Each rectangular trace is discretised into a grid of parallel current filaments
across its width x thickness cross-section. For two equal-length parallel
filaments (length L, transverse centre-to-centre distance d) the exact
Neumann-integral mutual inductance is
    M = (mu0/2pi) [ L*asinh(L/d) - sqrt(L^2+d^2) + d ].
The conductor-to-conductor mutual is the average over all filament pairs
(uniform current split). This is the standard partial-element method used by
FastHenry and is independent of the engine's GMD-based Grover closed form.
"""
from __future__ import annotations

import math
import numpy as np

MU0 = 4 * math.pi * 1e-7


def _filaments(w_mm, t_mm, xc_mm, zc_mm, nw=5, nt=2):
    """Filament centre coordinates (mm) tiling a w x t cross-section at (xc,zc)."""
    xs = (np.arange(nw) + 0.5) / nw - 0.5            # -0.5..0.5
    zs = (np.arange(nt) + 0.5) / nt - 0.5
    X = xc_mm + xs * w_mm
    Z = zc_mm + zs * t_mm
    XX, ZZ = np.meshgrid(X, Z, indexing="ij")
    return XX.reshape(-1), ZZ.reshape(-1)


def _pair_M_nh(L_m, d_m):
    """Exact mutual inductance (nH) of two parallel equal-length filaments."""
    if d_m < 1e-9:
        d_m = 1e-9
    M = (MU0 / (2 * math.pi)) * (L_m * math.asinh(L_m / d_m)
                                 - math.sqrt(L_m**2 + d_m**2) + d_m)
    return M * 1e9


def fem_pair_mutual_nh(w1_mm, w2_mm, t_mm, h_mm, overlap_len_mm, nw=5, nt=2):
    """Independent multi-filament mutual inductance (nH) of a stacked trace pair:
    primary (width w1, at z=+h/2) above secondary (width w2, at z=-h/2), facing
    length overlap_len. Conductors centred in x."""
    L = overlap_len_mm * 1e-3
    x1, z1 = _filaments(w1_mm, t_mm, 0.0, +h_mm / 2.0, nw, nt)
    x2, z2 = _filaments(w2_mm, t_mm, 0.0, -h_mm / 2.0, nw, nt)
    n1, n2 = len(x1), len(x2)
    tot = 0.0
    for i in range(n1):
        dx = (x1[i] - x2) * 1e-3
        dz = (z1[i] - z2) * 1e-3
        d = np.sqrt(dx * dx + dz * dz)
        for j in range(n2):
            tot += _pair_M_nh(L, float(d[j]))
    return tot / (n1 * n2)


def _filament_self_inductance_nh(L_m, r_m):
    """Self partial inductance (nH) of a round filament (internal + external Neumann)."""
    if L_m < 1e-12 or r_m < 1e-12:
        return 0.0
    # internal DC + external
    L_int = (MU0 * L_m) / (8 * math.pi)
    L_ext = (MU0 / (2 * math.pi)) * L_m * (math.log(2 * L_m / r_m) - 1.0 + r_m / L_m)
    return (L_int + L_ext) * 1e9


def _trace_self_L_nh(trace, nw=5, nt=2):
    """Self L (nH) of one trace via its filament grid (uniform current average incl internal)."""
    L = trace["length_mm"] * 1e-3
    w = trace["width_mm"]
    t = trace.get("thick_mm", 0.07)
    if L < 1e-9:
        return 0.0
    xs, zs = _filaments(w, t, 0.0, 0.0, nw, nt)
    n = len(xs)
    area_per_mm2 = (w * t) / (nw * nt)
    r_per = math.sqrt(area_per_mm2 / math.pi) * 1e-3  # m
    tot = 0.0
    for p in range(n):
        for q in range(n):
            if p == q:
                tot += _filament_self_inductance_nh(L, r_per)
            else:
                dx = (xs[p] - xs[q]) * 1e-3
                dz = (zs[p] - zs[q]) * 1e-3
                d = math.hypot(dx, dz) or 1e-9
                tot += _pair_M_nh(L, d)
    return tot / (n * n)


def _pair_trace_mutual_nh(t1, t2, nw=5, nt=2):
    h = abs(t2.get("z_mm", 0.3) - t1.get("z_mm", 0.1))
    ov = min(t1["length_mm"], t2["length_mm"])
    return fem_pair_mutual_nh(t1["width_mm"], t2["width_mm"], t1.get("thick_mm", 0.07), h, ov, nw, nt)


def neumann_totals(layout, nw=5, nt=2):
    """Multi-filament Neumann free-space totals (independent of FastHenry/PEEC/Grover).
    Returns same dict keys as fasthenry_totals: L_mut_nH, L_pri_nH, L_sec_nH (nH)."""
    trs = layout.get("traces", [])
    pri = [t for t in trs if t.get("net") == "pri"]
    sec = [t for t in trs if t.get("net") == "sec"]
    L_mut = 0.0
    for a in pri:
        for b in sec:
            L_mut += _pair_trace_mutual_nh(a, b, nw, nt)
    def net_L(traces):
        if not traces:
            return 0.0
        n = len(traces)
        tot = 0.0
        for i in range(n):
            tot += _trace_self_L_nh(traces[i], nw, nt)
            for j in range(i + 1, n):
                M = _pair_trace_mutual_nh(traces[i], traces[j], nw, nt)
                tot += 2.0 * M
        return tot
    return {"L_mut_nH": L_mut, "L_pri_nH": net_L(pri), "L_sec_nH": net_L(sec)}


if __name__ == "__main__":
    for h in (0.2, 0.4, 0.8):
        M = fem_pair_mutual_nh(3.0, 3.0, 0.07, h, 40.0)
        print(f"h={h}mm  M={M:.4f} nH")
    # smoke totals
    lay = {"traces": [
        {"x0":0,"y0":0,"z_mm":0.10,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
        {"x0":0,"y0":0,"z_mm":0.30,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"},
    ]}
    print("neumann_totals smoke:", neumann_totals(lay))
