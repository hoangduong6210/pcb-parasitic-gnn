# FEM-v2 fixed baseline comparison

Status: VALIDATED; all 25 checkpoints accepted and clean-tracked replay passed.
Scoped claim `C-BASE-FEMV2-001` was admitted by the project owner on 2026-09-13.

Preflight `7273416_0` completed `0:0` without fitting or opening held-out bytes.
Its [receipt](probes/job_7273416/task_00/probe.json) records the frozen source,
runtime and task-private filesystem checks. Training array `7273435` contains
25 completed tasks; terminal admission job `7273449` accepted the full array.
The [accepted set](resume/round_00/accepted_artifact_set.json) authenticates
every numeric model bundle and terminal task record. Held-out finalizer
`7273521` completed successfully. Its
[summary](final/job_7273521/summary.json),
[metrics](final/job_7273521/metrics.json), and
[predictions](final/job_7273521/predictions.jsonl) are preserved without edits.
Archive replay `7273643` passed exact reconstruction; its
[receipt](ARCHIVE_MANIFEST.json) authenticates the analysis closure. The
[result page](../../../wiki/results/Corpus-V4-FEM-v2-Baselines.md) records the
admitted wording and its limitations. Clean-tracked replay
`7273758` completed successfully at checkout `a6a6a18`; the machine receipt
continues to set `claim_eligible=false`, independently of editorial decisions.

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
