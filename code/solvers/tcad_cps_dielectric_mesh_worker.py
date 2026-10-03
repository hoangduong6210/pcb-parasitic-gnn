#!/usr/bin/env python3
"""One fresh guarded dielectric CAD/mesh worker; no field solving."""
from __future__ import annotations
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_dielectric_mesh as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    layout_id, _, arm = c.mode_input(mode, p)
    from tcad_cps_dielectric_mesh_builder import build_mesh
    started, stages = time.monotonic(), []
    limits = p["worker_limits"][mode]

    def progress(stage, payload):
        elapsed = time.monotonic()-started
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": elapsed,
              "peak_rss_gib": rss, **payload}, allow_nan=False), flush=True)
        if len(stages) >= len(c.STAGES) or stage != c.STAGES[len(stages)]:
            raise ValueError("unexpected dielectric mesh stage sequence")
        stages.append(stage)
        if not c.bounded(elapsed, limits["worker_timeout_s"]) or not c.bounded(rss, limits["rss_gib_max"]):
            raise ValueError("dielectric mesh worker time/RSS cap exceeded")

    result = build_mesh(mode, progress, c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.payload")
    c.check_source()
    result.update(c.identity(), mode=mode, layout_id=layout_id, arm=arm, stages=stages,
        elapsed_s=time.monotonic()-started, peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
        scheduler=scheduler, runtime=runtime, **{k: False for k in c.CLOSED})
    if not c.assess_result(result, mode, p):
        raise ValueError("dielectric mesh result gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
