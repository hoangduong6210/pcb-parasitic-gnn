"""
fastcap_ref.py — 3-D inter-winding capacitance C_ps via FastCap (MIT, the
capacitance counterpart of FastHenry; open-source equivalent of Q3D for C).

Each PCB trace is an axis-aligned conductor box; its 6 faces are emitted as
quadrilateral panels (subdivided nsub x nsub) under conductor 1 (all primary
traces) or conductor 2 (all secondary traces). FastCap returns the Maxwell
capacitance matrix in picofarads (coordinates in metres); the physical
inter-winding capacitance is C_ps = |C_12| (off-diagonal magnitude).
"""
from __future__ import annotations
import re, subprocess, tempfile
from pathlib import Path
import numpy as np

FASTCAP = str(Path(__file__).resolve().parent / "tools" / "fastcap")
M = 1e-3   # mm -> m (FastCap outputs pF when coordinates are in metres)


def _face_panels(o, u, v, nsub):
    """Subdivide a face (origin o, edge vectors u,v) into nsub x nsub quads."""
    out = []
    for i in range(nsub):
        for j in range(nsub):
            a = o + u * (i / nsub) + v * (j / nsub)
            b = o + u * ((i + 1) / nsub) + v * (j / nsub)
            c = o + u * ((i + 1) / nsub) + v * ((j + 1) / nsub)
            d = o + u * (i / nsub) + v * ((j + 1) / nsub)
            out.append((a, b, c, d))
    return out


def _box_panels(t, nsub):
    """6 faces of a trace box -> list of quad panels (corners in metres)."""
    x0 = t.get("x0", 0.0) * M; y0 = t.get("y0", 0.0) * M
    z0 = t.get("z_mm", (t["layer"] + 0.5) * 0.2) * M
    L = t["length_mm"] * M; w = t["width_mm"] * M; h = t.get("thick_mm", 0.07) * M
    o = np.array([x0, y0, z0]); ex = np.array([L, 0, 0]); ey = np.array([0, w, 0]); ez = np.array([0, 0, h])
    faces = [
        (o, ex, ey), (o + ez, ex, ey),          # bottom, top (broad)
        (o, ex, ez), (o + ey, ex, ez),          # front, back
        (o, ey, ez), (o + ex, ey, ez),          # left, right
    ]
    panels = []
    for (oo, u, v) in faces:
        panels += _face_panels(oo, u, v, nsub)
    return panels


def layout_to_qui(layout, nsub=2):
    lines = ["0 planar-PCB Cps (pri=1, sec=2)"]
    for t in layout["traces"]:
        cond = 1 if t.get("net") == "pri" else (2 if t.get("net") == "sec" else 0)
        if cond == 0:
            continue
        for (a, b, c, d) in _box_panels(t, nsub):
            lines.append("Q %d " % cond + " ".join("%.6e" % x for x in
                         (*a, *b, *c, *d)))
    return "\n".join(lines) + "\n"


def _parse_matrix(txt):
    """Parse the FastCap 'CAPACITANCE MATRIX, picofarads' block -> dict {(i,j):pF}."""
    m = re.search(r"CAPACITANCE MATRIX, picofarads(.*)", txt, re.S)
    if not m:
        return None
    rows = {}
    for line in m.group(1).splitlines():
        nums = re.findall(r"-?\d+\.?\d*e?[-+]?\d*", line)
        # a data row looks like: <name> <idx> <c1> <c2> ...
        toks = line.split()
        if len(toks) >= 3 and toks[-1].replace('.', '').replace('-', '').replace('e', '').replace('+', '').isdigit():
            # find the integer conductor index (token just before the floats)
            try:
                # last len-? floats are the row; the conductor index is the int token
                idx = None
                for k, tk in enumerate(toks):
                    if tk.isdigit():
                        idx = int(tk); fk = k; break
                if idx is None:
                    continue
                vals = [float(x) for x in toks[fk + 1:]]
                rows[idx] = vals
            except ValueError:
                continue
    return rows


def fastcap_Cps(layout, nsub=2, order=2, timeout=120):
    """Inter-winding C_ps (pF) = |C_12| from a FastCap 3-D solve. None on failure."""
    if not any(t.get("net") == "pri" for t in layout["traces"]) or \
       not any(t.get("net") == "sec" for t in layout["traces"]):
        return None
    qui = layout_to_qui(layout, nsub=nsub)
    with tempfile.TemporaryDirectory() as d:
        qp = Path(d) / "in.qui"; qp.write_text(qui)
        try:
            r = subprocess.run([FASTCAP, "-o%d" % order, "in.qui"], cwd=d,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        rows = _parse_matrix(r.stdout)
        if not rows or 1 not in rows or len(rows[1]) < 2:
            return None
        return abs(rows[1][1])   # |C_12| pF


if __name__ == "__main__":
    # smoke: two stacked overlapping traces on adjacent layers -> finite Cps
    lay = {"traces": [
        {"x0": 0, "y0": 0, "z_mm": 0.10, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 0, "net": "pri"},
        {"x0": 0, "y0": 0, "z_mm": 0.28, "length_mm": 40, "width_mm": 5, "thick_mm": 0.07, "layer": 1, "net": "sec"},
    ]}
    for ns in (1, 2, 3):
        print("nsub=%d -> Cps = %s pF" % (ns, fastcap_Cps(lay, nsub=ns)))
