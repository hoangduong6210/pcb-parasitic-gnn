"""Separate guarded live-session CAD-to-mesh builder; frozen CAD is untouched."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_dielectric_mesh as c
from tcad_cps_dielectric_cad_builder import dim_tags, snapshot
from tcad_cps_dielectric_cad_metadata import (classify_before, domain_inputs, reachable,
    review_report, volume, close, bbox_matches)
from tcad_cps_dielectric_mesh_audit import audit_cad_mesh, extract_mesh_packet
from tcad_cps_dielectric_mesh_bundle import write_bundle
from tcad_cps_reference_worker import apply_mesh_policy
from geometry_contract import geometry_sha256
from scientific_artifact import sha256_file, sha256_json


def quality_observation(packet):
    """Small telemetry only; full finite signed arrays remain in the bundle."""
    import numpy as np
    return {"nodes": len(packet["node_tags"]), "tetrahedra": len(packet["tetrahedron_tags"]),
        "triangles": len(packet["triangle_tags"]), "metrics": {name: {
            "minimum": float(packet[name].min()), "maximum": float(packet[name].max()),
            "nonpositive_count": int(np.count_nonzero(packet[name] <= 0))}
            for name in ("min_sicn", "min_det_jac_mm3")}}


def build_mesh(mode, progress, directory):
    p = c.protocol()
    c.check_allocation(c.PHASE, p)
    c.check_source()
    c.check_runtime(p)
    _, layout, arm = c.mode_input(mode, p)
    if directory != c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.payload":
        raise ValueError("mesh payload path differs from attempt/mode")
    directory.mkdir(exist_ok=False)
    cfg = p["dielectric_cad"]["geometry_checks"]
    boxes, domain = domain_inputs(layout, arm["pad_mm"], cfg)
    progress("geometry_validated", {"n_traces": len(boxes)})
    import numpy as np
    import gmsh
    np.random.seed(0)
    if gmsh.isInitialized():
        raise ValueError("mesh worker requires a fresh native session")
    gmsh.initialize([], readConfigFiles=False, run=False)
    report = None
    try:
        # Same construction/removal statements as the immutable CAD builder.
        options = {}
        for name, value in p["dielectric_cad"]["cad_options"].items():
            gmsh.option.setNumber(name, value)
            options[name] = gmsh.option.getNumber(name)
        if options != p["dielectric_cad"]["cad_options"]:
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
        summary = review_report(report, layout, arm["pad_mm"], cfg, p["dielectric_cad"]["cad_options"])
        progress("cad_after_verified", summary)
        digest = sha256_json(report)
        if digest != p[c.PHASE]["cad_report_sha256"][mode]:
            raise ValueError("rebuilt CAD report differs from validated native identity")
        with (directory / "cad_report.json").open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        progress("cad_identity_verified", {"cad_report_sha256": digest})
        mesh_policy = apply_mesh_policy(gmsh, layout, arm, c.parent.parent.parent.parent.arm_protocol(p, arm))
        if mesh_policy != c.expected_policy(mode, p):
            raise ValueError("effective mesh policy differs from inherited candidate")
        build_options = gmsh.option.getString("General.BuildOptions")
        if "hxt" not in build_options.lower().split():
            raise ValueError("native build lacks HXT")
        progress("mesh_generate_started", {"mesh_policy": mesh_policy, "gmsh_build_options": build_options})
        gmsh.model.mesh.generate(3)
        raw = extract_mesh_packet(gmsh, report, p["worker_limits"][mode])
        raw_quality = quality_observation(raw)
        payload_cfg = p[c.PHASE]["payload"]
        raw_manifest = write_bundle(directory / "raw", raw, payload_cfg)
        del raw
        progress("raw_mesh_preserved", {"quality": raw_quality, "packet_sha256": raw_manifest["packet_sha256"],
            "payload_bytes": raw_manifest["payload_bytes"]})
        optimizer = p[c.PHASE]["optimizer"]
        progress("mesh_optimize_started", {"optimizer": optimizer})
        gmsh.model.mesh.optimize(**optimizer)
        progress("mesh_optimize_finished", {"optimizer": optimizer})
        # Fresh extraction after native mutation; never reuse pre-optimizer arrays.
        final = extract_mesh_packet(gmsh, report, p["worker_limits"][mode])
        final_manifest = write_bundle(directory / "final", final, payload_cfg, used_bytes=raw_manifest["payload_bytes"])
        progress("final_mesh_preserved", {"quality": quality_observation(final),
            "packet_sha256": final_manifest["packet_sha256"], "payload_bytes": final_manifest["payload_bytes"]})
        _, audit = audit_cad_mesh(final, report, layout, arm["pad_mm"], cfg,
            p["dielectric_cad"]["cad_options"], p[c.PHASE]["mesh_checks"], p["worker_limits"][mode])
        del final
        progress("boundary_audit_passed", audit)
        if snapshot(gmsh, cfg) != after:
            raise ValueError("CAD geometry changed during meshing/optimization")
        progress("cad_unchanged_after_mesh", {})
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
    progress("gmsh_finalized", {})
    bundles = {name: {"manifest_sha256": sha256_file(directory / name / "manifest.json"),
               "packet_sha256": manifest["packet_sha256"], "payload_bytes": manifest["payload_bytes"]}
               for name, manifest in (("raw", raw_manifest), ("final", final_manifest))}
    return {"cad_report": report, "cad_report_sha256": digest, "cad_summary": summary,
        "mesh_policy": mesh_policy, "mesh_policy_sha256": sha256_json(mesh_policy),
        "optimizer": optimizer, "optimizer_calls": 1, "gmsh_build_options": build_options,
        "quality_before": raw_quality, "bundles": bundles, "mesh_audit": audit,
        "mesh_audit_sha256": sha256_json(audit)}
