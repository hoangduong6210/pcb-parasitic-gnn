"""Exact-plane tensor-grid planning, without constructing any 3D mesh.

Real-layout planning belongs to a guarded SLURM worker. Tests use tiny explicit
boxes. The full Cartesian node product is a conservative node upper bound.
"""
from fractions import Fraction
import math


def fraction(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite coordinate required")
    return Fraction.from_float(float(value))


def rational(value):
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def exact_volume(box):
    return math.prod(fraction(box[k+1])-fraction(box[k]) for k in (0, 2, 4))


def axis_plan(boxes, domain, axis, policy, cap):
    lo, hi = domain[2*axis:2*axis+2]
    supports = [(max(lo, b[2*axis]-policy["support_expansion_mm"]),
                 min(hi, b[2*axis+1]+policy["support_expansion_mm"])) for b in boxes]
    # Exact value equality only: never merge close but distinct planes.
    canonical = sorted({lo, hi, *(b[k] for b in boxes for k in (2*axis, 2*axis+1))})
    planes = sorted({*canonical, *(v for interval in supports for v in interval)})
    if len(planes) > cap:
        raise ValueError("base-plane count exceeds cap")
    segments, total = [], 1
    for left, right in zip(planes, planes[1:]):
        near = any(left >= low and right <= high for low, high in supports)
        size = policy["near_size_mm" if near else "far_size_mm"]
        width = fraction(right)-fraction(left)
        count_ratio = width/fraction(size)
        count = -(-count_ratio.numerator//count_ratio.denominator)
        if count < 1 or total+count > cap:
            raise ValueError("subdivided axis exceeds point cap")
        segments.append({"left_mm": left, "right_mm": right, "near": near, "divisions": count})
        total += count
    points = [float(planes[0])]
    for segment in segments:
        left, right, n = fraction(segment["left_mm"]), fraction(segment["right_mm"]), segment["divisions"]
        points.extend(float(left+(right-left)*j/n) for j in range(1, n+1))
    if len(points) != total or any(a >= b for a, b in zip(points, points[1:])):
        raise ValueError("binary64 axis subdivision collapsed or reversed a cell")
    if not set(canonical).issubset(points):
        raise ValueError("canonical plane lost in subdivision")
    widths = [fraction(b)-fraction(a) for a, b in zip(points, points[1:])]
    base_widths = [fraction(b)-fraction(a) for a, b in zip(planes, planes[1:])]
    smallest = min(range(len(base_widths)), key=base_widths.__getitem__)
    return {"axis": axis, "canonical_planes_mm": canonical, "base_planes_mm": planes,
        "segments": segments, "points_mm": points, "points_hex_mm": [v.hex() for v in points],
        "point_count": total, "minimum_cell_width_mm": rational(min(widths)), "maximum_cell_width_mm": rational(max(widths)),
        "closest_base_planes_hex_mm": [float(v).hex() for v in planes[smallest:smallest+2]],
        "minimum_base_gap_mm": rational(base_widths[smallest])}


def plan_boxes(boxes, domain, policy, cfg, limits):
    if not isinstance(boxes, list) or not 0 < len(boxes) <= cfg["conductor_cap"]:
        raise ValueError("invalid conductor count")
    for box in [domain, *boxes]:
        if not isinstance(box, list) or len(box) != 6 or any(fraction(box[k+1]) <= fraction(box[k]) for k in (0, 2, 4)):
            raise ValueError("invalid box")
    if any(not all(domain[k] < b[k] < b[k+1] < domain[k+1] for k in (0, 2, 4)) for b in boxes):
        raise ValueError("conductor must lie strictly inside domain")
    for i, a in enumerate(boxes):
        for b in boxes[:i]:
            if all(min(a[k+1], b[k+1]) > max(a[k], b[k]) for k in (0, 2, 4)):
                raise ValueError("exact positive-volume conductor overlap")
    if any(fraction(policy[k]) <= 0 for k in ("near_size_mm", "far_size_mm", "support_expansion_mm")):
        raise ValueError("positive grid sizes/support required")
    if policy["near_size_mm"] > policy["far_size_mm"]:
        raise ValueError("near spacing exceeds far spacing")
    axes = [axis_plan(boxes, domain, k, policy, cfg["axis_points_max"]) for k in range(3)]
    indices = [{v: j for j, v in enumerate(a["points_mm"])} for a in axes]
    extents = [[(indices[k][b[2*k]], indices[k][b[2*k+1]]) for k in range(3)] for b in boxes]
    metal_counts = [math.prod(high-low for low, high in extent) for extent in extents]
    cells = math.prod(a["point_count"]-1 for a in axes)
    nodes = math.prod(a["point_count"] for a in axes)
    dielectric_cells = cells-sum(metal_counts)
    determinant_volume = exact_volume(domain)-sum((exact_volume(b) for b in boxes), Fraction(0))
    if dielectric_cells <= 0 or determinant_volume <= 0:
        raise ValueError("nonpositive dielectric domain")
    widths = [fraction(b)-fraction(a) for axis in axes for a, b in zip(axis["points_mm"], axis["points_mm"][1:])]
    ratio = max(widths)/min(widths)
    # For every six-simplex Kuhn pattern, ||J||F² <= 6*hmax² and
    # ||J^-1||F² <= 5/hmin², hence kappa2(J)² <= 30*(hmax/hmin)².
    bound_squared = 30*ratio**2
    checks = {"node_upper_bound": nodes <= limits["mesh_nodes_max"],
        "tetrahedron_count": 6*dielectric_cells <= limits["mesh_tetrahedra_max"],
        "jacobian_condition_bound": bound_squared <= fraction(cfg["jacobian_condition_bound_max"])**2}
    return {"schema": "pcb-gnn.layer-grid-plan-report.v1", "domain_box_mm": domain, "canonical_boxes_mm": boxes,
        "policy": policy, "axes": axes, "conductor_cell_ranges": extents, "conductor_cell_counts": metal_counts,
        "total_tensor_cells": cells, "dielectric_cells": dielectric_cells, "tetrahedra": 6*dielectric_cells,
        "tensor_node_upper_bound": nodes, "exact_dielectric_volume_mm3": rational(determinant_volume),
        "axis_width_ratio": rational(ratio), "jacobian_condition_upper_bound_squared": rational(bound_squared),
        "planning_checks": checks, "planning_feasible": all(checks.values()),
        "coordinates_snapped": False, "mesh_generated": False, "boundary_contract_passed": False,
        "field_solver_executed": False, "reference_qualified": False, "training_may_start": False, "claim_eligible": False}
