---
title: TCAD Capacitance Reference Pilot Evidence
status: REJECTED; pilot coverage incomplete at the frozen mesh-node cap
last_updated: 2026-10-02
paper_source: false
---

# TCAD Capacitance Reference Pilot Evidence

## Terminal archive and separately versioned next step

Following the owner's request to implement the next step, the terminal pilot
and finalizer were archived byte-for-byte in the main checkout. The
[59-file manifest](../../results/tcad/cps_reference_v1/archive/pilot_7641200/manifest.json)
includes failed outcomes and terminal accounting. Archive reconstruction and
raw-log/result binding checks passed. The original source and worktree remain
unchanged; the original pilot is still rejected for incomplete coverage.
The [compact-support recovery](TCAD-Cps-Support-Recovery.md) is a separate,
single-sentinel feasibility study with unchanged resource caps, not a repair
or replacement of the original numerical results. Earlier statements that the
terminal archive was pending describe the preceding status inspection only.

## Terminal status inspection on 2026-10-02

Read-only observation at 2026-10-03 01:02 UTC (2026-10-02 in the project
timezone): the pilot and finalizer have left the queue. Terminal accounting
reports the following, all with zero restarts:

| Task | Layout | State / exit | Elapsed seconds | Completed arms |
|---|---:|---|---:|---|
| 7641200_0 | 874 | COMPLETED / 0:0 | 2906 | All six |
| 7641200_1 | 1369 | COMPLETED / 0:0 | 3951 | All six |
| 7641200_2 | 597 | FAILED / 2:0 | 1691 | local0 and local1 only |
| 7641201 | Finalizer | FAILED / 2:0 | 2 | Incomplete-coverage summary retained |

For layout 597, local2 generated 3,452,236 mesh nodes, above the frozen
3,000,000-node cap. The worker raised `frozen mesh_nodes_max exceeded` before
matrix assembly; it did not produce a local2 capacitance. Its logged peak RSS
was 11.932788848876953 GiB, below the 120 GiB worker cap. The parent recorded
1169.003894195892 seconds for that arm, below the 1,200-second timeout. The
observed stop is therefore the node cap, not an out-of-memory event, timeout or
recurrence of the earlier JSON serialization error. Repeat2, pad20 and far2
were not attempted for this layout, in accordance with the stop rule.

The finalizer wrote `complete=false`, `pilot_passed=false`, empty comparisons
and a task-2 terminal-coverage error. Its nonzero exit reflects the failed
coverage gate; no separate finalizer exception was logged. Successful execution
of the first two layouts is not acceptance of the three-layout sensitivity
study. No convergence claim, full-panel expansion, training or paper result is
enabled.

Artifacts remain in the unchanged execution worktree
`.internal/tcad-cps-reference-v1-jsonfix/`, under
`results/tcad/cps_reference_v1/`. The final summary at
`finalize/job_7641201/summary.json` has SHA-256
`659248d247f43011951166465e15213003d884e94a4b8eacd56692c2f8a0ffa1`;
task 2's `pilot/job_7641200/task_2/attempt.json` has SHA-256
`470e9cc3b04e1bba6529b235cf9452b88da90e2579c267b0a173032f9ff75701`.
The terminal pilot archive has not yet been copied into tracked main-branch
evidence. This status inspection only reads scheduler records, JSON and logs;
it does not rerun numerical finalization or launch a recovery job.

Next decision: review the mesh-size and runtime growth of the largest sentinel
before defining a separately versioned recovery. Preserve the rejected pilot;
do not silently raise caps, drop layout 597 or report two-layout statistics as
the planned three-layout result. The status wiki update is local and uncommitted;
remote `main` was rechecked at `163c6fce7e11a576bb9476948fb1349fa255e73c`.
The earlier entries below are historical observations, not current queue state.

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
automatic retry with wider limits. Recovery source
`d00426684f93155cc20924630facc63a94e72d32` was pushed and verified against the
remote `main` hash. A new detached worktree passed the lock and repository
manifest checks for 6,770 tracked files other than the manifest. Recovery smoke
`7641193` was submitted from that clean source. The pilot remains gated on
terminal smoke success and the backend-equivalence receipt.

## Validated smoke and pilot submission on 2026-10-02

Recovery smoke `7641193` completed `0:0`, zero restarts, in six seconds on
`a0102`, with three allocated CPUs and one scientific thread. Its
[attempt receipt](../../results/tcad/cps_reference_v1/smoke/job_7641193/attempt.json)
has SHA-256
`79814e9f1a771f9fc4887422cb4f90809373f25d87ed31556c08837235408fc6`.
Raw logs and terminal accounting are preserved beside it. The toy mesh had
2,159 nodes and 12,336 tetrahedra. AMG capacitance was 1.0304787645351507 pF;
direct capacitance was 1.0304787645351505 pF on the identical system. AMG
relative residual was 8.292661101095258e-11. All frozen smoke gates passed.
These values check implementation consistency only; they are neither physical
validation nor mesh-convergence evidence.

The read-only admission check reconstructed the saved result from its raw log,
verified source/lock bindings and terminal `COMPLETED/0:0` with zero restarts.
Only then was pilot array `7641200` submitted, tasks 0–2 at throttle one for
layouts `874`, `1369`, `597`. Finalizer `7641201` was submitted with dependency
`afterany:7641200`. Both use the unchanged published recovery source and lock.
The initial pilot observation was `PENDING (Priority)` and the finalizer was
`PENDING (Dependency)`. The
[submission receipt](../../results/tcad/cps_reference_v1/submissions/pilot_7641200.json)
pins the chain. No pilot sensitivity result is available at submission.

A subsequent read-only observation found task `7641200_0` RUNNING on `a0147`,
with 41 allocated CPUs for the 160 GiB request and one scientific thread.
Tasks 1–2 were `PENDING (JobArrayTaskLimit)` as required by throttle one;
finalizer `7641201` remained `PENDING (Dependency)`. The ongoing attempt is
not copied into the archive while mutable. The post-smoke receipt update passed
80 focused pilot/wiki/prose tests, the deterministic prose audit, and the
repository-manifest check for 6,778 tracked files other than itself.

Next: observe all three terminal task outcomes, retain every arm and failure,
inspect the finalizer's exact-coverage and sensitivity gates, and index the
result before considering panel expansion. No full-panel solve, GNN training,
new claim or paper export is authorized by smoke success or scheduler completion.

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
execution commit. The smoke implementation check is validated; no qualified
reference, learning result or new claim is available.

The validated smoke archive, submission receipt and wiki status were published
as `48baf0b380a7fc70974e0e984b4be08c09bc8b13`; `git ls-remote` confirmed that
exact remote `main` hash. This publication receipt is a later documentation
update. Active jobs remain pinned to `d00426684f93155cc20924630facc63a94e72d32`.
