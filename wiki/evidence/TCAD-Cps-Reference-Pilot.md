---
title: TCAD Capacitance Reference Pilot Evidence
status: RUNNING; smoke failed closed; serialization recovery validated locally
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
The execution source was published as
`19523eb7d860cd3264cde56e4a6a3b39eaac4d8f`; `git ls-remote` confirmed that
exact remote `main` hash after the push. A clean detached execution worktree
was prepared at that commit and independently passed the lock and repository
manifest checks before submission.

## SLURM smoke submission on 2026-10-02

Submitted smoke job `7640925` from the clean execution worktree at
`19523eb7d860cd3264cde56e4a6a3b39eaac4d8f`. Its initial scheduler receipt was
`PENDING`, zero restarts, with the frozen 8 GiB request. No pilot or finalizer
had been submitted at that observation. The smoke must pass both same-matrix
backend checking and terminal accounting before pilot submission.

## Rejected smoke and serialization recovery on 2026-10-02

Job `7640925` finished `FAILED/2:0`, zero restarts, after nine seconds on
`a0102`. SLURM allocated three CPUs for the 8 GiB request; all scientific
threads remained one. The allocation/source guards passed and meshing ran on
the compute node. Stage logging then raised `TypeError` because scikit-fem's
`basis.N` was a NumPy `int32`, which the JSON encoder did not accept. This
occurred before matrix assembly and yielded no capacitance result. No pilot
or finalizer was launched. It is an implementation failure, not a negative
physical or mesh-sensitivity result.

The [retained attempt](../../results/tcad/cps_reference_v1/smoke/job_7640925/)
includes raw worker logs, arm/attempt receipts, scheduler logs and terminal
observation. The attempt SHA-256 is
`56f2644f73c276e5be453c5f61999e0ac654cd8f950d3aa9d7a54932a64018d3`.
The original execution worktree and commit remain unchanged.

The recovery converts numeric scalar telemetry to native JSON values while
still rejecting nonfinite values and unsupported types. A new scalar-only
regression test covers NumPy int32, int64, float32 and NaN. All 102 focused
tests and the prose audit pass. Only worker serialization and its tests change
within the execution closure: protocol, geometry panel, physics, mesh sizes,
tolerances and resource caps are unchanged. The new source lock SHA-256 is
`31f1aeb3dad2384f0f982b105722406f914f2a1b027230c074b5860b077fc510`.
This is a separately published software-recovery attempt, not requeue or an
automatic retry with wider limits. Its source publication and smoke submission
are the next actions; the pilot remains gated.

## Publication and internal-file boundary

The owner instructed that local agent guidance is internal. It is kept locally,
removed from Git tracking going forward, and ignored; prior Git history is not
rewritten. This change does not remove the public scientific-method or SLURM
rules documented in the wiki. The repository manifest follows tracked files
and must therefore drop the internal file as well.

The environment's default GitHub identity lacked push permission and returned
HTTP 403. The owner's authorized authentication completed the push without
changing global credentials or writing a credential into the repository.
The published commit removes the internal guidance file from tracking while
retaining its local copy. Historical commits and release tags remain intact.
This receipt is a subsequent documentation change, separate from the immutable
execution commit. No numerical outcome, qualified reference, learning result
or new claim is available.
