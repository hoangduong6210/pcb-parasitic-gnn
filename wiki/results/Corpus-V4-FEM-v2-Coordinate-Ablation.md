---
title: Corpus V4 FEM-v2 Coordinate-Update Ablation
status: VALIDATED; scientific claim admission pending
last_updated: 2026-09-15
paper_source: false
prose_reviewed: true
claim_ids: C-E3-FEMV2-001
---

# Corpus V4 FEM-v2 Coordinate-Update Ablation

## Question and scope

This fixed-protocol, post-hoc study tests whether learned coordinate updates
improve prediction over fixed-coordinate controls on the previously evaluated
FEM-v2 synthetic benchmark. Five family-held-out splits are crossed with five
initialization seeds. Each of the 25 cells trains three arms for 200 epochs,
without checkpoint selection or hyperparameter search. The
[design](../methods/Corpus-V4-FEM-v2-Coordinate-Ablation.md) specifies the
model, data isolation and comparison contract.

All three arms have E(3)-invariant scalar outputs on the encoded graph.
The intervention is coordinate updating, not the presence of equivariance.
The fixed-width control shares width 96; the capacity control uses width 101,
with 301,997 parameters versus 301,354 in the moving-coordinate model.
Approximate parameter matching does not equate their function classes.

## Family-macro prediction error

Entries are mean family-macro MAPE, in percent, across the 25 cells. Within
each cell, design errors are first averaged within each held-out family, then
across families. Lower is better.

| Arm | Cps | Lp | Ls | M |
|---|---:|---:|---:|---:|
| Moving coordinates, width 96 (`strict96`) | 11.623 | 4.328 | 4.173 | 3.904 |
| Fixed coordinates, width 96 (`fixed96`) | 11.763 | 4.449 | 4.233 | 3.883 |
| Fixed coordinates, capacity control (`fixed_matched`) | 10.895 | 4.269 | 4.090 | 3.810 |

## Paired differences

The difference is moving minus fixed, in percentage points. Positive values
favor the fixed-coordinate control. Intervals use 10,000 shared crossed-axis
resamples of the split and initialization axes. They describe seed-grid
sensitivity, not population confidence or independent-layout uncertainty.

| Control | Target | Mean difference, pp | 95% descriptive interval, pp |
|---|---|---:|---:|
| Fixed width 96 | Cps | -0.139 | -0.856 to 0.749 |
| Fixed width 96 | Lp | -0.120 | -0.638 to 0.254 |
| Fixed width 96 | Ls | -0.060 | -0.406 to 0.266 |
| Fixed width 96 | M | 0.021 | -0.178 to 0.242 |
| Capacity control | Cps | 0.728 | -0.019 to 1.467 |
| Capacity control | Lp | 0.060 | -0.298 to 0.523 |
| Capacity control | Ls | 0.083 | -0.160 to 0.327 |
| Capacity control | M | 0.095 | -0.043 to 0.287 |

All eight intervals include zero. Moving coordinates give slightly lower mean
error for three targets against the fixed-width control, but higher mean error
for every target against the capacity control. This seed grid does not show a
consistent coordinate-update advantage. It does not establish equivalence,
absence of benefit in other settings, or a general conclusion about EGNNs.

## Symmetry and numerical diagnostics

All 75 trained checkpoints passed the frozen symmetry checks: 40 transforms
on seven validation-family fixtures per checkpoint, including orthogonal
transforms, translations and node permutations. Across 21,000 graph-transform
evaluations, maximum scalar-invariance residuals were 3.5813e-7 for the moving
arm, 4.0428e-7 for the fixed-width arm and 3.2827e-7 for the capacity control.
The maximum moving-coordinate equivariance residual was 2.7393e-7, below the
declared relative tolerance of 2e-5. Fixed-coordinate unchanged residuals
were zero. These are finite numerical checks on encoded validation graphs,
not a proof about arbitrary raw-layout regeneration.

Every arm had zero nonpositive target predictions and zero two-winding
inductance positive-semidefiniteness violations on the evaluated cells.
The joint diagnostic is repeated in target records and must not be added
four times. Passing it does not validate a fabricated winding.

## Evidence and limitations

The [execution ledger](../evidence/Evidence-Ledger.md#e-c4-e3-femv2-analysis-01--coordinate-update-ablation)
owns scheduler and archive provenance. The machine
[summary](../../results/corpus_v4/strict_e3_fem_v2/recovery/v1/final/job_7326179/summary.json)
owns exact values under `results.arms`, `results.paired_contrasts` and
`results.trained_symmetry`. Coverage is 22,050 prediction rows, 300
arm-target metric rows and 200 paired contrasts. Scientific claim admission
remains pending; this page is not a paper export source.

The study was designed after earlier benchmark results were known. Its
synthetic active-leg geometries are not complete routed or fabricated PCB
windings. Capacitance uses the numerical FEM-v2 R3P16 reference, not an
independently confirmed continuum value. No new R4 comparison or inference
latency claim is made. The previously admitted GNN appears only as context
in the machine summary, not as a controlled ablation arm.
