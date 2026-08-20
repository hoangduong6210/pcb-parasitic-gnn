# Corpus V4 accuracy evidence

This directory owns the geometry-valid, family-crossed GNN accuracy lifecycle.
It contains research evidence, not manuscript-package files. No current
accuracy value is admitted until the final `ARCHIVE_MANIFEST.json` passes its
tracked clean-clone check and the claim is entered in the wiki evidence ledger.

## Lifecycle

| Path | Producer | Scientific role |
|---|---|---|
| `plan/v1/evaluation_dataset.jsonl` | `plan_corpus_v4_accuracy.py` | Frozen 1,500-row R3 target table with R4 values kept evaluation-only |
| `plan/v1/task_manifest.jsonl` | planner | Canonical row-major 5 split by 5 initialization task grid |
| `plan/v1/plan.json` | planner | Input, planner-source, overlap, and derived-artifact hash closure |
| `jobs/job_<array>/task_<id>/` | SLURM training runner | Fixed-epoch checkpoint, validation smoke fixtures, learning curve, source and scheduler receipt; no test prediction |
| `resume/round_<n>/candidate_index.json` | resume planner | Exact inventory of every explicitly supplied attempt root |
| `resume/round_<n>/accepted_artifact_set.json` | resume planner | Hash-pinned checkpoints with terminal task accounting |
| `resume/round_<n>/pending_task_set.json` | resume planner | Strictly ordered retry allowlist |
| `final/job_<finalizer>/` | SLURM finalizer | First test/R4 inference, 25 prediction tables, matrices, indexes, and analysis manifest |
| `ARCHIVE_MANIFEST.json` | archive verifier | Finalizer completion receipt and clean-clone-verifiable closure |

The angle-bracket names describe the runtime layout; they are not literal
tracked placeholders.

## Gates

1. Generate the plan deterministically from the pinned protocol and upstream
   solver archive.
2. Build an execution lock only after source review and tests pass.
3. Submit all training and finalization through SLURM. Login nodes may run only
   validation, hashing, acceptance planning, and archive checks.
4. Accept a task only after its exact array component reports
   `COMPLETED`/`0:0`.
5. Freeze all 25 checkpoints before any held-out inference is emitted.
6. Create the archive manifest only after the finalizer reports
   `COMPLETED`/`0:0`; subsequent clones use verifier
   `--check --require-git-tracked` without live scheduler access.

Exact commands, variables, retry rules, and resource contracts are maintained
in the
[SLURM submission playbook](../../../wiki/operations/SLURM-Submission-Playbook.md#15-submit-the-corpus-v4-accuracy-grid).
Scientific interpretation is maintained in the
[Corpus V4 accuracy protocol](../../../wiki/methods/Corpus-V4-Accuracy-Protocol.md).
