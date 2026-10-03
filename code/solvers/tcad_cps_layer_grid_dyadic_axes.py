"""Canonical-interval midpoint refinement; real-layout planning is SLURM-only.

Conductor-face bands select spacing but never become mandatory geometry planes.
No 3D cells, tetrahedra, native kernel or field system are constructed here.
"""
from fractions import Fraction
import math

from tcad_cps_layer_grid_axes import fraction, rational, exact_volume


def canonical_planes(boxes, domain, axis):
    return sorted({domain[2*axis], domain[2*axis+1],
        *(b[k] for b in boxes for k in (2*axis, 2*axis+1))})


def width_budget(boxes, domain, policy, cfg):
    gaps = [fraction(b)-fraction(a) for axis in range(3)
            for a, b in zip(canonical_planes(boxes, domain, axis), canonical_planes(boxes, domain, axis)[1:])]
    smallest = min(gaps)
    floor = min(smallest, fraction(policy["near_size_mm"])/4)
    maximum = min(fraction(policy["far_size_mm"]), fraction(cfg["jacobian_condition_bound_max"])*floor/cfg["width_budget_divisor"])
    if smallest <= 0 or floor <= 0 or maximum <= 0:
        raise ValueError("nonpositive canonical gap or width budget")
    return {"minimum_canonical_gap_mm": rational(smallest), "planning_width_floor_mm": rational(floor),
        "maximum_target_width_mm": rational(maximum), "divisor": cfg["width_budget_divisor"],
        "far_spacing_reduced": maximum < fraction(policy["far_size_mm"])}


def unpack(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def axis_plan(boxes, domain, axis, policy, cfg, budget):
    planes = canonical_planes(boxes, domain, axis)
    cap = cfg["axis_points_max"]
    if len(planes) > cap:
        raise ValueError("canonical-plane count exceeds cap")
    band = fraction(policy["face_band_half_width_mm"])
    faces = sorted({b[k] for b in boxes for k in (2*axis, 2*axis+1)})
    bands = [(fraction(v)-band, fraction(v)+band) for v in faces]
    maximum = unpack(budget["maximum_target_width_mm"])
    points, leaves, segments = [float(planes[0])], [], []
    for ordinal, (left, right) in enumerate(zip(planes, planes[1:])):
        first_leaf = len(leaves)
        stack = [(float(left), float(right), 0)]
        while stack:
            lo, hi, depth = stack.pop()
            low, high = fraction(lo), fraction(hi)
            near = any(low <= end and high >= start for start, end in bands)
            target = min(maximum, fraction(policy["near_size_mm"])) if near else maximum
            if high-low <= target:
                points.append(hi)
                leaves.append({"left_mm": lo, "right_mm": hi, "canonical_interval": ordinal,
                    "depth": depth, "near": near, "target_max_width_mm": rational(target)})
                if len(points) > cap:
                    raise ValueError("dyadic axis exceeds point cap")
                continue
            if depth >= cfg["subdivision_depth_max"]:
                raise ValueError("dyadic subdivision depth cap exceeded")
            mid = float((low+high)/2)
            if not lo < mid < hi:
                raise ValueError("rounded midpoint collapsed; canonical geometry is not snapped")
            # Left-first traversal produces a stable ascending coordinate list.
            stack.extend([(mid, hi, depth+1), (lo, mid, depth+1)])
        current = leaves[first_leaf:]
        segments.append({"left_mm": left, "right_mm": right, "leaves": len(current),
            "maximum_depth": max(v["depth"] for v in current), "near_leaves": sum(v["near"] for v in current)})
    if any(a >= b for a, b in zip(points, points[1:])) or not set(planes).issubset(points):
        raise ValueError("canonical plane lost or nonpositive dyadic cell")
    widths = [fraction(b)-fraction(a) for a, b in zip(points, points[1:])]
    gaps = [fraction(b)-fraction(a) for a, b in zip(planes, planes[1:])]
    closest = min(range(len(gaps)), key=gaps.__getitem__)
    return {"axis": axis, "canonical_planes_mm": planes, "base_planes_mm": planes,
        "segments": segments, "leaf_intervals": leaves, "points_mm": points, "points_hex_mm": [v.hex() for v in points],
        "point_count": len(points), "minimum_cell_width_mm": rational(min(widths)), "maximum_cell_width_mm": rational(max(widths)),
        "closest_base_planes_hex_mm": [float(v).hex() for v in planes[closest:closest+2]], "minimum_base_gap_mm": rational(gaps[closest])}


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
    if any(fraction(policy[k]) <= 0 for k in ("near_size_mm", "far_size_mm", "face_band_half_width_mm")):
        raise ValueError("positive grid sizes/face band required")
    if policy["near_size_mm"] > policy["far_size_mm"]:
        raise ValueError("near spacing exceeds far spacing")
    if cfg["width_budget_divisor"] != 12 or not 0 < cfg["subdivision_depth_max"] <= 64:
        raise ValueError("unfrozen width budget/depth rule")
    budget = width_budget(boxes, domain, policy, cfg)
    planned = [axis_plan(boxes, domain, k, policy, cfg, budget) for k in range(3)]
    indices = [{v: j for j, v in enumerate(a["points_mm"])} for a in planned]
    extents = [[(indices[k][b[2*k]], indices[k][b[2*k+1]]) for k in range(3)] for b in boxes]
    metal_counts = [math.prod(high-low for low, high in extent) for extent in extents]
    cells = math.prod(a["point_count"]-1 for a in planned)
    nodes = math.prod(a["point_count"] for a in planned)
    dielectric_cells = cells-sum(metal_counts)
    determinant_volume = exact_volume(domain)-sum((exact_volume(b) for b in boxes), Fraction(0))
    if dielectric_cells <= 0 or determinant_volume <= 0:
        raise ValueError("nonpositive dielectric domain")
    widths = [fraction(b)-fraction(a) for axis in planned for a, b in zip(axis["points_mm"], axis["points_mm"][1:])]
    ratio = max(widths)/min(widths)
    bound_squared = 30*ratio**2
    # The budget is a deterministic construction choice, not a waived gate:
    # recompute the original bound from the actual stored coordinates.
    checks = {"node_upper_bound": nodes <= limits["mesh_nodes_max"],
        "tetrahedron_count": 6*dielectric_cells <= limits["mesh_tetrahedra_max"],
        "jacobian_condition_bound": bound_squared <= fraction(cfg["jacobian_condition_bound_max"])**2}
    return {"schema": "pcb-gnn.layer-grid-dyadic-report.v1", "domain_box_mm": domain, "canonical_boxes_mm": boxes,
        "policy": policy, "width_budget": budget, "axes": planned, "conductor_cell_ranges": extents, "conductor_cell_counts": metal_counts,
        "total_tensor_cells": cells, "dielectric_cells": dielectric_cells, "tetrahedra": 6*dielectric_cells,
        "tensor_node_upper_bound": nodes, "exact_dielectric_volume_mm3": rational(determinant_volume),
        "axis_width_ratio": rational(ratio), "jacobian_condition_upper_bound_squared": rational(bound_squared),
        "planning_checks": checks, "planning_feasible": all(checks.values()),
        "coordinates_snapped": False, "mesh_generated": False, "boundary_contract_passed": False,
        "field_solver_executed": False, "reference_qualified": False, "training_may_start": False, "claim_eligible": False}
