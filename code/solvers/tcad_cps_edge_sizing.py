"""Analytic finite-segment sizing and native probes; real use is SLURM-guarded.

No native initialization on import. Probe generation/evaluation on actual layouts
belongs exclusively to the guarded builder. Synthetic tests use tiny rectangles.
"""
from fractions import Fraction
import math

from tcad_cps_column_contract import coordinate, fraction, rational, inputs
from scientific_artifact import sha256_json


def segments(boxes):
    if not isinstance(boxes, list) or not 0 < len(boxes) <= 128:
        raise ValueError("bounded nonempty conductor list required")
    result = []
    for owner, b in enumerate(boxes):
        if len(b) != 6 or not all(coordinate(v) for v in b) or any(b[k] >= b[k+1] for k in (0,2,4)):
            raise ValueError("finite nondegenerate canonical box required")
        for side in range(4):
            axis, other = side//2, 1-side//2
            a, z = [0.,0.], [0.,0.]
            a[axis] = z[axis] = float(b[side])
            a[other], z[other] = float(b[2*other]), float(b[2*other+1])
            result.append({"owner": owner, "side": side, "a_mm": a, "b_mm": z})
    return result


def literal(value):
    if not coordinate(value):
        raise ValueError("lossless finite coordinate literal required")
    text = format(float(value), ".17g")
    if float(text) != value:
        raise ValueError("coordinate literal changes stored value")
    return f"({text})"


def expression(segment):
    a, b = segment["a_mm"], segment["b_mm"]
    axis, other = segment["side"]//2, 1-segment["side"]//2
    if a[axis] != b[axis] or not a[other] < b[other]:
        raise ValueError("ordered axis-aligned segment required")
    fixed, along = ("x","y")[axis], ("x","y")[other]
    excess = f"Max(Max({literal(a[other])}-{along},0),{along}-{literal(b[other])})"
    return f"Sqrt(({fixed}-{literal(a[axis])})^2+({excess})^2)"


def distance_squared(point, segment):
    """Independent exact orthogonal projection, not the native clamp expression."""
    if len(point) != 2 or not all(coordinate(v) for v in point):
        raise ValueError("finite planar probe required")
    p, a, b = [tuple(fraction(v) for v in row) for row in (point,segment["a_mm"],segment["b_mm"])]
    delta = [b[k]-a[k] for k in range(2)]
    square = sum(v*v for v in delta)
    if square <= 0:
        raise ValueError("positive segment length required")
    t = max(Fraction(0), min(Fraction(1), sum((p[k]-a[k])*delta[k] for k in range(2))/square))
    return sum((p[k]-a[k]-t*delta[k])**2 for k in range(2))


def size_at_distance(distance, threshold):
    lo, hi = threshold["DistMin"], threshold["DistMax"]
    near, far = threshold["SizeMin"], threshold["SizeMax"]
    if not all(coordinate(v) for v in (distance,lo,hi,near,far)) or not 0 <= distance or not 0 < lo < hi or not 0 < near <= far:
        raise ValueError("finite positive size/transition contract required")
    if threshold["Sigmoid"] != 0 or threshold["StopAtDistMax"] != 0:
        raise ValueError("linear finite threshold required")
    if distance <= lo: return near
    if distance >= hi: return far
    alpha = (distance-lo)/(hi-lo)
    return near*(1-alpha)+far*alpha


def sizing_policy(boxes, policy, cfg, mesh):
    edges = segments(boxes)
    expressions = [expression(s) for s in edges]
    lo = cfg["edge_plateau_half_width_mm"]
    hi = lo+mesh["transition_thickness_mm"]
    threshold = {"DistMin": lo, "DistMax": hi, "SizeMin": policy["near_size_mm"],
        "SizeMax": policy["far_size_mm"], "Sigmoid": 0, "StopAtDistMax": 0}
    size_at_distance(0., threshold)
    if (len(expressions) > cfg["segment_count_max"] or sum(len(v.encode()) for v in expressions) > cfg["expression_bytes_max"]):
        raise ValueError("edge sizing field count/expression cap exceeded")
    return {"schema": "pcb-gnn.edge-sizing-request.v1", "segments": edges, "expressions": expressions,
        "distance_combination": "Min", "threshold": threshold, "policy": policy,
        "options": {**cfg["mesh_options"], "Mesh.MeshSizeMin": policy["near_size_mm"], "Mesh.MeshSizeMax": policy["far_size_mm"]}}


def apply_sizing(native, requested):
    for k,v in requested["options"].items(): native.option.setNumber(k,v)
    if {k:native.option.getNumber(k) for k in requested["options"]} != requested["options"]:
        raise ValueError("effective edge sizing options differ")
    api, rows = native.model.mesh.field, []
    if list(api.list()):
        raise ValueError("fresh edge session has preexisting fields")
    for text in requested["expressions"]:
        tag = api.add("MathEval")
        api.setString(tag,"F",text)
        if api.getType(tag) != "MathEval" or api.getString(tag,"F") != text:
            raise ValueError("native edge expression differs")
        rows.append({"tag":tag,"expression":text})
    minimum = api.add("Min")
    tags = [r["tag"] for r in rows]
    api.setNumbers(minimum,"FieldsList",tags)
    if api.getType(minimum) != "Min" or list(api.getNumbers(minimum,"FieldsList")) != tags:
        raise ValueError("native edge Min field differs")
    background = api.add("Threshold")
    settings = {**requested["threshold"],"InField":minimum}
    for k,v in settings.items(): api.setNumber(background,k,v)
    if api.getType(background) != "Threshold" or {k:api.getNumber(background,k) for k in settings} != settings:
        raise ValueError("native edge Threshold differs")
    api.setAsBackgroundMesh(background)
    if sorted(int(t) for t in api.list()) != sorted([*tags,minimum,background]):
        raise ValueError("unexpected native edge sizing field")
    return {"requested":requested,"distance_fields":rows,"minimum_tag":minimum,
        "background_tag":background,"threshold_settings":settings}


def validate_sizing(sizing, expected):
    if (set(sizing) != {"requested","distance_fields","minimum_tag","background_tag","threshold_settings"}
            or sizing["requested"] != expected or len(sizing["distance_fields"]) != len(expected["expressions"])
            or any(set(r) != {"tag","expression"} or r["expression"] != text
                for r,text in zip(sizing["distance_fields"],expected["expressions"]))
            or sizing["threshold_settings"] != {**expected["threshold"],"InField":sizing["minimum_tag"]}):
        raise ValueError("edge sizing effective metadata mismatch")
    tags = [r["tag"] for r in sizing["distance_fields"]]+[sizing["minimum_tag"],sizing["background_tag"]]
    if any(type(t) is not int or t <= 0 for t in tags) or len(set(tags)) != len(tags):
        raise ValueError("edge sizing effective field tag collision")
    return True


def probe_points(boxes, domain, requested, cfg):
    inputs(boxes,domain)
    points = [(x,y,0.) for x in domain[:2] for y in domain[2:4]]
    points += [((b[0]+b[1])/2,(b[2]+b[3])/2,0.) for b in [domain,*boxes]]
    t = requested["threshold"]
    distances = [t["DistMin"]/2,t["DistMin"],(t["DistMin"]+t["DistMax"])/2,t["DistMax"],t["DistMax"]+t["SizeMin"]]
    for edge in requested["segments"]:
        a,b = edge["a_mm"],edge["b_mm"]
        axis, other = edge["side"]//2,1-edge["side"]//2
        mid = [(a[k]+b[k])/2 for k in range(2)]
        points += [(*a,0.),(*b,0.),(*mid,0.)]
        for d in distances:
            for sign in (-1,1):
                point = list(mid)
                point[axis] += sign*d
                points.append((*point,0.))
        # Beyond both endpoints in an oblique direction: catches infinite-line
        # or L-infinity substitutes for the finite Euclidean segment distance.
        for endpoint,sign in ((a,-1),(b,1)):
            point = list(endpoint)
            point[other] += sign*t["DistMax"]
            point[axis] += t["DistMax"]
            points.append((*point,0.))
    unique = list(dict.fromkeys(tuple(float(v) for v in row) for row in points))
    if not 0 < len(unique) <= cfg["probe_points_max"] or not all(all(coordinate(v) for v in point) for point in unique):
        raise ValueError("invalid/unbounded edge probe set")
    return [list(v) for v in unique]


def evaluate_native(native, tag, points):
    """The inspected Gmsh plugin overwrites one existing scalar-point view."""
    if list(native.view.getTags()):
        raise ValueError("fresh sizing probe requires no existing views")
    view = native.view.add("edge_sizing_probe")
    try:
        flat = [v for point in points for v in [*point,-12345.]]
        native.view.addListData(view,"SP",len(points),flat)
        native.plugin.setNumber("MeshSizeFieldView","MeshSizeField",tag)
        native.plugin.setNumber("MeshSizeFieldView","View",native.view.getIndex(view))
        native.plugin.setNumber("MeshSizeFieldView","Component",0)
        returned = native.plugin.run("MeshSizeFieldView")
        if returned != view or [int(v) for v in native.view.getTags()] != [view]:
            raise ValueError("native sizing probe view identity changed")
        kinds,counts,data = native.view.getListData(view)
        if list(kinds) != ["SP"] or [int(v) for v in counts] != [len(points)] or len(data) != 1:
            raise ValueError("native sizing probe data shape changed")
        values = [float(v) for v in data[0]]
        if (len(values) != 4*len(points) or any(values[4*i:4*i+3] != point for i,point in enumerate(points))
                or not all(math.isfinite(v) for v in values)):
            raise ValueError("native sizing probe coordinates/nonfinite values")
        return values[3::4]
    finally:
        native.view.remove(view)


def probe(native, boxes, domain, sizing, cfg):
    requested = sizing["requested"]
    points = probe_points(boxes,domain,requested,cfg)
    native_distance = evaluate_native(native,sizing["minimum_tag"],points)
    native_size = evaluate_native(native,sizing["background_tag"],points)
    rows = []
    for i,point in enumerate(points):
        square = min(distance_squared(point[:2],s) for s in requested["segments"])
        expected = math.sqrt(float(square))
        rows.append({"point_mm":point,"exact_minimum_distance_squared_mm2":rational(square),
            "expected_distance_mm":expected,"native_distance_mm":native_distance[i],
            "expected_size_mm":size_at_distance(expected,requested["threshold"]),"native_size_mm":native_size[i]})
    return {"schema":"pcb-gnn.edge-sizing-probe.v1","sizing_sha256":sha256_json(sizing),
        "point_set_sha256":sha256_json(points),"points":rows,"point_count":len(rows),
        "rtol":cfg["probe_rtol"],"atol_mm":cfg["probe_atol_mm"],
        "probe_is_mesh_accuracy_test":False,"mesh_generated":False,"field_solver_executed":False}


def validate_probe(report, sizing, cfg):
    """Scalar metadata check; does not replay segment geometry or probe planning."""
    if (report["schema"] != "pcb-gnn.edge-sizing-probe.v1" or report["sizing_sha256"] != sha256_json(sizing)
            or report["rtol"] != cfg["probe_rtol"] or report["atol_mm"] != cfg["probe_atol_mm"]
            or type(report["point_count"]) is not int or report["point_count"] != len(report["points"])
            or not 0 < report["point_count"] <= cfg["probe_points_max"]
            or any(report[k] is not False for k in ("probe_is_mesh_accuracy_test","mesh_generated","field_solver_executed"))):
        raise ValueError("edge sizing probe identity/scope mismatch")
    points = [r["point_mm"] for r in report["points"]]
    if report["point_set_sha256"] != sha256_json(points) or len({tuple(p) for p in points}) != len(points):
        raise ValueError("edge sizing probe point identity mismatch")
    for row in report["points"]:
        q = row["exact_minimum_distance_squared_mm2"]
        n,d = int(q["numerator"]),int(q["denominator"])
        if n < 0 or d <= 0 or rational(Fraction(n,d)) != q:
            raise ValueError("invalid exact sizing-probe distance metadata")
        point = row["point_mm"]
        if len(point) != 3 or not all(coordinate(v) for v in point) or point[2] != 0.:
            raise ValueError("invalid sizing probe point")
        expected = math.sqrt(float(Fraction(n,d)))
        if row["expected_distance_mm"] != expected or row["expected_size_mm"] != size_at_distance(expected,sizing["requested"]["threshold"]):
            raise ValueError("sizing probe scalar expected-value mismatch")
        for quantity in ("distance","size"):
            value = row[f"native_{quantity}_mm"]
            if (not coordinate(value) or value < 0 or (quantity == "size" and value == 0)
                    or not math.isclose(value,row[f"expected_{quantity}_mm"],rel_tol=cfg["probe_rtol"],abs_tol=cfg["probe_atol_mm"])):
                raise ValueError("native edge sizing probe differs from independent oracle")
    return True


if __name__ == "__main__":
    raise SystemExit("Library only; actual geometry/native sizing probes require the guarded SLURM builder")
