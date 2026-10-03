---
title: TCAD Canonical-Interval Dyadic Planning
status: REJECTED capacity candidate; planning diagnostic validated
last_updated: 2026-10-03
paper_source: false
---

# TCAD Canonical-Interval Dyadic Planning

This separately versioned candidate follows the rejected
[projected-support plan](../evidence/TCAD-Layer-Grid-Planning.md). It changes
the grid construction rule, not geometry, physics, sample selection or the
original capacity/condition gates. It computes only one-dimensional coordinates
and prospective counts. No native geometry kernel, 3D mesh or field is created.

## Frozen construction rule

Only exact distinct canonical conductor/domain endpoints are mandatory planes.
For each axis, construct rational bands of half-width 0.055 mm around conductor
face coordinates. Their endpoints are never inserted as mandatory planes.
An interval overlapping any closed face band uses the near target; other
intervals use the bounded far target. Intervals inside a long conductor
projection may therefore use coarse spacing away from its faces. This remains
a globally propagated tensor grid, not local 3D adaptation.

Let g be the minimum exact gap between consecutive canonical planes across all
three axes. Set f = min(g, nominal near spacing / 4), and the maximum target
width to min(nominal far spacing, 10000 f / 12). The near target is the smaller
of nominal near spacing and that maximum. The divisor 12 is a prospective
construction margin, not a replacement quality gate or a fitted parameter.
It can only reduce a spacing target, never coarsen one to pass capacity.

Starting separately within each canonical interval, bisect only if its exact
stored-coordinate width exceeds its target. Compute the midpoint as an exact
rational and round once to binary64. Traverse left before right; reject a
rounded midpoint that is not strictly interior. Retain all distinct canonical
planes, including one-ULP gaps. Stop with failure rather than merge planes if
the 4,096-points/axis or 64-level subdivision cap is reached.

Record all stored coordinates in decimal/hexadecimal, canonical intervals,
leaves, depths, band classifications, target widths and exact width-budget
metadata. Recompute the unchanged conservative condition screen from the
actual stored widths: 30 (hmax/hmin)^2 <= 10000^2. The width-budget construction
does not waive this check. The preceding method page gives the Kuhn-simplex
norm bound; it is not a global FEM condition estimate or an accuracy proof.

Count tensor nodes and dielectric cells by canonical conductor index ranges,
without allocating 3D connectivity. Reject positive-volume conductor overlaps.
Each retained cell prospectively contributes six Kuhn tetrahedra. Require the
same original node/tetrahedron caps. A full tensor node count is conservative;
the declared prospective tetrahedron count is exact for this construction.

## Execution and interpretation

Protocol: `protocols/tcad_cps_layer_grid_dyadic_v1.json`. The unchanged toy,
selected sentinel and fresh repeat run through one verified SLURM allocation,
with inherited padding, nominal spacings and archived CAD identities. The
allocation requests one CPU, 8 GiB and 15 minutes; scientific threads stay one.
Each fresh worker is bounded by 180 seconds, 6 GiB and a 6-MiB report. Guards
verify actual allocation/compute host, frozen source and runtime before real
planning. Login-side review is byte/metadata-only and never regenerates axes.

Keep every completed plan, including negative gates. Stop only on worker,
geometry, identity or coverage failure; do not retry or tune this protocol.
Require identical complete sentinel/repeat report bytes for diagnosis completion.
Planning feasibility does not qualify a mesh. A later implementation needs
explicit structured-quality provenance and complete boundary/terminal/facet
checks; native Gmsh quality arrays must not be fabricated for a structured mesh.
Analytic field, same-mesh restriction and sensitivity studies follow separately.
All field/reference/training/claim flags remain false. This is reference
engineering, not a claimed graph-learning contribution. Results belong to the
[evidence owner](../evidence/TCAD-Layer-Grid-Dyadic.md).

## Observed outcome

The diagnostic and exact fresh repeat completed. Toy passed prospective gates;
the selected sentinel passed the condition screen but failed capacity. Both
complete plans and terminal metadata are archived. Do not generate this grid
or reinterpret diagnosis completion as mesh feasibility. The evidence owner
records exact counts, width-budget propagation and remaining limitations.

## Next candidate boundary

The next design hypothesis is a conforming planar footprint arrangement,
locally triangulated and paired with canonical z intervals, rather than a full
x/y coordinate product. Map every planar region to all covering conductor IDs;
only the appropriate z ranges are metal. Preserve canonical geometry and retain
the same finite-domain electrical problem. This would still propagate a shared
planar mesh through layers; it is not fully local 3D adaptation and may also
fail capacity or quality.

The official Gmsh 4.15.2 manual documents conforming Boolean fragments with
input/output maps, dimension-limited mesh generation, and layered mesh extrusion.
These support considering the construction; they do not establish correctness
or feasibility for this dataset. See the [Gmsh reference manual](https://gmsh.info/doc/texinfo/),
sections 6.8 (`occ/fragment`), 6.4 (`mesh/generate`) and tutorial t3, checked
2026-10-03. No native API was invoked on login during this review.

Before a real-input probe, separately specify planar ownership/topology and
area closure, boundary conformity, spacing, retained z coordinates, count caps,
positive-orientation/conditioning checks and exact-repeat scope. Start with a
bounded 2D-only/column-capacity study through SLURM; do not allocate a full 3D
grid merely to estimate its size. A later prism-to-tetrahedron rule needs a
consistent shared-face diagonal and its own independently checked quality
formula. The tensor-specific bound above must not be reused for a different
element map without proof, and native quality values must not be fabricated.
Full 3D facet/terminal/volume audit, analytic field and sensitivity checks remain
separate prerequisites. This engineering proposal is not a new TCAD claim.

The subsequent [column contract](TCAD-Column-Feasibility.md) now implements
exact ownership/count bookkeeping and a distinct prism-map conditioning
certificate with synthetic shared-facet tests. Its native integration and
real-input protocol remain pending; it does not change this rejected study.
