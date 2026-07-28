"""
fasthenry_ref.py — INDEPENDENT 3-D inductance reference via FastHenry
(FastFieldSolvers FastHenry2, MIT). This is the field-standard partial-element
3-D inductance extractor (the open-source equivalent of ANSYS Q3D for L), so it
upgrades the inductance ground truth from our 2-D filament approximation to a
full 3-D multipole-accelerated solve, and natively returns L(f), R(f) over a
frequency sweep (used for T3).

One FastHenry run on a layout returns the FULL port L/R matrix at each frequency:
each trace segment is one port (.external), and L_ij = Im(Z_ij)/(2*pi*f).
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

FASTHENRY = str(Path(__file__).resolve().parent / "tools" / "fasthenry")


def layout_to_inp(layout, freqs_hz=(1e5,), nhinc=1, nwinc=1):
    """Build a FastHenry .inp: one straight segment per trace (its real w,h,z).
    nhinc/nwinc subdivide each conductor's cross-section into filaments so the
    frequency sweep captures skin/proximity (set >1 for R(f); default 1 = T1)."""
    trs = layout["traces"]
    lines = ["* planar-PCB layout -> FastHenry", ".units mm"]
    fil = f" nhinc={nhinc} nwinc={nwinc}" if (nhinc > 1 or nwinc > 1) else ""
    ports = []
    for i, t in enumerate(trs):
        x0 = t.get("x0", 0.0); y0 = t.get("y0", 0.0)
        z = t.get("z_mm", (t["layer"] + 0.5) * 0.2)
        L = t["length_mm"]; w = t["width_mm"]; h = t.get("thick_mm", 0.07)
        na, nb = f"N{i}a", f"N{i}b"
        lines.append(f"{na} x={x0:.4f} y={y0:.4f} z={z:.4f}")
        lines.append(f"{nb} x={x0+L:.4f} y={y0:.4f} z={z:.4f}")
        lines.append(f"E{i} {na} {nb} w={w:.4f} h={h:.4f}{fil}")
        ports.append((i, na, nb, t.get("net", "")))
    for i, na, nb, _ in ports:
        lines.append(f".external {na} {nb}")
    fmin = min(freqs_hz); fmax = max(freqs_hz)
    ndec = 1 if fmin == fmax else max(1, int(round(np.log10(fmax / fmin))))
    lines.append(f".freq fmin={fmin:.6g} fmax={fmax:.6g} ndec={ndec}")
    lines.append(".end")
    return "\n".join(lines), ports


def _parse_zc(path):
    """Parse FastHenry Zc.mat -> list of (freq, ZmatrixComplex[N,N])."""
    txt = Path(path).read_text()
    out = []
    blocks = re.split(r"Impedance matrix for frequency =\s*([0-9eE.+-]+)\s+(\d+) x (\d+)", txt)
    # blocks: [pre, f1, n1, n1b, body1, f2, ...]
    for k in range(1, len(blocks), 4):
        f = float(blocks[k]); n = int(blocks[k + 1]); body = blocks[k + 3]
        nums = re.findall(r"([0-9eE.+-]+)\s*([+-][0-9eE.+-]+)j", body)
        vals = [float(a) + 1j * float(b) for a, b in nums]
        if len(vals) >= n * n:
            Z = np.array(vals[:n * n]).reshape(n, n)
            out.append((f, Z))
    return out


def fasthenry_L_matrix(layout, freqs_hz=(1e5,), nhinc=1, nwinc=1, timeout=300):
    """Return {freq: L[nH] NxN matrix, R[ohm] NxN}, ports. One 3-D solve.
    Returns (None, ports) on solver timeout/failure (caller skips)."""
    inp, ports = layout_to_inp(layout, freqs_hz, nhinc=nhinc, nwinc=nwinc)
    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / "in.inp"; ip.write_text(inp)
        try:
            subprocess.run([FASTHENRY, "in.inp"], cwd=d, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, ports
        zc = Path(d) / "Zc.mat"
        if not zc.exists():
            return None, ports
        res = {}
        for f, Z in _parse_zc(zc):
            L = Z.imag / (2 * np.pi * f) * 1e9   # nH
            R = Z.real                            # ohm
            res[f] = {"L_nH": L, "R_ohm": R}
        return res, ports


def fasthenry_totals(layout, freq_hz=1e5):
    """Total Cps-free inductive scalars from the 3-D FastHenry L matrix:
    L_mut = sum over pri-sec port pairs of |L_ij|; L_pri/L_sec = sum self+mutual
    within net (mirrors the analytical all-pairs convention)."""
    res, ports = fasthenry_L_matrix(layout, (freq_hz,))
    if not res:
        return None
    L = res[freq_hz]["L_nH"]
    pri = [i for i, (idx, a, b, net) in enumerate(ports) if net == "pri"]
    sec = [i for i, (idx, a, b, net) in enumerate(ports) if net == "sec"]
    L_mut = float(sum(L[i, j] for i in pri for j in sec))
    def net_tot(g):
        tot = 0.0
        for a in range(len(g)):
            tot += L[g[a], g[a]]
            for b in range(a + 1, len(g)):
                tot += 2.0 * L[g[a], g[b]]
        return float(tot)
    return {"L_mut_nH": L_mut, "L_pri_nH": net_tot(pri), "L_sec_nH": net_tot(sec)}


def fasthenry_Rac_curve(layout, freqs_hz, nhinc=4, nwinc=3, timeout=120):
    """Primary-winding R_ac/R_dc(f) curve from the FastHenry frequency sweep
    (skin/proximity rise). Returns (freqs, ratio[len(freqs)]) or None."""
    res, ports = fasthenry_L_matrix(layout, tuple(freqs_hz), nhinc=nhinc, nwinc=nwinc, timeout=timeout)
    if not res:
        return None
    pri = [i for i, (idx, a, b, net) in enumerate(ports) if net == "pri"]
    if not pri:
        return None
    fs = sorted(res.keys())
    Rtot = np.array([float(sum(res[f]["R_ohm"][i, i] for i in pri)) for f in fs])
    if Rtot[0] <= 0:
        return None
    return np.array(fs), Rtot / Rtot[0]


if __name__ == "__main__":
    # smoke: two stacked traces -> finite mutual
    lay = {"traces": [
        {"x0": 0, "y0": 0, "z_mm": 0.10, "length_mm": 40, "width_mm": 3, "thick_mm": 0.07, "layer": 0, "net": "pri"},
        {"x0": 0, "y0": 0, "z_mm": 0.30, "length_mm": 40, "width_mm": 3, "thick_mm": 0.07, "layer": 1, "net": "sec"},
    ]}
    print(fasthenry_totals(lay, 1e5))
