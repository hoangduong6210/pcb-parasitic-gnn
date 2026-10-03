---
title: TCAD Dyadic Layer-Grid Planning Evidence
status: PROPOSED candidate; frozen source regression passed before execution
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dyadic Layer-Grid Planning Evidence

## Preparation on 2026-10-03

The preceding projected-support candidate remains rejected and preserved in
its [terminal archive](TCAD-Layer-Grid-Planning.md). Its archive SHA-256 is
`8b66fc27509b53f3f42e7da1b546926666b9da1a64b507a75384acab198b4d4c`.
The new [dyadic method](../methods/TCAD-Layer-Grid-Dyadic.md) separates mandatory
canonical faces from nonmandatory refinement bands, with a prospective width
budget and unchanged condition/capacity gates. No real-layout numerical plan
has yet been computed for this candidate.

Implementation includes a separate stdlib planner, guarded workers, bounded
runner, protocol/source lock and report metadata review. Tests use only tiny
explicit synthetic boxes. The first run passed 73 cases with one pre-freeze
skip and exposed an incorrect parent-level lookup in a cap-inheritance test;
that test was corrected before source freeze. No frozen scientific source or
evidence was changed. Full regression, freeze and verified publication precede
one bounded SLURM planning job. All mesh/field/reference/training/claim gates
remain closed, and the full TCAD goal is incomplete.

The corrected pre-freeze suite passed **129 tests, one expected lock skip**,
including 74 new planner/worker/metadata cases and 55 wiki/prose tests. The
guarded runner's watchdog and receipt control flow matches its frozen parent
by AST. Synthetic tests cover hand-counted cells, one-ULP canonical preservation,
noninserted auxiliary band edges, stricter width budgets, leaf targets and
metadata mutation rejection. Freeze and post-freeze regression follow.

## Source freeze

The immutable lock contains **347 dependencies**, including the preceding
source lock and terminal archive. Protocol SHA-256:
`508a31650285e6c45b568d0763984ad3a910e6080147f4d920e80a36e376d8f0`.
Lock SHA-256:
`4e9f7d0ab7e9a3cee1ac54f2a8f1f38776914d3f60745be06735db7c271b2ea9`.
Post-freeze regression is running before publication. Four completed tiny
synthetic-fixture directories were removed after inspection; they can be
regenerated from tests. No scientific files or execution worktrees were removed.

The frozen regression passed **338 tests, zero skips**, in 69.66 seconds.
Coverage includes new planning/metadata guards, the preceding planner/archive,
exact tiny-synthetic arithmetic, original allocation checks, bundle boundaries
and wiki/prose contracts. Real-layout numerical work did not run on login.
Verified source publication and one bounded SLURM study follow.
