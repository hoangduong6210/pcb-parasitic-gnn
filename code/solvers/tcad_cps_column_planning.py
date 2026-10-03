"""Audited planar packet to prospective columns; real inputs are compute-only.

No native initialization, volume connectivity, field assembly or CLI execution.
All triangle certificates use sorted global node IDs and exact retained heights.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json

import tcad_cps_column_cad as cad
import tcad_cps_column_mesh as mesh
from tcad_cps_column_contract import (CLOSED, column_capacity, fraction, rational,
    prism_condition_bound, triangle_coordinates, unpack, vertical_plan)


def plan_packet(packet, report, boxes, domain, geometry, options, policy, settings, limits):
    audit = mesh.audit_packet(packet, report, boxes, domain, geometry, options, limits)
    a = mesh.canonical_packet(packet, limits)
    z = vertical_plan(boxes, domain, policy, point_cap=settings["axis_points_max"],
                      depth_cap=settings["subdivision_depth_max"])
    capacity = column_capacity(boxes, domain, z["points_mm"], audit["groups"], audit["planar_nodes"], limits)
    ownership = cad.review_report(report, boxes, domain, geometry, options)["ownership"]
    groups = {tuple(row["owners"]): row for row in capacity["groups"]}
    points = {int(tag): xy[:2].tolist() for tag, xy in zip(a["node_tags"], a["coordinates_mm"])}
    maximum = settings["jacobian_condition_bound_max"]
    if type(maximum) is not int or maximum <= 0:
        raise ValueError("positive integer condition bound required")
    digest = hashlib.sha256(b"pcb-gnn.column-condition-sequence.v1\0")
    counts, failures, worst, witness, minimum, mesh_volume = Counter(), 0, Fraction(0), None, None, Fraction(0)
    for tag, nodes, face in zip(a["triangle_tags"].tolist(), a["triangle_nodes"].tolist(), a["triangle_surfaces"].tolist()):
        owners = tuple(ownership[str(face)])
        group = groups[owners]
        ordered = sorted(nodes)
        xy = [points[node] for node in ordered]
        certificate = prism_condition_bound(xy, unpack(group["minimum_retained_height_mm"]),
            unpack(group["maximum_retained_height_mm"]), maximum)
        item = {"triangle_tag": tag, "ordered_node_tags": ordered, "owners": list(owners), "certificate": certificate}
        digest.update(json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n")
        bound = unpack(certificate["condition_upper_bound_squared"])
        det = unpack(certificate["minimum_positive_determinant_mm3"])
        if bound > worst:
            worst, witness = bound, item
        minimum = det if minimum is None else min(minimum, det)
        failures += not certificate["conditioning_passed"]
        counts[owners] += 1
        _, area2 = triangle_coordinates(xy)
        mesh_volume += abs(area2)/2*unpack(group["retained_height_mm"])
    if counts != Counter({tuple(g["owners"]): g["triangles"] for g in audit["groups"]}):
        raise ValueError("condition certificate does not cover every planar triangle")
    canonical_volume = unpack(capacity["exact_dielectric_volume_mm3"])
    # Canonical partition volume is exact, but native footprint coordinates may
    # differ within the unchanged CAD tolerance. Report both, never equate them.
    volume_error = abs(mesh_volume-canonical_volume)
    volume_limit = max(fraction(geometry["measure_atol_native"]), fraction(geometry["measure_rtol"])*canonical_volume)
    checks = {**capacity["capacity_checks"], "jacobian_condition_bound": failures == 0,
              "prospective_mesh_volume": volume_error <= volume_limit}
    return {"schema": "pcb-gnn.column-plan.v1", "packet_sha256": audit["packet_sha256"],
        "policy": policy, "vertical_axis": z, "planar_audit": audit, "capacity": capacity,
        "conditioning": {"schema": "pcb-gnn.column-condition-summary.v1", "triangles_checked": sum(counts.values()),
            "templates_checked": 3*sum(counts.values()), "failed_triangles": failures, "condition_limit": maximum,
            "condition_upper_bound_squared": rational(worst), "minimum_positive_determinant_mm3": rational(minimum),
            "certificate_sequence_sha256": digest.hexdigest(), "worst_witness": witness,
            "conditioning_passed": failures == 0, "native_quality_claimed": False},
        "prospective_mesh_volume_mm3": rational(mesh_volume), "mesh_canonical_volume_error_mm3": rational(volume_error),
        "mesh_canonical_volume_limit_mm3": rational(volume_limit), "planning_checks": checks,
        "planning_feasible": all(checks.values()), "planar_mesh_validated": True,
        "coordinates_snapped": False, "raw_connectivity_changed": False, **{k: False for k in CLOSED}}


if __name__ == "__main__":
    raise SystemExit("Library only; real planar packet planning requires guarded SLURM integration")
