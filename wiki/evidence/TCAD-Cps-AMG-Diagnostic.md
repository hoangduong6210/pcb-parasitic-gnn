---
title: TCAD AMG Diagnostic Evidence
status: VALIDATED; terminal diagnostic archived; no reference qualification
last_updated: 2026-10-03
paper_source: false
---

# TCAD AMG Diagnostic Evidence

## Terminal collection on 2026-10-03

The owner approved the next bounded implementation. The diagnostic's nine
terminal artifacts and scheduler logs are now copied byte-for-byte into the
main checkout. The [archive manifest](../../results/tcad/cps_amg_diagnostic_v1/archive/job_7647850/manifest.json)
has SHA-256 `0b6df0554a8ca2f76110af66518175209cf978630622408f29928970ff055a4e`.
Metadata/raw-log reconstruction, exact coverage, runtime/source identities and
successful terminal accounting were checked without numerical replay.
The new [seven-arm study](TCAD-Cps-AMG-Feasibility.md) uses fresh processes;
this diagnostic result is not substituted for an arm or promoted to a reference.
Earlier archive-pending observations below are historical.

## Terminal inspection on 2026-10-02

Read-only inspection at 2026-10-03 03:38 UTC found job `7647850` completed
`0:0`, zero restarts, in 406 seconds on `a0102`: 41 allocated CPUs, 160 GiB
requested, one scientific thread. Both required modes, toy and local0, passed.
The chain has no active job; RUNNING entries below are historical.

Local0 exactly reproduced the recorded system: 349,777 nodes, 1,903,228
tetrahedra, 18,629 free unknowns, 179,089 nonzeros and the frozen CSR-system
hash. Candidate operator complexity is 1.0860745216065755, below the unchanged
1.25 cap; the earlier default setup was rejected at 1.2752039488745819.
CG converged in 23 iterations with relative residual 6.980374190060632e-11.
Candidate/direct capacitance values are 114.99930105451428 and
114.99930105451433 pF, respectively, with relative difference
4.942936030007863e-16 and relative solution-vector L2 difference
6.504374695756848e-11. Direct relative residual is 3.600336942986729e-15.
The bounded parent observed 398.9546100180596 seconds and
3.171417236328125 GiB peak RSS for local0, within its unchanged worker caps.

The review checked successful terminal accounting, exact two-mode coverage,
source/geometry/matrix identities, per-mode receipt equality, raw-log hashes,
saved RESULT reconstruction and scalar acceptance gates. Frozen source locks
and execution worktree remain unchanged. Only metadata and logs were inspected;
no mesh, solve or numerical replay ran on login.

Artifacts remain in `.internal/tcad-cps-amg-diagnostic-v1/`, under
`results/tcad/cps_amg_diagnostic_v1/job_7647850/`, pending tracked collection.
Receipt SHA-256 values:

- `attempt.json`: `09c711ed345a51b7b54a3d5cd48e1fc0bfc746c6662d2dde00cb785da3141275`.
- `toy.json`: `7e3bb8d3136a942304ca5f509f9fbbbe7017ae171e51ac0e91f85f4ba51185c0`.
- `local0.json`: `d7147ab647908e9a0a7d4ec9b4e3342a0764e12c9435d6b538d6bc41b89f8a01`.

This removes the observed AMG setup obstacle on this local0 matrix without
widening its cap. It does not establish finer-level feasibility, mesh accuracy,
repeatability, padding, far-field or support sensitivity. Reference qualification,
claim eligibility, training and automatic feasibility expansion remain false.
The earlier rejected studies are unchanged.

Next proposed implementation: collect terminal evidence, then freeze a new
single-sentinel protocol using this candidate and all seven fresh feasibility
arms. No such job was submitted in this status review. Wiki changes are local
and uncommitted; no code, cap, paper, commit or push was changed. Remote `main`
was rechecked at `6a393612588a2c70e513a6f027e596ba7e5adc39`, which publishes
the earlier submission receipts, not this later terminal observation.

## Preparation on 2026-10-02

The owner requested continuation after the status inspection. The rejected
support study's ten terminal artifacts/logs are now copied byte-for-byte and
checked; the [support evidence](TCAD-Cps-Support-Recovery.md) owns the failure
and archive hash. No cap, old source or existing paper changed.

The [new method](../methods/TCAD-Cps-AMG-Diagnostic.md) fixes one unsmoothed
prolongation candidate and a toy-then-local0 same-matrix comparison. Preparation
is local at this checkpoint; no diagnostic job has been submitted. Last
verified remote `main` is `f62607eb442a7ccc51ae81f5ca03407f1e8d7fe0`.
The [runbook](../operations/TCAD-Cps-AMG-Diagnostic.md) requires validation,
source freeze and verified publication before execution. No new numerical
result, qualified reference, training permission or paper claim exists.

## Pre-execution validation

The additive implementation passed all 148 focused diagnostic, recovery,
original-pilot, wiki, prose, reproducibility and journal tests. This suite runs
no mesh or solve: it uses frozen metadata, syntax-tree assembly comparison and
fake numerical APIs. It checks rejection of login/array/wrong-resource execution,
cap overflow before CG, timeout/RSS process-group termination, failed-toy stop,
matrix/source mismatch and the absence of claim or expansion permission.
The deterministic prose audit, shell syntax and terminal-archive reconstruction
checks passed. Original and recovery source locks still verify unchanged.

The new source lock SHA-256 is
`7ff24ed07bc4233318a5ec9ebef8a3b552c75b37f13ca607966ec2690ecfbec3`.
It includes both earlier source closures, the rejected terminal archive and
the diagnostic protocol/code/tests. Source validation is not a numerical pass.
Next: verified source publication, then the single bounded SLURM job.

## Verified execution-source publication

Source, rejected-support archive, protocol/lock and wiki were published as
`396e51f879ae8007de35d3301be284a519aabf48`. A remote branch query confirmed
that exact `main` hash after the push. The repository manifest passed for
6,882 tracked files other than itself; precommit validation passed 81
diagnostic/wiki/prose tests and the deterministic prose audit. The execution
worktree is detached at this commit. This later publication receipt does not
change its source. No diagnostic numerical outcome is available yet.

## Bounded SLURM submission

The clean detached worktree passed the source-lock and 6,882-file manifest
checks before job `7647850` was submitted. The
[submission receipt](../../results/tcad/cps_amg_diagnostic_v1/submissions/job_7647850.json)
pins its source, lock, protocol, wrapper and resource request. Initial accounting
observed RUNNING on `a0102`, zero restarts, with 41 allocated CPUs for the
160 GiB request. Scientific threads remain one; the job has a 45-minute cap.

At the 2026-10-03 02:39 UTC observation, the fresh toy worker had passed and
local0 was generating its mesh. The toy's system hash matches the earlier
compact-support matrix exactly. Its candidate operator complexity is
1.0536193029490617, with 15 CG iterations and relative residual
4.4940130640994257e-11. Candidate/direct capacitance values are
1.1590918982639615 and 1.1590918982639618 pF; relative solution-vector L2
difference is 2.225369760146916e-11. These are provisional per-worker backend
checks in an ongoing job, not terminal admission or mesh accuracy evidence.
The raw toy receipt is under the execution worktree's
`results/tcad/cps_amg_diagnostic_v1/job_7647850/toy.json`.

No local0 result exists at this observation. Mutable job artifacts remain in
the frozen worktree until terminal collection. Next: inspect terminal state,
exact two-mode coverage, raw logs and the local0 same-matrix comparison.
No retry, full feasibility chain, training or paper export was submitted.
The submission/wiki receipt is a subsequent update; execution stays pinned
to the verified source commit above.

A follow-up scheduler check at 2 minutes 36 seconds elapsed still showed
RUNNING on `a0102`, with the toy passed and no local0 result or recorded failure.
The submission/wiki update passed 81 diagnostic/wiki/prose tests, the prose
audit and the regenerated 6,883-file repository manifest check. These checks
do not finalize the running numerical job.
