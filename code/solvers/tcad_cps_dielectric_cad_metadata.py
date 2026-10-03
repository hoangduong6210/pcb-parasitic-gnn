"""Stdlib-only replay of CAD metadata; never constructs geometry or a mesh."""
from __future__ import annotations
import math

from geometry_contract import geometry_sha256, trace_box, validate_layout
from tcad_cps_dielectric_topology import classify_interfaces


def tags(values, *, empty=False):
    if not isinstance(values, list) or any(type(v) is not int or v <= 0 for v in values):
        raise ValueError("invalid CAD tag list")
    if values != sorted(set(values)) or (not values and not empty):
        raise ValueError("CAD tags must be unique, sorted and present")
    return set(values)


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def domain_inputs(layout, pad, cfg):
    validate_layout(layout)
    if not finite(pad) or pad <= cfg["coordinate_atol_mm"]:
        raise ValueError("invalid CAD domain padding")
    boxes = [list(trace_box(layout, trace)) for trace in layout["traces"]]
    if any(not all(finite(v) for v in box) or any(box[i+1] <= box[i] for i in (0, 2, 4)) for box in boxes):
        raise ValueError("nonfinite/degenerate canonical box")
    for i, left in enumerate(boxes):
        for j, right in enumerate(boxes[:i]):
            if layout["traces"][i]["net"] != layout["traces"][j]["net"]:
                gap = math.sqrt(sum(max(left[k]-right[k+1], right[k]-left[k+1], 0.)**2 for k in (0, 2, 4)))
                if gap <= cfg["input_net_separation_min_mm"]:
                    raise ValueError("insufficient primary/secondary CAD separation")
    domain = [v for axis in (0, 2, 4) for v in
              (min(b[axis] for b in boxes)-pad, max(b[axis+1] for b in boxes)+pad)]
    return boxes, domain


def volume(box):
    return math.prod(box[i+1]-box[i] for i in (0, 2, 4))


def close(a, b, cfg):
    return math.isclose(a, b, rel_tol=cfg["measure_rtol"], abs_tol=cfg["measure_atol_native"])


def bbox_matches(actual, expected, cfg):
    return all(abs(a-b) <= cfg["coordinate_atol_mm"] for a, b in zip(actual, expected))


def contained(actual, expected, cfg):
    tolerance = cfg["coordinate_atol_mm"]
    return all(actual[k] >= expected[k]-tolerance and actual[k+1] <= expected[k+1]+tolerance for k in (0, 2, 4))


def snapshot_index(snapshot, cfg):
    """Check complete independent upward/downward native incidence and scalars."""
    if not isinstance(snapshot, dict) or set(snapshot) != {"0", "1", "2", "3"}:
        raise ValueError("CAD snapshot must contain all dimensions")
    index = {}
    for dim in range(4):
        records = snapshot[str(dim)]
        if not isinstance(records, list) or not 0 < len(records) <= cfg["entity_count_max_per_dimension"]:
            raise ValueError("CAD entity count outside cap")
        ids = [r["tag"] for r in records]
        tags(ids)
        index[dim] = {r["tag"]: r for r in records}
        for r in records:
            if set(r) != {"tag", "bbox_mm", "measure_native", "boundary", "upward", "kind"}:
                raise ValueError("unexpected CAD entity fields")
            box = r["bbox_mm"]
            if not isinstance(box, list) or len(box) != 6 or not all(finite(v) for v in box) or any(box[k] > box[k+1] for k in (0, 2, 4)):
                raise ValueError("invalid CAD bounding box")
            if dim and (not finite(r["measure_native"]) or r["measure_native"] <= 0):
                raise ValueError("nonpositive CAD measure")
            if dim == 0 and (r["measure_native"] is not None or r["boundary"]):
                raise ValueError("invalid CAD point record")
            tags(r["boundary"], empty=dim == 0)
            tags(r["upward"], empty=True)
            if dim == 3 and r["upward"]:
                raise ValueError("volume has upward entity")
            if dim in (1, 2) and r["kind"] != {1: "Line", 2: "Plane"}[dim]:
                raise ValueError("canonical boxes require planar faces and straight edges")
            if dim == 2 and sum(box[k+1]-box[k] <= 2*cfg["coordinate_atol_mm"] for k in (0, 2, 4)) != 1:
                raise ValueError("face must lie on one coordinate plane")
    for dim in range(1, 4):
        upward = {tag: set() for tag in index[dim-1]}
        for tag, entity in index[dim].items():
            for child in entity["boundary"]:
                if child not in upward:
                    raise ValueError("unknown downward CAD entity")
                if not contained(index[dim-1][child]["bbox_mm"], entity["bbox_mm"], cfg):
                    raise ValueError("child CAD bounds outside parent")
                upward[child].add(tag)
        if any(owners != set(index[dim-1][tag]["upward"]) for tag, owners in upward.items()):
            raise ValueError("independent CAD incidence disagrees")
    return index


def reachable(index, volumes):
    reach = {3: set(volumes)}
    for dim in (3, 2, 1):
        reach[dim-1] = {child for tag in reach[dim] for child in index[dim][tag]["boundary"]}
    return reach


def classify_before(snapshot, layout, pad, provenance, cfg):
    boxes, domain = domain_inputs(layout, pad, cfg)
    index = snapshot_index(snapshot, cfg)
    if not isinstance(provenance, list) or len(provenance) != len(boxes)+1:
        raise ValueError("fragment map does not match ordered input count")
    descendants = [tags(row) for row in provenance]
    if descendants[0] != set(index[3]):
        raise ValueError("outer-box descendants do not cover all volumes")
    metal = set()
    nets = {"pri": set(), "sec": set()}
    for box, trace, children in zip(boxes, layout["traces"], descendants[1:]):
        if not children <= descendants[0] or metal & children:
            raise ValueError("missing/overlapping trace descendants")
        metal.update(children)
        nets[trace["net"]].update(children)
        entities = [index[3][v] for v in children]
        if any(not contained(r["bbox_mm"], box, cfg) for r in entities):
            raise ValueError("trace descendants outside canonical box")
        union = [v for axis in (0, 2, 4) for v in
                 (min(r["bbox_mm"][axis] for r in entities), max(r["bbox_mm"][axis+1] for r in entities))]
        if not bbox_matches(union, box, cfg) or not close(math.fsum(r["measure_native"] for r in entities), volume(box), cfg):
            raise ValueError("trace volume/bounds differ from canonical box")
    if not close(math.fsum(r["measure_native"] for r in index[3].values()), volume(domain), cfg):
        raise ValueError("fragmented enclosing volume is not conserved")
    if any(not contained(r["bbox_mm"], domain, cfg) for entities in index.values() for r in entities.values()):
        raise ValueError("CAD entity outside enclosing box")

    outer, areas = [], [[] for _ in range(6)]
    tolerance = cfg["coordinate_atol_mm"]
    for tag, face in index[2].items():
        b = face["bbox_mm"]
        planes = [side for side in range(6) if abs(b[2*(side//2)]-domain[side]) <= tolerance
                  and abs(b[2*(side//2)+1]-domain[side]) <= tolerance]
        if len(planes) > 1:
            raise ValueError("outer face lies on ambiguous planes")
        if planes:
            outer.append(tag)
            areas[planes[0]].append(face["measure_native"])
    for side, values in enumerate(areas):
        expected = math.prod(domain[k+1]-domain[k] for k in (0, 2, 4) if k//2 != side//2)
        if not values or not close(math.fsum(values), expected, cfg):
            raise ValueError("six outer-plane areas are not conserved")
    plan = classify_interfaces(all_volumes=sorted(index[3]), all_faces=sorted(index[2]),
        outer_descendants=sorted(descendants[0]), primary_descendants=sorted(nets["pri"]),
        secondary_descendants=sorted(nets["sec"]), outer_faces=outer,
        volume_faces={v: r["boundary"] for v, r in index[3].items()},
        face_volumes={f: r["upward"] for f, r in index[2].items()})
    contacts = []
    for name in ("primary", "secondary"):
        curves = {e for f in plan["faces"][name] for e in index[2][f]["boundary"]}
        points = {p for e in curves for p in index[1][e]["boundary"]}
        contacts.append((curves, points))
    if contacts[0][0] & contacts[1][0] or contacts[0][1] & contacts[1][1]:
        raise ValueError("primary/secondary shared edge or vertex")
    # All original entities must belong to a volume; unidentified debris is not
    # silently removed and must never be interpreted as an electrode surface.
    initial_reach = reachable(index, index[3])
    if any(initial_reach[d] != set(index[d]) for d in range(4)):
        raise ValueError("orphan entity before conductor removal")
    return index, plan


def review_report(report, layout, pad, cfg, options):
    """Replay the full retained-domain contract using captured native metadata."""
    if set(report) != {"schema", "geometry_sha256", "canonical_boxes_mm", "domain_box_mm",
                       "input_volume_tags", "fragment_output_volumes", "fragment_map",
                       "before", "after", "removed_entities", "options"}:
        raise ValueError("unexpected CAD report fields")
    if report["schema"] != "pcb-gnn.dielectric-cad-report.v1" or report["geometry_sha256"] != geometry_sha256(layout):
        raise ValueError("CAD report geometry/schema mismatch")
    boxes, domain = domain_inputs(layout, pad, cfg)
    if report["canonical_boxes_mm"] != boxes or report["domain_box_mm"] != domain or report["options"] != options:
        raise ValueError("CAD report input/options mismatch")
    if any(not finite(v) for v in report["options"].values()) or any(
            not finite(v) for b in [report["domain_box_mm"], *report["canonical_boxes_mm"]] for v in b):
        raise ValueError("invalid CAD coordinate/option type")
    input_tags = report["input_volume_tags"]
    if len(input_tags) != len(boxes)+1 or len(set(input_tags)) != len(input_tags) or any(type(t) is not int or t <= 0 for t in input_tags):
        raise ValueError("CAD input identity/order missing")
    before, plan = classify_before(report["before"], layout, pad, report["fragment_map"], cfg)
    if tags(report["fragment_output_volumes"]) != set(before[3]):
        raise ValueError("fragment output/native entities differ")
    after = snapshot_index(report["after"], cfg)
    reach = reachable(before, plan["volumes"]["dielectric"])
    if set(report["removed_entities"]) != {"0", "1", "2", "3"}:
        raise ValueError("removal receipt dimension coverage")
    for dim in range(4):
        if set(after[dim]) != reach[dim] or tags(report["removed_entities"][str(dim)], empty=True) != set(before[dim])-reach[dim]:
            raise ValueError("retained/removed entity closure mismatch")
        for tag, current in after[dim].items():
            expected = dict(before[dim][tag])
            expected["upward"] = [] if dim == 3 else sorted(set(expected["upward"]) & reach[dim+1])
            if current != expected:
                raise ValueError("retained geometry/incidence changed during removal")
    if any(reachable(after, after[3])[d] != set(after[d]) for d in range(4)):
        raise ValueError("orphan entity remains after removal")
    return {"cad_contract_passed": True, "retained_volumes": len(after[3]),
        "primary_faces": plan["faces"]["primary"], "secondary_faces": plan["faces"]["secondary"],
        "outer_faces": plan["faces"]["outer"], "internal_dielectric_faces": plan["faces"]["internal_dielectric"],
        "before_entity_counts": {str(d): len(before[d]) for d in range(4)},
        "after_entity_counts": {str(d): len(after[d]) for d in range(4)}}
