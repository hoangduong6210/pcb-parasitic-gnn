---
title: Corpus V4 Family-Held-Out Accuracy
status: admitted current result
last_updated: 2026-08-19
paper_source: true
prose_reviewed: true
claim_ids: C-ACC-001
---

# Corpus V4 Family-Held-Out Accuracy

## Evaluation scope

One fixed four-layer message-passing network was evaluated on the frozen
1,500-layout synthetic active-leg corpus. The experiment crossed five
swap-closed turn-count-family splits with five initialization seeds. Each split
held out 13 of the 66 geometry families, and its test partition contained 282
to 306 layouts. Across the five splits, the test sets contain 1,470
split-layout memberships and 1,017 unique layouts. Repeating each split for
five initialization seeds produced 7,350 layout-model rows, with one prediction
for each target in every row.

All 25 models used the final checkpoint after 200 epochs. Validation loss was
diagnostic only: it did not select an epoch, model, hyperparameter, exclusion,
or retry. The training tasks emitted no test or FEM-R4P16 prediction. Held-out
inference began only after all checkpoints had passed the accepted-set gate.

## Full-test result

The primary statistic is family-macro mean absolute percentage error (MAPE).
Absolute percentage error is averaged within each of the 13 held-out families
and then averaged across families, preventing large families from receiving
more weight. The table reports the mean across the complete 5 by 5 grid.

| Target and numerical reference | Family-macro MAPE | 95% crossed-axis sensitivity interval | Observed cell range | Mean cellwise pooled APE | Mean cellwise median APE | Mean cellwise \(R^2\) |
|---|---:|---:|---:|---:|---:|---:|
| \(C_{ps}\), FEM-R3P16 | 12.890% | 12.001 to 13.796% | 10.915 to 15.431% | 12.781% | 10.102% | 0.9212 |
| \(L_p\), FastHenry | 4.272% | 3.407 to 5.394% | 2.873 to 7.691% | 4.265% | 2.897% | 0.9941 |
| \(L_s\), FastHenry | 4.076% | 3.275 to 4.967% | 2.939 to 5.939% | 4.094% | 2.976% | 0.9928 |
| \(M\), FastHenry | 3.554% | 3.243 to 3.814% | 2.432 to 4.451% | 3.506% | 2.762% | 0.9924 |

Mean cellwise MAE was 6.815 pF for \(C_{ps}\), 33.649 nH for \(L_p\),
35.590 nH for \(L_s\), and 23.985 nH for \(M\). All predictions were finite
and positive. The target-specific results should remain separate; the protocol
does not define an aggregate physical-accuracy scalar across quantities with
different units and numerical references.

## Matched capacitance fidelity view

The same predictions were also evaluated against FEM-R3P16 and FEM-R4P16 on a
matched 39-layout panel within each split. This comparison isolates the change
of capacitance reference because the layouts and predictions are identical.

| Numerical reference | Family-macro MAPE | 95% crossed-axis sensitivity interval | Observed cell range | Mean cellwise median APE | Mean cellwise \(R^2\) |
|---|---:|---:|---:|---:|---:|
| FEM-R3P16 | 13.770% | 12.276 to 15.620% | 10.648 to 19.148% | 11.138% | 0.9200 |
| FEM-R4P16 | 15.932% | 14.077 to 18.235% | 11.141 to 22.853% | 11.686% | 0.8966 |

Each split contributes three layouts from each of its 13 test families. The
five panels overlap: their 195 split-layout memberships represent 135 unique
layouts from 45 families. They are therefore sensitivity views, not independent
replicates. The full-test FEM-R3P16 result and the selected-panel FEM-R4P16
result use different layout sets and must not be compared directly; the valid
matched comparison is the two-row table above.

## Interval interpretation

The descriptive interval resamples the five split rows and five initialization
columns independently with replacement, evaluates the Cartesian 5 by 5 mean,
and takes the 2.5th and 97.5th percentiles of 10,000 draws. It summarizes
sensitivity within the evaluated seed grid. It is not a population confidence
interval and does not cover other machines, training protocols, fabricated
boards, manufacturing variation, or arbitrary PCB geometries.

These results measure agreement with synthetic numerical references under
held-out turn-count-family splits. FEM-R3P16 is a fixed discretized workflow,
FEM-R4P16 is a higher-resolution comparator rather than truth, and neither
solver agreement nor the observed grid variation establishes hardware
accuracy.
