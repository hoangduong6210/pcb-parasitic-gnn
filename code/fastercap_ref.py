"""
fastercap_ref.py — 3-D inter-winding capacitance C_ps via FasterCap (LGPL,
ADAPTIVE-mesh; the open-source counterpart of Q3D for C). FasterCap auto-refines
near close surfaces, which the uniform-mesh FastCap could not, so it converges on
the ~0.1 mm planar inter-layer gaps.

Panels use CONSISTENT OUTWARD normals (each box face wound so u x v points out);
FasterCap warns / returns a non-diagonally-dominant matrix otherwise. C_ps =
|C_12| (off-diagonal of the Maxwell matrix). Headless via xvfb-run.
"""
from __future__ import annotations
import re, subprocess, tempfile
from pathlib import Path
import numpy as np

FASTERCAP = str(Path(__file__).resolve().parent / "tools" / "fastercap")
M = 1e-3   # mm -> m (FasterCap outputs Farads when coords are in metres)


def _face_panels(o, u, v, nsub):
    """Subdivide a face (origin o, edges u,v with u x v = OUTWARD normal)."""
    out = []
    for i in range(nsub):
        for j in range(nsub):
            a = o + u*(i/nsub) + v*(j/nsub)
            b = o + u*((i+1)/nsub) + v*(j/nsub)
            c = o + u*((i+1)/nsub) + v*((j+1)/nsub)
            d = o + u*(i/nsub) + v*((j+1)/nsub)
            out.append((a, b, c, d))
    return out


def _box_panels(t, nsub):
    """6 faces of a trace box with OUTWARD-pointing normals (u x v = outward)."""
    x0 = t.get("x0", 0.0)*M; y0 = t.get("y0", 0.0)*M
    z0 = t.get("z_mm", (t["layer"]+0.5)*0.2)*M
    L = t["length_mm"]*M; w = t["width_mm"]*M; h = t.get("thick_mm", 0.07)*M
    o = np.array([x0, y0, z0]); ex = np.array([L, 0, 0]); ey = np.array([0, w, 0]); ez = np.array([0, 0, h])
    faces = [
        (o,       ey, ex),   # bottom z=z0: ey x ex = -z (out)
        (o+ez,    ex, ey),   # top    z=z1: ex x ey = +z (out)
        (o,       ex, ez),   # y=y0:  ex x ez = -y (out)
        (o+ey,    ez, ex),   # y=y1:  ez x ex = +y (out)
        (o,       ez, ey),   # x=x0:  ez x ey = -x (out)
        (o+ex,    ey, ez),   # x=x1:  ey x ez = +x (out)
    ]
    panels = []
    for (oo, u, v) in faces:
        panels += _face_panels(oo, u, v, nsub)
    return panels


def layout_to_qui(layout, nsub=1):
    lines = ["0 planar-PCB Cps (pri=1, sec=2)"]
    for t in layout["traces"]:
        cond = 1 if t.get("net") == "pri" else (2 if t.get("net") == "sec" else 0)
        if cond == 0:
            continue
        for (a, b, c, d) in _box_panels(t, nsub):
            lines.append("Q %d " % cond + " ".join("%.6e" % x for x in (*a, *b, *c, *d)))
    return "\n".join(lines) + "\n"


def _parse_matrix(txt):
    """FasterCap prints 'Capacitance matrix is:' then 'Dimension N x N' then rows
    '<i>  c_i1 c_i2 ...' in Farads. Return NxN numpy (pF) or None."""
    m = re.search(r"Capacitance matrix is:\s*\n\s*Dimension\s+(\d+)\s*x\s*(\d+)(.*)", txt, re.S)
    if not m:
        return None
    n = int(m.group(1)); rows = []
    for line in m.group(3).splitlines():
        nums = re.findall(r"-?\d+\.?\d*[eE]?[-+]?\d*", line)
        vals = [float(x) for x in nums if x not in ("", "-", "+")]
        if len(vals) >= n + 1:        # leading index + n entries
            rows.append(vals[1:1+n])
        if len(rows) == n:
            break
    if len(rows) != n:
        return None
    return np.array(rows) * 1e12      # F -> pF


def fastercap_Cps(layout, nsub=1, mesh_tol=0.02, timeout=300):
    """Inter-winding C_ps (pF) = |C_12| from a FasterCap adaptive 3-D solve."""
    if not any(t.get("net") == "pri" for t in layout["traces"]) or \
       not any(t.get("net") == "sec" for t in layout["traces"]):
        return None
    qui = layout_to_qui(layout, nsub=nsub)
    with tempfile.TemporaryDirectory() as d:
        qp = Path(d) / "in.qui"; qp.write_text(qui)
        try:
            r = subprocess.run(["xvfb-run", "-a", FASTERCAP, "-b", "in.qui",
                                "-a%g" % mesh_tol], cwd=d, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        C = _parse_matrix(r.stdout)
        if C is None or C.shape != (2, 2):
            return None
        return abs(float(C[0, 1]))


if __name__ == "__main__":
    lay = {"traces": [
        {"x0": 0, "y0": 0, "z_mm": 0.10, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 0, "net": "pri"},
        {"x0": 0, "y0": 0, "z_mm": 0.28, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 1, "net": "sec"},
    ]}
    # parallel-plate truth: eps0*A/d = 8.854e-12*200e-6/0.11e-3 ~ 16.1 pF
    for tol in (0.05, 0.02, 0.01):
        print("mesh_tol=%.3f -> Cps = %s pF (truth ~16.1)" % (tol, fastercap_Cps(lay, nsub=1, mesh_tol=tol)))
