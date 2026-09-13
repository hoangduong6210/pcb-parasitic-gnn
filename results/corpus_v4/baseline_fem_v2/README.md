# FEM-v2 fixed baseline comparison

Status: protocol and execution lock frozen; scheduler preflight is next.
No baseline training or held-out comparison is admitted by this index.

The study reuses accuracy-v3's exact five split-scoped train/validation tables,
test partitions and admitted GNN predictions. Each of 25 split/initialization
cells fits Constant, Ridge, Random Forest and Extra Trees. Deterministic
controls repeated across initialization cells do not add independent seeds.
The 48-dimensional pooled features and log1p targets use training-only
normalization. No solver is invoked and no hyperparameter search is performed.

## Frozen artifacts

- Protocol: `protocols/corpus_v4_baseline_fem_v2_v1.json`, SHA-256
  `f7464ad2c0fc259491d84e5c3c064f1001a708523f4ba19e9303c36b79798802`.
- Execution lock: `protocols/corpus_v4_baseline_fem_v2_execution_lock_v1.json`,
  SHA-256 `1c76d1b84cdbb674dbc7b9b615e2625ba7c29d672fe29e6e841076bd0d23e243`.
- Input plan: `results/corpus_v4/accuracy_v3/plan/v1/`; unchanged upstream
  hashes and the GNN comparison archive are authenticated by the new lock.
- Pipeline: `code/experiments/proofs/corpus_v4_baseline_v1.py`.

## Artifact lifecycle

1. `probes/`: singleton filesystem checks, no model fitting.
2. `jobs/job_ARRAY/task_XX/`: task-private numeric model bundle and result.
3. `resume/`: exact 25-task terminal accepted set; all bundles validated first.
4. `final/job_JOB/`: held-out predictions, paired metrics and summary.
5. `ARCHIVE_MANIFEST.json`: independent numerical replay and terminal closure.

The complete paired analysis reports family-macro MAPE differences in
percentage points with crossed-axis descriptive sensitivity intervals, plus
nonpositive and passivity diagnostics. The GNN test results were known before
this extension was designed; it is not a new blinded benchmark. No causal
graph advantage, baseline inference speed or physical-board accuracy is
established merely by completing these jobs.

See the [protocol](../../../wiki/methods/Corpus-V4-FEM-v2-Baseline-Protocol.md),
[live status](../../../wiki/status/Live-Execution.md), and
[SLURM playbook](../../../wiki/operations/SLURM-Submission-Playbook.md).
