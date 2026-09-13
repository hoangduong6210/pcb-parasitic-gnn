# FEM-v2 coordinate-update ablation

Status: design and model implementation; predictive training is disabled.

Initialized-model qualification job `7275182` is submitted from source
`9a1733ca4e64762f92578f4d158f71c9a8b41f13`. Its protocol SHA-256 is
`a7fc5cdf3ee08e0bc431060719659c2d156ff827265c59766f35253b3a711f64`.
No passing numerical result is recorded yet.

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
