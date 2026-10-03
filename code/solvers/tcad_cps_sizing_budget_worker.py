#!/usr/bin/env python3
"""Allocation-guarded archived geometry/sizing diagnosis; no native mesh or solve."""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_sizing_budget as c
from scientific_artifact import sha256_file, sha256_json

SUMMARY_KEYS = ("coverage", "step_field_workload_indices", "native_log_counts",
    "conditional_full_column_node_bound_from_log", "logged_nodes_within_capture_cap",
    "conditional_full_column_node_bound_passes")


def archived_geometry(mode, p):
    """Called only below main's allocation/source/runtime guards."""
    c.check_allocation(c.PHASE, p)
    c.check_source()
    c.check_runtime(p)
    from tcad_cps_dielectric_cad_metadata import domain_inputs, review_report
    from tcad_cps_column_cad import review_report as review_planar
    from tcad_cps_column_builder import sizing_policy
    from geometry_contract import geometry_sha256
    layout_id, layout, arm = c.mode_input(mode, p)
    cfg, options = p["dielectric_cad"]["geometry_checks"], p["dielectric_cad"]["cad_options"]
    original = c.cad_report(mode, p)
    review_report(original, layout, arm["pad_mm"], cfg, options)
    boxes, domain = domain_inputs(layout, arm["pad_mm"], cfg)
    if boxes != original["canonical_boxes_mm"] or domain != original["domain_box_mm"]:
        raise ValueError("sizing diagnostic geometry differs from canonical CAD")
    paths, provenance = c.archived_inputs(mode, p)
    planar, sizing = (c.read_json(c.ROOT / paths[k]) for k in ("planar_cad", "sizing"))
    review_planar(planar, boxes, domain, cfg, options)
    expected = sizing_policy(boxes, c.policy(mode, p), p)
    if (set(sizing) != {"requested", "box_fields", "background_tag"} or sizing["requested"] != expected
            or len(sizing["box_fields"]) != len(boxes)
            or any(set(row) != {"tag", "settings"} or row["settings"] != field
                for row,field in zip(sizing["box_fields"], expected["box_fields"]))):
        raise ValueError("archived effective sizing differs from frozen parent settings")
    tags = [row["tag"] for row in sizing["box_fields"]] + [sizing["background_tag"]]
    if any(type(t) is not int or t <= 0 for t in tags) or len(set(tags)) != len(tags):
        raise ValueError("archived sizing field tags collide")
    return boxes, domain, sizing["requested"], (c.ROOT / paths["native_stdout"]).read_text(), {
        "layout_id": layout_id, "geometry_sha256": geometry_sha256(layout), "arm": arm,
        "canonical_cad_sha256": sha256_json(original), "archived_inputs": provenance}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    if mode not in p[c.PHASE]["modes"]:
        raise ValueError("unfrozen sizing diagnostic mode")
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    from tcad_cps_sizing_budget_math import diagnose
    started = time.monotonic()
    boxes, domain, sizing, log, provenance = archived_geometry(mode, p)
    report = diagnose(boxes, domain, sizing, c.policy(mode, p), p["worker_limits"][mode], p[c.PHASE], log)
    report.update(provenance)
    data = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    if len(data) > p[c.PHASE]["report_bytes_max"]:
        raise ValueError("sizing diagnostic report byte cap exceeded")
    output = c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.report.json"
    with output.open("xb") as stream:
        stream.write(data)
    c.check_source()
    elapsed = time.monotonic()-started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2
    if not c.bounded(elapsed, p["worker_limits"][mode]["worker_timeout_s"]) or not c.bounded(rss, p["worker_limits"][mode]["rss_gib_max"]):
        raise ValueError("sizing diagnostic worker time/RSS cap exceeded")
    result = {**c.identity(), "scheduler": scheduler, "runtime": runtime, "mode": mode,
        "report_sha256": sha256_file(output), "report_bytes": len(data), "summary": {k: report[k] for k in SUMMARY_KEYS},
        "elapsed_s": elapsed, "peak_rss_gib": rss, **{k: False for k in c.CLOSED}}
    print("RESULT="+json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
