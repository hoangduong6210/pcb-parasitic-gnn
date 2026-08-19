---
title: Cps R3/R4 Production Discrepancy
status: admitted descriptive result
last_updated: 2026-08-19
paper_source: true
prose_reviewed: true
claim_ids: C-CPS-DISC-001
evidence_ids: E-C4-DISC-01
---

# Cps R3/R4 Production Discrepancy

## Question and comparison

This analysis measures the difference between the two finalized capacitance
fidelities on their shared geometries. FEM-R3P16 is the fixed bulk numerical
target. FEM-R4P16 uses the same geometry, material, boundary, and solver
contract with a finer mesh. It is a higher-resolution comparator, not continuum
or physical truth.

The frozen registry contains 198 layouts, with three designs from each of 66
swap-closed turn-count families. Nine layouts are mandatory anchors inherited
from the convergence study. Those anchors were originally chosen with
capacitance order statistics. The other 189 layouts were chosen with
geometry-only descriptors and deterministic tie-breaking. No new R3/R4
discrepancy was used to add, remove, or replace a layout.

For each matched geometry, the signed relative discrepancy is

\[
\delta_i = 100\frac{C_{i,\mathrm{R3P16}}-C_{i,\mathrm{R4P16}}}
{|C_{i,\mathrm{R4P16}}|}.
\]

## Selected-registry result

| Quantity | Value |
|---|---:|
| Matched layouts | 198 |
| Swap-closed families | 66 |
| R3 greater than R4 | 198 of 198 |
| Median absolute discrepancy | 8.479% |
| Mean absolute discrepancy | 8.849% |
| 90th percentile | 11.568% |
| 95th percentile | 12.533% |
| Observed range | 2.754% to 17.517% |
| Median of the 66 family medians | 8.468% |

Every observed signed discrepancy was positive, so the signed and absolute
discrepancy summaries coincide on this registry. The result records a
same-signed difference on the selected panel. It does not identify the
continuum error of either fidelity.

## Statistical scope

The 198 layouts form a deterministic selected registry, not a probability
sample from the 1,500-layout corpus. The family expansion weights document the
size of each family; they are not sampling probabilities and are not used to
claim an unbiased full-corpus estimate. The five family-split test panels are
overlapping sensitivity views. Concatenating their 39-pair memberships yields
195 panel memberships, not 195 independent observations or five independent
replicates.

No confidence interval or hypothesis test is attached to this descriptive
result. The audit protocol was frozen after the underlying solver outcomes
existed, so its reporting rules are not described as prospectively declared.
The observed median is not used as a global correction for FEM-R3P16, and the
analysis does not establish physical capacitance accuracy.
