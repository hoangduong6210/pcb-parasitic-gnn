"""Exact stored-binary-coordinate diagnostics; no native/CLI entry point.

Real packets must only be passed by the allocation-guarded worker. Unit tests
use tiny explicit arrays. Exactness concerns stored doubles, not CAD geometry.
"""
from fractions import Fraction
import math


def triple(points):
    a, b, c = [[p[j]-points[0][j] for j in range(3)] for p in points[1:]]
    return a[0]*(b[1]*c[2]-b[2]*c[1]) + a[1]*(b[2]*c[0]-b[0]*c[2]) + a[2]*(b[0]*c[1]-b[1]*c[0])


def homogeneous(points):
    """Independent exact 4x4 determinant by pivoted rational elimination."""
    matrix = [[Fraction(1), *p] for p in points]
    determinant = Fraction(1)
    for col in range(4):
        pivot = next((j for j in range(col, 4) if matrix[j][col]), None)
        if pivot is None:
            return Fraction(0)
        if pivot != col:
            matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
            determinant = -determinant
        value = matrix[col][col]
        determinant *= value
        for row in range(col+1, 4):
            multiplier = matrix[row][col]/value
            for j in range(col+1, 4):
                matrix[row][j] -= multiplier*matrix[col][j]
            matrix[row][col] = Fraction(0)
    return determinant


def rational(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def error_against_exact(value, exact, tolerance):
    difference = abs(Fraction.from_float(float(value))-exact)
    relative = difference/abs(exact) if exact else None
    return {"absolute_mm3": rational(difference),
        "relative": rational(relative) if relative is not None else None,
        "within_rtol": difference <= tolerance*abs(exact)}


def diagnose(packet, limits, rtol):
    import numpy as np
    from tcad_cps_dielectric_mesh_audit import canonical_packet, packet_sha256
    a = canonical_packet(packet, limits)
    t = np.searchsorted(a["node_tags"], a["tetrahedron_nodes"])
    if np.any(t >= len(a["node_tags"])) or not np.array_equal(a["node_tags"][t], a["tetrahedron_nodes"]):
        raise ValueError("tetrahedron references unknown node")
    xyz = a["coordinates_mm"]
    edges = [xyz[t[:, j]]-xyz[t[:, 0]] for j in (1, 2, 3)]
    vector = np.einsum("ij,ij->i", edges[0], np.cross(edges[1], edges[2]))
    if not np.isfinite(vector).all() or not math.isfinite(rtol) or rtol <= 0:
        raise ValueError("nonfinite determinant or invalid tolerance")
    native = a["min_det_jac_mm3"]
    close = np.isclose(vector, native, rtol=rtol, atol=0.)
    # Convert each stored double BEFORE subtraction; never approximate fractions.
    exact_xyz = [[Fraction.from_float(float(v)) for v in p] for p in xyz]
    tolerance = Fraction.from_float(float(rtol))
    rows = []
    summary = {"tetrahedra": len(t), "original_gate_mismatches": int((~close).sum()),
        "nonpositive_sicn": int((a["min_sicn"] <= 0).sum()),
        "sign_counts": {k: {s: 0 for s in ("negative", "zero", "positive")} for k in ("native", "vector", "scalar", "exact")},
        "outside_rtol_against_exact": {k: 0 for k in ("native", "vector", "scalar")},
        "interesting_tetrahedron_tags": [], "exact_methods_agree": True}
    for i, nodes in enumerate(t):
        points = [exact_xyz[int(j)] for j in nodes]
        exact = triple(points)
        if exact != homogeneous(points):
            raise ValueError("independent exact determinant methods disagree")
        scalar = triple([[float(v) for v in xyz[j]] for j in nodes])
        if not math.isfinite(scalar):
            raise ValueError("nonfinite scalar determinant")
        values = {"native": float(native[i]), "vector": float(vector[i]), "scalar": scalar}
        errors = {k: error_against_exact(v, exact, tolerance) for k, v in values.items()}
        for k, value in {**values, "exact": exact}.items():
            summary["sign_counts"][k]["negative" if value < 0 else "positive" if value > 0 else "zero"] += 1
        for k, error in errors.items():
            summary["outside_rtol_against_exact"][k] += int(not error["within_rtol"])
        row = {"tetrahedron_tag": int(a["tetrahedron_tags"][i]), "node_tags": a["tetrahedron_nodes"][i].tolist(),
            "volume_tag": int(a["tetrahedron_volumes"][i]), "min_sicn": float(a["min_sicn"][i]),
            "determinant_mm3": values, "exact_determinant_mm3": rational(exact),
            "original_gate_close": bool(close[i]), "errors_against_exact": errors}
        if not close[i] or exact <= 0 or row["min_sicn"] <= 0 or any(not e["within_rtol"] for e in errors.values()):
            row["coordinates_hex_mm"] = [[float(v).hex() for v in xyz[j]] for j in nodes]
            summary["interesting_tetrahedron_tags"].append(row["tetrahedron_tag"])
        rows.append(row)
    return {"schema": "pcb-gnn.jacobian-arithmetic-report.v1", "packet_sha256": packet_sha256(a),
        "jacobian_rtol": rtol, "jacobian_atol": 0., "relative_error_denominator": "abs(exact stored-coordinate determinant); null if zero",
        "summary": summary, "rows": rows,
        "boundary_contract_passed": False, "field_solver_executed": False,
        "reference_qualified": False, "training_may_start": False, "claim_eligible": False}
