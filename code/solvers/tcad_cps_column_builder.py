"""Guarded fresh 2D native construction; never generate volume connectivity."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_column_feasibility as c
from scientific_artifact import sha256_file, sha256_json


def preserve_json(path, value, cap):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in planar output path")
    data = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    if not 0 < len(data) <= cap:
        raise ValueError("planar metadata byte cap exceeded")
    with path.open("xb") as stream:
        stream.write(data)


def sizing_policy(boxes, policy, p):
    expansion = p["mesh"]["box_expansion_mm"]
    if expansion <= 0:
        raise ValueError("positive sizing expansion required")
    fields = []
    for box in boxes:
        fields.append({"XMin": box[0]-expansion, "XMax": box[1]+expansion,
            "YMin": box[2]-expansion, "YMax": box[3]+expansion, "ZMin": -expansion, "ZMax": expansion,
            "VIn": policy["near_size_mm"], "VOut": policy["far_size_mm"], "Thickness": p["mesh"]["transition_thickness_mm"]})
    return {"options": {**p[c.PHASE]["mesh_options"], "Mesh.MeshSizeMin": policy["near_size_mm"],
            "Mesh.MeshSizeMax": policy["far_size_mm"]}, "box_fields": fields, "background": "Min",
            "policy": policy}


def apply_sizing(native, requested):
    options = requested["options"]
    for name, value in options.items():
        native.option.setNumber(name, value)
    if {k: native.option.getNumber(k) for k in options} != options:
        raise ValueError("effective planar mesh options differ")
    api, tags, fields = native.model.mesh.field, [], []
    if list(api.list()):
        raise ValueError("fresh planar session has preexisting mesh fields")
    for expected in requested["box_fields"]:
        tag = api.add("Box")
        for name, value in expected.items():
            api.setNumber(tag, name, value)
        observed = {k: api.getNumber(tag, k) for k in expected}
        if api.getType(tag) != "Box" or observed != expected:
            raise ValueError("effective planar Box field differs")
        fields.append({"tag": tag, "settings": observed})
        tags.append(tag)
    background = api.add("Min")
    api.setNumbers(background, "FieldsList", tags)
    if api.getType(background) != "Min" or list(api.getNumbers(background, "FieldsList")) != tags:
        raise ValueError("effective planar Min field differs")
    api.setAsBackgroundMesh(background)
    if sorted(int(tag) for tag in api.list()) != sorted([*tags, background]):
        raise ValueError("unexpected planar sizing field")
    return {"requested": requested, "box_fields": fields, "background_tag": background}


def build(mode, progress, directory):
    p = c.protocol()
    if mode not in p[c.PHASE]["modes"]:
        raise ValueError("unfrozen planar mode")
    c.check_allocation(c.PHASE, p)
    c.check_source()
    c.check_runtime(p)
    if directory != c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.payload":
        raise ValueError("planar output path differs from attempt/mode")
    # Numerical/native imports and real geometry processing are below guards.
    import gmsh
    import tcad_cps_column_cad as cad
    import tcad_cps_column_mesh as mesh
    from tcad_cps_column_bundle import write_bundle
    from tcad_cps_column_planning import plan_packet
    from tcad_cps_dielectric_cad_metadata import domain_inputs, review_report
    from geometry_contract import geometry_sha256
    layout_id, layout, arm = c.mode_input(mode, p)
    cfg, options = p["dielectric_cad"]["geometry_checks"], p["dielectric_cad"]["cad_options"]
    original = c.cad_report(mode, p)
    review_report(original, layout, arm["pad_mm"], cfg, options)
    boxes, domain = domain_inputs(layout, arm["pad_mm"], cfg)
    if boxes != original["canonical_boxes_mm"] or domain != original["domain_box_mm"]:
        raise ValueError("planar canonical inputs differ from archived CAD")
    if mesh.LEAKAGE_BITS != p[c.PHASE]["leakage_upper_bound_bits"]:
        raise ValueError("unfrozen leakage-bound rounding rule")
    directory.mkdir(exist_ok=False)
    cap = p[c.PHASE]["report_bytes_max"]
    progress("canonical_geometry_verified", {"n_traces": len(boxes), "cad_report_sha256": sha256_json(original)})
    if gmsh.isInitialized():
        raise ValueError("planar builder requires fresh native session")
    gmsh.initialize([], readConfigFiles=False, run=False)
    try:
        for name, value in options.items():
            gmsh.option.setNumber(name, value)
        if {k: gmsh.option.getNumber(k) for k in options} != options:
            raise ValueError("effective planar CAD options differ")
        gmsh.model.add("tcad_column_footprints")
        occ = gmsh.model.occ
        inputs = [occ.addRectangle(b[0], b[2], 0., b[1]-b[0], b[3]-b[2]) for b in [domain, *boxes]]
        occ.synchronize()
        before = cad.snapshot(gmsh, cfg, validate=False)
        preserve_json(directory / "inputs.json", {"canonical_boxes_mm": boxes, "domain_box_mm": domain,
            "input_surface_tags": inputs, "before": before, "options": options}, cap)
        progress("planar_inputs_preserved", {"surfaces": len(inputs)})
        output, mapping = occ.fragment([(2, inputs[0])], [(2, t) for t in inputs[1:]],
            tag=-1, removeObject=True, removeTool=True)
        occ.synchronize()
        after = cad.snapshot(gmsh, cfg, validate=False)
        cad_report = {"schema": cad.SCHEMA, "canonical_boxes_mm": boxes, "domain_box_mm": domain,
            "input_surface_tags": inputs, "fragment_output_surfaces": cad.dimensions(output, 2),
            "fragment_map": [cad.dimensions(row, 2) for row in mapping], "before": before, "after": after, "options": options}
        preserve_json(directory / "cad.json", cad_report, cap)
        progress("planar_cad_preserved", {"cad_sha256": sha256_json(cad_report)})
        cad_summary = cad.review_report(cad_report, boxes, domain, cfg, options)
        progress("planar_cad_verified", {"entity_counts": cad_summary["entity_counts"]})
        policy = c.policy(mode, p)
        sizing = apply_sizing(gmsh, sizing_policy(boxes, policy, p))
        preserve_json(directory / "sizing.json", sizing, cap)
        progress("planar_mesh_generate_started", {"dimension": 2})
        gmsh.model.mesh.generate(2)
        progress("planar_mesh_generate_finished", {"dimension": 2})
        packet = mesh.read_native(gmsh, after, p["worker_limits"][mode])
        bundle = write_bundle(directory / "raw", packet, p[c.PHASE]["payload"])
        progress("planar_packet_preserved", {"packet_sha256": bundle["packet_sha256"], "payload_bytes": bundle["payload_bytes"]})
        post = cad.snapshot(gmsh, cfg, validate=False)
        preserve_json(directory / "post_mesh_cad.json", post, cap)
        if post != after:
            raise ValueError("planar CAD changed during native meshing")
        progress("planar_cad_unchanged", {})
        plan = plan_packet(packet, cad_report, boxes, domain, cfg, options, policy, p[c.PHASE], p["worker_limits"][mode])
        report = {"schema": "pcb-gnn.column-feasibility-report.v1", "layout_id": layout_id,
            "geometry_sha256": geometry_sha256(layout), "arm": arm, "canonical_cad_sha256": sha256_json(original),
            "planar_cad_sha256": sha256_json(cad_report), "sizing_sha256": sha256_json(sizing),
            "gmsh_build_options": gmsh.option.getString("General.BuildOptions"), "plan": plan,
            "planar_mesh_generated": True, **{k: False for k in c.CLOSED}}
        preserve_json(directory / "report.json", report, cap)
        progress("column_plan_preserved", {"planning_feasible": plan["planning_feasible"], "planning_checks": plan["planning_checks"]})
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
    progress("gmsh_finalized", {})
    return {"report_sha256": sha256_file(directory / "report.json"), "report_bytes": (directory / "report.json").stat().st_size,
        "planning_feasible": plan["planning_feasible"], "planar_mesh_generated": True,
        "bundle": {"manifest_sha256": sha256_file(directory / "raw/manifest.json"),
            "packet_sha256": bundle["packet_sha256"], "payload_bytes": bundle["payload_bytes"]}}


if __name__ == "__main__":
    raise SystemExit("Use the allocation/source/runtime-guarded column worker")
