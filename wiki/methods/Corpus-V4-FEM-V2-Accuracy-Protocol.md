---
title: Corpus V4 FEM-v2 Accuracy Protocol
status: frozen; checkpoint-only training admitted
last_updated: 2026-08-29
paper_source: false
---

# Corpus V4 FEM-v2 Accuracy Protocol

## Scientific question and scope

This experiment asks how closely one fixed message-passing network reproduces
four numerical targets on the geometry-valid synthetic active-leg corpus. It
does not estimate error against a fabricated board, a continuum field solution,
or an unrestricted population of PCB layouts. The archived pre-FEM-v2 result
`C-ACC-001` remains a separate versioned result and supplies no value to this
study.

## Immutable data join

Every sample is joined by `(layout_id, geometry_sha256)`. The join contains
1,500 admitted deterministic one-thread R3 capacitance observations, 198 sparse
R4 capacitance observations, and the finalized FastHenry inductance labels. The
R3 values are the only capacitance targets visible to training. R4 remains in a
separate evaluation mapping and is opened only by the finalizer.

The loader replays the admitted FEM-v2 archive before materializing samples. It
also requires the frozen geometry-family, high-fidelity selection, and split
registries. Duplicate, missing, extra, nonpositive, hash-mismatched, or
family-inconsistent records fail closed. The historical capacitance column in
the inductance label file is deliberately ignored.

## Crossed family design

Split seeds 40 through 44 are crossed with initialization seeds 40 through 44.
The resulting 25 tasks use row-major identity. Each split contains 46 training,
7 validation, and 13 test families. The five R4 test panels contain 195 layout
memberships, but only 135 unique layouts from 45 unique families. They are
held-out within their respective splits and must not be described as five
independent panels.

| Split seed | Training layouts | Validation layouts | Test layouts | R4 test layouts |
|---:|---:|---:|---:|---:|
| 40 | 1,039 | 170 | 291 | 39 |
| 41 | 1,066 | 152 | 282 | 39 |
| 42 | 1,012 | 182 | 306 | 39 |
| 43 | 1,076 | 125 | 299 | 39 |
| 44 | 1,055 | 153 | 292 | 39 |

## Model and optimization

The model is a four-layer pure-PyTorch message-passing network with hidden width
96 and four graph-level outputs. Each cell uses AdamW with learning rate 0.002,
weight decay \(10^{-5}\), batch size 32, gradient clipping at 5, and a cosine
schedule over exactly 200 epochs. Node, edge, and target normalization is fitted
only on the training layouts. Validation loss is recorded for diagnosis and
does not select an epoch, checkpoint, exclusion, or retry.

## Checkpoint-before-test boundary

Each training task may read only its training and validation partitions. It
writes a safe-NPZ checkpoint, a learning curve, five validation smoke examples,
and provenance records. It emits no held-out prediction and never opens R4.

All 25 checkpoints must pass their byte, source, membership, runtime, and
terminal scheduler gates before the finalizer performs the first test
inference. Failed or missing tasks remain in a hash-pinned pending set. A retry
creates a new attempt and cannot overwrite earlier evidence.

## Metrics and physical diagnostic

Family-macro MAPE is the primary per-target summary. Pooled median, mean, and
95th-percentile APE, physical-unit MAE, signed bias, \(R^2\), and counts of
nonpositive or nonfinite predictions are secondary. No mixed-unit average is
reported as overall accuracy.

For each prediction, the finalizer also evaluates the positive-semidefinite
condition of the two-winding inductance matrix:

\[
|M| \leq \sqrt{L_pL_s}\,(1+10^{-9}).
\]

The number and rate of violations are retained for every split and
initialization. A prediction violation is diagnostic rather than an integrity
gate, so it cannot silently remove an unfavorable model or test layout.

R3 capacitance metrics cover every test layout. The R4 view compares the same
predictions against both R3 and R4 values on the fixed 39-layout panel for each
split. The archive also stores the R3-to-R4 numerical-reference gap once per
split and once on the complete 198-layout registry. R4 is a higher-resolution
numerical comparator, not truth and not a global correction to R3.

## Seed-grid uncertainty language

Every model metric retains its complete 5 by 5 matrix. A deterministic
10,000-draw row-and-column resampling summary describes sensitivity within the
evaluated seed grid. Its interval is descriptive. It is not a population
confidence interval and does not include machine variation, alternative
training protocols, fabricated hardware, or arbitrary-layout uncertainty.
Reference-fidelity gaps are not duplicated across initialization seeds.

## Admission boundary

Protocol freeze, checkpoint execution, archive verification, and scientific
claim admission are distinct states. The execution lock now admits
checkpoint-only SLURM training. Held-out inference remains closed until an
accepted set authenticates all 25 checkpoints, and scientific claims remain
closed until the final archive is reviewed. Archive closure makes the metrics
replayable; it does not by itself create a paper claim.
