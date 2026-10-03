---
title: TCAD Mesh-Only HXT Probe
status: RUNNING; frozen mesh-only diagnostic
last_updated: 2026-10-03
paper_source: false
---

# TCAD Mesh-Only HXT Probe

The preceding [seven-arm study](TCAD-Cps-AMG-Feasibility.md) stopped at
local1's mesh-generation time cap. This separate diagnostic tests one mesher,
not a new capacitance solver or a retry with larger limits. The
[protocol](../../protocols/tcad_cps_mesh_probe_v1.json) binds that terminal
archive and preserves the geometry, compact conductor Box fields, local and
far sizes, padding, random seed and one-thread settings. Only
`Mesh.Algorithm3D=10` and nonnumerical native logging change. The
[research plan](../manuscript/TCAD-Research-Plan.md) records the primary-source
motivation and scientific prerequisite.

Three fresh processes execute in order: toy, layout-597 local1, then an
identical local1 repeat. The toy has 600 seconds, 6 GiB RSS, 300,000 nodes and
1,500,000 tetrahedra; each sentinel worker has 1,200 seconds, 120 GiB RSS,
3,000,000 nodes and 20,000,000 tetrahedra. A parent enforces time and process
RSS, kills the worker process group at a cap, retains stdout/stderr and stops
at the first failure. No matrix assembly, AMG, CG or capacitance is computed.

The unchanged geometry builder and field helper are reused. The worker checks
actual compute-node allocation, source and runtime before numerical imports.
Native Gmsh logs expose internal meshing progress; the receipt records effective
options, HXT build support, all eight completed stages, region counts and
resource measurements. Each mode must contain dielectric and both conductor
regions, finite coordinates and valid connectivity.

The ordered mesh fingerprint hashes a schema prefix and labelled dtype/shape
headers followed by C-order bytes for metre coordinates (`<f8`), tetrahedral
connectivity (`<i8`) and region labels (`|i1`). It is deliberately not
permutation-invariant. The two fresh sentinel runs must have exactly equal
fingerprints, node/tetrahedron counts, region counts and effective-policy hashes.
Complete but nonrepeatable observations are a valid negative outcome, not
mesh feasibility. An incomplete sequence is also retained.

A mesh pass only permits preparation of separately frozen backend and
sensitivity checks. Changing the mesher changes the discretization; old
capacitances and matrix hashes are not transferred. Reference qualification,
training, automatic expansion and paper claims remain false in every outcome.

See the [runbook](../operations/TCAD-Cps-Mesh-Probe.md) and
[evidence record](../evidence/TCAD-Cps-Mesh-Probe.md).
