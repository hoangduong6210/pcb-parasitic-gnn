---
title: TCAD Column Volume Mesh Evidence
status: PROPOSED; synthetic implementation checks only
last_updated: 2026-10-03
paper_source: false
---

# TCAD Column Volume Mesh Evidence

## Preparation and source-only scope

At 16:37:39 UTC on 2026-10-03, local HEAD and GitHub main were clean and equal
to `40c11a12e11bdc17196438088339bacfd8cb6a18`; the owner queue was empty.
The preceding goal turn made guarded native validation, preservation and
publication progress. The full TCAD goal remains active and incomplete.

The [new volume method](../methods/TCAD-Column-Volume-Mesh.md) now has two
library modules: `tcad_cps_column_volume_geometry.py` constructs deterministic
slabs and binds rectangular CAD surfaces; `tcad_cps_column_volume_audit.py`
checks actual connectivity, signed determinants, complete slab/seam facet
incidence, boundary measures and terminal-anchored connected components.
They have no native initialization, field assembly, file-writing workflow or
usable meshing CLI. Actual inputs require a future allocation/source/runtime-
guarded SLURM worker, source lock and separately frozen execution protocol.

The array audit is specific to the declared column construction, not a
universal tetrahedral-mesh validator. It rejects internal CAD subdivisions
without an explicit volume-owner contract and requires rectangular exterior
CAD faces with verified corner/edge structure. The previous selected CAD
reports have no internal dielectric faces; integration must verify that fact
under its own input binding, not silently discard extra faces. Native padded
bounds are used for containment without changing coordinates. The final
mesh/native area comparison retains the original stricter measure tolerance.

## Synthetic tests

The initial core passed **39 tests** in 2.02 seconds. After strengthening
rectangle corner/edge checks and cap/plan schema validation, 39 tests passed
again in 2.30 seconds. Expanded coverage passed **54 tests** in 2.66 seconds.
All inputs are tiny hand-built fixtures; no real layout or native session ran.

Expanded regression subsequently passed **534 tests, zero skips**, in 89.41
seconds. It includes the new volume core, frozen column construction/CAD/mesh/
planning/bundle tests, earlier dielectric-mesh audit, edge-v2 integration and
archive checks, and the wiki/prose contracts. Archived real-input checks in this
suite are byte/scalar inspections, not real-mesh numerical replay. The owner's
queue was empty at 17:18:28 UTC. No volume execution protocol is frozen and no
new scientific job has been submitted at this source-only checkpoint.

The principal fixture contains 96 nodes and 258 tetrahedra with two interior
unit-box conductor holes. The streamed audit agrees with an independent
whole-mesh face enumeration: 180 exterior triangles and 426 interior facets,
volume 43 mm3, boundary area 90 mm2 and one terminal-anchored component.
Every preserved boundary triangle's tetrahedron owner is checked. An additional
25-node planar fixture verifies deterministic omission of only the two unused
strictly metal-interior column nodes; original coordinates and source arrays
remain unchanged. Another fixture retains a nonrepresentable exact height
difference in the determinant oracle rather than rounding the difference first.

Negative tests cover changed/missing/duplicate/flipped connectivity, invalid
planes and caps, independent coordinate-determinant disagreement, invalid slab
order, nonmanifold facets, wrong seam orientation or ownership, CAD group/area/
normal mismatches, ambiguous surfaces, unanchored components and conflicting
volume owners. A failed audit cannot be resumed with repaired input. Sparse
native source tags, reversed source record order, raw clockwise planar triangles
and native-style padded metadata do not change the generated volume geometry.

## Remaining execution prerequisites

The tested source-only core was published as
`adc48b6703a17a626f6966209916befabd02e0d3`, with matching local/GitHub main
confirmed at 17:21:15 UTC. Final checks passed the 7,467-file manifest, prose
audit and 55 wiki/prose tests. This is not an execution lock or a qualified
real-volume result. Prior frozen sources and evidence remain unchanged.

Next implement bounded
chunked volume payload preservation, source/archive bindings, guarded workers,
watchdog and byte-only terminal collection. Freeze resource and payload limits
before a single toy/sentinel/fresh-repeat SLURM study. Preserve each slab before
its gate and retain partial failures. Recompute the upstream planar/conditioning
contract on compute before accepting it as input. No actual volume mesh or
boundary qualification, electrical result, new claim or paper export follows
from these synthetic checks alone.
