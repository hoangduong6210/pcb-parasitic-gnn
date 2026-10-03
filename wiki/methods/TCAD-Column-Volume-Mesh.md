---
title: TCAD Column Volume Connectivity and Boundary Qualification
status: PROPOSED; implementation before guarded execution
last_updated: 2026-10-03
paper_source: false
---

# TCAD Column Volume Connectivity and Boundary Qualification

## Input and scientific boundary

The [edge-local v2 study](../evidence/TCAD-Edge-Feasibility-v2.md) passed its
native probes, planar audit and prospective column gates. The next study must
construct and inspect actual tetrahedron connectivity, not infer a volume mesh
from those counts. Preserve that source and archive. Use its byte-bound planar
packets, canonical z planes, complete conductor ownership masks and original
3D CAD report; replay the necessary input audits only in guarded SLURM workers.
Do not regenerate or tune the 2D sizing policy or snap coordinates.

## Construction and independent checks

Use the frozen three-tetrahedron prism rule, globally ordered planar node IDs
and exact signed planar areas. For every z interval, include precisely the
dielectric prisms prescribed by complete footprint ownership and canonical
conductor heights. Preserve each generated slab before its numerical/topology
gate. New node identities encode the original planar ordinal and z-plane index;
retain that mapping when excluding nodes that belong to no generated dielectric
tetrahedron. This is the declared domain construction, not repair of a rejected
mesh. Preserve all original input arrays unchanged.

Audit every actual tetrahedron's signed coordinate determinant against its exact
column determinant, with the unchanged relative comparison tolerance. Recheck
the inherited exact condition certificates, canonical volume and count caps.
No native quality metric may be invented for this non-native 3D construction.

Enumerate all four oriented facets of every tetrahedron, slab by slab. Reject
duplicate/nonmanifold ownership and non-cancelling internal orientations. Join
horizontal facets between consecutive slabs by exact node identity, retaining
their orientations and component owners. Every unmatched facet must match an
explicit terminal or outer CAD surface, with correct dielectric-outward normal,
surface area and bounds. The full face accounting must satisfy four times the
tetrahedron count equals twice the interior-facet count plus the boundary count.
Track connected components across slab joins and require terminal anchoring;
primary, secondary and outer boundary node sets must be disjoint.

Streaming is a memory strategy, not reduced coverage. Synthetic tests must
compare the slab audit to an independent whole-mesh facet enumeration, include
cross-slab seams and conductor cavities, and reject altered connectivity,
coordinates, missing surfaces, wrong labels/orientations and unanchored pieces.
The terminal collector remains byte/scalar-only, never a real-mesh replay on
login. A new source/protocol lock, complete payload format and bounded worker
must be frozen and published before any real-volume execution.

## Scope after a pass

A pass may qualify the declared geometric volume/boundary contract only. It
does not establish capacitance accuracy, field conditioning or a reference.
Analytic opposing-face box, same-mesh restriction, residual, charge/energy and
mesh/domain-sensitivity checks remain separate prerequisites for field and
learning work. No paper claim or snapshot is admitted by this implementation.

## Current preparation

At 16:37:39 UTC on 2026-10-03, local HEAD and GitHub main matched the published
edge-v2 receipt commit with a clean worktree and empty owner queue. The previous
turn made native validation and publication progress. The next implementation
starts with the streamed connectivity/facet audit and tiny synthetic tests;
there is no new volume execution or submission yet.

The construction and streamed facet/component libraries now pass their initial
expanded tiny-fixture tests. The [evidence owner](../evidence/TCAD-Column-Volume-Mesh.md)
records coverage and limitations, including explicit rectangular exterior CAD
binding and rejection of unhandled internal CAD partitions. Bounded payload
preservation and guarded execution remain to be implemented before source
freeze and an actual SLURM volume study.
