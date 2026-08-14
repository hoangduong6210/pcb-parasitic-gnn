"""
fem_capacitance_3d.py — 3-D inter-winding capacitance C_ps via a scikit-fem
electrostatic FEM (BSD, Python-native; no subprocess, no BEM panel orientation).

Robust where the surface-BEM solvers (FastCap/FasterCap) were not: a VOLUME FEM
of the Laplace problem div(eps grad phi)=0 on a gmsh tet mesh of the air box with
the real pri/sec conductor boxes embedded (true 3-D registration + fringing, thin
gaps resolved by the conforming mesh). Dirichlet phi=1V on every primary node,
phi=0V on every secondary node; the inter-winding C_ps = 2W/V^2 with
W = 1/2 * integral(eps |grad phi|^2) over the dielectric.

Validated against the parallel-plate analytic eps0*eps_r*A/d.
"""
from __future__ import annotations
from collections.abc import Callable
import os
from typing import Any

import numpy as np

from geometry_contract import trace_box, validate_layout

EPS0 = 8.854187817e-12   # F/m
ProgressCallback = Callable[[str, dict[str, Any]], None]


def _progress(callback: ProgressCallback | None, stage: str, **payload: Any) -> None:
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


def _solve_condensed_system(
    A,
    b: np.ndarray,
    *,
    linear_solver: str,
    rtol: float,
    maxiter: int,
    progress: ProgressCallback | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve a symmetric positive-definite condensed Laplace system."""
    from scipy.sparse.linalg import spsolve

    if linear_solver == "direct":
        _progress(progress, "direct_solve_started")
        solution = spsolve(A, b)
        metadata: dict[str, Any] = {"linear_solver": "scipy_superlu_direct"}
    elif linear_solver == "amg_cg":
        import pyamg
        from scipy.sparse.linalg import cg

        A = A.tocsr()
        A.sort_indices()
        _progress(progress, "amg_setup_started")
        hierarchy = pyamg.smoothed_aggregation_solver(
            A,
            B=np.ones((A.shape[0], 1)),
            symmetry="symmetric",
            max_coarse=50,
        )
        _progress(
            progress,
            "amg_setup_completed",
            amg_levels=len(hierarchy.levels),
            operator_complexity=float(hierarchy.operator_complexity()),
        )
        iterations = 0

        def count_iteration(_current: np.ndarray) -> None:
            nonlocal iterations
            iterations += 1

        _progress(progress, "cg_solve_started")
        solution, info = cg(
            A,
            b,
            M=hierarchy.aspreconditioner(cycle="V"),
            rtol=rtol,
            atol=0.0,
            maxiter=maxiter,
            callback=count_iteration,
        )
        metadata = {
            "linear_solver": "pyamg_smoothed_aggregation_cg",
            "solver_info": int(info),
            "iterations": iterations,
            "amg_levels": len(hierarchy.levels),
            "operator_complexity": float(hierarchy.operator_complexity()),
        }
        if info != 0:
            raise RuntimeError(f"AMG-CG did not converge: info={info}")
    else:
        raise ValueError(f"unsupported linear solver: {linear_solver}")

    if not np.isfinite(solution).all():
        raise RuntimeError("linear solver returned non-finite values")
    denominator = max(float(np.linalg.norm(b)), np.finfo(float).tiny)
    relative_residual = float(np.linalg.norm(A @ solution - b) / denominator)
    metadata["relative_residual"] = relative_residual
    metadata["rtol"] = float(rtol)
    metadata["maxiter"] = int(maxiter)
    if relative_residual > max(10.0 * rtol, 1e-10):
        raise RuntimeError(
            f"linear residual {relative_residual:.3e} exceeds acceptance tolerance"
        )
    return np.asarray(solution), metadata


def fem_cps_3d_diagnostics(
    layout,
    eps_r=4.2,
    refine=0,
    pad_mm=8.0,
    *,
    linear_solver="direct",
    solver_rtol=1e-10,
    solver_maxiter=500,
    progress: ProgressCallback | None = None,
    strict=False,
):
    """Return C_ps and mesh diagnostics for an explicit mesh/domain setting."""
    import skfem
    from skfem import Basis, ElementTetP1, BilinearForm
    from skfem.helpers import dot, grad
    if not any(t.get("net") == "pri" for t in layout["traces"]) or \
       not any(t.get("net") == "sec" for t in layout["traces"]):
        return None
    try:                          # gmsh fails to mesh intersecting (invalid) boxes
        m, elem_region = _build_mesh(
            layout, eps_r=eps_r, refine=refine, pad_mm=pad_mm, progress=progress
        )
    except Exception:
        try:
            import gmsh
            if gmsh.isInitialized():
                gmsh.finalize()
        except Exception:
            pass
        if strict:
            raise
        return None
    basis = Basis(m, ElementTetP1())
    _progress(progress, "basis_created", n_dofs=basis.N)

    # uniform dielectric: conductor interiors have grad(phi)=0 (all nodes fixed to
    # one potential), so they add no energy and a constant eps is exact here.
    @BilinearForm
    def laplace(u, v, _):
        return dot(grad(u), grad(v))
    K = laplace.assemble(basis)
    _progress(progress, "matrix_assembled", n_dofs=K.shape[0], nnz=K.nnz)

    # Dirichlet: nodes touched by pri elements -> 1V, sec elements -> 0V
    pri_nodes = np.unique(m.t[:, elem_region == 1].ravel()) if (elem_region == 1).any() else np.array([], int)
    sec_nodes = np.unique(m.t[:, elem_region == 2].ravel()) if (elem_region == 2).any() else np.array([], int)
    sec_nodes = np.setdiff1d(sec_nodes, pri_nodes)
    if len(pri_nodes) == 0 or len(sec_nodes) == 0:
        return None
    u = basis.zeros(); u[pri_nodes] = 1.0; u[sec_nodes] = 0.0
    D = np.concatenate([pri_nodes, sec_nodes])
    A, b, expanded, free = skfem.condense(K, basis.zeros(), x=u, D=D)
    _progress(
        progress,
        "system_condensed",
        n_free=A.shape[0],
        nnz=A.nnz,
        linear_solver=linear_solver,
    )
    free_solution, solver_metadata = _solve_condensed_system(
        A,
        b,
        linear_solver=linear_solver,
        rtol=solver_rtol,
        maxiter=solver_maxiter,
        progress=progress,
    )
    expanded[free] = free_solution
    u = expanded
    _progress(progress, "linear_solve_completed", **solver_metadata)
    W = 0.5 * EPS0 * eps_r * float(u @ (K @ u))   # Joules (V=1, uniform eps)
    _progress(progress, "energy_computed", energy_j=W)
    return {
        "cps_pf": 2.0 * W * 1e12,                 # C = 2W/V^2 (V=1) -> pF
        "mesh_nodes": int(m.p.shape[1]),
        "mesh_tetrahedra": int(m.t.shape[1]),
        "refine": int(refine),
        "pad_mm": float(pad_mm),
        "eps_r": float(eps_r),
        **solver_metadata,
    }


def fem_cps_3d(layout, eps_r=4.2, refine=0, pad_mm=8.0):
    """3-D electrostatic C_ps (pF) between the primary and secondary windings."""
    diagnostics = fem_cps_3d_diagnostics(
        layout, eps_r=eps_r, refine=refine, pad_mm=pad_mm
    )
    return diagnostics["cps_pf"] if diagnostics is not None else None


def parallel_plate_pf(area_mm2, gap_mm, eps_r=4.2):
    return eps_r * EPS0 * (area_mm2 * 1e-6) / (gap_mm * 1e-3) * 1e12


if __name__ == "__main__":
    # parallel-plate validation: 40x5 mm plates, 0.11 mm gap, eps_r=4.2
    lay = {
        "geometry_schema": "pcb-planar-active-legs.v3",
        "n_layers": 2, "board_w_mm": 45.0, "board_h_mm": 10.0,
        "stackup": {"layer_pitch_mm": 0.18, "layer_z0_mm": 0.10},
        "design_rules": {"same_layer_clearance_mm": 0.20, "board_edge_margin_mm": 0.0},
        "traces": [
            {"trace_id": "pri-0", "x0": 2, "y0": 2, "length_mm": 40,
             "width_mm": 5, "thick_mm": 0.07, "layer": 0, "net": "pri",
             "current_sign": 1},
            {"trace_id": "sec-0", "x0": 2, "y0": 2, "length_mm": 40,
             "width_mm": 5, "thick_mm": 0.07, "layer": 1, "net": "sec",
             "current_sign": 1},
        ],
    }
    truth = parallel_plate_pf(40*5, 0.28-0.17, 4.2)
    for r in (0, 1):
        c = fem_cps_3d(lay, eps_r=4.2, refine=r)
        print("refine=%d -> Cps=%.2f pF (parallel-plate truth ~%.1f pF)" % (r, c if c else -1, truth))
