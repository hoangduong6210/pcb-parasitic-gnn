"""
fem_capacitance_ref.py — INDEPENDENT 2-D electrostatic FEM capacitance reference.

This solves the cross-section Laplace problem for a primary/secondary foil-trace
pair with scikit-fem (BSD) and extracts the coupling capacitance from the field
energy. It is methodologically INDEPENDENT of the analytical parallel-plate +
fringing label (`trace_peec.trace_capacitance_pf`) — different physics engine,
no shared formula — so it provides a genuine ground-truth cross-check that the
analytical "silver" labels (and hence the GNN trained on them) are physical.

Method: per-unit-length 2-D Laplace ∇·(ε∇φ)=0 on the dielectric cross-section
with the two conductors as embedded Dirichlet regions (φ=1 V on primary, 0 V on
secondary), homogeneous Neumann on the far box. Energy W' = ½ε₀ε_r ∫|∇φ|² dA
gives C' = 2W'/V² per unit length; C = C'·L_overlap.
"""
from __future__ import annotations

import numpy as np
import skfem
from skfem import MeshTri, Basis, ElementTriP1, asm
from skfem.helpers import dot, grad
from skfem.models.poisson import laplace

EPS0 = 8.854187817e-12


def fem_pair_capacitance_pf(w1_mm, w2_mm, t_mm, h_mm, overlap_len_mm, eps_r=4.2,
                            box_mult=6.0, ngrid=90):
    """Independent 2-D FEM coupling capacitance (pF) for a stacked trace pair.
    w1/w2 = trace widths, t = Cu thickness, h = vertical center separation,
    overlap_len = facing length. Conductors centered, primary above secondary."""
    w1, w2, t, h = (x * 1e-3 for x in (w1_mm, w2_mm, t_mm, h_mm))
    L = overlap_len_mm * 1e-3
    wmax = max(w1, w2)
    half_x = box_mult * wmax / 2.0
    z_span = box_mult * (h + t)
    # structured cross-section grid (x horizontal, z vertical)
    xs = np.linspace(-half_x, half_x, ngrid)
    zs = np.linspace(-z_span / 2, z_span / 2, ngrid)
    m = MeshTri.init_tensor(xs, zs)
    basis = Basis(m, ElementTriP1())

    K = asm(laplace, basis)            # ∫∇u·∇v  (ε constant -> factor later)
    p = m.p                            # [2, Nnodes]
    X, Z = p[0], p[1]

    z_pri = +h / 2.0
    z_sec = -h / 2.0
    in_pri = (np.abs(X) <= w1 / 2) & (np.abs(Z - z_pri) <= t / 2)
    in_sec = (np.abs(X) <= w2 / 2) & (np.abs(Z - z_sec) <= t / 2)
    # ensure each conductor grabs at least its nearest node
    if not in_pri.any():
        in_pri[np.argmin((X) ** 2 + (Z - z_pri) ** 2)] = True
    if not in_sec.any():
        in_sec[np.argmin((X) ** 2 + (Z - z_sec) ** 2)] = True

    dofs_pri = np.where(in_pri)[0]
    dofs_sec = np.where(in_sec)[0]
    u = basis.zeros()
    u[dofs_pri] = 1.0
    u[dofs_sec] = 0.0
    dirichlet = np.unique(np.concatenate([dofs_pri, dofs_sec]))

    u = skfem.solve(*skfem.condense(K, basis.zeros(), x=u, D=dirichlet))

    # field energy per unit length: W' = ½ ε ∫|∇φ|²  = ½ ε (uᵀ K u)
    eps = EPS0 * eps_r
    energy_per_len = 0.5 * eps * (u @ (K @ u))
    if energy_per_len <= 0:
        return 0.0
    C_per_len = 2.0 * energy_per_len / (1.0 ** 2)   # V = 1
    C = C_per_len * L
    return float(C * 1e12)   # pF


if __name__ == "__main__":
    # self-test: a wide, close pair should approach parallel-plate εA/d
    w = 3.0; t = 0.07; h = 0.2; L = 40.0; eps_r = 4.2
    C_fem = fem_pair_capacitance_pf(w, w, t, h, L, eps_r)
    A = (w * 1e-3) * (L * 1e-3)
    C_pp = eps_r * EPS0 * A / (h * 1e-3) * 1e12
    print(f"FEM={C_fem:.3f} pF  parallel-plate={C_pp:.3f} pF  ratio={C_fem/C_pp:.2f}")
