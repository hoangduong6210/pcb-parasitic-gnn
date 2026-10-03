#!/usr/bin/env python3
"""Allocation/source/runtime-guarded native API qualification on tiny fixtures."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "code/experiments/proofs"))
import tcad_cps_field_probe_api as c
from scientific_artifact import sha256_file, sha256_json


def main_state(native, sizing, p):
    from tcad_cps_model_field_probe import state, scaffold
    from tcad_cps_column_cad import snapshot
    api = native.model.mesh.field
    return {"session":state(native),"cad":snapshot(native,p["dielectric_cad"]["geometry_checks"],validate=False),
        "mesh":scaffold(native),
        "options":{k:native.option.getNumber(k) for k in {**p["dielectric_cad"]["cad_options"],**sizing["requested"]["options"]}},
        "fields":{"tags":[int(t) for t in api.list()],
            "expressions":[{"tag":r["tag"],"type":api.getType(r["tag"]),"F":api.getString(r["tag"],"F")} for r in sizing["distance_fields"]],
            "minimum":{"tag":sizing["minimum_tag"],"type":api.getType(sizing["minimum_tag"]),
                "FieldsList":[int(t) for t in api.getNumbers(sizing["minimum_tag"],"FieldsList")]},
            "threshold":{"tag":sizing["background_tag"],"type":api.getType(sizing["background_tag"]),
                "settings":{k:api.getNumber(sizing["background_tag"],k) for k in sizing["threshold_settings"]}}}}


def build(mode, directory):
    p = c.protocol()
    if mode not in p[c.PHASE]["modes"]:
        raise ValueError("unfrozen field probe mode")
    c.check_allocation(c.PHASE,p)
    c.check_source()
    c.check_runtime(p)
    if directory != c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.payload":
        raise ValueError("field probe payload path differs")
    # All native imports, point planning and construction occur below guards.
    import gmsh
    import tcad_cps_edge_sizing as edge
    import tcad_cps_model_field_probe as adapter
    from tcad_cps_edge_builder import preserve_json
    cfg, fixture, probe_cfg = p[c.PHASE],p[c.PHASE]["fixture"],c.probe_config(p)
    directory.mkdir(exist_ok=False)
    def preserve(name,data):
        preserve_json(directory / f"{name}.json",data,cfg["report_bytes_max"])
    preserve("fixture",fixture)
    if gmsh.isInitialized():
        raise ValueError("field probe qualification requires fresh native session")
    gmsh.initialize([],readConfigFiles=False,run=False)
    try:
        for k,v in p["dielectric_cad"]["cad_options"].items(): gmsh.option.setNumber(k,v)
        gmsh.model.add("tcad_field_probe_fixture")
        for box in [fixture["domain_mm"],*fixture["boxes_mm"]]:
            gmsh.model.occ.addRectangle(box[0],box[2],0.,box[1]-box[0],box[3]-box[2])
        gmsh.model.occ.synchronize()
        requested = edge.sizing_policy(fixture["boxes_mm"],cfg["policy"],probe_cfg,p["mesh"])
        sizing = edge.apply_sizing(gmsh,requested)
        preserve("sizing",sizing)
        edge.validate_sizing(sizing,requested)
        before = main_state(gmsh,sizing,p)
        preserve("before",before)
        if any(before["mesh"][k] for k in ("node_tags","coordinates_mm","parametric","element_types","element_tags","element_nodes")):
            raise ValueError("original fixture must have no mesh")
        if before["options"] != {**p["dielectric_cad"]["cad_options"],**requested["options"]}:
            raise ValueError("original fixture effective options differ")
        points = edge.probe_points(fixture["boxes_mm"],fixture["domain_mm"],requested,probe_cfg)
        if len(points) > cfg["fixture_points_max"]:
            raise ValueError("synthetic field-probe fixture point cap exceeded")
        try:
            distance = adapter.evaluate(gmsh,sizing["minimum_tag"],points,lambda name,data:preserve("distance."+name,data))
            size = adapter.evaluate(gmsh,sizing["background_tag"],points,lambda name,data:preserve("size."+name,data))
            comparison = adapter.comparison(points,sizing,probe_cfg,distance,size)
            preserve("comparison",comparison)
        finally:
            after = main_state(gmsh,sizing,p)
            preserve("after",after)
        if before != after:
            raise ValueError("original CAD/fields/options/mesh changed after native probe")
        edge.validate_probe(comparison,sizing,probe_cfg)
        report = {"schema":"pcb-gnn.field-probe-api-report.v1","fixture":fixture,"point_count":len(points),
            "comparison_sha256":sha256_json(comparison),"original_state_unchanged":True,
            "synthetic_probe_elements_only":True,"gmsh_build_options":gmsh.option.getString("General.BuildOptions"),
            "files_sha256":{path.name:sha256_file(path) for path in sorted(directory.iterdir())},
            **{k:False for k in c.CLOSED}}
        preserve("report",report)
    finally:
        if gmsh.isInitialized(): gmsh.finalize()
    return directory / "report.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    if mode not in p[c.PHASE]["modes"]: raise ValueError("unfrozen field probe mode")
    scheduler = c.check_allocation(c.PHASE,p)
    c.check_source()
    runtime = c.check_runtime(p)
    started = time.monotonic()
    path = build(mode,c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.payload")
    c.check_source()
    elapsed = time.monotonic()-started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2
    if not c.bounded(elapsed,p["worker_limits"][mode]["worker_timeout_s"]) or not c.bounded(rss,p["worker_limits"][mode]["rss_gib_max"]):
        raise ValueError("field probe worker time/RSS cap exceeded")
    result = {**c.identity(),"scheduler":scheduler,"runtime":runtime,"mode":mode,
        "report_sha256":sha256_file(path),"report_bytes":path.stat().st_size,
        "elapsed_s":elapsed,"peak_rss_gib":rss,"synthetic_probe_elements_only":True,**{k:False for k in c.CLOSED}}
    print("RESULT="+json.dumps(result,allow_nan=False),flush=True)


if __name__ == "__main__":
    main()
