---
title: TCAD Compact-Support Recovery Runbook
status: REJECTED; execution closed; runbook retained for provenance
last_updated: 2026-10-02
paper_source: false
---

# TCAD Compact-Support Recovery Runbook

Both submitted jobs are terminal and the study is incomplete at its AMG cap.
Do not resubmit this frozen chain or increase its limits. The
[evidence page](../evidence/TCAD-Cps-Support-Recovery.md) records the archive;
the separately versioned [AMG diagnostic](TCAD-Cps-AMG-Diagnostic.md) is the
next bounded step.

Follow the [method](../methods/TCAD-Cps-Compact-Support-Recovery.md) and record
outcomes in [recovery evidence](../evidence/TCAD-Cps-Support-Recovery.md).
The original protocol, code, locks and execution worktree remain unchanged.
All meshing, solving, smoke tests and numerical finalization are SLURM-only.

## Freeze and submission

1. Archive the original terminal pilot with
   `code/experiments/proofs/archive_tcad_cps_pilot_v1.py`; its `--check` mode
   reconstructs only metadata and geometry descriptors, never a solver result.
   Preserve the archive manifest, diagnostics, failed task and finalizer.
2. Run the no-solver tests and wiki/prose checks. Freeze the additive source
   and input closure using
   `code/experiments/proofs/tcad_cps_support_recovery.py --freeze-lock`.
   The lock includes the original source lock, archived bytes and the new
   effective-protocol hash. It refuses to overwrite an existing recovery lock.
3. Commit and publish the source, archive and wiki. Verify the remote branch
   hash. Create a new clean detached worktree at that exact commit inside the
   authorized workspace; do not modify old execution worktrees.
4. Export the new worktree, commit and lock through `PCB_TCAD_EXECUTION_ROOT`,
   `PCB_TCAD_SOURCE_COMMIT` and `PCB_TCAD_LOCK_SHA256`. Quote paths, unset
   authentication tokens, and submit from the worktree with its `logs/` present.

| Phase | Wrapper under code/jobs/ | Requested allocation |
|---|---|---|
| Smoke | submit_tcad_cps_support_smoke.sh | 1 CPU, 8 GiB, 15 min |
| Single-sentinel feasibility | submit_tcad_cps_support_feasibility.sh | 1 CPU, 160 GiB, 3 h |
| Finalizer | submit_tcad_cps_support_finalize.sh | 1 CPU, 8 GiB, 15 min |

All use `pgs0407` / `nextgen`, one node and task, no requeue, and one
scientific thread. Allocated CPUs may exceed the request because of memory
policy. There is no array in this recovery. Keep the original worker caps:
1,200 seconds, 120 GiB RSS, 3,000,000 nodes, 20,000,000 tetrahedra and AMG
operator complexity 1.25. Seven arms yield at most 8,400 worker seconds
inside the three-hour scheduler envelope. These are ceilings, not forecasts.

Submit feasibility only after the new smoke's raw-log checks and terminal
`COMPLETED/0:0`, zero restarts. Supply its ID as `PCB_TCAD_SMOKE_JOB_ID`.
Supply the feasibility job ID to the finalizer as `PCB_TCAD_FEASIBILITY_JOB_ID`
and use `--dependency=afterany:JOB_ID`. This retains failure outcomes rather
than leaving the finalizer dependent on success. No further study is submitted
automatically after finalization.

## Evidence and safety

Parent and worker verify actual compute hostname and active allocation before
numerical imports. They also verify exact source, submitted wrapper, runtime,
archive and protocol hashes. Attempts are exclusive directories under
`results/tcad/cps_support_recovery_v1/`; symlinked output paths and overwrite
are rejected. Raw logs and incremental receipts remain after every failure.
Timeout or RSS overflow terminates the worker process group.

Finalization rechecks raw-log and prerequisite bindings, full seven-arm
coverage, geometry and terminal accounting before computing the scalar
diagnostics on a compute node. Failed attempts retain their receipt hash and
observed arm failures in the final summary. Terminal collection, wiki evidence
and scientific review must precede any decision about another pilot. The paper
remains an export from a later admitted wiki snapshot, not from job output.
