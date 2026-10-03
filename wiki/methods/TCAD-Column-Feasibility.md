---
title: TCAD Planar Footprint and Column Feasibility Contract
status: PROPOSED candidate; guarded source frozen and synthetic contracts validated
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

The implementation now includes arithmetic, native CAD/mesh readers, a guarded
2D builder, raw-array bundles and a prospective column planner. Validation so
far uses tiny synthetic fixtures and a fake native API only. The real native
kernel has not been called for this candidate. Protocol/source are now frozen;
publication and real-input feasibility remain pending. Library entries refuse
execution; the worker and builder verify allocation, source and runtime before
native imports or real geometry processing. Real work is SLURM-only.

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

## Planar CAD and mesh audit

Capture native input rectangles before fragmenting, then the full output map,
point coordinates, line lengths, surface areas and upward/downward incidence.
Every projection keeps its original conductor index, including coincident
projections. Require independent native incidence agreement, canonical input
corners/extents, complete owner masks and per-mask native area closure. Each
curve lies on a finite canonical rectangle edge; internal curves have two
parents and the four outer sides conserve length. Reject unresolved short
edges rather than snapping or repairing them. These readers use documented
Gmsh fragment maps, entity adjacency and point-value queries; field settings
are read back after assignment. See the [Gmsh reference](https://gmsh.info/doc/texinfo/).

Preserve first-order node, triangle and line arrays, including native entity
classification and raw connectivity. Global and entity-local observations must
agree. Canonicalization sorts records by global tags only. A separate CCW view
supports directed edge checks without modifying the raw packet. Require one
connected triangulated disk, one outer cycle, Euler closure, connected patches
on each CAD face, and a cycle/path vertex link at every interior/boundary vertex.
Native line elements must be complete nonoverlapping endpoint chains on their
CAD curves, with matching triangle/curve/face incidence and node classification.

Triangle centroids must match complete ownership, but centroid checks alone are
insufficient. Exact rational triangle/rectangle clipping checks the full area.
For each original conductor, sum nonnegative ownership discrepancies, rounding
each discrepancy **upward** to a multiple of `2^-80 mm2`. This conservative
error bound avoids denominator growth; it never rounds geometry or understates
leakage. Compare the aggregate once against the unchanged absolute/relative
CAD area tolerance, not a per-triangle tolerance multiplied by triangle count.
Also compare exact triangle areas with native surfaces and canonical masks.

## Packet-to-column integration and provenance

Only a packet passing the planar audit reaches column planning. Certify every
triangle with sorted global node IDs and the exact retained-height extrema of
its complete owner group. Record coverage, worst witness, failed-triangle count,
minimum positive determinant and a deterministic hash of the complete ordered
certificate sequence. Capacity or condition failure remains a retained report,
not a worker failure that silently skips the prescribed repeat.

The canonical partition volume remains distinct from the prospective volume
computed from actual planar triangle areas and retained heights. Report both,
their exact difference and the unchanged CAD relative/absolute volume gate.
This distinction prevents a within-tolerance native coordinate discrepancy from
being called exact canonical volume equality. Neither is a generated 3D mesh.

Native arrays use deterministic little-endian chunks and shape/dtype/hash
manifests. Byte-only terminal checks can verify file closure and reconstruct the
packet digest without importing a numerical library or replaying real arrays.
Save completed raw packets before numerical audit, including when audit fails;
all produced partial files remain after interruption. Failure before extraction
may leave only earlier CAD/metadata and logs, not a complete array packet.

## Prospective execution and next action

The frozen protocol is `protocols/tcad_cps_column_feasibility_v1.json`.
It binds the rejected dyadic archive and the original archived 3D
CAD identity. It prescribes fresh toy/sentinel/repeat processes, one 2D Delaunay
generation per process, first-order triangles, fixed seed/threads, no explicit
optimizer, and projected inherited Box sizing fields with read-back settings.
No auxiliary full x/y CAD grid is inserted. The frozen resource envelope is
600 seconds and 6 GiB per worker, inside one 35-minute, 8-GiB SLURM allocation.
Planar capture caps are 200,000 nodes, 400,000 triangles and 100,000 lines;
the earlier 3D prospective node/tetrahedron limits remain unchanged. Per-mode
binary data is capped at 64 MiB. The complete report and packet must repeat
byte-identically, excluding resource telemetry. No retries or automatic tuning.
Track `planar_mesh_generated` separately from `volume_mesh_generated`.

Synthetic integration/negative regression has passed on the source lock.
Publish source before the bounded SLURM study. Only then may native work run. A
later full 3D facet/terminal/volume audit, analytic field, same-mesh restriction
and sensitivity study remain separate prerequisites. These are reference
engineering steps, not a novel GNN contribution or an admitted paper claim.
The [evidence owner](../evidence/TCAD-Column-Feasibility.md) records implementation
coverage and the absence of real-input results.
