#!/usr/bin/env python3
"""Guarded unoptimized HXT diagnostic; signed quality statistics, no field solve."""
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
from tcad_cps_hxt_isolation import (assess_result, assess_quality, check_allocation, check_runtime,
    check_source, identity, mode_input, parent, protocol)
from tcad_cps_mesh_probe_worker import mesh_metadata
from tcad_cps_reference_worker import apply_mesh_policy, numeric_json
from geometry_contract import geometry_sha256, trace_box
from scientific_artifact import sha256_json

REGIONS = ("dielectric", "primary", "secondary")


def quality_metadata(tags, regions, sicn, jacobian, cfg):
    """Small synthetic tests may call this; actual mesh arrays are compute-only."""
    import numpy as np
    arrays = [np.asarray(a) for a in (tags, regions, sicn, jacobian)]
    tags, regions, sicn, jacobian = arrays
    if any(a.ndim != 1 or len(a) != len(tags) for a in arrays) or not len(tags):
        raise ValueError("quality arrays have inconsistent/empty shape")
    if not np.issubdtype(tags.dtype, np.integer) or not np.issubdtype(regions.dtype, np.integer):
        raise ValueError("quality element tags/regions must be integers")
    if tags.min() <= 0 or tags.max() > np.iinfo(np.int64).max or not np.isin(regions, [0, 1, 2]).all():
        raise ValueError("quality tags/region labels invalid")
    order = np.argsort(tags, kind="stable")
    arrays = [a[order] for a in arrays]
    tags, regions, sicn, jacobian = arrays
    if np.any(tags[1:] == tags[:-1]):
        raise ValueError("duplicate quality element tag")
    digest = hashlib.sha256((cfg["schema"] + "\0").encode())
    for name, value, dtype in zip(("element_tags", "element_region", "minSICN", "minDetJac"), arrays, ("<i8", "i1", "<f8", "<f8")):
        array = np.ascontiguousarray(value, dtype=dtype)
        header = json.dumps({"name": name, "dtype": array.dtype.str, "shape": list(array.shape)}, sort_keys=True, separators=(",", ":"))
        digest.update(header.encode() + b"\0")
        digest.update(memoryview(array).cast("B"))
    by_region = {}
    for index, name in enumerate(REGIONS):
        mask = regions == index
        values = {"count": int(mask.sum())}
        for metric, array in (("minSICN", sicn), ("minDetJac", jacobian)):
            subset = array[mask]
            finite = subset[np.isfinite(subset)]
            quantiles = np.quantile(finite, cfg["quantile_probabilities"], method=cfg["quantile_method"]).tolist() if len(finite) else [None]*len(cfg["quantile_probabilities"])
            values[metric] = {"finite_count": int(len(finite)), "nonpositive_count": int((subset <= 0).sum()), "quantiles": quantiles}
        values["sicn_below_threshold"] = {str(t): int((sicn[mask] < t).sum()) for t in cfg["sicn_diagnostic_thresholds"]}
        by_region[name] = values
    return {"schema": cfg["schema"], "metrics": list(cfg["metrics"]), "metric_units": dict(cfg["metric_units"]),
            "quantile_probabilities": list(cfg["quantile_probabilities"]), "quantile_method": cfg["quantile_method"],
            "element_count": int(len(tags)), "arrays_sha256": digest.hexdigest(), "regions": by_region}


def volume_region(layout, center):
    """Same frozen centre-in-box convention as the unchanged geometry builder."""
    for trace in layout["traces"]:
        box = trace_box(layout, trace)
        if all(box[2*i] - 1e-3 <= center[i] <= box[2*i+1] + 1e-3 for i in range(3)):
            return 1 if trace["net"] == "pri" else 2
    return 0


def collect_quality(gmsh, layout, cfg, limits):
    import numpy as np
    tags, regions, count = [], [], 0
    for _, volume in sorted(gmsh.model.getEntities(3)):
        kinds, blocks, _ = gmsh.model.mesh.getElements(3, volume)
        if len(kinds) != 1 or int(kinds[0]) != cfg["element_type"]:
            raise ValueError("non-first-order-tetrahedral or empty volume")
        block = np.asarray(blocks[0])
        count += len(block)
        if count > limits["mesh_tetrahedra_max"]:
            raise ValueError("quality collection exceeds frozen tetrahedron cap")
        region = volume_region(layout, gmsh.model.occ.getCenterOfMass(3, volume))
        tags.append(block)
        regions.append(np.full(len(block), region, dtype=np.int8))
    if not tags:
        raise ValueError("no tetrahedra for quality collection")
    tags, regions = np.concatenate(tags), np.concatenate(regions)
    sicn = gmsh.model.mesh.getElementQualities(tags, "minSICN")
    jacobian = gmsh.model.mesh.getElementQualities(tags, "minDetJac")
    return quality_metadata(tags, regions, sicn, jacobian, cfg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation("hxt_isolation", p)
    check_source()
    runtime = check_runtime(p)
    layout_id, layout, arm = mode_input(args.mode, p)
    import numpy as np
    import gmsh
    from fem_capacitance_3d import _build_mesh
    np.random.seed(0)
    started, stages, configured, observed_logging, qualities = time.monotonic(), [], [], {}, []
    build_options = ""
    limits = p["worker_limits"][args.mode]

    def enforce_caps(payload):
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2 > limits["rss_gib_max"] or time.monotonic()-started > limits["worker_timeout_s"]:
            raise ValueError("HXT-isolation worker time/RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    def progress(stage, payload):
        nonlocal build_options
        try:
            enforce_caps(payload)
        except ValueError:
            print("CAP_EVENT=" + json.dumps({"stage": stage, **payload}, allow_nan=False, default=numeric_json), flush=True)
            raise
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("repeated HXT-isolation configuration")
            configured.append(apply_mesh_policy(gmsh, layout, arm, parent.parent.arm_protocol(p, arm)))
            for key, value in p["mesh_probe"]["native_log_options"].items():
                gmsh.option.setNumber(key, value)
                observed_logging[key] = gmsh.option.getNumber(key)
            build_options = gmsh.option.getString("General.BuildOptions")
            if observed_logging != p["mesh_probe"]["native_log_options"] or p["mesh_probe"]["required_build_feature"] not in build_options.lower().split():
                raise ValueError("HXT/native logging unavailable")
            payload = {**payload, "mesh_policy": configured[0], "native_log_options": observed_logging,
                       "gmsh_build_options": build_options, "inherited_h_min_h_max_overridden": True}
        if stage == "mesh_generated":
            if qualities:
                raise ValueError("repeated quality collection")
            qualities.append(collect_quality(gmsh, layout, p["hxt_isolation"]["quality"], limits))
            payload = {**payload, "mesh_quality": qualities[0]}
        stages.append(stage)
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": time.monotonic()-started,
              "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2, **payload},
              allow_nan=False, default=numeric_json), flush=True)
        enforce_caps(payload)
        if stage == "mesh_generated":
            candidate = {"mesh_tetrahedra": qualities[0]["element_count"],
                         "region_tetrahedra": {k: v["count"] for k, v in qualities[0]["regions"].items()}}
            if not assess_quality(qualities[0], candidate, p):
                raise ValueError("invalid or degenerate unoptimized mesh quality; raw diagnostic retained")

    mesh, regions = _build_mesh(layout, eps_r=p["physics"]["eps_r"], refine=0, pad_mm=arm["pad_mm"], progress=progress)
    metadata = mesh_metadata(mesh, regions, p["mesh_probe"]["mesh_fingerprint_schema"])
    progress("mesh_fingerprinted", metadata)
    if len(configured) != 1 or len(qualities) != 1:
        raise ValueError("missing HXT-isolation policy/quality observation")
    check_source()
    result = {**identity(), **metadata, "mode": args.mode, "layout_id": layout_id,
              "geometry_sha256": geometry_sha256(layout), "arm": arm, "mesh_quality": qualities[0],
              "numerical_quality_qualified": False, "mesh_policy": configured[0],
              "mesh_policy_sha256": sha256_json(configured[0]), "native_log_options": observed_logging,
              "gmsh_build_options": build_options, "stages": stages, "field_solver_executed": False,
              "elapsed_s": time.monotonic()-started, "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
              "scheduler": scheduler, "runtime": runtime}
    if not assess_result(result, args.mode, p):
        raise ValueError("HXT-isolation result/quality/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
