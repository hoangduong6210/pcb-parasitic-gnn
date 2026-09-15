# FEM-v2 coordinate-update ablation

Status: predictive source and execution inputs are hash-locked; static
validation and the no-fit sandbox probe are pending, so predictive training
remains disabled.

Initialized-model qualification job `7275182` completed `0:0` in 21 s from source
`9a1733ca4e64762f92578f4d158f71c9a8b41f13`. Its protocol SHA-256 is
`a7fc5cdf3ee08e0bc431060719659c2d156ff827265c59766f35253b3a711f64`.
All 15 seed/arm records passed the initialized-model checks. The
[qualification receipt](qualification/job_7275182/result.json) has SHA-256
`07cd5b4ba54b688c5aac25bb8d07a05b14a7a0d4f57ea1e6b9f1427881c005b3`.
Predictive training remains disabled; this result is not an accuracy claim.

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
It closes 26 source files and 58 input files. Training remains blocked until
that lock is committed, pushed, validated from its clean checkout, and followed
by a successful singleton no-fit SLURM probe. A complete run then requires 25 task receipts,
75 trained-checkpoint symmetry receipts, terminal admission, held-out
finalization, numerical reconstruction, and a clean Git-tracked replay. The
machine summary keeps the previous GNN result contextual and does not turn
training wall times into an inference-runtime claim.
