"""Exact sizing-area and vertical-budget diagnostic; real inputs are SLURM-only.

The inverse-size-squared integral is a geometric workload index, not a node
prediction or an achieved-edge-size bound. No native kernel/mesh/field is made.
"""
from collections import defaultdict
from fractions import Fraction
import re

from tcad_cps_column_contract import (coordinate, footprint_partition, inputs,
    fraction, rational, unpack, vertical_plan)
from tcad_cps_layer_grid_axes import exact_volume

CLOSED = ("mesh_generated", "planar_mesh_generated", "volume_mesh_generated", "boundary_contract_passed",
          "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible")


def rectangle(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("rectangle requires four coordinates")
    if any(not isinstance(v, Fraction) and not coordinate(v) for v in value):
        raise ValueError("finite exact rectangle coordinates required")
    result = tuple(v if isinstance(v, Fraction) else fraction(v) for v in value)
    if result[0] >= result[1] or result[2] >= result[3]:
        raise ValueError("positive rectangle extents required")
    return result


def coverage(rectangles, domain, *, rectangle_cap=128, cell_cap=100000):
    """Exact clipped union and multiplicity, using interval bookkeeping only."""
    outer = rectangle(domain)
    if (type(rectangle_cap) is not int or not 0 < rectangle_cap <= 128
            or type(cell_cap) is not int or not 0 < cell_cap <= 100000
            or not isinstance(rectangles, list) or not 0 < len(rectangles) <= rectangle_cap):
        raise ValueError("invalid rectangle count or reference-cell cap")
    clipped = []
    for raw in rectangles:
        box = rectangle(raw)
        r = tuple(max(box[k], outer[k]) if k % 2 == 0 else min(box[k], outer[k]) for k in range(4))
        if r[0] < r[1] and r[2] < r[3]:
            clipped.append(r)
    planes = [sorted({outer[2*a], outer[2*a+1], *(b[k] for b in clipped for k in (2*a, 2*a+1))}) for a in (0,1)]
    count = (len(planes[0])-1)*(len(planes[1])-1)
    if count > cell_cap:
        raise ValueError("reference-cell cap exceeded before area enumeration")
    active = [[{i for i,b in enumerate(clipped) if b[2*a] <= lo and hi <= b[2*a+1]}
        for lo,hi in zip(axis, axis[1:])] for a,axis in enumerate(planes)]
    area = defaultdict(Fraction)
    for i,(x0,x1) in enumerate(zip(planes[0], planes[0][1:])):
        for j,(y0,y1) in enumerate(zip(planes[1], planes[1][1:])):
            area[len(active[0][i] & active[1][j])] += (x1-x0)*(y1-y0)
    total = (outer[1]-outer[0])*(outer[3]-outer[2])
    union = sum((v for n,v in area.items() if n > 0), Fraction(0))
    individual = sum(((b[1]-b[0])*(b[3]-b[2]) for b in clipped), Fraction(0))
    if sum(area.values(), Fraction(0)) != total or sum((n*v for n,v in area.items()), Fraction(0)) != individual:
        raise ValueError("independent area/multiplicity closure failed")
    return {"rectangle_count": len(rectangles), "nonempty_clipped_rectangles": len(clipped),
        "unique_clipped_rectangles": len(set(clipped)), "reference_cells": count,
        "area_by_multiplicity_mm2": [{"multiplicity": k, "area_mm2": rational(v)} for k,v in sorted(area.items())],
        "union_area_mm2": rational(union), "sum_clipped_rectangle_areas_mm2": rational(individual),
        "overlap_excess_area_mm2": rational(individual-union), "domain_area_mm2": rational(total)}


def logged_counts(text):
    if not isinstance(text, str) or len(text.encode()) > 2097152:
        raise ValueError("bounded native stdout required")
    rows = re.findall(r"^Info\s*:\s*([0-9]+) nodes ([0-9]+) elements\s*$", text, flags=re.MULTILINE)
    if len(rows) != 1:
        raise ValueError("exactly one unambiguous native total required")
    nodes, elements = map(int, rows[0])
    if not 0 < nodes <= elements < 1000000000:
        raise ValueError("invalid native total metadata")
    return {"nodes": nodes, "mixed_dimension_elements": elements, "source": "native stdout only",
        "independently_audited": False, "triangle_count_inferred": False}


def budgets(boxes, domain, policy, limits, cfg):
    partition = footprint_partition(boxes, domain)
    z = vertical_plan(boxes, domain, policy, point_cap=cfg["axis_points_max"], depth_cap=cfg["subdivision_depth_max"])
    points = z["points_mm"]
    widths = [fraction(b)-fraction(a) for a,b in zip(points, points[1:])]
    occupied = [(points.index(b[4]), points.index(b[5])) for b in boxes]
    groups, volume = [], Fraction(0)
    for group in partition["groups"]:
        removed = [i for owner in group["owners"] for i in range(*occupied[owner])]
        if len(removed) != len(set(removed)):
            raise ValueError("overlapping metal intervals in a complete-owner column")
        kept = sorted(set(range(len(widths)))-set(removed))
        if not kept:
            raise ValueError("empty dielectric column")
        height = sum((widths[i] for i in kept), Fraction(0))
        volume += unpack(group["area_mm2"])*height
        groups.append({"owners": group["owners"], "area_mm2": group["area_mm2"], "retained_intervals": kept,
            "retained_interval_count": len(kept), "retained_height_mm": rational(height)})
    expected = exact_volume(domain)-sum((exact_volume(box) for box in boxes), Fraction(0))
    if volume != expected:
        raise ValueError("exact canonical dielectric volume closure failed")
    if any(type(limits[k]) is not int or limits[k] <= 0 for k in ("mesh_nodes_max", "mesh_tetrahedra_max", "planar_nodes_max", "planar_triangles_max")):
        raise ValueError("positive integer original mesh caps required")
    least = min(g["retained_interval_count"] for g in groups)
    most = max(g["retained_interval_count"] for g in groups)
    return {"vertical_axis": z, "groups": groups, "exact_dielectric_volume_mm3": rational(volume),
        "planar_node_budget_from_full_column_bound": limits["mesh_nodes_max"]//len(points),
        "planar_node_budget_with_capture_cap": min(limits["planar_nodes_max"], limits["mesh_nodes_max"]//len(points)),
        "minimum_retained_intervals": least, "maximum_retained_intervals": most,
        "planar_triangle_sufficient_budget": min(limits["planar_triangles_max"], limits["mesh_tetrahedra_max"]//(3*most)),
        "planar_triangle_necessary_ceiling": min(limits["planar_triangles_max"], limits["mesh_tetrahedra_max"]//(3*least)),
        "mesh_connectivity_observed": False, "limits": {k: limits[k] for k in ("mesh_nodes_max", "mesh_tetrahedra_max", "planar_nodes_max", "planar_triangles_max")}}


def diagnose(boxes, domain, requested_sizing, policy, limits, cfg, native_log):
    inputs(boxes, domain)
    fields = requested_sizing["box_fields"]
    near, far = (fraction(policy[k]) for k in ("near_size_mm", "far_size_mm"))
    if not 0 < near <= far or len(fields) != len(boxes):
        raise ValueError("sizing/geometry coverage or spacing mismatch")
    core, halo = [], []
    for box,f in zip(boxes, fields):
        if set(f) != {"XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax", "VIn", "VOut", "Thickness"} or not all(coordinate(v) for v in f.values()):
            raise ValueError("bounded scalar Box field settings required")
        r = rectangle([f[k] for k in ("XMin", "XMax", "YMin", "YMax")])
        if (not f["ZMin"] < 0 < f["ZMax"] or fraction(f["VIn"]) != near or fraction(f["VOut"]) != far
                or f["Thickness"] < 0 or any(r[k] > fraction(box[k]) if k % 2 == 0 else r[k] < fraction(box[k]) for k in range(4))):
            raise ValueError("projected sizing core excludes conductor, z=0 or requested sizes")
        core.append(r)
        t = fraction(f["Thickness"])
        halo.append(tuple(v-t if k % 2 == 0 else v+t for k,v in enumerate(r)))
    options = requested_sizing["options"]
    if (requested_sizing["background"] != "Min" or requested_sizing["policy"] != policy
            or options["Mesh.MeshSizeMin"] != policy["near_size_mm"] or options["Mesh.MeshSizeMax"] != policy["far_size_mm"]):
        raise ValueError("archived sizing policy mismatch")
    parts = {name: coverage(rects, domain[:4], rectangle_cap=cfg["rectangle_cap"], cell_cap=cfg["reference_cells_max"])
        for name,rects in (("conductors", [b[:4] for b in boxes]), ("near_core", core), ("expanded_envelope", halo))}
    area = unpack(parts["conductors"]["domain_area_mm2"])
    values = [unpack(parts[name]["union_area_mm2"]) for name in parts]
    if not 0 < values[0] <= values[1] <= values[2] <= area:
        raise ValueError("sizing area containment failed")
    indices = {name: rational(unpack(row["union_area_mm2"])/near**2 + (area-unpack(row["union_area_mm2"]))/far**2)
        for name,row in parts.items()}
    budget = budgets(boxes, domain, policy, limits, cfg)
    logged = logged_counts(native_log)
    full = logged["nodes"]*budget["vertical_axis"]["point_count"]
    return {"schema": "pcb-gnn.sizing-budget-report.v1", "canonical_boxes_mm": boxes, "domain_box_mm": domain,
        "policy": policy, "coverage": parts, "step_field_workload_indices": indices,
        "step_field_index_is_node_prediction": False, "transition_function_replayed": False,
        "expanded_envelope_is_measured_transition_area": False, "vertical_budget": budget,
        "native_log_counts": logged, "conditional_full_column_node_bound_from_log": full,
        "logged_nodes_within_capture_cap": logged["nodes"] <= limits["planar_nodes_max"],
        "conditional_full_column_node_bound_passes": full <= limits["mesh_nodes_max"],
        "candidate_selected": False, "coordinates_snapped": False, **{k: False for k in CLOSED}}


if __name__ == "__main__":
    raise SystemExit("Library only; actual sizing/geometry diagnosis requires guarded SLURM integration")
