---
title: TCAD Planar Footprint and Column Feasibility Contract
status: PROPOSED candidate; exact synthetic contract implemented
last_updated: 2026-10-03
paper_source: false
---

# TCAD Planar Footprint and Column Feasibility Contract

The [dyadic tensor candidate](../evidence/TCAD-Layer-Grid-Dyadic.md) passed
its condition screen but failed capacity. The next candidate replaces the
full x/y coordinate product with a conforming, locally triangulated planar
footprint arrangement and a shared vertical coordinate list. This still
propagates a planar mesh through layers; it is not fully local 3D adaptation
and may fail capacity or quality. Canonical conductor boxes, finite Neumann
outer boundary, primary/secondary potentials and dielectric physics stay fixed.

The current implementation is an exact-arithmetic library and tiny synthetic
tests only. It does not call a native kernel, generate a planar mesh, create
a 3D connectivity array or solve a field. Native integration, guarded execution,
prospective protocol/source freeze and real-input feasibility remain to be done.
Its command-line entry refuses execution. Real inputs must only be passed by
a later allocation/source/runtime-guarded SLURM worker, never on login.

## Complete footprint ownership

Keep all original conductor indices even when their x/y projections coincide.
A planar region is labelled by the complete set of covering conductors, not
one selected owner and not only the union of metal footprints. Conductors can
overlap in projection while occupying disjoint z intervals. Reject positive
3D volume overlap, nonfinite/degenerate inputs, conductors touching the domain
boundary and integer coordinates that would silently round to another double.

An independent area oracle uses all exact x/y endpoint intervals solely for
bookkeeping. Intersect the active conductor sets in each x and y interval and
sum exact rectangular areas by ownership mask. These reference rectangles are
**not** the proposed native mesh or prescribed global meshing lines. Native
fragment descendants and their areas must later agree with this independent
partition, including empty-ownership dielectric and multiply owned projections.
One-ULP-wide reference strips are retained rather than merged.

## Vertical coordinates and prospective counts

Retain every distinct canonical conductor/domain z face. Reuse the immutable
midpoint/face-band subdivision routine on z alone, with positive nominal near
and far spacings, bounded point/depth caps and no inserted band-edge planes.
Unlike the rejected tensor construction, an unrelated x/y gap does not set a
global far-spacing budget. This is a new construction policy, not relaxation of
the previous study's protocol or its failed gate. The later protocol must fix
all spacing values and quality thresholds before real inputs are processed.

For each complete footprint mask, remove exactly the canonical z intervals
occupied by its conductor owners. Require every ownership mask and positive
integer planar triangle counts. A triangle in each retained interval forms one
prospective prism; each prism contributes three tetrahedra under the rule below.
The full planar-node count times the number of z points is a conservative node
bound. Compute dielectric volume independently as footprint area times retained
height, and require exact equality with enclosing-box volume minus all conductor
volumes. No 3D array is needed for these counts. Passing count checks does not
validate the supplied planar observations or qualify a mesh.

## Consistent prism decomposition

Sort each triangle's three global planar node IDs. Let their lower vertices be
0, 1, 2 and their upper vertices 3, 4, 5 in the same order. The three templates
are `(0,1,2,5)`, `(0,4,1,5)` and `(0,3,4,5)`. Reverse orientation when the
sorted triangle is clockwise. The diagonal on any common vertical quadrilateral
is fixed by its shared global planar IDs, so neighbouring prisms cannot choose
incompatible side-face triangulations. Horizontal interfaces retain the same
planar triangle. Node renumbering must be global and frozen in the future
integration; independent per-face renumbering would invalidate this argument.

The exact signed determinant of every positively oriented tetrahedron is twice
the planar triangle area times the interval height. Three element volumes sum
to the prism volume. Synthetic tests independently check signs/volumes with a
4-by-4 homogeneous determinant, side-facet matching under all four-node orderings
of a two-triangle fixture, and horizontal matching between adjacent layers.
This establishes the template, not a complete native mesh boundary audit.

## New element-map conditioning certificate

The tensor-specific bound is not reused. For each actual planar triangle and
each of the three prism templates, form its exact Jacobian at unit height.
With h expressed in mm, `J(h) = diag(1,1,h) J(1)`. Its squared Frobenius norms
give `||J(h)||_F^2 = A + B h^2` and
`||J(h)^(-1)||_F^2 = C + D/h^2`. The squared spectral condition number is at
most their product. With t = h^2 this is `AC + BD + BC t + AD/t`, convex for
positive t. Its maximum over a closed positive interval occurs at an endpoint.
Thus evaluate both actual minimum/maximum retained heights for each template,
using exact rational coordinates and differences before any subtraction is
rounded. Keep rational z differences as rationals; casting them to double first
could shrink the interval and invalidate a bound.

The helper's default limit is the existing 10,000 element-condition threshold.
A future protocol must bind this value and independently check the native
triangle identities and every retained height interval. This is an element-map
geometry certificate, not native Gmsh quality, assembled FEM conditioning or
capacitance accuracy. Positive determinant alone does not pass it. Reports
explicitly deny native-quality provenance and keep all field/reference/training/
claim gates closed.

## Integration prerequisites and next action

Implement one bounded 2D-only/column-capacity probe, not a full 3D mesh just to
count its size. Capture the ordered native rectangle inputs, fragment map,
complete planar incidence and measures, and unchanged canonical geometry.
Validate ownership/area closure and actual triangle-to-region and edge-to-curve
coverage before counting columns. Bind the original archived 3D CAD identity;
2D projection must not change the physical problem. Preserve failed native
outputs as well as accepted ones, and define deterministic repeat scope.
Track planar mesh generation/validation separately from volume-mesh generation;
a future 2D meshing run must not inherit a misleading blanket no-mesh flag from
the earlier coordinate-only planners.

Then freeze resources, nominal sizing, caps, provenance, quality checks and
fresh toy/sentinel/repeat workers with actual-allocation/source/runtime guards.
Only after that source is published may native 2D work run through SLURM. A
later full 3D facet/terminal/volume audit, analytic field, same-mesh restriction
and sensitivity study remain separate prerequisites. These are reference
engineering steps, not a novel GNN contribution or an admitted paper claim.
The [evidence owner](../evidence/TCAD-Column-Feasibility.md) records implementation
coverage and the absence of real-input results.
