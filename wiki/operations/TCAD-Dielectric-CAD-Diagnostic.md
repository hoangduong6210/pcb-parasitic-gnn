---
title: TCAD Dielectric-Domain CAD Diagnostic Runbook
status: VALIDATED; terminal CAD archive checked; no retry
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric-Domain CAD Diagnostic Runbook

The CAD-only job has completed and its terminal archive is checked. The
evidence page owns exact accounting and report hashes; the sequence below
preserves the completed execution, not a resubmission instruction.
`code/experiments/proofs/archive_tcad_cps_dielectric_cad_v1.py` provides
`--source-root` for one-time terminal collection and `--check` for metadata-only
verification. It rejects overwrite, symlinks, incomplete membership, changed
bytes, source/submission mismatch and nonterminal/restarted accounting. Before
publication, check every archive member is Git-tracked; force-add only the
exact ignored scheduler `.out` file, never internal agent instructions.

The [CAD protocol](../../protocols/tcad_cps_dielectric_cad_v1.json) checks the
domain-construction prerequisite of the
[dielectric-only formulation](../methods/TCAD-Dielectric-Only-Formulation.md).
There is deliberately no meshing or field solving. CAD construction is still
compute work and must never run on login, including a toy or smoke check.

1. Run fake-native, metadata, prior-source/archive and wiki/prose tests. Freeze
   using `code/experiments/proofs/tcad_cps_dielectric_cad.py --freeze-lock`;
   it must refuse replacing an existing lock. Rerun exact dependency checks.
2. Publish and remotely verify the clean source commit. Use a sparse detached
   execution worktree containing the complete source-lock membership, its lock,
   `.gitignore` and `MANIFEST.json`; do not create a full quota-heavy clone.
   After a no-checkout worktree add, populate its index and set the exact
   sparse patterns. Inspect `git ls-files -t` before `git checkout-index --all`
   materializes only the non-skip-worktree entries; do not use overwrite or
   ignore-skip-worktree flags. An index alone is not a populated checkout.
   Validate the full manifest in main and materialized locked closure in the
   execution checkout. Internal agent instructions stay untracked.
3. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT`,
   `PCB_TCAD_LOCK_SHA256` and `PCB_GNN_PYTHON=/usr/bin/python3`. Unset GitHub
   credentials. Submit `code/jobs/submit_tcad_cps_dielectric_cad.sh` once from
   that checkout after creating its log directory. The builder, worker and
   parent all enforce the actual compute-node allocation before native work.
4. One node/task, account `pgs0407`, partition `nextgen`, one requested CPU,
   8 GiB and 15 minutes, no requeue/array/retry. Scientific threads remain one
   even if memory policy allocates more CPUs. Toy, largest-sentinel local1 and
   its fresh repeat are sequential; each worker is capped at 180 seconds and
   6 GiB RSS. Total worker ceiling is 540 seconds, not measured runtime.
5. Stop at the first failed mode. Preserve mode receipts and raw stdout/stderr,
   including partial stages. Do not switch construction method, tolerances,
   geometry or caps after seeing the result. Full reports bind canonical input,
   fragment provenance, options, before/after entity geometry and incidence,
   plus removed entities. Fresh-repeat admission requires exact report hashes.
6. After terminal accounting, call metadata-only `terminal_review` in
   `run_tcad_cps_dielectric_cad.py`. Exact complete coverage requires
   `COMPLETED/0:0`; controlled incomplete coverage requires `FAILED/2:0`,
   both with zero restarts. Infrastructure exceptions need an incident record.
   Preserve byte-exact reports/logs, source identity and raw accounting before
   any next study. No overwrite or untracked archive member is acceptable.

The [evidence page](../evidence/TCAD-Dielectric-CAD-Diagnostic.md) owns actual
source and scheduler receipts. A CAD pass checks only the declared construction
and retention contract. It does not authorize a field solve, training or paper
claim. A later mesh diagnostic must separately pin its boundary-triangle,
quality, resource and repeatability gates before execution.
