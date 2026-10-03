#!/usr/bin/env python3
"""Fresh-process compact-support solve, guarded before numerical imports."""
from __future__ import annotations
import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_support_recovery import (arm_protocol, assess_result, check_allocation,
    check_runtime, check_source, identity, protocol, target)
from tcad_cps_reference_worker import apply_mesh_policy, numeric_json
from geometry_contract import geometry_sha256
from scientific_artifact import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "feasibility"), required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation(args.phase, p)
    check_source()
    runtime = check_runtime(p)
    if args.phase == "smoke":
        arm, layout, layout_id = p["smoke"]["arm"], p["smoke"]["layout"], "smoke"
    else:
        row = target(p)
        layout, layout_id = row["layout"], row["layout_id"]
        arm = next(a for a in p["recovery"]["recovery_arms"] if a["name"] == args.arm)
    if arm["name"] != args.arm:
        raise ValueError("unfrozen recovery arm")
    policy = arm_protocol(p, arm)
    # No mesher/solver/numerical-stack import is allowed above these guards.
    import numpy as np
    import gmsh
    from fem_capacitance_3d import fem_cps_3d_diagnostics
    np.random.seed(0)
    limits = p["resources"][args.phase]
    configured, stages = [], []
    started = time.monotonic()

    def progress(stage, payload):
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("unexpected repeated mesh generation")
            configured.append(apply_mesh_policy(gmsh, layout, arm, policy))
            payload = {**payload, "tcad_mesh_policy": configured[0], "inherited_h_min_h_max_overridden": True}
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        stages.append(stage)
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": time.monotonic()-started,
                                     "peak_rss_gib": peak, **payload}, allow_nan=False, default=numeric_json), flush=True)
        if peak > limits["rss_gib_max"]:
            raise MemoryError("frozen RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max"),
                         ("operator_complexity", "operator_complexity_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    solver = p["linear_solver"]
    result = fem_cps_3d_diagnostics(layout, eps_r=p["physics"]["eps_r"], refine=0, pad_mm=arm["pad_mm"],
        linear_solver=solver["name"], comparison_solver="direct" if args.phase == "smoke" else None,
        solver_rtol=solver["rtol"], solver_maxiter=solver["maxiter"], progress=progress, strict=True)
    if result is None or len(configured) != 1:
        raise ValueError("missing recovery result/mesh policy")
    result.update(peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
        elapsed_s=time.monotonic()-started, layout_id=layout_id, geometry_sha256=geometry_sha256(layout),
        arm=arm, mesh_policy=configured[0], mesh_policy_sha256=sha256_json(configured[0]),
        scheduler=scheduler, runtime=runtime, stages=stages, **identity())
    check_source()
    if not assess_result(result, p, args.phase):
        raise ValueError("recovery numerical/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
