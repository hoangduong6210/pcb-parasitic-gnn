#!/usr/bin/env python3
"""Guarded one-candidate diagnostic; no numerical imports at module scope."""
from __future__ import annotations
import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
from tcad_cps_amg_diagnostic import (assess_result, candidate_kwargs, check_allocation,
    check_runtime, check_source, check_system, identity, mode_input, protocol)
from tcad_cps_reference_worker import apply_mesh_policy, numeric_json
from geometry_contract import geometry_sha256
from scientific_artifact import sha256_json


def assemble_system(layout, p, arm, progress):
    """Unchanged frozen assembly recipe; exact recorded CSR hash is mandatory."""
    import numpy as np
    import skfem
    from skfem import Basis, ElementTetP1, BilinearForm
    from skfem.helpers import dot, grad
    from fem_capacitance_3d import _build_mesh
    m, elem_region = _build_mesh(layout, eps_r=p["physics"]["eps_r"], refine=0,
                                pad_mm=arm["pad_mm"], progress=progress)
    basis = Basis(m, ElementTetP1())
    progress("basis_created", {"n_dofs": basis.N})

    @BilinearForm
    def laplace(u, v, _):
        return dot(grad(u), grad(v))
    K = laplace.assemble(basis)
    progress("matrix_assembled", {"n_dofs": K.shape[0], "nnz": K.nnz})
    pri_nodes = np.unique(m.t[:, elem_region == 1].ravel()) if (elem_region == 1).any() else np.array([], int)
    sec_nodes = np.unique(m.t[:, elem_region == 2].ravel()) if (elem_region == 2).any() else np.array([], int)
    sec_nodes = np.setdiff1d(sec_nodes, pri_nodes)
    if len(pri_nodes) == 0 or len(sec_nodes) == 0:
        raise ValueError("missing terminal nodes")
    u = basis.zeros(); u[pri_nodes] = 1.0; u[sec_nodes] = 0.0
    D = np.concatenate([pri_nodes, sec_nodes])
    A, b, expanded, free = skfem.condense(K, basis.zeros(), x=u, D=D)
    progress("system_condensed", {"n_free": A.shape[0], "nnz": A.nnz})
    return m, K, A, b, expanded, free


def solve_candidate(A, b, p, progress):
    import numpy as np
    import pyamg
    from scipy.sparse.linalg import cg
    from fem_capacitance_3d import _sparse_system_sha256
    A = A.tocsr(copy=True)
    A.sum_duplicates()
    A.sort_indices()
    digest = _sparse_system_sha256(A, b)
    progress("candidate_setup_started", {"input_system_sha256": digest})
    hierarchy = pyamg.smoothed_aggregation_solver(
        A, B=np.ones((A.shape[0], 1)), **candidate_kwargs(p))
    complexity = float(hierarchy.operator_complexity())
    progress("candidate_setup_completed", {"operator_complexity": complexity, "amg_levels": len(hierarchy.levels)})
    iterations = 0

    def count(_):
        nonlocal iterations
        iterations += 1

    progress("cg_solve_started", {})
    solution, info = cg(A, b, M=hierarchy.aspreconditioner(cycle="V"),
                        rtol=p["linear_solver"]["rtol"], atol=0.0,
                        maxiter=p["linear_solver"]["maxiter"], callback=count)
    if info != 0 or not np.isfinite(solution).all():
        raise ValueError(f"candidate CG failed: info={info}")
    residual = float(np.linalg.norm(A @ solution-b)/max(float(np.linalg.norm(b)), np.finfo(float).tiny))
    if not np.isfinite(residual) or residual > p["gates"]["relative_residual_max"]:
        raise ValueError("candidate residual gate failed")
    metadata = {"input_system_sha256": digest, "candidate": candidate_kwargs(p),
                "solver_info": int(info), "relative_residual": residual, "iterations": iterations,
                "operator_complexity": complexity, "amg_levels": len(hierarchy.levels)}
    progress("candidate_solve_completed", metadata)
    return solution, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("toy", "local0"), required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation("diagnostic", p)
    check_source()
    runtime = check_runtime(p)
    layout_id, layout, arm = mode_input(args.mode, p)
    # All numerical imports and execution follow actual allocation/source guards.
    import numpy as np
    import gmsh
    from fem_capacitance_3d import EPS0, _solve_condensed_system, _sparse_system_sha256
    np.random.seed(0)
    started, configured = time.monotonic(), []
    limits = p["worker_limits"][args.mode]

    def progress(stage, payload):
        if stage == "mesh_generate_started":
            if configured:
                raise ValueError("repeated diagnostic meshing")
            configured.append(apply_mesh_policy(gmsh, layout, arm, p))
            payload = {**payload, "mesh_policy": configured[0]}
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2
        elapsed = time.monotonic()-started
        print("STAGE=" + json.dumps({"stage": stage, "elapsed_s": elapsed, "peak_rss_gib": peak, **payload},
              allow_nan=False, default=numeric_json), flush=True)
        if peak > limits["rss_gib_max"] or elapsed > limits["worker_timeout_s"]:
            raise ValueError("diagnostic time/RSS cap exceeded")
        for key, cap in (("n_nodes", "mesh_nodes_max"), ("n_tetrahedra", "mesh_tetrahedra_max"),
                         ("operator_complexity", "operator_complexity_max")):
            if key in payload and payload[key] > limits[cap]:
                raise ValueError(f"frozen {cap} exceeded")

    m, K, A, b, expanded, free = assemble_system(layout, p, arm, progress)
    A = A.tocsr(copy=False)
    A.sum_duplicates()
    A.sort_indices()
    system = {"system_sha256": _sparse_system_sha256(A, b), "mesh_nodes": int(m.p.shape[1]),
              "mesh_tetrahedra": int(m.t.shape[1]), "n_free": int(A.shape[0]), "nnz": int(A.nnz)}
    progress("system_fingerprinted", system)
    check_system(system, args.mode, p)
    solution, metadata = solve_candidate(A.copy(), b.copy(), p, progress)
    direct, direct_meta = _solve_condensed_system(A.copy(), b.copy(), linear_solver="direct",
        rtol=p["linear_solver"]["rtol"], maxiter=p["linear_solver"]["maxiter"], progress=progress)
    if metadata["input_system_sha256"] != direct_meta["input_system_sha256"] or metadata["input_system_sha256"] != system["system_sha256"]:
        raise ValueError("candidate/direct matrix identity mismatch")

    def capacitance(values):
        u = expanded.copy()
        u[free] = values
        return EPS0 * p["physics"]["eps_r"] * float(u @ (K @ u)) * 1e12

    result = {**identity(), **system, **metadata, "mode": args.mode,
              "layout_id": layout_id, "geometry_sha256": geometry_sha256(layout), "arm": arm,
              "cps_pf": capacitance(solution), "comparison": {**direct_meta, "cps_pf": capacitance(direct)},
              "solution_relative_l2": float(np.linalg.norm(solution-direct)/max(float(np.linalg.norm(direct)), np.finfo(float).tiny)),
              "mesh_policy": configured[0], "mesh_policy_sha256": sha256_json(configured[0]),
              "peak_rss_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024**2,
              "elapsed_s": time.monotonic()-started, "scheduler": scheduler, "runtime": runtime}
    check_source()
    if not assess_result(result, args.mode, p):
        raise ValueError("diagnostic comparison/resource gate failed")
    print("RESULT=" + json.dumps(result, allow_nan=False, default=numeric_json), flush=True)


if __name__ == "__main__":
    main()
