# FEM-v2 coordinate-update ablation

Status: all 25 training tasks completed and 75 checkpoints are preserved in
`jobs/job_7318063/`. Recovery admission passed all 75 checkpoints at eight
threads under the original tolerance. Held-out finalization completed in
`recovery/v1/final/job_7326179/`; numerical and clean tracked archive replay
both passed. The scoped result is admitted as `C-E3-FEMV2-001`; the [result page](../../../wiki/results/Corpus-V4-FEM-v2-Coordinate-Ablation.md)
owns the scoped interpretation and links each table to machine evidence.

Initialized-model qualification job `7275182` completed `0:0` in 21 s from source
`9a1733ca4e64762f92578f4d158f71c9a8b41f13`. Its protocol SHA-256 is
`a7fc5cdf3ee08e0bc431060719659c2d156ff827265c59766f35253b3a711f64`.
All 15 seed/arm records passed the initialized-model checks. The
[qualification receipt](qualification/job_7275182/result.json) has SHA-256
`07cd5b4ba54b688c5aac25bb8d07a05b14a7a0d4f57ea1e6b9f1427881c005b3`.
This initialized-model qualification does not establish predictive accuracy.

The [design page](../../../wiki/methods/Corpus-V4-FEM-v2-Coordinate-Ablation.md)
defines three arms and distinguishes coordinate-update benefit from the
encoded-graph invariance shared by all arms. The draft design protocol is
`protocols/corpus_v4_strict_e3_fem_v2_design_v1.json`; it is not an execution lock.

The first executable stage is initialized-model qualification under
`protocols/strict_e3_model_qualification_v1.json`. It uses two artificial
graphs, five initialization seeds and 40 proper/improper orthogonal transforms
with translations per seed, shared across three arms. This is 600 transformed
arm evaluations, plus batched/separate comparisons. No fitting or corpus
access is part of this stage. Its outputs belong in `qualification/job_JOB/`.

Qualification of initialized synthetic behavior is not a predictive result or
proof that a trained model will pass every numerical symmetry check. Training
requires its own source lock, isolated namespace, checkpoint admission,
held-out finalizer and independent archive replay. Historical results remain
unchanged. The canonical [live status](../../../wiki/status/Live-Execution.md)
records submission identities and terminal outcomes.

The additive predictive protocol is
`protocols/corpus_v4_strict_e3_fem_v2_v1.json`. Its pipeline reuses the five
frozen family splits crossed with five initialization seeds. Each task trains
the `strict96`, `fixed96`, and `fixed_matched` arms sequentially and writes
three numeric, non-executable NPZ checkpoints. The sandbox exposes one
split-scoped train/validation table and the task's initially empty output
directory; test, R4, previous-model, other-split, and other-task artifacts are
absent.

The generated execution lock is
`protocols/corpus_v4_strict_e3_fem_v2_execution_lock_v1.json`, with SHA-256
`f8c776604220cc013243eeca9dc6fe16c0ec5455d86fcbb105f9eb19df839c20`.
It closes 26 source files and 58 input files. The lock was published and static
validation passed. Probe `7315639` passed before training array `7318063`
completed all 25 tasks. A complete run requires 25 task receipts,
75 trained-checkpoint symmetry receipts, terminal admission, held-out
finalization, numerical reconstruction, and a clean Git-tracked replay. The
machine summary keeps the previous GNN result contextual and does not turn
training wall times into an inference-runtime claim.

Admission `7318065` failed validation-metric replay at two scientific threads.
The preserved [diagnostic](diagnostics/job_7326041/result.json) reproduces
every stored task-zero metric exactly with eight threads, twice. Both
two-thread repeats fail 48 metric leaves under the original tolerance.
Recovery job `7326163` checked all 75 checkpoints at eight threads before
permitting held-out evaluation. Its [accepted set](recovery/v1/admission/job_7326163/accepted_artifact_set.json)
has SHA-256 `483169c013b19149f40cea118803b3700dd4c9d6799e84af769161459a6c7634`.
The checkpoint archive retains the original source, normalization, targets
and task identities. Checkpoint admission is separate from scientific claim
admission. Finalizer `7326179`, numerical replay `7326203`, and clean tracked
replay `7326296` all completed successfully. The
[tracked receipt](recovery/v1/verify/job_7326296/result.json) closes numerical
reconstruction and Git-tracked evidence checks. That receipt alone did not
grant scientific admission; the separate owner decision on 2026-09-15 admitted
only the scoped wording registered as `C-E3-FEMV2-001`.
