---
title: TCAD Canonical-Plane Tensor-Grid Planning
status: REJECTED projected-support candidate; planning implementation validated
last_updated: 2026-10-03
paper_source: false
---

# TCAD Canonical-Plane Tensor-Grid Planning

The [arithmetic diagnosis](../evidence/TCAD-Jacobian-Arithmetic.md) localized
floating errors on nearly coplanar tetrahedra. This prospective candidate uses
the axis-aligned canonical conductor boxes to assess a structured alternative.
The current study creates only one-dimensional coordinate lists and integer
capacity estimates. It does not create tetrahedra, import a native geometry
kernel, assemble a field system or qualify a reference.

## Geometry and spacing

Use the same toy and previously selected largest sentinel, padding, nominal
near/far spacings and archived CAD identities. The proposed meshing policy is
new: it is not equivalent to the prior three-dimensional Gmsh Box field. For
each coordinate axis, retain all canonical conductor/domain endpoints exactly.
Add the clipped endpoints of each conductor's projection expanded by 0.055 mm.
Only exactly equal stored coordinate values are deduplicated. Distinct planes
one floating-point step apart remain distinct and can make the candidate fail.

Each base interval is either fully inside the union of expanded projections
or outside it. Apply the nominal near or far spacing accordingly. Divide an
interval uniformly using the exact rational ceiling of width/nominal spacing,
then round each rational interpolation once to binary64. Preserve both original
endpoints; reject collapsed or reversed subdivisions. Nominal spacing is a
construction target, not a claim that rounded widths obey an exact real-valued
spacing bound. Record every point as decimal and hexadecimal, base intervals,
division counts, exact minimum gaps and their location. No tolerance-based
snapping, midpoint classification, accumulated stepping or tiny-cell deletion.

The Cartesian product includes each conductor as a union of whole cells.
Reject any positive-volume overlap under exact endpoint comparisons, even if
an earlier geometry tolerance would have hidden it. Count conductor cells by
their axis-index ranges and subtract them from the total product. Record the
exact dielectric volume from the stored canonical box endpoints. No 3D cell
array is allocated. The full tensor-node product bounds the nodes that a later
dielectric-only implementation would retain; it can be conservative.

## Prospective geometric-quality screen

The intended later cell decomposition has six Kuhn simplices per cuboid,
defined by all coordinate-axis permutations and a consistent body diagonal.
The current count is six times the dielectric-cell count, not an executed mesh
or a verified facet-conformity observation.

In a simplex's axis order its Jacobian has rows `[hx,hx,hx]`, `[0,hy,hy]`,
`[0,0,hz]`. The inverse has rows `[1/hx,-1/hy,0]`, `[0,1/hy,-1/hz]`,
`[0,0,1/hz]`. Axis permutations and orientation-preserving column reordering
do not change the relevant norm bounds. With the smallest/largest positive
stored-coordinate interval widths `hmin` and `hmax`, the squared Frobenius norms
are bounded by `6*hmax^2` and `5/hmin^2`; hence
`kappa_2(J)^2 <= 30*(hmax/hmin)^2`. Tiny synthetic rational-matrix tests check
the inverse and bound for all six axis orders.

Before real-layout execution, require this conservative global bound to be at
most `10000^2`. This is an engineering conditioning screen with a large margin
from the rejected near-coplanar regime, not a calibrated accuracy threshold,
global FEM matrix condition estimate or convergence proof. Retain a failed
screen without lowering its bound after observing the layout.

Require the full tensor-node upper bound and prospective dielectric tetrahedron
count to fit the unchanged toy/sentinel mesh caps. Projection refinement can
propagate fine spacing across a whole tensor product; this capacity check is
deliberately performed before expensive meshing. A completed diagnosis may
show an infeasible candidate. No automatic alternative or parameter search is
included in this protocol.

## Execution and interpretation

Protocol: `protocols/tcad_cps_layer_grid_plan_v1.json`. Run toy, local1 and fresh
repeat1 through one SLURM allocation: 8 GiB, 15 minutes, one requested CPU and
one scientific thread. Each worker has 180 seconds, 6 GiB and a 6-MiB report
cap; each axis is limited to 4,096 points and a layout to 128 conductors. Actual
allocation/compute host, source and runtime guards precede real-layout planning.
Login-side review checks bytes and metadata, never regenerates the axes.

Retain all computed plans, including negative capacity/conditioning checks.
Stop only on worker, geometry, identity or coverage failure. Complete diagnosis
requires exact local1/repeat1 report bytes. Planning feasibility is separate
from diagnosis completion and never marks a mesh or field valid. A later mesh
implementation needs its own frozen boundary/quality checks, then analytic
field, same-mesh restriction and sensitivity protocols. This is reference
engineering, not a novel graph-learning contribution. Outcomes belong to the
[evidence owner](../evidence/TCAD-Layer-Grid-Planning.md).

## Observed outcome

The bounded planning job completed with exact fresh-repeat reports and a
checked archive. The projected-support candidate failed capacity and/or
conditioning preflight; no mesh was generated. The linked evidence page owns
the counts and the distinction between canonical planes and near-coincident
auxiliary support endpoints. A new face-band/midpoint subdivision candidate
requires its own prospective protocol; do not rerun or modify this frozen one.
