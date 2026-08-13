"""Canonical geometry contract shared by graph construction and field solvers.

Version 3 uses ``layer`` as the discrete stackup identity.  The physical z
coordinate is derived from the layout stackup; a per-trace ``z_mm`` value is
accepted only as a redundant assertion and must match exactly within tolerance.
Trace rectangles use lower-left ``x0``/``y0`` coordinates and positive extents.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


GEOMETRY_SCHEMA = "pcb-planar-active-legs.v3"
DEFAULT_LAYER_PITCH_MM = 0.18
DEFAULT_LAYER_Z0_MM = 0.05
DEFAULT_CLEARANCE_MM = 0.20
_TOL_MM = 1e-9


class GeometryContractError(ValueError):
    """Raised when a layout cannot represent one unambiguous PCB geometry."""


def layer_z_mm(layout: dict[str, Any], layer: int) -> float:
    stackup = layout.get("stackup", {})
    pitch = float(stackup.get("layer_pitch_mm", DEFAULT_LAYER_PITCH_MM))
    z0 = float(stackup.get("layer_z0_mm", DEFAULT_LAYER_Z0_MM))
    return z0 + int(layer) * pitch


def trace_z_mm(layout: dict[str, Any], trace: dict[str, Any]) -> float:
    expected = layer_z_mm(layout, int(trace["layer"]))
    if "z_mm" in trace and not math.isclose(
        float(trace["z_mm"]), expected, rel_tol=0.0, abs_tol=_TOL_MM
    ):
        raise GeometryContractError(
            f"trace {trace.get('trace_id', '?')} has z_mm={trace['z_mm']} but "
            f"layer {trace['layer']} maps to {expected} mm"
        )
    return expected


def trace_box(layout: dict[str, Any], trace: dict[str, Any]) -> tuple[float, ...]:
    x0 = float(trace["x0"])
    y0 = float(trace["y0"])
    zc = trace_z_mm(layout, trace)
    length = float(trace["length_mm"])
    width = float(trace["width_mm"])
    thickness = float(trace.get("thick_mm", 0.07))
    return x0, x0 + length, y0, y0 + width, zc - thickness / 2, zc + thickness / 2


def trace_center_mm(layout: dict[str, Any], trace: dict[str, Any]) -> tuple[float, float, float]:
    x0, x1, y0, y1, z0, z1 = trace_box(layout, trace)
    return (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2


def xy_clearance_mm(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Euclidean edge clearance for two axis-aligned x-y rectangles."""
    dx = max(a[0] - b[1], b[0] - a[1], 0.0)
    dy = max(a[2] - b[3], b[2] - a[3], 0.0)
    return math.hypot(dx, dy)


def volumes_overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return (
        min(a[1], b[1]) - max(a[0], b[0]) > _TOL_MM
        and min(a[3], b[3]) - max(a[2], b[2]) > _TOL_MM
        and min(a[5], b[5]) - max(a[4], b[4]) > _TOL_MM
    )


def validate_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Validate one layout and return deterministic audit statistics.

    Raises ``GeometryContractError`` on the first contract violation.  No solver
    may run before this gate passes.
    """
    if layout.get("geometry_schema") != GEOMETRY_SCHEMA:
        raise GeometryContractError(
            f"geometry_schema must be {GEOMETRY_SCHEMA!r}"
        )
    n_layers = int(layout.get("n_layers", 0))
    board_w = float(layout.get("board_w_mm", 0.0))
    board_h = float(layout.get("board_h_mm", 0.0))
    if n_layers < 2 or board_w <= 0 or board_h <= 0:
        raise GeometryContractError("positive board dimensions and at least two layers are required")
    stackup = layout.get("stackup", {})
    if "layer_pitch_mm" not in stackup or "layer_z0_mm" not in stackup:
        raise GeometryContractError("v3 requires an explicit layer pitch and z origin")
    if float(stackup["layer_pitch_mm"]) <= 0 or float(stackup["layer_z0_mm"]) < 0:
        raise GeometryContractError("stackup pitch must be positive and z origin non-negative")
    traces = layout.get("traces", [])
    if not traces:
        raise GeometryContractError("at least one trace is required")
    nets = {trace.get("net") for trace in traces}
    if not {"pri", "sec"}.issubset(nets):
        raise GeometryContractError("both pri and sec traces are required")

    minimum_clearance = float(
        layout.get("design_rules", {}).get("same_layer_clearance_mm", DEFAULT_CLEARANCE_MM)
    )
    edge_margin = float(layout.get("design_rules", {}).get("board_edge_margin_mm", 0.0))
    if minimum_clearance < 0 or edge_margin < 0:
        raise GeometryContractError("design-rule clearances must be non-negative")
    boxes = []
    fingerprints = set()
    trace_ids = set()
    per_net = {"pri": 0, "sec": 0}
    for index, trace in enumerate(traces):
        trace_id = trace.get("trace_id")
        if trace_id is None:
            raise GeometryContractError(f"trace {index} has no trace_id")
        if trace_id in trace_ids:
            raise GeometryContractError(f"duplicate trace_id {trace_id!r}")
        trace_ids.add(trace_id)
        if trace.get("net") not in per_net:
            raise GeometryContractError(f"trace {trace_id} has unsupported net {trace.get('net')!r}")
        if "current_sign" not in trace or int(trace["current_sign"]) != 1:
            raise GeometryContractError(
                "v3 active-leg scope currently requires co-directed series currents"
            )
        layer = int(trace.get("layer", -1))
        if not 0 <= layer < n_layers:
            raise GeometryContractError(f"trace {trace_id} has invalid layer {layer}")
        for field in ("length_mm", "width_mm", "thick_mm"):
            if float(trace.get(field, 0.0)) <= 0:
                raise GeometryContractError(f"trace {trace_id} has non-positive {field}")
        box = trace_box(layout, trace)
        if box[0] < -_TOL_MM or box[1] > board_w + _TOL_MM:
            raise GeometryContractError(f"trace {trace_id} exceeds board width")
        if box[2] < -_TOL_MM or box[3] > board_h + _TOL_MM:
            raise GeometryContractError(f"trace {trace_id} exceeds board height")
        if (
            box[0] + _TOL_MM < edge_margin or box[1] - _TOL_MM > board_w - edge_margin
            or box[2] + _TOL_MM < edge_margin or box[3] - _TOL_MM > board_h - edge_margin
        ):
            raise GeometryContractError(
                f"trace {trace_id} violates {edge_margin:g} mm board-edge margin"
            )
        fingerprint = tuple(round(value, 9) for value in box) + (trace["net"],)
        if fingerprint in fingerprints:
            raise GeometryContractError(f"trace {trace_id} duplicates a conductor volume")
        fingerprints.add(fingerprint)
        boxes.append(box)
        per_net[trace["net"]] += 1

    minimum_observed = math.inf
    compared_same_layer = 0
    for left in range(len(traces)):
        for right in range(left + 1, len(traces)):
            if volumes_overlap(boxes[left], boxes[right]):
                raise GeometryContractError(
                    f"trace volumes overlap: {traces[left]['trace_id']} and {traces[right]['trace_id']}"
                )
            if traces[left]["layer"] == traces[right]["layer"]:
                compared_same_layer += 1
                clearance = xy_clearance_mm(boxes[left], boxes[right])
                minimum_observed = min(minimum_observed, clearance)
                if clearance + _TOL_MM < minimum_clearance:
                    raise GeometryContractError(
                        f"same-layer clearance {clearance:.6g} mm below {minimum_clearance:.6g} mm "
                        f"between {traces[left]['trace_id']} and {traces[right]['trace_id']}"
                    )
    return {
        "schema": GEOMETRY_SCHEMA,
        "n_traces": len(traces),
        "n_pri": per_net["pri"],
        "n_sec": per_net["sec"],
        "n_same_layer_pairs": compared_same_layer,
        "minimum_same_layer_clearance_mm": (
            None if math.isinf(minimum_observed) else minimum_observed
        ),
        "board_contained": True,
        "layer_z_consistent": True,
        "volume_overlap_pairs": 0,
    }


def validate_passive_labels(labels: dict[str, Any], tolerance: float = 1e-6) -> dict[str, float]:
    lp = float(labels["L_pri_nH"])
    ls = float(labels["L_sec_nH"])
    mutual = float(labels["L_mut_nH"])
    cps = float(labels["Cps_pF"])
    if min(lp, ls, cps) <= 0 or not all(math.isfinite(value) for value in (lp, ls, mutual, cps)):
        raise GeometryContractError("labels must be finite with positive Lp, Ls, and Cps")
    coupling = abs(mutual) / math.sqrt(lp * ls)
    if coupling > 1.0 + tolerance:
        raise GeometryContractError(
            f"passivity violated: |M|/sqrt(Lp*Ls)={coupling:.9g}"
        )
    return {"coupling_coefficient": coupling, "passivity_margin": 1.0 - coupling}


def geometry_sha256(layout: dict[str, Any]) -> str:
    payload = json.dumps(layout, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()
