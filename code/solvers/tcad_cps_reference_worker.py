#!/usr/bin/env python3
"""One bounded fresh-process solve. No scientific import before the SLURM guard."""
from __future__ import annotations

import argparse
import json
import numbers
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_reference import (PANEL, PROTOCOL, assess_result, check_allocation,
                                check_runtime, check_source, identity, read_json)
from geometry_contract import geometry_sha256, trace_box
from scientific_artifact import sha256_json


def numeric_json(value):
    """Serialize numerical scalar telemetry without importing NumPy pre-guard."""
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    raise TypeError(f"unsupported telemetry type: {type(value).__name__}")


def apply_mesh_policy(gmsh, layout: dict, arm: dict, protocol: dict) -> dict:
    policy = protocol["mesh"]
    near = policy["near_sizes_mm"][arm["level"]]
    options = {**policy["gmsh_options"], "Mesh.MeshSizeMin": near,
               "Mesh.MeshSizeMax": arm["far_size_mm"], "General.NumThreads": 1,
               "Mesh.MaxNumThreads1D": 1, "Mesh.MaxNumThreads2D": 1, "Mesh.MaxNumThreads3D": 1}
    for name, value in options.items():
        gmsh.option.setNumber(name, value)
    observed = {name: gmsh.option.getNumber(name) for name in options}
    if observed != options:
        raise ValueError("Gmsh did not retain the requested mesh options")
    mesh_fields, boxes = [], []
    expansion = policy["box_expansion_mm"]
    for trace in layout["traces"]:
        box = trace_box(layout, trace)
        settings = dict(zip(("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"),
                            [v + (-expansion if i % 2 == 0 else expansion) for i, v in enumerate(box)]))
        settings.update(VIn=near, VOut=arm["far_size_mm"], Thickness=policy["transition_thickness_mm"])
        field = gmsh.model.mesh.field.add("Box")
        for name, value in settings.items():
            gmsh.model.mesh.field.setNumber(field, name, value)
        mesh_fields.append(field)
        boxes.append(settings)
    field = gmsh.model.mesh.field.add("Min")
    gmsh.model.mesh.field.setNumbers(field, "FieldsList", mesh_fields)
    gmsh.model.mesh.field.setAsBackgroundMesh(field)
    return {"options": observed, "boxes": boxes, "near_size_mm": near,
            "far_size_mm": arm["far_size_mm"], "pad_mm": arm["pad_mm"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "pilot"), required=True)
    parser.add_argument("--arm", required=True)
    args = parser.parse_args()
    protocol = read_json(ROOT / PROTOCOL)
    scheduler = check_allocation(args.phase, protocol)
    check_source()
    runtime = check_runtime(protocol)
    if args.phase == "smoke":
        arm, layout = protocol["smoke"]["arm"], protocol["smoke"]["layout"]
        layout_id = "smoke"
    else:
        panel = read_json(ROOT / PANEL)
        layout_id = panel["pilot_layout_ids"][int(os.environ["SLURM_ARRAY_TASK_ID"])]
        layout = next(r["layout"] for r in panel["rows"] if r["layout_id"] == layout_id)
        arm = next(a for a in protocol["pilot_arms"] if a["name"] == args.arm)
    if arm["name"] != args.arm:
        raise ValueError("unfrozen arm requested")
    # Importing the numerical stack is deliberately below all allocation guards.
    import numpy as np
    import gmsh
    from fem_capacitance_3d import fem_cps_3d_diagnostics
    np.random.seed(0)
    limits = protocol["resources"][args.phase]
    configured, stages = [], []
    started = time.monotonic()

    def progress(stage: str, payload: dict) -> None:
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("unexpected second mesh generation")
            configured.append(apply_mesh_policy(gmsh, layout, arm, protocol))
            payload = {**payload, "tcad_mesh_policy": configured[0],
                       "inherited_h_min_h_max_overridden": True}
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        record = {"stage": stage, "elapsed_s": time.monotonic() - started,
                  "peak_rss_gib": peak, **payload}
        stages.append(stage)
        print("STAGE=" + json.dumps(record, allow_nan=False, default=numeric_json), flush=True)
        if peak > limits["rss_gib_max"]:
            raise MemoryError("frozen RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max"),
                         ("operator_complexity", "operator_complexity_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    solver = protocol["linear_solver"]
    result = fem_cps_3d_diagnostics(
        layout, eps_r=protocol["physics"]["eps_r"], refine=0, pad_mm=arm["pad_mm"],
        linear_solver=solver["name"], comparison_solver="direct" if args.phase == "smoke" else None,
        solver_rtol=solver["rtol"], solver_maxiter=solver["maxiter"], progress=progress, strict=True)
    if result is None or len(configured) != 1:
        raise ValueError("missing solve result or local mesh policy")
    result.update(peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
                  elapsed_s=time.monotonic() - started, arm=arm, layout_id=layout_id,
                  geometry_sha256=geometry_sha256(layout), mesh_policy=configured[0],
                  mesh_policy_sha256=sha256_json(configured[0]), stages=stages,
                  scheduler=scheduler, runtime=runtime, **identity())
    check_source()
    if not assess_result(result, protocol, args.phase):
        raise ValueError("numerical or resource result gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
