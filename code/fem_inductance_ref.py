"""
inductance_ref.py — INDEPENDENT multi-filament mutual-inductance reference
(FastHenry-style Neumann double-integral), used to check the GNN's inductive
output against something other than the analytical Grover/PEEC label
(panel round-1 CRITICAL, 3 reviewers).

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


if __name__ == "__main__":
    for h in (0.2, 0.4, 0.8):
        M = fem_pair_mutual_nh(3.0, 3.0, 0.07, h, 40.0)
        print(f"h={h}mm  M={M:.4f} nH")
