---
title: TCAD Dielectric-Domain CAD Diagnostic Evidence
status: PROPOSED; implementation tested with fake native API; no native execution
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric-Domain CAD Diagnostic Evidence

## Implementation checkpoint on 2026-10-03

The preceding terminal/formulation checkpoint and its publication receipt are
published. Remote main was rechecked at
`b1f8527e244786cb9f038d6f85763e00845fe669`; the worktree was clean before this
implementation. The previous goal turn made progress by preserving the failed
optimizer archive, adding topology checks and updating original-method review.
The full TCAD goal remains active and unachieved.

The separate [CAD diagnostic protocol](../../protocols/tcad_cps_dielectric_cad_v1.json)
now has a native builder, metadata replay, guarded worker, bounded parent and
SLURM wrapper. It constructs canonical per-trace boxes and an enclosing box,
uses native fragment correspondence, removes only metal volumes and proven
orphan subentities, then verifies the retained dielectric domain. This is the
geometry prerequisite in the [formulation contract](../methods/TCAD-Dielectric-Only-Formulation.md),
not another optimizer trial or a numerical reference.

Initial validation passed 57 tests with the source-lock test deferred until
freeze. Tests use constructed boundary metadata and a fake native API, including
an eight-piece conductor whose internal faces, edges and point must be removed
without losing exterior interfaces. No Gmsh geometry, mesh or field solver ran.
Expanded failure-injection and predecessor regression checks follow before
source freeze, publication and any native SLURM run.

All old protocols, source locks and rejected raw evidence remain unchanged.
No new job is submitted at this checkpoint. Even complete positive CAD results
will leave meshing, reference, training and claim flags false. Exact source,
lock, submission and terminal receipts will be recorded here when they exist.

## Source-supported mapping decision

Read-only inspection of the [official Gmsh 4.15.2 source archive](https://gmsh.info/src/gmsh-4.15.2-source.tgz)
found `src/geo/GModelIO_OCC.cpp` concatenating object then tool entities at
lines 4056–4059, and appending one correspondence entry per ordered input at
lines 4136–4166. The adapter therefore binds one outer-box object followed by
per-trace tools in canonical layout order. It checks exact input/map counts
and descendants against native entities, per-trace bounds and analytic volumes;
it does not infer material from a volume number or centroid.

Source was streamed for reading, not installed or compiled. The installed
Python API text was also read to check initialization, fragment and adjacency
arguments. Native initialization disables configuration-file loading and app
execution; the pinned CAD options are read back. These observations support
implementation choices but do not establish native geometry correctness.

## Pre-freeze validation

The expanded CAD suite passed 72 cases with the source-lock test still deferred.
It adds native option/input/map errors, lost interfaces, unsafe orphan removal,
changed retained geometry, existing-session protection, edge/vertex shorts,
parent watchdogs, complete/negative/incomplete receipts and closed claim flags.
The combined new CAD/topology/wiki/prose run passed 206 tests with that one
pre-freeze skip. An earlier broader predecessor regression passed 438 tests
before the last three CAD cases were added. Prose audit and wrapper syntax
checks passed. Full post-freeze regression remains required.

The quota check reports approximately 998,000 of 1,000,000 file slots used;
only a sparse execution checkout is planned. No scientific evidence or prior
worktree was removed. The [official option reference](https://gmsh.info/doc/texinfo/#Geometry-options)
also confirms the named OCC parallel/bounds and geometry-tolerance settings;
effective values must still be read back in the native job.

## Source freeze

The new lock closes 223 dependencies, including the unchanged predecessor
source, checked rejected archive, new CAD implementation and synthetic tests.

- Protocol SHA-256: `b365cc75f843b3a6461047393c4ae6e5db9fa102950b090f14267ed032e9d29e`.
- Lock SHA-256: `29484923fc973e1a670aac598a4826ad0e48f51fe89eb72e07f67a766c058792`.

This is a source freeze, not a CAD result. Post-freeze regression, verified
publication and sparse execution-source verification still precede submission.

The full post-freeze regression subsequently passed all 442 tests with no skips,
including the 73 CAD cases, unchanged source/archive checks and wiki/prose
contracts. Prose audit, wrapper syntax and documentation diff checks passed.
No real CAD operation was used to obtain these test results.
