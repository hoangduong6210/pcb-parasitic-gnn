#!/usr/bin/env python3
"""Guarded real-layout axis planning; never allocate 3D connectivity or solve."""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_layer_grid_dyadic as c
from scientific_artifact import sha256_file, sha256_json

SUMMARY_KEYS = ("width_budget", "total_tensor_cells", "dielectric_cells", "tetrahedra", "tensor_node_upper_bound",
    "axis_width_ratio", "jacobian_condition_upper_bound_squared", "planning_checks", "planning_feasible")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    if mode not in p[c.PHASE]["modes"]:
        raise ValueError("unfrozen grid planning mode")
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    # Even real-layout axis planning is restricted to the verified allocation.
    from tcad_cps_layer_grid_dyadic_axes import plan_boxes
    from tcad_cps_dielectric_cad_metadata import domain_inputs, review_report
    from geometry_contract import geometry_sha256
    started = time.monotonic()
    layout_id, layout, arm = c.mode_input(mode, p)
    cfg = p["dielectric_cad"]
    cad = c.cad_report(mode, p)
    review_report(cad, layout, arm["pad_mm"], cfg["geometry_checks"], cfg["cad_options"])
    boxes, domain = domain_inputs(layout, arm["pad_mm"], cfg["geometry_checks"])
    if boxes != cad["canonical_boxes_mm"] or domain != cad["domain_box_mm"]:
        raise ValueError("canonical grid inputs differ from archived CAD")
    report = plan_boxes(boxes, domain, c.policy(mode, p), p[c.PHASE], p["worker_limits"][mode])
    report.update(layout_id=layout_id, geometry_sha256=geometry_sha256(layout), cad_report_sha256=sha256_json(cad), arm=arm)
    data = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    if len(data) > p[c.PHASE]["report_bytes_max"]:
        raise ValueError("grid planning report byte cap exceeded")
    output = c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.report.json"
    with output.open("xb") as stream:
        stream.write(data)
    c.check_source()
    elapsed = time.monotonic()-started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2
    if not c.bounded(elapsed, p["worker_limits"][mode]["worker_timeout_s"]) or not c.bounded(rss, p["worker_limits"][mode]["rss_gib_max"]):
        raise ValueError("grid planning worker time/RSS cap exceeded")
    result = {**c.identity(), "scheduler": scheduler, "runtime": runtime, "mode": mode,
        "report_sha256": sha256_file(output), "report_bytes": len(data), "summary": {k: report[k] for k in SUMMARY_KEYS},
        "elapsed_s": elapsed, "peak_rss_gib": rss, **{k: False for k in c.CLOSED}}
    print("RESULT="+json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
