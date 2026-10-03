---
title: TCAD Mesh-Only HXT Probe Runbook
status: REJECTED; terminal closure checked; historical runbook retained
last_updated: 2026-10-03
paper_source: false
---

# TCAD Mesh-Only HXT Probe Runbook

The single frozen attempt is terminal and incomplete; the linked evidence
page owns its checked archive. The execution instructions below are retained
for reproducibility, not permission to rerun the failed attempt. Use the
collector's `--check` mode for current metadata-only validation.

This runbook executes only the [mesh-only method](../methods/TCAD-Cps-Mesh-Probe.md).
Meshing is heavy work and must run on a verified SLURM compute node, never on
login. Small contract tests, source hashes and scalar receipt reviews are not
numerical replay. No array, automatic retry or cap increase is enabled.

1. Run no-solver tests, wiki contracts, prose audit, wrapper syntax and the
   preceding terminal-archive check. Freeze the new lock with
   `code/experiments/proofs/tcad_cps_mesh_probe.py --freeze-lock`; it refuses
   to replace an existing lock. Rerun the frozen-source test.
2. Commit and publish source; verify the remote branch hash before submission.
   Preserve old worktrees and use a new detached sparse execution checkout to
   respect file-count quota. Materialize exactly the new lock's file closure,
   the lock itself, `.gitignore` and `MANIFEST.json`. Check the complete manifest
   in main; do not claim full-manifest verification of unmaterialized paths.
3. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT`,
   `PCB_TCAD_LOCK_SHA256` and `PCB_GNN_PYTHON=/usr/bin/python3`. Check the clean
   source and locked bytes. Unset credentials before submission. Create the
   log directory and submit `code/jobs/submit_tcad_cps_mesh_probe.sh`.
4. The allocation requests account `pgs0407`, partition `nextgen`, one node,
   one task, one CPU, 160 GiB and 55 minutes, with requeue disabled. Scientific
   threads stay one if memory policy allocates more CPUs. Three workers have
   a combined 3,000-second ceiling; each retains its preceding per-worker caps.
5. Monitor only this job. Retain the exclusive attempt directory, individual
   JSON receipts and raw logs, including incomplete observations. Stop at the
   first failed worker. Do not change frozen source or rerun the same attempt.
6. After terminal accounting, use `terminal_review` from
   `run_tcad_cps_mesh_probe.py` for metadata-only closure review. It checks
   source/runtime, exact file coverage, ordered worker prefix, raw-log hashes,
   results and scalar caps. Complete observations require `COMPLETED/0:0`;
   incomplete controlled outcomes require `FAILED/2:0`; both need zero restarts.
   Infrastructure failures outside these states need a separate explicit
   incident record, not automatic admission.
7. Collect the reviewed terminal closure without overwriting evidence and
   update the [evidence page](../evidence/TCAD-Cps-Mesh-Probe.md), live status
   and repository publication receipts. Mesh feasibility is not field accuracy,
   reference qualification, training permission or a paper claim.

The additive collector is
`code/experiments/proofs/archive_tcad_cps_mesh_probe_v1.py`. After terminal
accounting, pass `--source-root .internal/tcad-cps-mesh-probe-v1` from main;
use `--check` for subsequent metadata-only validation. It verifies the pinned
execution commit, lock, frozen receipt validator, terminal accounting and
submission identity before copying. No source-lock change or field computation
is part of collection. An infrastructure failure outside the controlled
terminal-state contract remains a separate incident, not a fabricated pass.

Before publication, verify that every manifest member and the archive manifest
are Git-tracked. The scheduler `.out` file matches an existing ignore pattern
and needs an explicit scoped add. Preserve native log trailing whitespace;
exclude only the two raw worker stdout paths from whitespace lint and verify
their immutable hashes instead. Never normalize raw evidence to satisfy lint.
