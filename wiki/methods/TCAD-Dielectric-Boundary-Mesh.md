---
title: TCAD Dielectric Boundary-Mesh Audit
status: PROPOSED; array and fake-native audit implemented; native mesh unperformed
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric Boundary-Mesh Audit

## Implementation boundary on 2026-10-03

The [CAD prerequisite](../evidence/TCAD-Dielectric-CAD-Diagnostic.md) passed
its declared toy/sentinel/repeat checks. The new
`code/solvers/tcad_cps_dielectric_mesh_audit.py` implements the extraction and
array-audit part of the next mesh-only study. It has no native import, session
creation, generation, optimizer, field assembly, solver or executable CLI.
Its real-array callers must be separately guarded SLURM workers; numerical
replay of real meshes is also compute work. This implementation checkpoint
does not authorize a standalone native run or reuse the old CAD allocation.

All old source locks, protocols and raw evidence are unchanged. No real mesh
has been generated or replayed in this step. Native construction must eventually
reproduce the two validated CAD-report identities before meshing. The old
builder finalizes its session before returning; a separate guarded builder
must therefore carry the same construction contract into a live mesh session,
without monkeypatching or modifying the frozen CAD source.

## Extraction and array contract

The public audit replays the full CAD report before using its retained-volume
and surface incidence. The lower-level private audit is exposed only for tiny
synthetic unit fixtures. Native extraction reads every retained volume and face
individually and compares the resulting element IDs/connectivity against global
dimension-specific reads. Mixed, unsupported and absent element types fail;
there is no silent skipping of non-tetrahedral material or high-order elements.

The [Gmsh 4.15.2 API reference](https://gmsh.info/doc/texinfo/gmsh.html#Namespace-gmsh_002fmodel_002fmesh)
and installed Python API text were inspected for `getNodes`, `getElements`,
`getElementProperties` and `getElementQualities`. They distinguish native node
and element identifiers from array positions and expose reference-element
coordinates. The reader checks first-order type-4 tetrahedra and type-2 triangles,
including their affine reference coordinates. It uses native signed condition
and determinant metrics, not an absolute-value substitute. These API contracts
support the implementation; they are not a successful native observation.

The canonical packet contains native node tags, coordinates in mm, native
tetrahedron tags/connectivity/owning CAD volumes, native triangle
tags/connectivity/owning CAD faces, and per-tetrahedron `minSICN` and
`minDetJac` in native mm-cubed units. Sort records by tag while preserving each
element's vertex order; do not renumber, reorient, repair or delete elements.
The packet SHA-256 covers labelled little-endian dtype/shape headers and exact
array bytes. Sparse large native IDs use search-based compact indexing, not
an allocation indexed by the largest tag. Unit conversion for a future field
solver is separate; the audit must not silently change mm into meters.

Required checks are:

- Exact packet schema, positive unique integer tags, finite array coordinates,
  matching shapes, supported element widths and pre-facet count caps. Element
  identifiers are unique across the extracted dimensions. No repeated vertex,
  duplicate connectivity, unknown node or unused node is accepted.
- Exact retained-volume and face coverage. Each boundary face has one retained
  dielectric owner; each internal dielectric face has its two distinct owners.
  Primary, secondary and outer groups are nonempty and partition the exterior.
- Strictly positive native signed condition and Jacobian, plus an independent
  determinant from the tetrahedron's actual coordinates and unaltered local
  vertex order. Compare the determinant to native `minDetJac` without an
  absolute tolerance that could hide a sign error near zero.
- Tetrahedron volumes sum to each retained CAD volume; vertices stay inside
  their owner's bounds. Surface triangle areas sum to each CAD face; their
  vertices stay in its planar bounds. Geometry-measure tolerances remain explicit
  inputs to the later frozen protocol, not values fitted to a native result.
- Enumerate all four tetrahedron facets. A facet has one or two owners; paired
  internal orientations must cancel. Native triangles must match exactly all
  one-owner exterior facets and all cross-volume internal facets. An internal
  dielectric interface is not silently exposed as an extra boundary condition.
- Joined native triangle labels must have the expected dielectric owner or
  owner pair. Primary and secondary node sets must not overlap each other or
  the outer-boundary node set. Each tetrahedral connected component must touch
  a terminal, rejecting a detached Neumann-only component.

The returned diagnostics keep field execution, numerical accuracy, reference,
training and claim flags false. They report topology and signed-validity checks,
not a condition-number bound, exhaustive geometric intersection proof, mesh
convergence or accurate capacitance. A tiny positive determinant is not evidence
of adequate numerical conditioning.

## Synthetic validation

The initial expanded suite passed 102 tests. It uses only a hand-constructed
96-node, 258-tetrahedron lattice with two interior unit-cube holes and a split
variant, plus small malformed arrays and a fake native API. Analytic volume
and area checks are independent of the audit's facet join. Tests cover record
ordering, reference-element conventions, mixed/global extraction disagreement,
type and count failures, sparse IDs, signed-quality rejection, flipped elements,
wrong ownership/planes, terminal shorts, internal-face orientation,
nonmanifold facets and an extra unanchored component. No Gmsh session ran.

The first test pass caught two fixture errors: the split plane excludes the
second hole's end face, and fake native quality arrays must follow requested
element-tag order rather than their original storage order. Those fixture
expectations were corrected; no native observation or scientific gate changed.
The combined boundary-audit, prior CAD/topology, rejected mesh-study archives,
wiki and prose regression subsequently passed all 570 tests with no skips.
After a local naming cleanup, the 102-test audit suite passed again. The
deterministic prose audit and diff checks passed. These are synthetic and
metadata checks, not a native mesh or field experiment.

## Next execution design

Implement a separate live-session CAD-to-mesh builder, guarded worker, bounded
parent, payload archive and source lock before submitting anything. Bind the
validated CAD report hashes and unchanged canonical geometry, permittivity,
terminal voltages and finite outer-Neumann target from the
[formulation contract](TCAD-Dielectric-Only-Formulation.md).

The planned single candidate is the already source-reviewed HXT generation
with automatic optimization disabled, followed by one explicit default-optimizer
call on the retained dielectric domain. Keep compact Box fields, mesh sizes,
padding, one thread, seeds and earlier mesh-study time/RSS/node/tetrahedron caps.
This is a new domain formulation, not a retry of the rejected all-volume study.
The old toy had a dielectric quality failure, so raw quality remains an
observation and final strict-positive checks remain necessary. There is no
fallback optimizer, tolerance relaxation, cap increase or claim that metal
removal will cure the previous timeout.

The new protocol must pin triangle and payload caps too. Preserve fresh
post-optimization coordinates, connectivity, ownership and metrics with a
deterministic chunked-array manifest; metadata-only collection may verify hashes
on login, while numerical packet replay must go through SLURM. Source/runtime
and allocation/host checks must precede native imports. Run toy, selected
sentinel and fresh repeat, stopping at the first failure under an external
worker watchdog. Freeze and publish the implementation/protocol before the
bounded job. This page is a design, not a submission receipt or frozen protocol.

Only a later successful mesh diagnostic permits separately specified field
qualification: same-mesh restriction, analytic opposing-face box, residual,
charge/energy consistency and mesh/domain sensitivity. Reference qualification,
controlled learning and a verified TCAD contribution remain incomplete.
