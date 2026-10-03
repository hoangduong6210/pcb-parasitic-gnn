---
title: TCAD AMG Diagnostic Runbook
status: RUNNING; published source; single diagnostic job submitted
last_updated: 2026-10-02
paper_source: false
---

# TCAD AMG Diagnostic Runbook

Follow the [method](../methods/TCAD-Cps-AMG-Diagnostic.md); record every outcome
in [evidence](../evidence/TCAD-Cps-AMG-Diagnostic.md). Do not modify earlier
protocols, locks, source or execution worktrees.

1. Preserve the rejected support attempt with
   `code/experiments/proofs/archive_tcad_cps_support_v1.py`. Its `--check` mode
   verifies hashes, terminal accounting and log-derived metadata only.
2. Run no-solver tests and wiki/prose checks. Freeze the new closure with
   `code/experiments/proofs/tcad_cps_amg_diagnostic.py --freeze-lock`.
   This refuses to replace an existing lock.
3. Commit the new source and archive. Verify publication against remote `main`
   before creating a clean detached execution worktree at that exact commit.
4. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT` and
   `PCB_TCAD_LOCK_SHA256`; unset authentication tokens. Submit
   `code/jobs/submit_tcad_cps_amg_diagnostic.sh` from that worktree. Request one
   CPU, 160 GiB and 45 minutes on `pgs0407` / `nextgen`, no requeue. The scheduler
   may allocate additional CPUs for memory; numerical threads remain one.
5. The parent and workers check actual compute-node allocation, frozen source,
   executed wrapper and pinned runtime before numerical imports. Each mode has
   an exclusive raw-log pair and receipt; timeout/RSS overflow kills its process
   group. A failed toy blocks local0. No subsequent study is submitted.
6. After terminal accounting, inspect the retained exact two-mode coverage,
   source/system bindings, raw-log hashes and successful zero-restart `0:0`
   completion. Numerical comparison is performed within the compute job, never
   replayed on login. Archive terminal artifacts without overwrite and update
   the evidence page before any next-protocol decision.

An in-job positive receipt is not terminal admission. Failures remain evidence;
they are not rerun under changed limits. No paper export is part of this job.
