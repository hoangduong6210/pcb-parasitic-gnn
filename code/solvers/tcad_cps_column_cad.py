"""Planar native-metadata reader/reviewer; no initialization or meshing entry.

Actual CAD snapshots/replays belong to the future guarded SLURM integration.
Unit tests use tiny synthetic reports and fake native readers only.
"""
from collections import Counter
import math

from tcad_cps_column_contract import footprint_partition, unpack, coordinate, CLOSED

SCHEMA = "pcb-gnn.column-planar-cad.v1"


def ids(values, *, empty=False):
    if (not isinstance(values,list) or any(type(v) is not int or v <= 0 for v in values)
            or values != sorted(set(values)) or (not empty and not values)):
        raise ValueError("positive sorted unique CAD tags required")
    return set(values)


def dimensions(pairs, dimension):
    if any(len(p) != 2 or type(p[0]) is not int or p[0] != dimension or type(p[1]) is not int for p in pairs):
        raise ValueError("unexpected native dimension/tag")
    result = sorted(p[1] for p in pairs)
    ids(result,empty=True)
    return result


def close(actual, expected, cfg):
    return math.isclose(actual,float(expected),rel_tol=cfg["measure_rtol"],abs_tol=cfg["measure_atol_native"])


def bounds_inside(actual, expected, tolerance):
    return all(actual[k] >= expected[k]-tolerance and actual[k+1] <= expected[k+1]+tolerance for k in (0,2,4))


def planar_box(rect):
    return [*rect[:4],0.,0.]


def on_side(a,b,rect,side,tolerance):
    axis,other = side//2,1-side//2
    return (abs(a[axis]-rect[side]) <= tolerance and abs(b[axis]-rect[side]) <= tolerance
        and min(a[other],b[other]) >= rect[2*other]-tolerance
        and max(a[other],b[other]) <= rect[2*other+1]+tolerance)


def snapshot(native,cfg, *, validate=True):
    """Read both independent incidence directions and actual point coordinates."""
    result = {}
    for dim in range(4):
        tags = dimensions(native.model.getEntities(dim),dim)
        if len(tags) > cfg["entity_count_max_per_dimension"] or (dim == 3 and tags):
            raise ValueError("planar CAD cap/volume-entity violation")
        rows = []
        for tag in tags:
            raw = native.model.getBoundingBox(dim,tag)
            boundary = dimensions(native.model.getBoundary([(dim,tag)],combined=False,oriented=False,recursive=False),dim-1) if dim else []
            up,down = native.model.getAdjacencies(dim,tag)
            up,down = sorted(int(v) for v in up),sorted(int(v) for v in down)
            if down != boundary:
                raise ValueError("independent native incidence disagrees")
            rows.append({"tag":tag,"kind":native.model.getType(dim,tag),
                "bbox_mm":[float(raw[i]) for i in (0,3,1,4,2,5)],"boundary":boundary,"upward":up,
                "measure_native":float(native.model.occ.getMass(dim,tag)) if dim else None,
                "point_mm":[float(v) for v in native.model.getValue(dim,tag,[])] if dim == 0 else None})
        result[str(dim)] = rows
    if validate:
        index_snapshot(result,cfg)
    return result


def index_snapshot(value,cfg):
    if set(value) != {"0","1","2","3"} or value["3"] != []:
        raise ValueError("complete planar dimensions required; volumes forbidden")
    index = {}
    tolerance = cfg["coordinate_atol_mm"]
    for dim in range(3):
        rows = value[str(dim)]
        if not isinstance(rows,list) or not 0 < len(rows) <= cfg["entity_count_max_per_dimension"]:
            raise ValueError("planar entity count outside cap")
        ids([r["tag"] for r in rows])
        index[dim] = {r["tag"]:r for r in rows}
        for r in rows:
            if set(r) != {"tag","kind","bbox_mm","boundary","upward","measure_native","point_mm"}:
                raise ValueError("unexpected planar entity fields")
            box = r["bbox_mm"]
            if (not isinstance(box,list) or len(box) != 6 or not all(coordinate(x) for x in box)
                    or any(box[k] > box[k+1] for k in (0,2,4)) or max(abs(box[4]),abs(box[5])) > tolerance
                    or r["kind"] != ("Point","Line","Plane")[dim]):
                raise ValueError("nonplanar/nonlinear/invalid CAD entity")
            ids(r["boundary"],empty=dim == 0)
            ids(r["upward"],empty=dim == 2)
            if dim == 0:
                point = r["point_mm"]
                if (r["boundary"] or r["measure_native"] is not None or not isinstance(point,list)
                        or len(point) != 3 or not all(coordinate(x) for x in point) or point[2] != 0.
                        or not bounds_inside([v for x in point for v in (x,x)],box,tolerance)):
                    raise ValueError("invalid native planar point")
            elif r["point_mm"] is not None or not coordinate(r["measure_native"]) or r["measure_native"] <= 0:
                raise ValueError("positive native planar measure required")
            if dim == 2 and r["upward"]:
                raise ValueError("planar face has a volume parent")
    for dim in (1,2):
        inverse = {tag:set() for tag in index[dim-1]}
        for tag,r in index[dim].items():
            for child in r["boundary"]:
                if child not in inverse or not bounds_inside(index[dim-1][child]["bbox_mm"],r["bbox_mm"],tolerance):
                    raise ValueError("unknown/outside child CAD entity")
                inverse[child].add(tag)
        if any(not parents or parents != set(index[dim-1][tag]["upward"]) for tag,parents in inverse.items()):
            raise ValueError("orphan or disagreeing independent CAD incidence")
    for edge in index[1].values():
        if len(edge["boundary"]) != 2:
            raise ValueError("straight edge must have two endpoints")
        a,b = [index[0][p]["point_mm"] for p in edge["boundary"]]
        dx,dy = abs(a[0]-b[0]),abs(a[1]-b[1])
        if not ((dx <= tolerance < dy) or (dy <= tolerance < dx)) or not close(math.hypot(dx,dy),edge["measure_native"],cfg):
            raise ValueError("non-axis-aligned/short/incorrect-length CAD edge")
    for face in index[2].values():
        degree = Counter(p for e in face["boundary"] for p in index[1][e]["boundary"])
        if len(degree) < 4 or any(n != 2 for n in degree.values()):
            raise ValueError("planar face boundary is not a union of closed loops")
    return index


def review_report(report,boxes,domain,cfg,options):
    oracle = footprint_partition(boxes,domain)
    if (set(report) != {"schema","canonical_boxes_mm","domain_box_mm","input_surface_tags",
                       "fragment_output_surfaces","fragment_map","before","after","options"}
            or report["schema"] != SCHEMA or report["canonical_boxes_mm"] != boxes or report["domain_box_mm"] != domain
            or report["options"] != options or not all(coordinate(v) for v in report["options"].values())):
        raise ValueError("planar CAD report identity/options mismatch")
    tolerance = cfg["coordinate_atol_mm"]
    before,after = (index_snapshot(report[k],cfg) for k in ("before","after"))
    ordered = report["input_surface_tags"]
    if not isinstance(ordered,list) or len(ordered) != len(boxes)+1:
        raise ValueError("planar creation order/coverage missing")
    if ids(sorted(ordered)) != set(before[2]):
        raise ValueError("native input surface identity mismatch")
    for tag,box in zip(ordered,[domain,*boxes]):
        face = before[2][tag]
        if (any(abs(a-b) > tolerance for a,b in zip(face["bbox_mm"],planar_box(box)))
                or not close(face["measure_native"],(box[1]-box[0])*(box[3]-box[2]),cfg)
                or len(face["boundary"]) != 4):
            raise ValueError("native input rectangle differs from canonical footprint")
        points = {p for e in face["boundary"] for p in before[1][e]["boundary"]}
        expected = [(x,y) for x in box[:2] for y in box[2:4]]
        if len(points) != 4 or any(sum(abs(before[0][p]["point_mm"][0]-x) <= tolerance
                                     and abs(before[0][p]["point_mm"][1]-y) <= tolerance for p in points) != 1 for x,y in expected):
            raise ValueError("native input rectangle corner mismatch")
    mapping = report["fragment_map"]
    if not isinstance(mapping,list) or len(mapping) != len(boxes)+1:
        raise ValueError("fragment provenance input count mismatch")
    descendants = [ids(row) for row in mapping]
    all_faces = set(after[2])
    if descendants[0] != all_faces or ids(report["fragment_output_surfaces"]) != all_faces or any(not d <= all_faces for d in descendants):
        raise ValueError("fragment output/provenance/entity coverage mismatch")
    ownership = {tag:tuple(i for i,d in enumerate(descendants[1:]) if tag in d) for tag in sorted(all_faces)}
    expected_area = {tuple(g["owners"]):unpack(g["area_mm2"]) for g in oracle["groups"]}
    if set(ownership.values()) != set(expected_area):
        raise ValueError("complete native ownership masks disagree with exact oracle")
    for mask,area in expected_area.items():
        if not close(math.fsum(after[2][tag]["measure_native"] for tag in all_faces if ownership[tag] == mask),area,cfg):
            raise ValueError("native ownership area differs from exact oracle")
    for tag,owners in ownership.items():
        if any(not bounds_inside(after[2][tag]["bbox_mm"],planar_box(boxes[i]),tolerance) for i in owners):
            raise ValueError("fragment lies outside its canonical conductor owners")
    for dim in range(3):
        if any(not bounds_inside(r["bbox_mm"],planar_box(domain),tolerance) for r in after[dim].values()):
            raise ValueError("fragment entity outside enclosing footprint")
    outer = [[] for _ in range(4)]
    for tag,edge in after[1].items():
        a,b = [after[0][p]["point_mm"] for p in edge["boundary"]]
        sides = [s for s in range(4) if on_side(a,b,domain,s,tolerance)]
        if len(sides) > 1 or len(edge["upward"]) != (1 if sides else 2):
            raise ValueError("nonmanifold/unidentified exterior CAD curve")
        if not any(on_side(a,b,box,side,tolerance) for box in [domain,*boxes] for side in range(4)):
            raise ValueError("CAD curve not on a canonical footprint boundary")
        if sides:
            outer[sides[0]].append(edge["measure_native"])
    for side,lengths in enumerate(outer):
        k = 2*(1-side//2)
        if not lengths or not close(math.fsum(lengths),domain[k+1]-domain[k],cfg):
            raise ValueError("outer footprint side length not conserved")
    return {"planar_cad_contract_passed":True,"ownership":{str(k):list(v) for k,v in ownership.items()},
        "exact_partition":oracle,"entity_counts":{str(d):len(after[d]) for d in range(3)},
        "coordinates_snapped":False,"planar_mesh_validated":False,**{k:False for k in CLOSED}}


if __name__ == "__main__":
    raise SystemExit("Library only; native construction requires the guarded SLURM integration")
