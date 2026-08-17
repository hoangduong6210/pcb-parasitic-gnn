---
title: Electrostatic FEM Capacitance Method
status: admitted method with unresolved mesh convergence
last_updated: 2026-08-15
paper_source: true
prose_reviewed: true
claim_ids: C-FEM-001, C-FEM-002, C-FEM-003
citation_keys: skfem, gmsh
---

# Electrostatic FEM Capacitance Method

The capacitance calculation solves the electrostatic equation

\[
\nabla\cdot\left(\epsilon\nabla V\right)=0
\]

on a tetrahedral volume mesh. Primary and secondary conductor volumes are held
at 1 and 0 V. The inter-winding capacitance follows from the stored electric
field energy,

\[
C_{ps}=2W,
\qquad
W=\frac{1}{2}\int_\Omega \epsilon |\nabla V|^2\,d\Omega.
\]

Gmsh constructs the tetrahedral mesh and scikit-fem assembles the finite-element
system. Production runs use smoothed-aggregation algebraic multigrid with
conjugate gradients, relative tolerance \(10^{-10}\), a maximum of 500
iterations, and a required final relative residual no larger than \(10^{-9}\).
The current model uses an effective uniform relative permittivity of 4.2.

## Numerical sensitivity definitions

At fixed refine-3, domain sensitivity is

\[
\Delta_{\mathrm{domain}}
=
\frac{|C_{\mathrm{R3P12}}-C_{\mathrm{R3P16}}|}
{|C_{\mathrm{R3P16}}|}\times100\%.
\]

At fixed 16 mm padding, mesh sensitivity is

\[
\Delta_{\mathrm{mesh}}
=
\frac{|C_{\mathrm{R3P16}}-C_{\mathrm{R4P16}}|}
{|C_{\mathrm{R4P16}}|}\times100\%.
\]

Each comparison must independently satisfy a median no larger than 2% and a
maximum no larger than 5% over the frozen nine-layout set.

Passing the domain gate supports the selected outer-domain padding. Failing the
mesh gate means that refine-3 is not accepted as a mesh-converged production
reference. It does not invalidate a clearly named fixed numerical surrogate
target. Refine-4 is the highest feasible level tested across the frozen subset,
not a proof of convergence to the continuum solution.
