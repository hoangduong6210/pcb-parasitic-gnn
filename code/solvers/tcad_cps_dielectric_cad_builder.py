"""Guarded native CAD construction/removal; deliberately no mesh generation."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_dielectric_cad import PHASE, check_allocation, check_source, check_runtime, mode_input, protocol
from tcad_cps_dielectric_cad_metadata import (classify_before, domain_inputs, reachable,
    review_report, snapshot_index, tags, volume, close, bbox_matches)
from geometry_contract import geometry_sha256


def dim_tags(pairs, dim):
    values = []
    for pair in pairs:
        if len(pair) != 2 or type(pair[0]) is not int or pair[0] != dim or type(pair[1]) is not int:
            raise ValueError("unexpected native entity dimension/type")
        values.append(pair[1])
    tags(sorted(values), empty=True)
    return sorted(values)


def snapshot(native, cfg):
    """Read both native incidence directions; no geometry mutation here."""
    result = {}
    for dim in range(4):
        ids = dim_tags(native.model.getEntities(dim), dim)
        if not 0 < len(ids) <= cfg["entity_count_max_per_dimension"]:
            raise ValueError("native entity count outside cap")
        rows = []
        for tag in ids:
            raw = native.model.getBoundingBox(dim, tag)
            bbox = [float(raw[i]) for i in (0, 3, 1, 4, 2, 5)]
            boundary = dim_tags(native.model.getBoundary([(dim, tag)], combined=False,
                oriented=False, recursive=False), dim-1) if dim else []
            up, down = native.model.getAdjacencies(dim, tag)
            # The Python API uses native integer arrays for adjacencies.
            up, down = sorted(int(v) for v in up), sorted(int(v) for v in down)
            if down != boundary:
                raise ValueError("native getBoundary/getAdjacencies disagree")
            rows.append({"tag": tag, "bbox_mm": bbox, "boundary": boundary, "upward": up,
                "measure_native": float(native.model.occ.getMass(dim, tag)) if dim else None,
                "kind": native.model.getType(dim, tag)})
        result[str(dim)] = rows
    snapshot_index(result, cfg)
    return result


def build_cad(mode, progress):
    p = protocol()
    check_allocation(PHASE, p)
    check_source()
    check_runtime(p)
    _, layout, arm = mode_input(mode, p)
    cfg = p[PHASE]["geometry_checks"]
    boxes, domain = domain_inputs(layout, arm["pad_mm"], cfg)
    progress("geometry_validated", {"n_traces": len(boxes)})
    import gmsh
    if gmsh.isInitialized():
        raise ValueError("CAD worker requires a fresh native session")
    gmsh.initialize([], readConfigFiles=False, run=False)
    report = None
    try:
        options = {}
        for name, value in p[PHASE]["cad_options"].items():
            gmsh.option.setNumber(name, value)
            options[name] = gmsh.option.getNumber(name)
        if options != p[PHASE]["cad_options"]:
            raise ValueError("effective CAD options differ from protocol")
        gmsh.model.add("tcad_dielectric_domain")
        occ = gmsh.model.occ
        inputs = [occ.addBox(b[0], b[2], b[4], b[1]-b[0], b[3]-b[2], b[5]-b[4])
                  for b in [domain, *boxes]]
        occ.synchronize()
        for tag, expected in zip(inputs, [domain, *boxes]):
            raw = gmsh.model.getBoundingBox(3, tag)
            actual = [float(raw[i]) for i in (0, 3, 1, 4, 2, 5)]
            if not bbox_matches(actual, expected, cfg) or not close(occ.getMass(3, tag), volume(expected), cfg):
                raise ValueError("native input box differs from canonical geometry")
        output, mapping = occ.fragment([(3, inputs[0])], [(3, t) for t in inputs[1:]],
                                       tag=-1, removeObject=True, removeTool=True)
        occ.synchronize()
        output = dim_tags(output, 3)
        provenance = [dim_tags(row, 3) for row in mapping]
        progress("occ_fragmented", {"n_volumes": len(output), "input_count": len(inputs)})
        before = snapshot(gmsh, cfg)
        index, plan = classify_before(before, layout, arm["pad_mm"], provenance, cfg)
        if output != sorted(index[3]):
            raise ValueError("native fragment output/entity mismatch")
        reach = reachable(index, plan["volumes"]["dielectric"])
        removed = {str(dim): sorted(set(index[dim])-reach[dim]) for dim in range(4)}
        progress("cad_before_verified", {"entity_counts": {str(d): len(index[d]) for d in range(4)}})
        occ.remove([(3, v) for v in removed["3"]], recursive=False)
        occ.synchronize()
        if dim_tags(gmsh.model.getEntities(3), 3) != sorted(reach[3]):
            raise ValueError("metal-volume removal changed dielectric volumes")
        progress("metal_volumes_removed", {"removed_volumes": removed["3"]})
        # Never recursively erase a face that remains an electrode interface.
        # Remove only pre-proven metal-only debris, after its parents are gone.
        for dim in (2, 1, 0):
            current = set(dim_tags(gmsh.model.getEntities(dim), dim))
            if not reach[dim] <= current or not current <= set(index[dim]):
                raise ValueError("unexpected entity lost/created during removal")
            orphan = current-reach[dim]
            if not orphan <= set(removed[str(dim)]):
                raise ValueError("unproven orphan removal target")
            for tag in sorted(orphan):
                up, _ = gmsh.model.getAdjacencies(dim, tag)
                if len(up):
                    raise ValueError("proposed orphan still has parent entity")
            if orphan:
                occ.remove([(dim, tag) for tag in sorted(orphan)], recursive=False)
                occ.synchronize()
        progress("orphan_entities_removed", {"removed_entities": removed})
        after = snapshot(gmsh, cfg)
        report = {"schema": "pcb-gnn.dielectric-cad-report.v1", "geometry_sha256": geometry_sha256(layout),
            "canonical_boxes_mm": boxes, "domain_box_mm": domain, "input_volume_tags": inputs,
            "fragment_output_volumes": output, "fragment_map": provenance,
            "before": before, "after": after, "removed_entities": removed, "options": options}
        summary = review_report(report, layout, arm["pad_mm"], cfg, p[PHASE]["cad_options"])
        progress("cad_after_verified", summary)
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
    progress("gmsh_finalized", {})
    return report
