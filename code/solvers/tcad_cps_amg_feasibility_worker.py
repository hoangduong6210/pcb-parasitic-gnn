#!/usr/bin/env python3
"""Fresh-process feasibility solve using the frozen diagnostic AMG helpers."""
from __future__ import annotations
import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_amg_feasibility import (arm_protocol, assess_result, check_allocation,
    check_anchor, check_runtime, check_source, identity, inputs, protocol)
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
    layout_id, layout, arm = inputs(args.phase, args.arm, p)
    policy = arm_protocol(p, arm)
    # No numerical library is imported until actual allocation/source validation.
    import numpy as np
    import gmsh
    from fem_capacitance_3d import EPS0, _solve_condensed_system, _sparse_system_sha256
    from tcad_cps_amg_worker import assemble_system, solve_candidate
    np.random.seed(0)
    limits = p["resources"][args.phase]
    started, configured, stages = time.monotonic(), [], []

    def progress(stage, payload):
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("repeated AMG feasibility mesh generation")
            configured.append(apply_mesh_policy(gmsh, layout, arm, policy))
            payload = {**payload, "mesh_policy": configured[0]}
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        elapsed = time.monotonic()-started
        stages.append(stage)
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": elapsed, "peak_rss_gib": peak, **payload},
              allow_nan=False, default=numeric_json), flush=True)
        if peak > limits["rss_gib_max"] or elapsed > limits["worker_timeout_s"]:
            raise ValueError("frozen worker time/RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max"),
                         ("operator_complexity", "operator_complexity_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    m, K, A, b, expanded, free = assemble_system(layout, policy, arm, progress)
    A = A.tocsr(copy=False)
    A.sum_duplicates()
    A.sort_indices()
    system = {"system_sha256": _sparse_system_sha256(A, b), "mesh_nodes": int(m.p.shape[1]),
              "mesh_tetrahedra": int(m.t.shape[1]), "n_free": int(A.shape[0]), "nnz": int(A.nnz)}
    progress("system_fingerprinted", system)
    check_anchor(system, args.phase, arm, p)
    solution, metadata = solve_candidate(A.copy(), b.copy(), p, progress)
    if metadata["input_system_sha256"] != system["system_sha256"]:
        raise ValueError("candidate changed the system identity")

    def capacitance(values):
        u = expanded.copy()
        u[free] = values
        return EPS0 * p["physics"]["eps_r"] * float(u @ (K @ u)) * 1e12

    result = {**system, **metadata, "linear_solver": "pyamg_unsmoothed_aggregation_cg",
              "cps_pf": capacitance(solution)}
    if args.phase == "smoke":
        direct, other = _solve_condensed_system(A.copy(), b.copy(), linear_solver="direct",
            rtol=p["linear_solver"]["rtol"], maxiter=p["linear_solver"]["maxiter"], progress=progress)
        result["comparison"] = {**other, "system_sha256": other["input_system_sha256"], "cps_pf": capacitance(direct)}
        result["solution_relative_l2"] = float(np.linalg.norm(solution-direct)/max(float(np.linalg.norm(direct)), np.finfo(float).tiny))
    result.update(**identity(), arm=arm, layout_id=layout_id, geometry_sha256=geometry_sha256(layout),
        mesh_policy=configured[0], mesh_policy_sha256=sha256_json(configured[0]), stages=stages,
        scheduler=scheduler, runtime=runtime, elapsed_s=time.monotonic()-started,
        peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2)
    check_source()
    if len(configured) != 1 or not assess_result(result, p, args.phase):
        raise ValueError("AMG feasibility numerical/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
