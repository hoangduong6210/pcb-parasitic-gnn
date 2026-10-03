---
title: TCAD Capacitance Reference Pilot Runbook
status: REJECTED; pilot terminal with incomplete coverage; no active chain
last_updated: 2026-10-02
paper_source: false
---

# TCAD Capacitance Reference Pilot Runbook

The [method](../methods/TCAD-Cps-Reference-Qualification.md) owns scientific
choices. The [evidence record](../evidence/TCAD-Cps-Reference-Pilot.md) owns
source pins, scheduler receipts, failures and final outcomes. All meshing,
solver smoke tests, solving and numerical finalization are SLURM-only.

## Before submission

1. Generate the geometry-only panel with
   `code/experiments/proofs/plan_tcad_cps_reference.py`; `--check` reconstructs
   it without solving. Run the no-solver contract suite, wiki tests and prose
   audit. Freeze source/input bytes with
   `code/experiments/proofs/tcad_cps_reference.py --freeze-lock`.
2. Commit the protocol, panel, implementation, tests and wiki. Regenerate the
   tracked-file manifest. Verify the pushed remote branch hash.
3. Create a clean detached execution worktree at that exact commit inside the
   authorized project workspace. Do not edit it while jobs are active. Updates
   to the main checkout's wiki must not change execution source bytes.
4. Export `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT` and
   `PCB_TCAD_LOCK_SHA256` from the published source. Quote paths. Ensure the
   worktree's `logs/` exists and submit from that worktree. Credentials are not
   job inputs and must be unset before submission.

## Bounded chain

| Phase | Wrapper under code/jobs/ | Allocation | Dependency |
|---|---|---|---|
| Smoke | submit_tcad_cps_reference_smoke.sh | 1 requested CPU, 8 GiB, 15 min | None |
| Pilot | submit_tcad_cps_reference_pilot.sh | 1 requested CPU, 160 GiB, 3 h per task; array 0–2%1 | Terminal validated smoke |
| Finalize | submit_finalize_tcad_cps_reference.sh | 1 requested CPU, 8 GiB, 15 min | afterany of pilot array |

Use account `pgs0407` and partition `nextgen`; all wrappers disable requeue.
The pilot additionally receives `PCB_TCAD_SMOKE_JOB_ID`. Submit it only after
checking the smoke's `COMPLETED/0:0`, zero restarts and passed attempt record.
The finalizer receives that smoke ID and `PCB_TCAD_PILOT_ARRAY_ID` and uses
`--dependency=afterany:ARRAY_ID` so rejected attempts remain visible.
No automatic panel expansion, training or claim admission follows the chain.

The pilot has at most eighteen worker solves: six arms on each of three
sentinels. Each worker has a 1,200 s wall cap, 120 GiB RSS cap, three-million
node cap, twenty-million tetrahedron cap and AMG operator-complexity cap 1.25.
The requested scheduler ceiling is nine task-hours; at most six hours are
inside numerical workers before timeout. Neither is a runtime prediction.
Memory policy can allocate more CPUs than requested; all scientific libraries
and Gmsh remain at one thread. Record requested and allocated CPUs separately.

The smoke worker has a 600 s cap, 6 GiB RSS, 300,000 nodes and 1,500,000
tetrahedra, with the same operator-complexity ceiling. Even this small smoke
must not be invoked on a login node.

## Guards and retained evidence

Both parent and worker validate the live scheduler record, owner, account,
partition, resources, no-requeue state and actual hostname before numerical
imports. Spoofed SLURM variables alone cannot satisfy the compute-host check.
Execution also pins the clean Git commit, lock, exact submitted wrapper,
geometry registry, protocol and runtime package versions. The parent kills
the worker process group on timeout or sampled RSS overflow. Stage callbacks
check mesh sizes and AMG complexity before later stages proceed.

Each phase/task gets an exclusive directory under
`results/tcad/cps_reference_v1/`; existing attempts and symlinked output roots
are refused. Save raw worker stdout/stderr, per-arm hashes and incremental
attempt receipts. Scheduler logs also preserve failures that occur before an
attempt directory is created. Finalization checks terminal accounting, exact
three-task geometry coverage, raw-log hashes and result reconstruction before
reporting sensitivity. A complete negative sensitivity result is valid
evidence, not permission to widen thresholds. Failed execution remains failed.

After terminal execution, index every attempt in the wiki and preserve the
artifact closure before any scientific review. Paper text can use only a later
identified wiki snapshot with admitted claim language; this pilot is not
currently a paper source.
