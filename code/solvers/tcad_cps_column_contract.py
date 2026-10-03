"""Exact footprint/column bookkeeping; library only, real inputs are SLURM-only.

No CAD API, planar triangulation, 3D connectivity array, or field is created.
The x/y arrangement below is an independent area oracle, not a meshing grid.
"""
from fractions import Fraction
import math

from tcad_cps_layer_grid_axes import fraction, rational, exact_volume
from tcad_cps_layer_grid_dyadic_axes import axis_plan

PRISM_PATTERN = ((0, 1, 2, 5), (0, 4, 1, 5), (0, 3, 4, 5))
CLOSED = ("volume_mesh_generated", "boundary_contract_passed", "field_solver_executed",
          "reference_qualified", "training_may_start", "claim_eligible")


def coordinate(value):
    try:
        return type(value) in (float,int) and math.isfinite(value) and float(value) == value
    except (OverflowError, ValueError):
        return False


def inputs(boxes, domain, cap=128):
    if type(cap) is not int or cap <= 0 or not isinstance(boxes, list) or not 0 < len(boxes) <= cap:
        raise ValueError("invalid conductor count/cap")
    for box in [domain, *boxes]:
        if not isinstance(box, list) or len(box) != 6 or not all(coordinate(v) for v in box):
            raise ValueError("finite canonical boxes required")
        if any(box[k] >= box[k+1] for k in (0, 2, 4)):
            raise ValueError("nonpositive canonical extent")
    if any(not all(domain[k] < b[k] < b[k+1] < domain[k+1] for k in (0, 2, 4)) for b in boxes):
        raise ValueError("conductor not strictly inside domain")
    for i, a in enumerate(boxes):
        for b in boxes[:i]:
            if all(min(a[k+1], b[k+1]) > max(a[k], b[k]) for k in (0, 2, 4)):
                raise ValueError("positive-volume conductor overlap")


def footprint_partition(boxes, domain, cap=128):
    """Exact area per complete ownership mask; coincident projections allowed."""
    inputs(boxes, domain, cap)
    planes = [sorted({domain[k], domain[k+1], *(b[j] for b in boxes for j in (k,k+1))}) for k in (0,2)]
    active = [[{i for i,b in enumerate(boxes) if b[2*a] <= lo and hi <= b[2*a+1]}
               for lo,hi in zip(axis,axis[1:])] for a,axis in enumerate(planes)]
    widths = [[fraction(hi)-fraction(lo) for lo,hi in zip(axis,axis[1:])] for axis in planes]
    area = {}
    for i, dx in enumerate(widths[0]):
        for j, dy in enumerate(widths[1]):
            owners = tuple(sorted(active[0][i] & active[1][j]))
            area[owners] = area.get(owners, Fraction(0)) + dx*dy
    return {"schema": "pcb-gnn.column-footprint-partition.v1", "canonical_boxes_mm": boxes,
        "domain_box_mm": domain, "reference_planes_xy_mm": planes,
        "reference_rectangles": len(widths[0])*len(widths[1]),
        "groups": [{"owners": list(owners), "area_mm2": rational(value)} for owners,value in sorted(area.items())],
        "domain_area_mm2": rational(sum(area.values(), Fraction(0))), "coordinates_snapped": False}


def vertical_plan(boxes, domain, policy, *, point_cap=4096, depth_cap=64):
    """Canonical z faces with band/midpoint refinement; no x/y width budget."""
    inputs(boxes, domain)
    if (type(point_cap) is not int or not 2 <= point_cap <= 4096
            or type(depth_cap) is not int or not 0 < depth_cap <= 64):
        raise ValueError("invalid vertical planning cap")
    if any(not coordinate(policy[k]) or policy[k] <= 0
           for k in ("near_size_mm", "far_size_mm", "face_band_half_width_mm")):
        raise ValueError("finite positive spacing/band required")
    if policy["near_size_mm"] > policy["far_size_mm"]:
        raise ValueError("near spacing exceeds far spacing")
    # Reuse only the immutable one-dimensional midpoint construction. Its
    # global tensor width budget/condition certificate is deliberately not used.
    return axis_plan(boxes, domain, 2, policy,
        {"axis_points_max": point_cap, "subdivision_depth_max": depth_cap},
        {"maximum_target_width_mm": rational(fraction(policy["far_size_mm"]))})


def owners_key(owners, count):
    if (not isinstance(owners, list) or any(type(v) is not int or not 0 <= v < count for v in owners)
            or owners != sorted(set(owners))):
        raise ValueError("invalid complete ownership mask")
    return tuple(owners)


def unpack(value):
    n, d = int(value["numerator"]), int(value["denominator"])
    if d <= 0:
        raise ValueError("positive rational denominator required")
    return Fraction(n,d)


def column_capacity(boxes, domain, z_points, groups, planar_nodes, limits):
    """Prospective counts only; native ownership/mesh validity is not inferred.

    groups are aggregated planar triangle counts by *complete* ownership mask.
    A later native integration must independently validate these observations.
    """
    partition = footprint_partition(boxes, domain)
    expected = {tuple(g["owners"]): unpack(g["area_mm2"]) for g in partition["groups"]}
    if (not isinstance(z_points, list) or not 2 <= len(z_points) <= 4096
            or not all(coordinate(z) for z in z_points)
            or z_points != sorted(set(z_points)) or z_points[0] != domain[4] or z_points[-1] != domain[5]
            or not {b[j] for b in boxes for j in (4,5)}.issubset(z_points)):
        raise ValueError("vertical coordinates lose canonical geometry/coverage")
    if type(planar_nodes) is not int or planar_nodes < 3:
        raise ValueError("invalid planar node count")
    if any(type(limits[k]) is not int or limits[k] <= 0 for k in ("mesh_nodes_max", "mesh_tetrahedra_max")):
        raise ValueError("positive integer capacity limits required")
    observed = {}
    if not isinstance(groups, list) or not groups:
        raise ValueError("nonempty aggregate planar groups required")
    for group in groups:
        if not isinstance(group, dict) or set(group) != {"owners", "triangles"}:
            raise ValueError("unexpected planar group fields")
        key = owners_key(group["owners"], len(boxes))
        if key in observed or type(group["triangles"]) is not int or group["triangles"] <= 0:
            raise ValueError("duplicate mask/nonpositive triangle count")
        observed[key] = group["triangles"]
    if set(observed) != set(expected):
        raise ValueError("planar ownership-mask coverage mismatch")
    widths = [fraction(b)-fraction(a) for a,b in zip(z_points,z_points[1:])]
    ranges = [(z_points.index(b[4]), z_points.index(b[5])) for b in boxes]
    prisms, volume, rows = 0, Fraction(0), []
    for owners in sorted(expected):
        occupied = [j for owner in owners for j in range(*ranges[owner])]
        if len(occupied) != len(set(occupied)):
            raise ValueError("multiple metal owners in the same positive-volume column")
        removed = set(occupied)
        retained = [j for j in range(len(widths)) if j not in removed]
        n = observed[owners]*len(retained)
        prisms += n
        height = sum((widths[j] for j in retained), Fraction(0))
        volume += expected[owners]*height
        rows.append({"owners": list(owners), "planar_triangles": observed[owners],
            "retained_z_intervals": retained, "prisms": n,
            "retained_height_mm": rational(height),
            "minimum_retained_height_mm": rational(min(widths[j] for j in retained)),
            "maximum_retained_height_mm": rational(max(widths[j] for j in retained))})
    canonical_volume = exact_volume(domain)-sum((exact_volume(b) for b in boxes), Fraction(0))
    if volume != canonical_volume or volume <= 0:
        raise ValueError("independent column/canonical dielectric volume mismatch")
    nodes, tetrahedra = planar_nodes*len(z_points), 3*prisms
    checks = {"node_upper_bound": nodes <= limits["mesh_nodes_max"], "tetrahedron_count": tetrahedra <= limits["mesh_tetrahedra_max"]}
    return {"schema": "pcb-gnn.column-capacity.v1", "groups": rows, "planar_nodes": planar_nodes,
        "vertical_points": len(z_points), "column_node_upper_bound": nodes, "prisms": prisms, "tetrahedra": tetrahedra,
        "exact_dielectric_volume_mm3": rational(volume), "capacity_checks": checks,
        "capacity_feasible": all(checks.values()), "planar_mesh_validated": False,
        "conditioning_validated": False, "coordinates_snapped": False, **{k: False for k in CLOSED}}


def triangle_coordinates(points):
    if not isinstance(points, (list,tuple)) or len(points) != 3:
        raise ValueError("three planar vertices required")
    if any(not isinstance(p, (list,tuple)) or len(p) != 2
           or not all(coordinate(v) for v in p) for p in points):
        raise ValueError("finite planar coordinates required")
    xy = [[fraction(v) for v in p] for p in points]
    area2 = (xy[1][0]-xy[0][0])*(xy[2][1]-xy[0][1])-(xy[1][1]-xy[0][1])*(xy[2][0]-xy[0][0])
    if area2 == 0:
        raise ValueError("exactly degenerate planar triangle")
    return xy, area2


def prism_indices(points, triangle, layer):
    """Three positive tetrahedra; globally ordered planar IDs fix side diagonals."""
    if (type(layer) is not int or layer < 0 or not isinstance(triangle, (list,tuple)) or len(triangle) != 3
            or any(type(i) is not int or not 0 <= i < len(points) for i in triangle) or len(set(triangle)) != 3):
        raise ValueError("invalid triangle/layer identity")
    ordered = sorted(triangle)
    _, area2 = triangle_coordinates([points[i] for i in ordered])
    ids = [j*len(points)+i for j in (layer,layer+1) for i in ordered]
    patterns = PRISM_PATTERN if area2 > 0 else tuple((t[0],t[2],t[1],t[3]) for t in PRISM_PATTERN)
    return [tuple(ids[i] for i in t) for t in patterns]


def determinant(matrix):
    a,b,c = matrix
    return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])


def inverse(matrix):
    det = determinant(matrix)
    if det == 0:
        raise ValueError("singular prism map")
    cofactor = []
    for i in range(3):
        row = []
        for j in range(3):
            minor = [[matrix[r][c] for c in range(3) if c != j] for r in range(3) if r != i]
            row.append((-1)**(i+j)*(minor[0][0]*minor[1][1]-minor[0][1]*minor[1][0]))
        cofactor.append(row)
    return [[cofactor[j][i]/det for j in range(3)] for i in range(3)]


def prism_condition_bound(points, minimum_height, maximum_height, maximum_condition=10000):
    """Exact Frobenius upper bound, maximized over a continuous height interval.

    J(h)=diag(1,1,h)*J(1); the squared norm product is
    (A+B*h*h)*(C+D/(h*h)), convex in h*h. Endpoints therefore suffice.
    This is a geometry certificate, not an assembled FEM condition/accuracy claim.
    """
    xy, area2 = triangle_coordinates(points)
    if any(not isinstance(h, Fraction) and not coordinate(h) for h in (minimum_height, maximum_height)):
        raise ValueError("finite stored-coordinate or exact rational heights required")
    # Canonical z differences are generally not representable as binary64.
    # The integration must pass their Fractions directly, without rounding.
    lo, hi = (h if isinstance(h, Fraction) else fraction(h) for h in (minimum_height, maximum_height))
    if lo <= 0 or hi < lo or type(maximum_condition) is not int or maximum_condition <= 0:
        raise ValueError("invalid prism height/condition limit")
    vertices = [p+[Fraction(z)] for z in (0,1) for p in xy]
    bounds = []
    for tetra in PRISM_PATTERN:
        v = [vertices[k] for k in tetra]
        jac = [[v[k][i]-v[0][i] for k in (1,2,3)] for i in range(3)]
        inv = inverse(jac)
        a = sum(x*x for row in jac[:2] for x in row)
        b = sum(x*x for x in jac[2])
        c = sum(row[j]**2 for row in inv for j in (0,1))
        d = sum(row[2]**2 for row in inv)
        bound = max((a+b*h*h)*(c+d/(h*h)) for h in (lo,hi))
        bounds.append({"A_mm2": rational(a), "B": rational(b), "C_per_mm2": rational(c), "D": rational(d),
                       "condition_upper_bound_squared": rational(bound)})
    worst = max(unpack(b["condition_upper_bound_squared"]) for b in bounds)
    return {"schema": "pcb-gnn.column-prism-condition.v1", "tetrahedra": bounds,
        "minimum_height_mm": rational(lo), "maximum_height_mm": rational(hi),
        "minimum_positive_determinant_mm3": rational(abs(area2)*lo),
        "condition_upper_bound_squared": rational(worst), "condition_limit": maximum_condition,
        "conditioning_passed": worst <= maximum_condition**2, "native_quality_claimed": False,
        **{k: False for k in CLOSED}}


if __name__ == "__main__":
    raise SystemExit("Library only; real-input integration requires a separate guarded SLURM protocol")
