---
title: TCAD Dielectric-Only Formulation Contract
status: PROPOSED; bounded CAD diagnostic validated; mesh and field pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric-Only Formulation Contract

The [explicit-optimizer study](../evidence/TCAD-HXT-Explicit-Optimization.md)
ended at its sentinel time cap. This separate investigation asks whether
excluding fixed-potential conductor interiors produces a usable discretization
within unchanged resource ceilings. No speed, quality or novelty claim follows
from the proposal. The optimizer's bottleneck has not been attributed solely
to conductor interiors; dielectric slivers may remain after their removal.
The archived raw toy actually has its nonpositive signed-condition observation
in dielectric, as recorded on the linked evidence page. Removing metal volume
is therefore not assumed to eliminate the mesh-quality failure.

## Electrical quantity and equivalence boundary

Keep the canonical conductor boxes and stackup from `geometry_contract.py`,
uniform relative permittivity 4.2, primary at 1 V, secondary at 0 V and the same
finite enclosing box with homogeneous natural-Neumann boundary. The target
remains twice the electrostatic energy at this unit voltage, expressed in pF;
it is not silently changed to free-space mutual Maxwell capacitance.

The existing `fem_capacitance_3d.py` fixes every conductor-element node to its
net potential, but assembles conductor elements too. In exact arithmetic,
constant P1 nodal values imply zero element gradient. Conductor elements touch
no free row, so deleting their contributions leaves the same free block and
Dirichlet forcing **if the retained dielectric mesh and interface constraints
are identical**. Interior conductor degrees of freedom must also be removed;
keeping orphan rows would create a singular system. Floating-point cancellation
in the old global energy need not be exactly zero on degenerate elements.

A same-mesh restriction test can examine that algebraic statement. Independently
remeshing a dielectric-only CAD domain changes the discretization and does not
justify equal matrix hashes or bitwise equal capacitance. Later field tests must
separate implementation equivalence from mesh/domain convergence. Reject nodes
assigned to both nets rather than silently giving one potential precedence.

## Proposed CAD and boundary contract

Use fragment provenance, not conductor-centroid classification. Preserve the
identity and order of input outer/primary/secondary entities, then explicitly
aggregate their descendants. Require nonempty disjoint primary and secondary
sets inside the enclosing-box descendants; dielectric is their complement.
Verify input/output map association against the pinned native API before the
adapter is frozen. No inference from an output volume number is sufficient.

The [separate CAD implementation](../evidence/TCAD-Dielectric-CAD-Diagnostic.md)
now binds correspondence in source-confirmed object-then-tool order. It uses
one enclosing box followed by the individual canonical trace boxes, without
net fusion. The geometry contract rejects volumetric trace overlap; keeping
per-trace provenance permits bounds/volume checks that an aggregate net label
would obscure. This changes construction bookkeeping, not conductor geometry.

Read each volume's boundary independently from each face's upward adjacency.
Require exact entity coverage and agreement between these two incidence maps.
The [Gmsh API](https://gmsh.info/doc/texinfo/#gmsh_002fmodel_002fgetAdjacencies)
provides upward/downward incidence; the
[fragment API](https://gmsh.info/doc/texinfo/#gmsh_002fmodel_002focc_002ffragment)
provides entity correspondence. API descriptions are design support, not a
successful CAD observation.

| Face owners | Treatment |
|---|---|
| Dielectric and primary | Primary Dirichlet surface |
| Dielectric and secondary | Secondary Dirichlet surface |
| Two dielectric volumes | Internal interface, no extra boundary condition |
| One dielectric volume on independently checked outer box | Natural-Neumann surface |
| Two volumes of the same conductor net | Interior metal face; absent from retained dielectric domain |
| Primary and secondary, more than two owners, or other single-owner face | Reject |

`code/solvers/tcad_cps_dielectric_topology.py` implements these **abstract
metadata** checks and rejects dielectric components without any terminal
boundary. It emits expected retained incidence and keeps all geometry,
removal, mesh, field, reference, training and claim flags false. Its synthetic
fixtures are not closed CAD solids. It cannot detect edge/vertex shorts,
incorrect coordinates, zero area, overlapping solids or dishonest provenance.

Before actual removal, the guarded adapter must independently verify
canonical geometry, positive volume/area, box containment and the six outer
planes. Never label an unidentified hole as outer merely because it has one
owner. Remove conductor volumes nonrecursively, preserve interface surfaces,
and remove only proven orphan lower-dimensional entities. After synchronization,
check the exact retained volume/face incidence and reachability of all surface,
curve and point entities. No recursive removal that erases needed interfaces.

The implemented CAD-only path captures full native entity records for all four
dimensions: tag, type, bounding box, measure and independent incidence. Replay
checks each trace's fragment-volume sum and bounds, total enclosing volume,
six outer-plane area sums, net surface/edge/vertex separation, and exact
retained entity closure. Remaining entity metadata must be unchanged except
for adjacency to removed parents. Input net separation, coordinate/measure
tolerances, entity caps and CAD options are pinned in its new protocol. This
does not relax any old mesh-quality threshold or prove meshing feasibility.

After meshing, require all extracted nodes to be used, supported tetrahedral
types only, exact boundary-triangle coverage of the tetrahedral boundary,
nonempty disjoint primary/secondary node sets, and finite strictly positive
signed quality/Jacobians for every retained element. A positive metric alone
does not qualify conditioning or accuracy. Lower-dimensional topology checks
must detect net shorts even when no whole face is shared.

## Execution and qualification sequence

1. Validate abstract classification with tiny synthetic fixtures on login.
   This step does not import Gmsh or a numerical library.
2. Implement a separate guarded CAD adapter and no-field diagnostic. Check
   actual SLURM allocation, executing node, frozen source and runtime before
   native imports. Freeze policy, caps, exact receipts and fresh-repeat gates
   before any toy or sentinel CAD/mesh job. No current job is authorized by
   this prose alone; do not reuse the failed optimizer protocol.
3. If geometry/mesh gates pass, separately specify controlled field tests:
   same-mesh restriction, an analytic box with full opposing terminal faces
   and insulating side walls, algebraic residual, charge/energy consistency,
   then mesh and enclosing-domain sensitivity. The finite fringing PCB toy is
   not that analytic parallel-plate problem.
4. Retain the new formulation identity in every receipt. Do not relabel old
   targets, reopen training or export a paper claim without separate evidence
   review and admission.

The bounded native CAD diagnostic has now completed through SLURM; its
[evidence page](../evidence/TCAD-Dielectric-CAD-Diagnostic.md) owns the checked
terminal archive and exact-repeat reports. No meshing, solving or fitting was
performed. Next is a separate boundary-aware mesh diagnostic, binding these
CAD identities and preserving every original rejected result. Numerical
qualification and a learning contribution remain future work.

## Validation checkpoint on 2026-10-03

All 79 topology tests passed, covering input types/coverage, independent
incidence disagreement, terminal overlap, unidentified exterior faces,
nonmanifold faces, disconnected Neumann-only components, deterministic output
and closed scientific flags. The combined topology/wiki/prose run passed
134 tests; the deterministic prose audit passed separately. These fixtures
exercise metadata logic only and do not validate real geometry or field physics.
