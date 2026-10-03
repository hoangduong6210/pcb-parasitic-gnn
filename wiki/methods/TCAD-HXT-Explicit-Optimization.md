---
title: TCAD HXT Explicit-Optimization Diagnostic
status: RUNNING; source frozen; diagnostic observations only
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Explicit-Optimization Diagnostic

This follows the [rejected unoptimized toy](../evidence/TCAD-HXT-Optimization-Isolation.md)
and the [source-based research decision](../manuscript/TCAD-Research-Plan.md).
It is a separate mesh-only study, not a retry or an accepted numerical reference.
The [protocol](../../protocols/tcad_cps_hxt_postopt_v1.json) retains HXT,
geometry, compact Box fields, mesh sizes, padding, seed, runtime and one thread.

## One explicit candidate

Keep `Mesh.Optimize=0`, explicitly set `Mesh.OptimizeNetgen=0`, and pin/read
back `Mesh.OptimizeThreshold=0.3`. After HXT generation call the default
`gmsh.model.mesh.optimize(method="", force=False, niter=1, dimTags=[])` exactly
once. No alternate optimizer, repeated call, fallback or expanded budget is
included. The API's `niter=1` is not an internal iteration/time guarantee for
this branch; the original parent watchdog still bounds the entire worker.

Further inspection of the [official Gmsh 4.15.2 source](https://gmsh.info/src/gmsh-4.15.2-source.tgz),
`src/mesh/meshGRegion.cpp` lines 278–291, found that the explicit region
optimizer dispatches with `QMTET_GAMMA`, and skips fully discrete, transfinite
or extruded regions under its stated conditions. It does not consult the
automatic `Mesh.Optimize` switch there. Our builder uses fragmented OCC boxes,
not those excluded mesh methods. Gamma-based optimization does not make the
0.3 setting a minimum signed-condition guarantee: the diagnostic separately
measures `minSICN` and `minDetJac` and applies the inherited strict-positive gate.

## Fresh extraction and before/after observations

The new builder copies the original geometry and region/extraction logic into
a separate source file. It checks actual SLURM allocation, locked source and
pinned runtime before numerical imports, including when invoked directly.
The old builder and every previous execution source remain unchanged.

Sequence: generate; record raw node count and quality; log optimizer start;
perform the single call; log optimizer finish; fetch fresh node tags and
coordinates; record post-optimization quality; extract current connectivity;
finalize Gmsh; construct and fingerprint the mesh. Optimizing in the old
builder's existing callback would retain stale coordinates, so it is not used.
Fake-API tests deliberately move a coordinate and change connectivity/node
count, verifying that the final fingerprint uses the new arrays.

Before and after, retain all three regions, element counts, finite/nonpositive
counts, signed-condition bins, linear quantiles, native-unit Jacobians and
canonical quality-array fingerprints under the unchanged parent schema.
Before optimization, negative/nonfinite metrics are diagnostic observations;
malformed arrays, missing regions and resource violations still stop the worker.
After optimization, every metric must be finite and strictly positive. Bind
post-optimization quality counts to the extracted mesh. Record the pre-gate
outcome explicitly; never relabel a failed raw mesh as passing.

Toy, local1 and a fresh identical local1 repeat run in separate processes.
Repeatability requires identical pre-quality, post-quality, raw node count,
final ordered mesh, effective policy and optimizer receipts. Summary/fingerprint
logging does not save complete native arrays for independent elementwise replay.
Preserve negative and incomplete observations, including optimizer exceptions.

## Resource and interpretation boundaries

Retain 600/1,200/1,200-second worker limits, 6/120/120 GiB RSS, toy caps of
300,000 nodes and 1,500,000 tetrahedra, and sentinel caps of 3,000,000 nodes and
20,000,000 tetrahedra. Generation, optimization, quality and extraction share
the same limits. Stop on the first failed mode; one 160 GiB/55-minute SLURM
allocation, no retry or array. No meshing or real quality-array work on login.

Even `diagnostic_passed=true` leaves `mesh_feasible`,
`numerical_quality_qualified`, `field_solver_executed`, `reference_qualified`,
`training_may_start` and `claim_eligible` false. Conditioning, field agreement,
charge/energy consistency and mesh/domain sensitivity require separate studies.
The [runbook](../operations/TCAD-HXT-Explicit-Optimization.md) owns execution;
the [evidence page](../evidence/TCAD-HXT-Explicit-Optimization.md) owns outcomes.
