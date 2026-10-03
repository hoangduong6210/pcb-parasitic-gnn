---
title: TCAD Edge-Local Feasibility v2 Evidence
status: PROPOSED; pre-execution integration checks
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Feasibility v2 Evidence

## Preparation on 2026-10-03

Local HEAD and GitHub main were reverified at
`4c4fa0a690e0404dc01e592f78edd9736eb4ec52`; no scientific job was active.
The [new integration](../methods/TCAD-Edge-Feasibility-v2.md) retains all
edge-v1 scientific/resource gates and uses the separately qualified adapter.
Its parent is the native API terminal archive, SHA-256
`b4d339befd6993abfd9a36316fb155cfe11afd90b5d4142230aab8e645eb17bd`.
The real-layout baseline protocol SHA-256 is
`16472fe0dc5f6ca880df1e7766330b3a884276ae5c4d1fdce5ba61b4e5027cea`.
Both earlier execution sources and terminal evidence remain unchanged.

Initial fake-native integration passed **79 tests with one expected pre-lock
skip** in 16.35 seconds. The fixture explicitly separates original CAD/empty
mesh, temporary model-backed point elements, and the generated planar packet.
Tests reject plugin, numeric, cleanup and original-state failures before mesh
generation, retain partial raw records, and reject rehashed metadata tampering.
Terminal tests forbid native imports, layout probe reconstruction and actual
mesh planning. These synthetic tests are not native qualification results.

Expanded regression, source freeze/publication and one bounded SLURM submission
are next. No v2 native attempt has run. The full TCAD goal remains active and
incomplete; no new paper claim is admitted or snapshot exported.

Expanded pre-freeze regression passed **563 tests with one expected lock skip**
in 149.55 seconds. A separate tightened protocol-type check passed 80 tests
with the same expected pre-lock skip. The prose audit and wrapper syntax check
passed. Five inspected completed fixture roots were removed without touching
scientific data or execution worktrees. Freeze and rerun the final source suite
before publication and the one SLURM attempt.

## Frozen source identities

- Protocol: `protocols/tcad_cps_edge_feasibility_v2.json`, SHA-256
  `5ce71ce4b556deedada58591051faf429117e70e74e052e3538fdf875ab1bed6`.
- Lock: `protocols/tcad_cps_edge_feasibility_v2.lock.json`, SHA-256
  `6dd9567573dff42854a79a9df16e8c65c97e899aa61fd2c8b365c5ad5fe12d41`.
- Source/input dependencies: 530, including the qualified adapter, unchanged
  real-layout baseline and complete parent terminal archive.

Final frozen regression passed **565 tests, zero skips**, in 160.27 seconds.
No actual layout probe or native mesh has run in v2; source publication remains
pending. Publish this frozen source, verify a fresh sparse worktree, then
submit the single bounded toy/sentinel/repeat attempt.
