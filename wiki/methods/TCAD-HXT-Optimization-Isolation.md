---
title: TCAD HXT Optimization-Isolation Diagnostic
status: REJECTED; toy quality gate failed; original specification preserved
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Optimization-Isolation Diagnostic

The diagnostic is now terminal and incomplete. The
[evidence record](../evidence/TCAD-HXT-Optimization-Isolation.md) records a
toy signed-quality rejection and the preserved archive. The sentinel and
fresh repeat were not run. The specification below remains unchanged; this
negative result does not permit field use or a relaxed quality gate.

The preceding [HXT probe](TCAD-Cps-Mesh-Probe.md) timed out during native 3D
improvement. This separate diagnostic sets only `Mesh.Optimize=0`, retaining
HXT, geometry, compact Box fields, sizes, padding, random seed, logging, pinned
runtime and one scientific thread. It isolates the optimization stage identified
in the [source review](../manuscript/TCAD-Research-Plan.md). It does not declare
that stage unnecessary for reliable field computation.

The [protocol](../../protocols/tcad_cps_hxt_isolation_v1.json) orders three fresh
processes: toy, layout-597 local1 and an identical local1 repeat. The toy retains
600 seconds, 6 GiB RSS, 300,000 nodes and 1,500,000 tetrahedra. Each sentinel
retains 1,200 seconds, 120 GiB RSS, 3,000,000 nodes and 20,000,000 tetrahedra.
Stop at the first failed worker, retain every receipt and log, and never retry
with larger limits. All computation remains inside verified SLURM allocation.

## Predeclared quality observations

The installed pinned Gmsh 4.15.2 API documentation for
`model.mesh.getElementQualities` identifies `minSICN` as the sampled minimum
signed inverted condition number and `minDetJac` as the minimum Jacobian
determinant. Collect both on native first-order tetrahedra before Gmsh finalizes,
using unique element tags. Native geometry coordinates are millimetres, so
the determinant is reported in cubic millimetres; the signed condition metric
is dimensionless. This is source/API inspection, not a numerical test result.

For dielectric, primary and secondary elements separately, retain counts,
finite/nonpositive counts, quantiles at probabilities 0, .01, .05, .5, .95,
.99 and 1 using NumPy's linear method, and signed-condition counts below .01,
.05 and .1. These histogram thresholds are observations, not accuracy gates.
Require every element's two metrics to be finite and strictly positive, and
the signed-condition metric not to exceed one beyond a 1e-12 allowance.
Reject missing regions, other element types, duplicate tags or mismatched
quality/mesh region counts. Bad numeric observations remain serializable in
the raw diagnostic rather than silently disappearing.

The quality fingerprint sorts unique native tags and hashes labelled
dtype/shape headers and exact arrays for tags (`<i8`), regions (`|i1`) and the
two quality metrics (`<f8`). A fresh repeat must match that fingerprint and
summary, the inherited ordered mesh fingerprint, counts and policy hash.
Native quality inspection, extraction, mesh hashing and source checks count
toward the worker/parent budget; stage timing is not advertised as pure meshing
latency. A complete nonrepeatable observation set is retained as negative.

## Interpretation boundary

`diagnostic_passed` means complete bounded, positive-element, repeatable mesh
observations only. `mesh_feasible`, `numerical_quality_qualified`,
`field_solver_executed`, `reference_qualified`, `training_may_start` and
`claim_eligible` remain false even then. Positive near-degenerate elements can
still be poor numerical elements; no conditioning or discretization-accuracy
guarantee follows. Field use requires separate algebraic, charge/energy and
sensitivity qualification, not a post-hoc relaxation of quality requirements.

The [runbook](../operations/TCAD-HXT-Optimization-Isolation.md) owns execution;
the [evidence record](../evidence/TCAD-HXT-Optimization-Isolation.md) owns results.
