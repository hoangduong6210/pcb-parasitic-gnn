---
title: TCAD Capacitance Reference Pilot Evidence
status: PROPOSED; implementation validation; no solve submitted
last_updated: 2026-10-02
paper_source: false
---

# TCAD Capacitance Reference Pilot Evidence

## Preparation on 2026-10-02

The owner approved the first stage of the TCAD continuation and reaffirmed
wiki-first scientific records and SLURM-only heavy execution. The
[method](../methods/TCAD-Cps-Reference-Qualification.md) and
[runbook](../operations/TCAD-Cps-Reference-Pilot.md) define the bounded pilot.
No historical solver, label, claim or released paper package was changed.

The geometry-only planner generated twelve development representatives and
three sentinels, in task order: `874`, `1369`, `597`. The selected artifact is
[`panel.json`](../../results/tcad/cps_reference_v1/plan/panel.json), SHA-256
`260127de27e670f4104e4a60e3d90444fefe0c6a435189c0d037fb1e0fc0d9dd`.
Selection uses no target values. The source corpus and protocol identities are
embedded in the panel and execution lock.

Read-only infrastructure checks found the Ascend SLURM controller available,
the `pgs0407` account associated, `nextgen` up, and no active jobs for the user.
The installed Python and numerical package versions match the proposed
runtime pins. No mesh or numerical solve was run on the login node.

Initial no-solver validation passed 23 tests; the lock test was intentionally
skipped before source freezing. After freezing, all 101 focused pilot, wiki,
reproducibility, prose and released-journal tests passed, as did the deterministic
prose audit and shell syntax checks. The repository manifest passed for 6,763
tracked files other than itself. Panel reconstruction passed. The lock SHA-256 is
`e3cf45b5de6f89c7d79e6d65ae34756f898e5e60fa5e1c5891f46c297de52d9f`.
Immutable source publication and scheduler receipts are pending.

## Publication and internal-file boundary

The owner instructed that local agent guidance is internal. It is kept locally,
removed from Git tracking going forward, and ignored; prior Git history is not
rewritten. This change does not remove the public scientific-method or SLURM
rules documented in the wiki. The repository manifest follows tracked files
and must therefore drop the internal file as well.

Last remotely verified branch before this implementation:
`e072b3a6485768ee50dccf9bf58423eefef6429e`. The new pilot source has not yet
been published at this preparation checkpoint. No numerical outcome, qualified
reference, learning result or new claim is available.
