---
title: Corpus V4 Accuracy Protocol
status: frozen protocol; accuracy evidence pending
last_updated: 2026-08-19
paper_source: true
prose_reviewed: true
claim_ids: C-ACC-001
---

# Corpus V4 Accuracy Protocol

## Scientific question

The experiment measures how closely one fixed graph-surrogate architecture
reproduces the numerical targets in the geometry-valid synthetic corpus. It
does not measure fabricated-board accuracy. Capacitance agreement is reported
against FEM-R3P16 on the complete test partition and, separately, against both
FEM-R3P16 and FEM-R4P16 on the same selected 39-layout panel in each split.
FEM-R4P16 is a higher-resolution comparator rather than physical truth.

## Immutable data join

Every record is joined by the pair `(layout_id, geometry_sha256)`. Geometry is
read from the finalized 1,500-layout corpus. The three inductance targets are
read from the finalized FastHenry observations. The historical capacitance
column in that file is not admitted. The optimization capacitance target is the
1,500-layout FEM-R3P16 observation table. The 198 FEM-R4P16 values remain in a
separate evaluation-only mapping.

The loader rejects duplicate, missing, extra, nonpositive, hash-mismatched, or
family-inconsistent records. It consumes the frozen family and split
registries; it does not generate a random split.

## Crossed design

Five split seeds and five initialization seeds, numbered 40 through 44, form a
complete 5 by 5 grid. Task identity is row-major:

\[
k = 5i + j,
\]

where (i) indexes the split seed and (j) indexes the initialization seed.
Task 12, corresponding to split 42 and initialization 42, is designated for
later latency measurement before any accuracy result is observed.

Each split contains 46 training families, 7 validation families, and 13 test
families. The layout counts are:

| Split seed | Train | Validation | Test | Selected R4 test panel |
|---:|---:|---:|---:|---:|
| 40 | 1,039 | 170 | 291 | 39 |
| 41 | 1,066 | 152 | 282 | 39 |
| 42 | 1,012 | 182 | 306 | 39 |
| 43 | 1,076 | 125 | 299 | 39 |
| 44 | 1,055 | 153 | 292 | 39 |

The five selected R4 test views overlap. They contain 195 memberships but only
135 unique layouts from 45 unique families. Each 39-layout view is held out for
its own split; the complete 198-layout registry is not globally held out.

## Frozen model and optimization

The baseline is the four-layer message-passing network with hidden width 96 and
four graph-level outputs. Each cell uses AdamW, learning rate 0.002, weight
decay (10^{-5}), batch size 32, gradient clipping at 5, and a cosine schedule
over exactly 200 epochs. The loss is SmoothL1 on train-standardized log1p
targets.

Node, edge, and target statistics are fitted on the training partition only.
Validation loss is recorded as a diagnostic. It does not select an epoch,
checkpoint, hyperparameter, exclusion, or retry. Every cell uses its final
epoch. R4 values do not enter normalization, optimization, diagnostics,
checkpoint selection, hyperparameter selection, or any acceptance predicate.
The pinned loader validates all input bytes before training, but the training
stage emits no held-out prediction or metric.

## Reporting units

For target (t) and design (i), absolute percentage error is

\[
e_{i,t}=100\frac{|\widehat{y}_{i,t}-y_{i,t}|}{|y_{i,t}|}.
\]

The primary per-target summary is family-macro MAPE: first average within each
test family, then average across the 13 held-out families. Pooled median, mean,
and 95th-percentile APE, physical-unit MAE, signed bias, (R^2), and counts of
nonpositive or nonfinite predictions are also retained. Predictions are not
clipped before metrics. No single scalar is called overall physical accuracy.

Every metric retains its complete 5 by 5 matrix. A 10,000-draw row-and-column
resampling summary describes sensitivity to the evaluated seed grid. Its
reported 95% interval is descriptive, not a population confidence interval,
and it excludes cross-machine, retraining-protocol, fabrication, and arbitrary
PCB uncertainty.

## Artifact and execution gates

Each training cell is one SLURM array element. It writes a new job-scoped
directory atomically and cannot overwrite an earlier attempt. The task bundle
contains a learning curve, exact membership hashes, scheduler and source
receipts, five validation-only smoke fixtures, and a pickle-free safe-NPZ
checkpoint. It contains no test prediction, R4 prediction, or accuracy metric.
The checkpoint loader authenticates metadata and archive bytes before opening
the ZIP container, enforces an exact array allowlist and numerical contract,
and reproduces five frozen smoke predictions.

The accepted-set planner requires terminal `COMPLETED`/`0:0` accounting and one
valid attempt for each canonical task. Missing tasks remain pending; two
distinct valid attempts for one task fail closed. Only after all 25 checkpoint
manifests are frozen does the SLURM finalizer perform the first held-out
inference. It independently recomputes train-only normalizers, checks them
against every checkpoint, writes per-layout R3/R4 evaluation records, builds
the complete matrices, and publishes all 25 checkpoint hashes. A post-run
archive verifier then requires successful finalizer accounting and closes the
accepted set, candidate index, task artifacts, prediction tables, matrices,
source lock, and analysis manifest. Accuracy values become claim-eligible only
after that closure is reviewed and entered in the evidence ledger.
