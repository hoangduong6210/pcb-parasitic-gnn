# Corpus V4 accuracy evidence

This directory owns the geometry-valid, family-crossed GNN accuracy lifecycle.
It contains research evidence, not manuscript-package files. The tracked
`ARCHIVE_MANIFEST.json` has passed the clean-clone gate, and the scoped result is
admitted in the [current claim registry](../../../wiki/claims/Current-Claim-Language.md).

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

## Finalized closure

The closure contains 25 accepted safe-NPZ checkpoints, 25 held-out prediction
tables, complete 5 by 5 metric matrices, and the matched R3/R4 capacitance
view. Training remained checkpoint-only until the accepted set contained all
25 tasks. The finalizer then emitted 7,350 layout-model rows containing all
four target predictions; 975 of those rows belong to the matched capacitance
panels. No raw scheduler log is required for scientific replay because the
terminal receipts are frozen in the accepted set and archive manifest.

The paper-safe interpretation is in
[Corpus V4 Family-Held-Out Accuracy](../../../wiki/results/Corpus-V4-Accuracy.md).
Job identities, source and protocol roots, and file hashes are in
[E-C4-ACC-01](../../../wiki/evidence/Evidence-Ledger.md#e-c4-acc-01--finalized-family-crossed-accuracy).

## Clean-clone verification

Run this login-safe check from a clean repository root. It authenticates and
replays the stored evidence; it does not train a model or invoke a field solver.

```bash
python3 code/quality/verify_corpus_v4_accuracy_archive.py \
  --protocol protocols/corpus_v4_accuracy_v1.json \
  --expected-protocol-sha256 f707eb45e44042bc7231a4393caa1b998a283658ce2c3d4093e7c6c7a3eaf3bf \
  --plan results/corpus_v4/accuracy/plan/v1/plan.json \
  --expected-plan-sha256 e67509a6a742bb6a936287a79e9622f087a14ba08219a7c9521f05288b704206 \
  --task-manifest results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 2c7079fdd844d9e54a76d32a3bee6e623735303d7d59185ee97e3daf40000f20 \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v1.json \
  --expected-execution-lock-sha256 6b212fcbf1112c81c9f21d1f1511dcd5ac473b5492cd29c9bc7f5ecf6b173e61 \
  --expected-source-git-head f3074d2cb6082b6740452e9c8d0560d0d11eeb61 \
  --accepted-set results/corpus_v4/accuracy/resume/round_01/accepted_artifact_set.json \
  --expected-accepted-set-sha256 5e65fc0be6cbccc9fd30309a53a6ab03f52d39bb8a5e88b8c743fdb87b070235 \
  --analysis-manifest results/corpus_v4/accuracy/final/job_6905011/ANALYSIS_MANIFEST.json \
  --expected-analysis-manifest-sha256 a2764cac891b3630eaf927aaf024badbacba7ac3b65e82a544f329b341b1570f \
  --out results/corpus_v4/accuracy/ARCHIVE_MANIFEST.json \
  --check --require-git-tracked
```

Expected terminal line:

```text
Corpus V4 accuracy archive: PASS (29 analysis files)
```
