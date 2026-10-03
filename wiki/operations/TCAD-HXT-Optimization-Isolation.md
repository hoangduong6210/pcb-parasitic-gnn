---
title: TCAD HXT Optimization-Isolation Runbook
status: REJECTED; terminal archive checked; do not resubmit frozen attempt
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Optimization-Isolation Runbook

This attempt is closed after a toy quality-gate failure. The procedure below
is the preserved execution specification, not an instruction to resubmit it.
Use `code/experiments/proofs/archive_tcad_cps_hxt_isolation_v1.py --check` for
metadata-only archive verification. The collector reuses the frozen validator
in a credential-scrubbed child process and checks exact member closure, hashes,
source identity and zero-restart terminal accounting. It refuses overwrites.

Native stdout bytes, including trailing whitespace, are preserved unchanged.
When publishing, force-add only the exact ignored scheduler `.out` archive
member; never broaden that exception to internal files. Exclude only the raw
toy stdout from whitespace lint, and check all source and documentation diffs.
Verify that every manifest member is Git-tracked before publication. The
[evidence page](../evidence/TCAD-HXT-Optimization-Isolation.md) owns the receipt,
hashes and interpretation; no reference or training eligibility follows.

This is a new [mesh-only diagnostic](../methods/TCAD-HXT-Optimization-Isolation.md),
not a rerun of the failed optimized mesh. No field assembly, solve or training
is included. Meshing and quality-array calculations must remain on compute
nodes; only tiny synthetic tests and metadata/source checks run on login.

1. Validate new tests, previous source/archives, wiki and prose contracts and
   wrapper syntax. Freeze `protocols/tcad_cps_hxt_isolation_v1.lock.json` using
   `code/experiments/proofs/tcad_cps_hxt_isolation.py --freeze-lock`, which
   refuses replacement. Rerun the post-freeze source test.
2. Publish and verify the exact source commit. Use a new detached sparse
   checkout containing all lock members, the lock, `.gitignore` and
   `MANIFEST.json`; materialize its index after the no-checkout worktree add.
   Check the full manifest in main and only materialized source closure in the
   sparse checkout. Preserve all older worktrees and evidence.
3. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT`,
   `PCB_TCAD_LOCK_SHA256` and `PCB_GNN_PYTHON=/usr/bin/python3`. Verify the clean
   source and executed wrapper identity. Unset credentials, create the log
   directory and submit `code/jobs/submit_tcad_cps_hxt_isolation.sh`.
4. The single allocation uses account `pgs0407`, partition `nextgen`, one node,
   one task, one requested CPU, 160 GiB and 55 minutes; no requeue, array or
   retry. Scientific threads stay one if memory policy grants extra CPUs.
   Per-worker caps and the 3,000-second aggregate ceiling are unchanged.
5. Monitor that job only. A quality or resource failure stops subsequent modes.
   Preserve the attempt directory, mode JSON and raw stdout/stderr. Do not
   change running source or substitute another geometry or quality threshold.
6. After terminal accounting, invoke `terminal_review` from
   `run_tcad_cps_hxt_isolation.py` for scalar/hash/coverage review. Complete
   observations require `COMPLETED/0:0`; controlled incomplete outcomes require
   `FAILED/2:0`, both with zero restarts. Infrastructure exceptions need an
   explicit incident record. Collect all terminal evidence and verify every
   archive member is Git-tracked before publication.

Any `diagnostic_passed` observation still leaves field use, numerical-quality
qualification, reference qualification and training closed. The
[evidence page](../evidence/TCAD-HXT-Optimization-Isolation.md) owns actual
publication and scheduler receipts; this runbook is not itself a submission.
