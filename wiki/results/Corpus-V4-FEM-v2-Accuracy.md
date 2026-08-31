---
title: Corpus V4 FEM-v2 Family-Held-Out Accuracy
status: admitted current result
last_updated: 2026-08-31
paper_source: true
prose_reviewed: true
claim_ids: C-ACC-FEMV2-001
---

# Corpus V4 FEM-v2 Family-Held-Out Accuracy

## Evaluation scope

The current accuracy study uses the deterministic one-thread FEM-v2 package on
the frozen 1,500-layout synthetic active-leg corpus. It crosses five
swap-closed turn-count-family splits with five initialization seeds. Every
split holds out 13 of the 66 geometry families and contains 282 to 306 test
layouts. The five test sets contain 1,470 split-layout memberships and 1,017
unique layouts. Repeating each split for five initialization seeds produces
7,350 layout-model rows for every target.

All 25 models use the fixed final checkpoint after 200 epochs. Validation loss
is diagnostic only and does not choose an epoch, model, exclusion, retry, or
hyperparameter. Training receives one split-scoped train-plus-validation
artifact. Held-out inference begins only after all 25 checkpoint bundles pass
the immutable accepted-set gate.

## Full-test result

The primary statistic is family-macro mean absolute percentage error. Absolute
percentage error is averaged within each held-out family and then across the 13
families, so larger families receive no extra weight. The central value is the
mean across the complete 5 by 5 split and initialization grid.

| Target and numerical reference | Family-macro MAPE | 95% crossed-axis descriptive interval | Observed cell range | Mean pooled APE | Mean median APE | Mean \(R^2\) |
|---|---:|---:|---:|---:|---:|---:|
| \(C_{ps}\), one-thread FEM-v2 R3P16 | 12.550% | 11.796 to 13.366% | 10.825 to 15.667% | 12.467% | 9.791% | 0.9244 |
| \(L_p\), FastHenry | 4.173% | 3.414 to 5.015% | 2.837 to 6.330% | 4.177% | 2.871% | 0.9941 |
| \(L_s\), FastHenry | 3.964% | 3.263 to 4.729% | 2.712 to 5.564% | 3.992% | 2.952% | 0.9936 |
| \(M\), FastHenry | 3.413% | 3.052 to 3.734% | 2.484 to 4.201% | 3.364% | 2.658% | 0.9931 |

Mean cellwise MAE is 6.686 pF for \(C_{ps}\), 33.525 nH for \(L_p\),
34.960 nH for \(L_s\), and 23.092 nH for \(M\). All predictions are finite
and positive. Across all 7,350 layout-model rows, no predicted inductance
matrix violates \(|M| \leq \sqrt{L_pL_s}(1+10^{-9})\). This passivity check is
a prediction diagnostic, not a training acceptance gate or evidence of
hardware accuracy.

## Matched capacitance fidelity view

The same predictions are evaluated against one-thread FEM-v2 R3P16 and R4P16
on a fixed 39-layout panel within each split. Layouts and predictions are
identical between the two rows, so the comparison isolates the numerical
capacitance reference.

| Numerical reference | Family-macro MAPE | 95% crossed-axis descriptive interval | Observed cell range | Mean median APE | Mean \(R^2\) |
|---|---:|---:|---:|---:|---:|
| FEM-v2 R3P16 | 12.917% | 11.975 to 14.113% | 10.627 to 17.612% | 10.140% | 0.9284 |
| FEM-v2 R4P16 | 14.838% | 13.713 to 16.303% | 11.832 to 19.477% | 10.748% | 0.9081 |

Each split contributes three layouts from each of its 13 held-out families.
The five panels overlap: 195 split-layout memberships represent 135 unique
layouts from 45 families. They are sensitivity views, not independent
replicates. R4P16 is a higher-resolution comparator rather than truth. The
full-test R3 result and selected-panel R4 result use different layout sets and
must not be compared directly.

## Interval and claim interpretation

The crossed-axis interval independently resamples the five split rows and five
initialization columns with replacement, evaluates the resulting Cartesian
5 by 5 mean, and takes the 2.5th and 97.5th percentiles of 10,000 draws. It is a
descriptive sensitivity interval for the evaluated seed grid, not a population
confidence interval.

These numbers measure agreement with fixed synthetic numerical references
under held-out turn-count-family splits. They do not establish fabricated-board
accuracy, manufacturing robustness, mesh convergence, or generalization to
arbitrary routed PCB windings. The tracked result is owned by
`C-ACC-FEMV2-001` and its execution closure by `E-C4-FEM-V2-ACC-V3-01`.
