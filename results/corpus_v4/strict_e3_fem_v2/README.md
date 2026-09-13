# FEM-v2 coordinate-update ablation

Status: design and model implementation; predictive training is disabled.

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
