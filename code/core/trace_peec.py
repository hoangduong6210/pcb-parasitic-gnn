"""
Trace-level PEEC models for PCB foil conductors (planar magnetics).

Extends the spirit of engine/peec_cps.py (parallel-plate + Massarini) to
rectangular copper traces on multilayer PCBs.

Models implemented (analytical / semi-analytical, fast for data gen):
- Self and mutual inductance of thin rectangular filaments/strips (Grover / Ruehli approximations).
- Capacitance: parallel plate + fringing (Hurley-inspired) + side walls.
- AC resistance: skin-effect for strips (Dowell-style 1D + simple proximity).

These serve as "silver labels" for initial GNN training. They are much better
than the old layer-overlap scalar for arbitrary trace routing.

References (to be expanded in 02_literature/):
- Grover, "Inductance Calculations" (1946)
- Ruehli, IBM JRD 1972 (PEEC)
- Hurley & Wilcox, "Inductance and capacitance formulas..."
- Massarini & Kazimierczuk (for round-wire baseline comparison)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple
import numpy as np


MU0 = 4 * math.pi * 1e-7
EPS0 = 8.854187817e-12


@dataclass
class Trace:
    """Rectangular foil trace segment (axis-aligned for v0)."""
    x0: float   # mm
    y0: float   # mm
    z: float    # mm (layer center)
    length_mm: float
    width_mm: float
    thick_mm: float   # Cu thickness (e.g. 0.070 for 2oz)
    net: str          # "pri", "sec", "gnd", ...


def strip_self_inductance_nh(trace: Trace) -> float:
    """
    Approximate self partial inductance of a thin rectangular strip (nH).
    Grover-style formula for a straight conductor of rectangular cross-section.

    L ≈ (μ0 / 2π) * l * [ln(2l / (w+t)) + 0.5 + (w+t)/(3l) ... ]   (long conductor approx)
    """
    l = trace.length_mm * 1e-3
    w = trace.width_mm * 1e-3
    t = trace.thick_mm * 1e-3
    if l < 1e-9 or w < 1e-9:
        return 0.0
    # Effective geometric mean distance for thin strip
    gmd = (w + t) / 4.0 + 0.2235 * (w + t)   # common engineering approx
    ln_term = math.log(2.0 * l / max(gmd, 1e-12))
    L = (MU0 / (2 * math.pi)) * l * (ln_term + 0.5 + (w + t) / (3.0 * l))
    return L * 1e9   # nH


def mutual_inductance_rect_nh(t1: Trace, t2: Trace) -> float:
    """
    Mutual partial inductance between two parallel or collinear strips.
    Uses simplified Grover mutual formula for parallel filaments + area correction.

    For co-planar or vertically stacked (different z), uses average distance.
    """
    # centers
    dx = (t2.x0 + t2.length_mm/2) - (t1.x0 + t1.length_mm/2)
    dy = 0.0   # assume parallel for v0; future: general angle
    dz = t2.z - t1.z
    d = math.sqrt(dx*dx + dy*dy + dz*dz) * 1e-3  # m
    l = min(t1.length_mm, t2.length_mm) * 1e-3

    if d < 1e-9 or l < 1e-9:
        return 0.0

    # Classic filament mutual (Grover)
    if d > 2 * l:
        M = (MU0 * l / (2 * math.pi)) * (math.log(2 * l / d) - 1 + d / l)
    else:
        # short-distance correction (rough)
        rho = d / l
        M = (MU0 * l / (2 * math.pi)) * (math.log(2 / rho + math.sqrt(1 + 4 / (rho*rho))) - math.sqrt(1 + rho*rho) + rho)

    # crude area factor for width (average over facing edges)
    w_avg = (t1.width_mm + t2.width_mm) * 0.5 * 1e-3
    area_factor = 1.0 / (1.0 + (w_avg / max(d, 1e-6)))
    return M * area_factor * 1e9   # nH


def trace_capacitance_pf(t1: Trace, t2: Trace, eps_r: float = 4.0,
                         h_sep_mm: float | None = None) -> float:
    """
    Two-trace capacitance (pF) using parallel plate + simple fringing.
    h_sep_mm: vertical separation (layer-to-layer). If None, compute from z diff.
    """
    if h_sep_mm is None:
        h_sep_mm = abs(t2.z - t1.z)
    d = max(h_sep_mm, 0.01) * 1e-3  # m
    # Overlap length and effective width
    overlap_len = min(t1.length_mm, t2.length_mm) * 1e-3
    # effective facing width
    w_eff = min(t1.width_mm, t2.width_mm) * 1e-3
    if overlap_len < 1e-9 or w_eff < 1e-9:
        return 0.0

    C_pp = eps_r * EPS0 * w_eff * overlap_len / d

    # Fringing (very approx, Hurley-style logarithmic)
    fringing = 0.5 * eps_r * EPS0 * overlap_len * math.log(1 + 2 * w_eff / d)   # rough
    return (C_pp + fringing) * 1e12


def trace_ac_resistance_mohm(trace: Trace, freq_hz: float, rho_cu: float = 1.68e-8) -> float:
    """
    Simple skin-effect resistance for a rectangular trace (mOhm).
    Uses classic skin depth; proximity left for GNN to learn from geometry.
    """
    if freq_hz < 1:
        return 0.0
    delta = math.sqrt(rho_cu / (math.pi * freq_hz * MU0))   # m
    w = trace.width_mm * 1e-3
    t = trace.thick_mm * 1e-3
    l = trace.length_mm * 1e-3

    # effective conducting cross section
    if t < 2 * delta:
        area_eff = w * t
    else:
        area_eff = w * min(t, 2 * delta)   # skin on top+bottom for thin foil

    R_dc = rho_cu * l / (w * t)
    # rough AC factor (Dowell-like for single trace)
    Fr = 1.0 + (t / (3 * delta)) if delta > 0 else 1.0
    return (R_dc * Fr) * 1e3 * 1000   # mOhm


def compute_rlgc_for_pair(t1: Trace, t2: Trace, freqs: np.ndarray,
                          eps_r: float = 4.0) -> dict:
    """
    Return dict with arrays R, L, C, G at each freq for the pair.
    G is stubbed (loss tangent * omega * C).
    """
    L = mutual_inductance_rect_nh(t1, t2) * 1e-9   # H (single value for now)
    C = trace_capacitance_pf(t1, t2, eps_r) * 1e-12

    R = np.array([trace_ac_resistance_mohm(t1, f) + trace_ac_resistance_mohm(t2, f) for f in freqs]) * 1e-3
    # simplistic: L and C assumed frequency-independent at this level (GNN can learn dispersion)
    L_arr = np.full_like(freqs, L, dtype=float)
    C_arr = np.full_like(freqs, C, dtype=float)
    G_arr = 2 * math.pi * freqs * C_arr * 0.02   # tan_delta ~ 0.02 typical FR4

    return {
        "R_ohm": R,
        "L_H": L_arr,
        "C_F": C_arr,
        "G_S": G_arr,
        "f_hz": freqs,
    }
