---
title: TCAD Edge-Local Feasibility Evidence
status: PROPOSED
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Feasibility Evidence

## Preparation on 2026-10-03

The [new method](../methods/TCAD-Edge-Feasibility.md) tests an explicit finite
perimeter-distance policy after the archived Box sizing-budget diagnosis.
Original sources, rejected attempts, caps and tolerances remain untouched.
Initial integration passed 74 synthetic tests with one expected pre-lock skip.
Expanded pre-freeze regression passed 495 tests with one expected lock skip.
The fixed source/input lock passed **496 frozen tests, zero skips**, in 107.56
seconds. The prose audit passed. No actual layout probe, native mesh or
scientific job has run.

The parent protocol SHA-256 is
`34084a9ee2555c7c072152b9d178978fc0c7a321b7f6bc5fa3d45eb48cecd7b8`;
the parent terminal archive is
`da1c2edd357cf7fa85ddbf5fc37e962391d42bd421ef5bdd44e15da723c5c790`.
The new study retains the original worker limits and requested SLURM resources,
not the shorter diagnostic-only limits. Publication verification and one
sparse-worktree submission are next.

## Frozen identities

- Protocol SHA-256:
  `16472fe0dc5f6ca880df1e7766330b3a884276ae5c4d1fdce5ba61b4e5027cea`.
- Source/input lock SHA-256:
  `7427e553dba07e8e8ba565342b27a7e891ed6e04d0fc00ac0bbd126fb641af6c`.
- Locked dependencies: 454; earlier locks and archive members are unchanged.

No accuracy, feasibility, reference qualification or paper claim is admitted.
