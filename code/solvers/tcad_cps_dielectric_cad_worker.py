#!/usr/bin/env python3
"""Fresh guarded CAD session with complete metadata; no meshing or field solve."""
from __future__ import annotations
import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_dielectric_cad as c
from scientific_artifact import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    layout_id, layout, arm = c.mode_input(mode, p)
    from tcad_cps_dielectric_cad_builder import build_cad
    started, stages = time.monotonic(), []
    limits = p["worker_limits"][mode]

    def progress(stage, payload):
        elapsed = time.monotonic()-started
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": elapsed,
              "peak_rss_gib": rss, **payload}, allow_nan=False), flush=True)
        if stages != c.STAGES[:len(stages)] or len(stages) >= len(c.STAGES) or stage != c.STAGES[len(stages)]:
            raise ValueError("unexpected CAD stage sequence")
        stages.append(stage)
        if not c.bounded(elapsed, limits["worker_timeout_s"]) or not c.bounded(rss, limits["rss_gib_max"]):
            raise ValueError("CAD worker time/RSS cap exceeded")

    report = build_cad(mode, progress)
    cfg = p[c.PHASE]
    summary = c.review_report(report, layout, arm["pad_mm"], cfg["geometry_checks"], cfg["cad_options"])
    c.check_source()
    result = {**c.identity(), "mode": mode, "layout_id": layout_id, "arm": arm,
        "cad_report": report, "cad_report_sha256": sha256_json(report), "cad_summary": summary,
        "cad_contract_passed": True, "stages": stages, "mesh_generated": False, "mesh_feasible": False,
        "field_solver_executed": False, "reference_qualified": False, "training_may_start": False,
        "claim_eligible": False, "elapsed_s": time.monotonic()-started,
        "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
        "scheduler": scheduler, "runtime": runtime}
    if not c.assess_result(result, mode, p):
        raise ValueError("CAD result gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
