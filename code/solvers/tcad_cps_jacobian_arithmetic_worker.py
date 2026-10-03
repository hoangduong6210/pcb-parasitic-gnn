#!/usr/bin/env python3
"""One guarded fresh arithmetic worker; read-only existing packet input."""
import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
import tcad_cps_jacobian_arithmetic as c
from scientific_artifact import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    mode = parser.parse_args().mode
    p = c.protocol()
    kind = c.input_kind(mode, p)
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    # Numerical imports/loading are strictly after allocation/source/runtime.
    from tcad_cps_dielectric_mesh_bundle import load_bundle
    from tcad_cps_jacobian_exact import diagnose
    started = time.monotonic()
    report = diagnose(load_bundle(c.input_path(mode, p), p[c.parent.PHASE]["payload"]),
        p["worker_limits"][mode], p[c.PHASE]["jacobian_rtol"])
    expected = p[c.PHASE]["inputs"][kind]
    if report["packet_sha256"] != expected["packet_sha256"] or report["summary"]["tetrahedra"] != expected["tetrahedra"]:
        raise ValueError("arithmetic report input/coverage mismatch")
    data = (json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()
    if len(data) > p[c.PHASE]["report_bytes_max"]:
        raise ValueError("arithmetic report byte cap exceeded")
    output = c.attempt_directory(os.environ["SLURM_JOB_ID"]) / f"{mode}.report.json"
    with output.open("xb") as stream:
        stream.write(data)
    c.check_source()
    elapsed = time.monotonic()-started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2
    if not c.bounded(elapsed, p["worker_limits"][mode]["worker_timeout_s"]) or not c.bounded(rss, p["worker_limits"][mode]["rss_gib_max"]):
        raise ValueError("arithmetic worker time/RSS cap exceeded")
    result = {**c.identity(), "scheduler": scheduler, "runtime": runtime, "mode": mode,
        "packet_sha256": report["packet_sha256"], "report_sha256": sha256_file(output), "report_bytes": len(data),
        "summary": report["summary"], "elapsed_s": elapsed, "peak_rss_gib": rss, **{k: False for k in c.CLOSED}}
    print("RESULT="+json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
