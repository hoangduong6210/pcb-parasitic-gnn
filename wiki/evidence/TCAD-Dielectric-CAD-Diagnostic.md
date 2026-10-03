---
title: TCAD Dielectric-Domain CAD Diagnostic Evidence
status: VALIDATED; terminal CAD diagnostic archive checked; no mesh or field
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric-Domain CAD Diagnostic Evidence

## Native execution and terminal archive on 2026-10-03

The clean sparse execution checkout passed all 223 source dependencies and the
pinned runtime check before [submission](../../results/tcad/cps_dielectric_cad_v1/submission.json)
at 08:27:20 UTC. Job `7651941` was observed RUNNING on `a0102`, zero restarts,
with 3 allocated CPUs for 8 GiB and one scientific thread. At 08:30:25 UTC,
accounting confirmed terminal `COMPLETED/0:0`, zero restarts and 51 elapsed
seconds; it was absent from the queue. All three modes passed. No job in this
diagnostic chain remains active.

| Mode | Parent worker time (s) | Worker-reported time (s) | Parent peak RSS (GiB) |
|---|---:|---:|---:|
| Toy | 11.015648934058845 | 7.338474743999541 | 0.05782318115234375 |
| Local1 | 10.515120377996936 | 6.91840859898366 | 0.06476974487304688 |
| Fresh local1 repeat | 10.514962820103392 | 6.777764320839196 | 0.06476974487304688 |

These times include guarding, metadata and validation work; they are not pure
CAD-kernel latency, mesh latency or field-extraction speedups. Mode and scheduler
stderr are empty. Native execution occurred only in the verified allocation.

Toy retains one dielectric volume with 18 faces, 36 curves and 24 points after
removing two conductor volumes. Local1 and its fresh repeat each retain one
dielectric volume with 162 faces, 324 curves and 216 points after removing
26 conductor volumes. The local1 boundary classification contains 72 primary,
84 secondary and six outer faces; no internal dielectric face is present.
Native bounding boxes, measures, types, incidence and ordered input
correspondence are retained. This is complete metadata for the declared CAD
checks, not an exported BREP or independent geometric-kernel proof. Later
meshing must reconstruct the canonical inputs with source-bound code and
recheck the CAD report before generating tetrahedra.

- Toy CAD-report SHA-256: `ffbf35380c0d76c808a49d79309b8830e34091e887b7f59c33c56045ce7e33ad`.
- Both local1 CAD-report SHA-256: `185994c79376c221d5d4dfc3cbc893988669eafe8cad9f2223f3f89c78d76dc7`.
- Attempt SHA-256: `f4cd0660eee269ad5f0732804a8490649ce26b2c1dec84d51ba0955db337e86b`.
- [Archive manifest](../../results/tcad/cps_dielectric_cad_v1/archive/job_7651941/manifest.json)
  SHA-256: `31704965e6b2b725ae5f8abc40dd4c30481f79874024aa1873bbd68c327122e0`.

The additive collector passed 25 synthetic tests before collecting this exact
14-member terminal closure. It reused the frozen receipt/source validator,
matched raw accounting and verified byte-exact copies; no native operation was
replayed on login. Completion, CAD diagnostic and repeatability flags are true;
mesh generation, mesh feasibility, field execution, reference, training and
claim flags remain false. At 08:42:31 UTC the complete archive checkpoint was
published and remote-hash verified as
`1deeb1a8dda0a69b5e4ffc6b566750a39dfc7a9a`. All 14 archive members are tracked
and the 7,036-file repository manifest passed. Execution source remains the
separately frozen commit recorded below.

The subsequent regression passed all 468 tests with no skips, including
26 collector/archive cases and exact native report/accounting assertions.
The predecessor source locks and rejected archives passed unchanged. Prose
audit and staged diff checks also passed; raw native logs were not reformatted.

This validates the declared CAD contract only for the toy and selected sentinel,
not arbitrary layouts, a tetrahedral discretization or physical accuracy. Next:
separate boundary-aware mesh implementation and a frozen mesh-only protocol.
It must bind the validated CAD reports, preserve terminal tags and verify every
tetrahedral boundary triangle. The old dielectric sliver observation remains
relevant; no quality threshold or old failed source is relaxed.

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

Source commit `c741fd7b813356b369c0b955705b4740f5805b71` was published and
remote-hash verified. The 7,019-file main manifest and subsequent 55-test
wiki/prose recheck passed. A fresh sparse worktree initially had only its index
populated, so the first metadata validator could not open its script. Inspection
confirmed exactly 226 non-skip entries and 6,794 excluded entries. The selected
files were then materialized with non-overwriting `checkout-index --all`;
no source, evidence or user file was deleted, and no job had been submitted.
