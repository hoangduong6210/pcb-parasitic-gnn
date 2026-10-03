#!/usr/bin/env python3
"""Guarded mesh-only worker; no matrix assembly, linear solver or field output."""
from __future__ import annotations
import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_mesh_probe import (assess_result, check_allocation, check_runtime, check_source,
    identity, mode_input, parent, protocol)
from tcad_cps_reference_worker import apply_mesh_policy, numeric_json
from geometry_contract import geometry_sha256
from scientific_artifact import sha256_json


def mesh_metadata(mesh, regions, schema):
    """Exact ordered-array identity, not a permutation-invariant mesh metric."""
    import numpy as np
    if mesh.p.ndim != 2 or mesh.p.shape[0] != 3 or mesh.t.ndim != 2 or mesh.t.shape[0] != 4:
        raise ValueError("unexpected tetrahedral mesh shape")
    if not np.issubdtype(mesh.t.dtype, np.integer) or not np.issubdtype(regions.dtype, np.integer):
        raise ValueError("noninteger connectivity/region labels")
    nodes, tetrahedra = mesh.p.shape[1], mesh.t.shape[1]
    if nodes == 0 or tetrahedra == 0 or regions.shape != (tetrahedra,) or not np.isfinite(mesh.p).all():
        raise ValueError("empty/nonfinite/inconsistent mesh")
    if mesh.t.min() < 0 or mesh.t.max() >= nodes or not np.isin(regions, [0, 1, 2]).all():
        raise ValueError("invalid connectivity or material region")
    counts = np.bincount(regions, minlength=3)
    if not (counts > 0).all():
        raise ValueError("missing dielectric or conductor mesh region")
    digest = hashlib.sha256((schema + "\0").encode())
    for name, value, dtype in (("coordinates_m", mesh.p, "<f8"), ("tetrahedra", mesh.t, "<i8"), ("element_region", regions, "i1")):
        array = np.ascontiguousarray(value, dtype=dtype)
        header = json.dumps({"name": name, "dtype": array.dtype.str, "shape": list(array.shape)}, sort_keys=True, separators=(",", ":"))
        digest.update(header.encode() + b"\0")
        digest.update(memoryview(array).cast("B"))
    return {"mesh_fingerprint_schema": schema, "mesh_sha256": digest.hexdigest(),
            "mesh_nodes": int(nodes), "mesh_tetrahedra": int(tetrahedra),
            "region_tetrahedra": dict(zip(("dielectric", "primary", "secondary"), map(int, counts)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation("mesh_probe", p)
    check_source()
    runtime = check_runtime(p)
    layout_id, layout, arm = mode_input(args.mode, p)
    # Imports and meshing follow actual compute-node, allocation and source checks.
    import numpy as np
    import gmsh
    from fem_capacitance_3d import _build_mesh
    np.random.seed(0)
    started, stages, configured, observed_logging = time.monotonic(), [], [], {}
    build_options = ""
    limits = p["worker_limits"][args.mode]

    def progress(stage, payload):
        nonlocal build_options
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("repeated mesh-probe configuration")
            configured.append(apply_mesh_policy(gmsh, layout, arm, parent.arm_protocol(p, arm)))
            for key, value in p["mesh_probe"]["native_log_options"].items():
                gmsh.option.setNumber(key, value)
                observed_logging[key] = gmsh.option.getNumber(key)
            build_options = gmsh.option.getString("General.BuildOptions")
            if observed_logging != p["mesh_probe"]["native_log_options"] or p["mesh_probe"]["required_build_feature"] not in build_options.lower().split():
                raise ValueError("HXT/native logging unavailable")
            payload = {**payload, "mesh_policy": configured[0], "native_log_options": observed_logging,
                       "gmsh_build_options": build_options, "inherited_h_min_h_max_overridden": True}
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        elapsed = time.monotonic()-started
        stages.append(stage)
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": elapsed, "peak_rss_gib": peak, **payload},
              allow_nan=False, default=numeric_json), flush=True)
        if peak > limits["rss_gib_max"] or elapsed > limits["worker_timeout_s"]:
            raise ValueError("mesh-probe worker time/RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    mesh, regions = _build_mesh(layout, eps_r=p["physics"]["eps_r"], refine=0, pad_mm=arm["pad_mm"], progress=progress)
    metadata = mesh_metadata(mesh, regions, p["mesh_probe"]["mesh_fingerprint_schema"])
    progress("mesh_fingerprinted", metadata)
    if len(configured) != 1:
        raise ValueError("missing mesh-probe configuration")
    check_source()
    result = {**identity(), **metadata, "mode": args.mode, "layout_id": layout_id,
              "geometry_sha256": geometry_sha256(layout), "arm": arm,
              "mesh_policy": configured[0], "mesh_policy_sha256": sha256_json(configured[0]),
              "native_log_options": observed_logging, "gmsh_build_options": build_options,
              "stages": stages, "field_solver_executed": False,
              "elapsed_s": time.monotonic()-started, "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
              "scheduler": scheduler, "runtime": runtime}
    if not assess_result(result, args.mode, p):
        raise ValueError("mesh-probe result/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
