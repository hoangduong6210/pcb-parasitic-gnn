---
title: Corpus V4 FEM-v2 Fixed Baseline Comparison
status: finalized result; archive review pending
last_updated: 2026-09-13
paper_source: false
prose_reviewed: true
claim_ids: C-BASE-FEMV2-001
---

# Corpus V4 FEM-v2 Fixed Baseline Comparison

## Question and scope

This post-hoc fixed-budget comparison evaluates the existing GNN against four
frozen pooled-feature procedures on the same synthetic FEM-v2 benchmark.
The five family-held-out splits are crossed with five initialization seeds.
Each comparison uses identical test layouts, family identifiers, geometry
hashes and numerical references. Capacitance uses one-thread FEM-v2 R3P16;
the three inductance targets use FastHenry at 100 kHz.

The baseline extension was designed after the GNN test results were known.
It is not a new blinded benchmark. Its fixed settings do not represent tuned
tree performance or equal training budgets. The
[protocol](../methods/Corpus-V4-FEM-v2-Baseline-Protocol.md) defines the
48-dimensional pooled representation, train-only preprocessing and absence
of hyperparameter search. Validation is diagnostic, with no train-plus-validation
refit. The graph model and pooled models differ in both representation and
function class, so this comparison does not isolate a causal graph advantage.

## Family-macro prediction error

Each entry is mean family-macro MAPE, in percent, over the 25 matched cells.
Within a cell, designs are averaged within each test family before averaging
the family errors. Lower is better. Repeated Constant and Ridge cells do not
constitute independent initialization replicates.

| Model | Cps | Lp | Ls | M |
|---|---:|---:|---:|---:|
| GNN | 12.550 | 4.173 | 3.964 | 3.413 |
| Constant | 62.421 | 71.129 | 68.898 | 57.026 |
| Ridge | 44.480 | 48.666 | 39.522 | 35.826 |
| Random Forest | 42.528 | 36.977 | 39.929 | 33.397 |
| Extra Trees | 42.130 | 30.325 | 39.763 | 29.428 |

The GNN has lower family-macro MAPE in every matched cell for every target
against each frozen baseline. This is an observation on this seed grid, not
a claim that any model wins on every individual layout or arbitrary PCB.

## Paired differences and descriptive sensitivity

The difference is baseline minus GNN, measured in percentage points; a
positive difference favors the GNN. The interval uses shared crossed-axis
resampling of the split and initialization axes, with 10,000 draws. It is a
descriptive seed-grid sensitivity interval, not a population confidence
interval. Overlapping split panels are not independent. Initialization
resampling of deterministic controls reflects variation in the paired GNN,
not additional independent Constant or Ridge fits.

| Baseline | Target | Mean difference, pp | 95% descriptive interval, pp |
|---|---|---:|---:|
| Constant | Cps | 49.871 | 38.476 to 61.253 |
| Constant | Lp | 66.956 | 56.262 to 77.787 |
| Constant | Ls | 64.934 | 57.185 to 72.755 |
| Constant | M | 53.613 | 40.875 to 67.332 |
| Ridge | Cps | 31.930 | 26.291 to 38.057 |
| Ridge | Lp | 44.494 | 39.885 to 49.987 |
| Ridge | Ls | 35.558 | 29.894 to 41.118 |
| Ridge | M | 32.413 | 27.257 to 38.923 |
| Random Forest | Cps | 29.978 | 23.946 to 35.381 |
| Random Forest | Lp | 32.804 | 27.126 to 38.404 |
| Random Forest | Ls | 35.965 | 26.234 to 45.868 |
| Random Forest | M | 29.984 | 24.498 to 34.942 |
| Extra Trees | Cps | 29.579 | 23.211 to 35.776 |
| Extra Trees | Lp | 26.153 | 23.034 to 28.719 |
| Extra Trees | Ls | 35.799 | 23.973 to 47.838 |
| Extra Trees | M | 26.014 | 18.889 to 33.193 |

All reported interval endpoints are positive. No significance test or
population coverage interpretation is attached to these intervals.

## Numerical diagnostics and limitations

The analysis retains nonpositive predictions and reports the joint
two-winding inductance positive-semidefiniteness diagnostic without clipping
or repairing predictions. The joint diagnostic is repeated in the per-target
records for convenience and must not be summed four times. A negative mutual
inductance alone is not a passivity violation; its sign depends on orientation.
For each of the four baselines, every evaluated cell recorded zero nonpositive
target predictions and zero joint inductance PSD violations. Passing these
numerical diagnostics does not validate the geometry as a fabricated winding.

The pooled baselines discard connectivity. A separately frozen pooled neural
network or controlled message-passing ablation is needed to distinguish the
effects of pooling, capacity and graph connectivity. The present result does
not establish strict-E(3) predictive benefit, baseline inference speed, or
the performance of optimized alternatives.

The corpus consists of synthetic co-directed active-leg abstractions, not
complete routed windings or fabricated boards. The FEM reference is not
mesh-converged or independent physical truth. These results quantify
agreement with one frozen numerical dataset, not physical extraction accuracy.

## Evidence ownership

`C-BASE-FEMV2-001` remains pending archive validation and scientific admission.
The [Evidence Ledger](../evidence/Evidence-Ledger.md) owns execution provenance;
the [artifact index](../../results/corpus_v4/baseline_fem_v2/README.md) links the
machine-readable predictions, metrics and archive closure. The GNN row is
owned by [the admitted accuracy study](Corpus-V4-FEM-v2-Accuracy.md).
