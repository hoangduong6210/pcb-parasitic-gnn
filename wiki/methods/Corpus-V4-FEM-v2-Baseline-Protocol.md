---
title: FEM-v2 Fixed Baseline Comparison Protocol
status: frozen protocol; execution validated
last_updated: 2026-09-13
paper_source: true
prose_reviewed: true
claim_ids: C-BASE-FEMV2-001
---

# FEM-v2 Fixed Baseline Comparison Protocol

## Question and study boundary

This extension compares the admitted message-passing GNN with fixed simpler
predictors on the same synthetic FEM-v2 benchmark. Its purpose is to measure
predictive agreement with the same numerical references, not physical-board
accuracy or a universal benefit from graphs.

The GNN held-out results were already available when this extension was
designed. The baseline choices are frozen before their own held-out inference,
but this is not a fresh blinded confirmatory benchmark. Reusing the established
partitions permits matched comparisons; it does not erase prior exposure to
the benchmark. No new solver labels are generated.

## Models and fixed budgets

| Model | Frozen configuration | Role |
|---|---|---|
| Constant | Training mean in log1p target space | Sanity reference |
| Ridge | Alpha 1; intercept; train-fitted feature scaling | Linear reference |
| Random Forest | 500 trees; maximum depth 16; minimum leaf size 2 | Nonlinear pooled-feature reference |
| Extra Trees | 500 trees; maximum depth 16; minimum leaf size 2 | Randomized pooled-feature reference |

The forest size, depth and leaf settings follow the earlier baseline study;
they are not selected from this extension's test results. There is no
hyperparameter search, validation-driven selection or training-plus-validation
refit. Validation is diagnostic only, as in the admitted fixed-epoch GNN study.
This compares specified procedures, not globally optimized model classes or
equal training-time budgets.

## Inputs and preprocessing

The study reuses the exact five family splits with seeds 40 through 44. Each
split has 46 training families, seven validation families and 13 test families.
Targets are the one-thread FEM-v2 R3P16 capacitance observation and the three
FastHenry inductance observations. Higher-resolution R4 values are not training
inputs or selection criteria.

The same graph builder supplies nine node features and seven edge features.
Node and edge normalization is fitted using training layouts only. For each
normalized feature dimension, pool its mean, maximum and signed log1p of its
sum. Concatenating node and edge pools produces 48 features. An empty edge set
has a zero edge pool. Layout identifiers, family identifiers, references and
solver diagnostics are never predictor inputs. Any pooled-feature scaling is
also fitted on training layouts only.

All models fit train-standardized log1p targets and invert that transformation
for physical-unit predictions. Predictions are not silently clipped to enforce
positivity or passivity. Invalid physical predictions are reported as model
diagnostics, not removed as inconvenient observations.

## Replication and data access

Stochastic forest fits cross the five splits with five fitting seeds, 40
through 44. Constant and Ridge are deterministic conditional on a split;
repeated deterministic results in the matched grid do not constitute independent
initialization replicates. They are paired with each corresponding GNN cell
only to preserve the comparison's split and GNN-initialization indexing.

Training uses the existing split-scoped training and validation artifact in a
restricted filesystem namespace. Test observations, other splits' training
artifacts, higher-resolution observations, GNN prediction files and other
tasks' output directories must not be visible to that process. All model
bundles must pass source, input, file-integrity and terminal-execution checks
before a separate evaluator can access held-out data. Checkpoints contain
numeric arrays, not executable serialized objects.

## Metrics and interpretation

The primary metric is family-macro MAPE for each target, using the same
definition as the admitted GNN study. Compare each baseline with the GNN on
the identical split, initialization cell and test memberships. Report
baseline-minus-GNN differences in percentage points, including their sign.
Positive differences favor the GNN; negative differences favor the baseline.

Crossed-axis resampling uses identical split and initialization draws for both
members of a paired difference. The interval is descriptive seed-grid
sensitivity, not a population confidence interval. Test appearances across
overlapping splits are not independent observations. Report every model and
target; model accuracy is not an integrity acceptance threshold.

Pooled-feature baselines discard graph connectivity. This comparison therefore
does not isolate the causal effect of message passing, representation, or
model capacity. A matched pooled-neural ablation would require its own study.
Fitting wall time is operational information and cannot support an inference
speed claim. Existing capacitance mesh-sensitivity and synthetic-geometry
limitations remain unchanged.

## Admission

The baseline claim remains pending until the frozen protocol, execution lock,
complete accepted checkpoint set, held-out evaluation, archive replay and
scientific review are complete. Results must be retained regardless of which
model performs better. No baseline outcome is claimed by this protocol page.
