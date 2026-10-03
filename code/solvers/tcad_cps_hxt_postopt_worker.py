#!/usr/bin/env python3
"""Guarded HXT plus one explicit optimizer; no field assembly or solve."""
from __future__ import annotations
import argparse
import copy
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_hxt_postopt import (assess_result, assess_quality, check_allocation, check_runtime,
    check_source, identity, mode_input, parent, protocol, quality_counts, valid_observation)
from tcad_cps_hxt_isolation_worker import collect_quality
from tcad_cps_mesh_probe_worker import mesh_metadata
from tcad_cps_reference_worker import apply_mesh_policy, numeric_json
from geometry_contract import geometry_sha256
from scientific_artifact import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation("hxt_postopt", p)
    check_source()
    runtime = check_runtime(p)
    layout_id, layout, arm = mode_input(args.mode, p)
    import numpy as np
    import gmsh
    from tcad_cps_hxt_postopt_mesh import _build_mesh
    np.random.seed(0)
    started, stages, configured, observed_logging, qualities = time.monotonic(), [], [], {}, {}
    optimizers = {"mesh_optimize_started": [], "mesh_optimize_finished": []}
    build_options, nodes_before = "", None
    limits = p["worker_limits"][args.mode]

    def enforce_caps(payload):
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2 > limits["rss_gib_max"] or time.monotonic()-started > limits["worker_timeout_s"]:
            raise ValueError("HXT-postopt worker time/RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    def progress(stage, payload):
        nonlocal build_options, nodes_before
        try:
            enforce_caps(payload)
        except ValueError:
            print("CAP_EVENT=" + json.dumps({"stage": stage, **payload}, allow_nan=False, default=numeric_json), flush=True)
            raise
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("repeated HXT-postopt configuration")
            configured.append(apply_mesh_policy(gmsh, layout, arm, parent.parent.arm_protocol(p, arm)))
            for key, value in p["mesh_probe"]["native_log_options"].items():
                gmsh.option.setNumber(key, value)
                observed_logging[key] = gmsh.option.getNumber(key)
            build_options = gmsh.option.getString("General.BuildOptions")
            if observed_logging != p["mesh_probe"]["native_log_options"] or p["mesh_probe"]["required_build_feature"] not in build_options.lower().split():
                raise ValueError("HXT/native logging unavailable")
            payload = {**payload, "mesh_policy": configured[0], "native_log_options": observed_logging,
                       "gmsh_build_options": build_options, "inherited_h_min_h_max_overridden": True}
        if stage in optimizers:
            if optimizers[stage] or sha256_json(payload.get("optimizer")) != sha256_json(p["hxt_postopt"]["optimizer"]):
                raise ValueError("optimizer invocation/configuration mismatch")
            if stage == "mesh_optimize_started" and set(qualities) != {"raw_mesh_generated"}:
                raise ValueError("optimizer started before raw quality observation")
            if stage == "mesh_optimize_finished" and len(optimizers["mesh_optimize_started"]) != 1:
                raise ValueError("optimizer finish without start")
            optimizers[stage].append(copy.deepcopy(payload["optimizer"]))
        if stage in ("raw_mesh_generated", "mesh_generated"):
            if stage in qualities:
                raise ValueError("repeated quality collection")
            if stage == "mesh_generated" and len(optimizers["mesh_optimize_finished"]) != 1:
                raise ValueError("post-optimization quality before optimizer finish")
            q = collect_quality(gmsh, layout, p["hxt_isolation"]["quality"], limits)
            qualities[stage] = q
            payload = {**payload, "mesh_quality": q,
                       "strict_quality_passed": assess_quality(q, quality_counts(q), p)}
            if stage == "raw_mesh_generated":
                nodes_before = payload["n_nodes"]
        stages.append(stage)
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": time.monotonic()-started,
              "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, **payload},
              allow_nan=False, default=numeric_json), flush=True)
        enforce_caps(payload)
        if stage in qualities:
            q = qualities[stage]
            if not valid_observation(q, p, limits):
                raise ValueError("invalid quality observation structure; raw diagnostic retained")
            if stage == "mesh_generated" and not assess_quality(q, quality_counts(q), p):
                raise ValueError("invalid or degenerate post-optimized mesh quality; raw diagnostic retained")

    mesh, regions = _build_mesh(layout, eps_r=p["physics"]["eps_r"], refine=0, pad_mm=arm["pad_mm"], progress=progress)
    metadata = mesh_metadata(mesh, regions, p["mesh_probe"]["mesh_fingerprint_schema"])
    progress("mesh_fingerprinted", metadata)
    if len(configured) != 1 or len(qualities) != 2 or any(len(v) != 1 for v in optimizers.values()):
        raise ValueError("missing HXT-postopt policy/quality/optimizer observation")
    check_source()
    before = qualities["raw_mesh_generated"]
    result = {**identity(), **metadata, "mode": args.mode, "layout_id": layout_id,
              "geometry_sha256": geometry_sha256(layout), "arm": arm,
              "mesh_quality": qualities["mesh_generated"], "quality_before": before,
              "nodes_before": nodes_before, "quality_before_passed": assess_quality(before, quality_counts(before), p),
              "optimizer": optimizers["mesh_optimize_finished"][0], "optimizer_calls": 1,
              "numerical_quality_qualified": False, "mesh_policy": configured[0],
              "mesh_policy_sha256": sha256_json(configured[0]), "native_log_options": observed_logging,
              "gmsh_build_options": build_options, "stages": stages, "field_solver_executed": False,
              "elapsed_s": time.monotonic()-started, "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
              "scheduler": scheduler, "runtime": runtime}
    if not assess_result(result, args.mode, p):
        raise ValueError("HXT-postopt result/quality/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
