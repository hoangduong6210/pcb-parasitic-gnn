---
title: TCAD HXT Explicit-Optimization Runbook
status: REJECTED; terminal archive checked; no retry
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Explicit-Optimization Runbook

The bounded job is terminal and its archive is checked; the evidence page
owns exact outcome and hashes. The sequence below preserves the completed
execution, not permission to retry. The additive metadata-only collector
`code/experiments/proofs/archive_tcad_cps_hxt_postopt_v1.py` supports
`--source-root` for terminal collection and `--check` for subsequent verification.
It refuses overwrite, symlinks, changed bytes, incomplete member closure,
source/submission mismatch or nonterminal/restarted accounting. Do not collect
from a running job. Preserve raw native stdout whitespace; force-add only exact
ignored scheduler `.out` members, never internal agent instructions. Every
archive member must be Git-tracked before publication.

This [diagnostic](../methods/TCAD-HXT-Explicit-Optimization.md) is separately
versioned. Preserve all prior sources and rejected archives. Tiny synthetic
tests and metadata checks are allowed on login; real meshing, optimization
and mesh quality computation require the verified compute-node allocation.

1. Validate `tests/test_tcad_cps_hxt_postopt.py`, previous source/archive
   regressions, wiki/prose contracts and wrapper syntax. Freeze with
   `code/experiments/proofs/tcad_cps_hxt_postopt.py --freeze-lock`; it refuses
   replacement. Rerun the source-closure check after freeze.
2. Publish and verify the exact source hash. Create a separate sparse detached
   execution worktree containing every lock member, its lock, `.gitignore` and
   `MANIFEST.json`. Materialize its index after the no-checkout worktree add.
   Check the full manifest in main, materialized source closure in the sparse
   checkout, and clean execution source before submission.
3. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT`,
   `PCB_TCAD_LOCK_SHA256`, and `PCB_GNN_PYTHON=/usr/bin/python3`. Unset GitHub
   credentials. Submit `code/jobs/submit_tcad_cps_hxt_postopt.sh` once after
   creating its log directory. The wrapper sets phase `hxt_postopt` and the
   executed-script identity, then the shared environment sets one thread.
4. One task/node, account `pgs0407`, partition `nextgen`, one requested CPU,
   160 GiB, 55 minutes, no requeue/array/retry. Extra memory-policy allocated
   CPUs do not change scientific threads. Per-worker limits remain unchanged.
5. Monitor only the submitted job. Keep the attempt receipt and raw mode and
   scheduler logs. On timeout, quality rejection or optimizer error, retain
   the outcome and do not retry with a different method or larger cap.
6. After terminal accounting, call metadata-only `terminal_review` from
   `run_tcad_cps_hxt_postopt.py`. Exact complete coverage requires
   `COMPLETED/0:0`; controlled incomplete coverage requires `FAILED/2:0`,
   both with zero restarts. Infrastructure exceptions require an incident
   record. Preserve all artifact members with hashes and terminal accounting;
   validate Git member closure before publishing an archive.

The [evidence page](../evidence/TCAD-HXT-Explicit-Optimization.md) owns source,
submission and terminal receipts. These instructions do not imply submission
or authorize a field solve, reference claim or training.
