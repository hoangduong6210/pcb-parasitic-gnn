"""Separate frozen-geometry builder: explicit optimization before fresh extraction.

Derived from fem_capacitance_3d._build_mesh; the original is untouched.
All real mesh operations are guarded by the actual SLURM allocation.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_hxt_postopt import check_allocation, check_source, check_runtime, protocol
from geometry_contract import trace_box, validate_layout

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _progress(callback, stage, **payload):
    if callback is not None:
        callback(stage, payload)


def _build_mesh(
    layout,
    eps_r=4.2,
    pad_mm=8.0,
    refine=0,
    progress: ProgressCallback | None = None,
):
    """gmsh OCC: air box + pri/sec conductor boxes (fragmented, tagged).
    Returns (skfem MeshTet, element_region array: 0=air,1=pri,2=sec)."""
    p = protocol()
    check_allocation("hxt_postopt", p)
    check_source()
    check_runtime(p)
    import numpy as np
    import gmsh
    from skfem import MeshTet
    validate_layout(layout)
    _progress(progress, "geometry_validated", n_traces=len(layout["traces"]))
    trs = layout["traces"]
    boxes = [trace_box(layout, trace) for trace in trs]
    xs = [box[0] for box in boxes] + [box[1] for box in boxes]
    ys = [box[2] for box in boxes] + [box[3] for box in boxes]
    zs = [box[4] for box in boxes] + [box[5] for box in boxes]
    x0, x1 = min(xs) - pad_mm, max(xs) + pad_mm
    y0, y1 = min(ys) - pad_mm, max(ys) + pad_mm
    z0, z1 = min(zs) - pad_mm, max(zs) + pad_mm

    if gmsh.isInitialized():
        gmsh.finalize()
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh_threads = int(os.environ.get("PCB_GNN_GMSH_THREADS", "1"))
    gmsh.option.setNumber("General.NumThreads", gmsh_threads)
    gmsh.option.setNumber("Mesh.MaxNumThreads3D", gmsh_threads)
    gmsh.model.add("cps")
    try:
        occ = gmsh.model.occ
        air = occ.addBox(x0, y0, z0, x1 - x0, y1 - y0, z1 - z0)
        pri_boxes, sec_boxes = [], []
        for trace, box in zip(trs, boxes):
            net = trace.get("net")
            if net not in ("pri", "sec"):
                continue
            volume = occ.addBox(
                box[0], box[2], box[4],
                box[1] - box[0], box[3] - box[2], box[5] - box[4],
            )
            (pri_boxes if net == "pri" else sec_boxes).append(volume)
        occ.synchronize()

        def fuse(volume_tags):
            if not volume_tags:
                return []
            if len(volume_tags) == 1:
                return [(3, volume_tags[0])]
            result, _ = occ.fuse(
                [(3, volume_tags[0])], [(3, tag) for tag in volume_tags[1:]]
            )
            return result

        pri_f = fuse(pri_boxes)
        sec_f = fuse(sec_boxes)
        occ.synchronize()
        occ.fragment([(3, air)], pri_f + sec_f)
        occ.synchronize()
        volumes = [entity[1] for entity in gmsh.model.getEntities(3)]
        _progress(progress, "occ_fragmented", n_volumes=len(volumes))

        region_of_volume = {}
        for volume in volumes:
            center = np.asarray(gmsh.model.occ.getCenterOfMass(3, volume))
            region = 0
            for trace, box in zip(trs, boxes):
                if trace.get("net") not in ("pri", "sec"):
                    continue
                if (
                    box[0] - 1e-3 <= center[0] <= box[1] + 1e-3
                    and box[2] - 1e-3 <= center[1] <= box[3] + 1e-3
                    and box[4] - 1e-3 <= center[2] <= box[5] + 1e-3
                ):
                    region = 1 if trace["net"] == "pri" else 2
                    break
            region_of_volume[volume] = region

        gaps = sorted(set(round(z, 4) for z in zs))
        dz = (
            min(gaps[index + 1] - gaps[index] for index in range(len(gaps) - 1))
            if len(gaps) > 1 else 0.2
        )
        h = max(dz * 0.8, 0.05)
        mesh_max = max(h * 12, 2.0) * (0.6 ** refine)
        gmsh.option.setNumber("Mesh.MeshSizeMin", h)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_max)
        _progress(progress, "mesh_generate_started", h_min=h, h_max=mesh_max)
        gmsh.model.mesh.generate(3)
        before_tags, _, _ = gmsh.model.mesh.getNodes()
        _progress(progress, "raw_mesh_generated", n_nodes=len(before_tags))
        _progress(progress, "mesh_optimize_started", optimizer=p["hxt_postopt"]["optimizer"])
        gmsh.model.mesh.optimize(**p["hxt_postopt"]["optimizer"])
        _progress(progress, "mesh_optimize_finished", optimizer=p["hxt_postopt"]["optimizer"])
        # Optimization can move, add or remove nodes/elements. Extract only now.
        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        _progress(progress, "mesh_generated", n_nodes=len(node_tags))

        coords = np.asarray(node_coords).reshape(-1, 3).T * 1e-3
        node_tags = np.asarray(node_tags, dtype=np.int64)
        tag_to_index = np.full(int(node_tags.max()) + 1, -1, dtype=np.int64)
        tag_to_index[node_tags] = np.arange(len(node_tags), dtype=np.int64)
        connectivity_blocks = []
        region_blocks = []
        for volume in volumes:
            element_types, _, element_nodes = gmsh.model.mesh.getElements(3, volume)
            for element_type, nodes in zip(element_types, element_nodes):
                if element_type != 4:
                    continue
                tags = np.asarray(nodes, dtype=np.int64).reshape(-1, 4)
                indices = tag_to_index[tags]
                if (indices < 0).any():
                    raise ValueError("gmsh connectivity references an unknown node tag")
                connectivity_blocks.append(indices)
                region_blocks.append(
                    np.full(indices.shape[0], region_of_volume[volume], dtype=np.int8)
                )
        if not connectivity_blocks:
            raise ValueError("gmsh returned no first-order tetrahedra")
        t = np.concatenate(connectivity_blocks, axis=0).T
        elem_region = np.concatenate(region_blocks)
        _progress(progress, "mesh_extracted", n_tetrahedra=t.shape[1])
    finally:
        if gmsh.isInitialized():
            gmsh.finalize()
    _progress(progress, "gmsh_finalized")
    m = MeshTet(coords, t)
    _progress(progress, "skfem_mesh_created")
    return m, elem_region
