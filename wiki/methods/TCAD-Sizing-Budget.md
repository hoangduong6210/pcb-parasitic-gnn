---
title: TCAD Archived Sizing and Vertical Budget Diagnostic
status: PROPOSED; source frozen and synthetic regression passed, execution pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Archived Sizing and Vertical Budget Diagnostic

The [column study](../evidence/TCAD-Column-Feasibility.md) produced a valid
toy packet but its sentinel exceeded the fixed planar-node capture cap. This
separate diagnostic explains the geometric sizing burden and the remaining
vertical capacity budget. It does not rerun Gmsh, change any cap, select a
replacement sizing policy, generate connectivity or evaluate capacitance.
Bindings and execution state belong to the [evidence page](../evidence/TCAD-Sizing-Budget.md).

## Fixed input and geometry checks

Bind the original qualified 3D CAD report and the failed study's preserved
planar CAD, sizing JSON and native stdout by source-lock/archive hashes.
Recheck canonical boxes, complete planar ownership and the exact requested
and read-back Box/Min fields against the unchanged parent policy. The sentinel
repeat reads the same archived local input: it tests arithmetic reproducibility,
not native mesh repeatability. Real geometry processing runs only after
allocation, actual compute-host, source and runtime guards on SLURM.

## Exact projected coverage and descriptive indices

Clip rectangles to the original x/y domain and compute exact rational union
area and multiplicity for three sets: canonical conductor footprints, archived
Box cores, and those cores expanded in each x/y direction by stored Thickness.
Retain duplicate projections, clipping, overlap and every positive one-ULP
strip. Core coordinates use their archived binary64 values; envelope arithmetic
is exact and is not rounded back to double. Reference endpoint cells are only
area bookkeeping, not a generated mesh. Cross-check domain area and the
multiplicity-weighted sum against summed individual clipped areas.

For each union area A, report `A/h_near^2 + (A_domain-A)/h_far^2`. This is a
dimensionless step-field workload index, **not** a node prediction, a replay of
the native transition function or an achieved edge-size bound. The
coordinate-expanded envelope is descriptive, not a measured transition area.

The [official Gmsh manual](https://gmsh.info/doc/texinfo/#Specifying-mesh-element-sizes)
documents background sizing and global size limits. Its Box-field reference
describes VIn, VOut and a Thickness interpolation layer. This diagnostic does
not infer the uninspected implementation formula or equate a size request with
realized mesh density. Native source access was unsuccessful during this review.

## Unchanged vertical and count budgets

Reuse the frozen z-only midpoint/face-band planner with nominal spacings and
all canonical z faces. For every complete projected owner mask, remove only
its conductor intervals, retain exact dielectric height and close total volume
against enclosing-box volume minus conductor volumes.

Let Nz be the z-point count, Nmax the original 3D-node cap, and Tmin/Tmax the
minimum/maximum retained interval counts over nonempty-area owner groups.
The full-column planar-node allowance is `floor(Nmax/Nz)`, intersected with
the original capture cap. With Emax the original tetrahedron cap, a sufficient
planar-triangle budget is `floor(Emax/(3*Tmax))`; the necessary ceiling is
`floor(Emax/(3*Tmin))`. Both also intersect the original triangle capture cap.
These conservative budgets do not predict triangle counts or guarantee
conditioning/topology. Zero budgets and exceeded allowances are retained.

Parse exactly one native stdout node/mixed-element total. Multiplying its node
count by Nz is a **conditional full-column node bound**, not an independently
audited sentinel mesh count. Do not infer a sentinel triangle count from the
mixed-dimensional element total or mistake a failed conservative bound for a
proof that every possible node-pruned construction must fail.

## Execution and interpretation

The fixed toy/local/repeat sequence uses fresh bounded diagnostic workers,
180 seconds and 6 GiB each, in one 15-minute/8-GiB no-requeue job. No native
initialization, optimization, solve, training or automatic retry occurs.
Byte/scalar metadata review on login never regenerates geometry or z plans.
Success means all diagnostic reports are valid and the repeated archived-input
reports are byte-identical. It does not admit a new meshing candidate, qualify
a reference or make any result manuscript-eligible.
