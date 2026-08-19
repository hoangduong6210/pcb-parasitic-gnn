---
title: Current Claim Registry
status: canonical claim registry
last_updated: 2026-08-19
paper_source: false
---

# Current Claim Registry

This registry controls scientific wording. Artifact lifecycle and scientific
admission are separate: a validated result still needs a reviewed claim before
it becomes paper eligible.

## Admitted claims

| Claim ID | Exact permitted statement | Scope and required qualifier | Evidence | Paper eligible |
|---|---|---|---|---|
| `C-GEOM-001` | The active corpus contains 1,500 unique layouts that pass the shared geometry contract. | Synthetic co-directed active-leg abstractions; no complete routed loops, vias, terminals, planes, or core window. | `E-C3-GEOM-01` | Yes, with the stated synthetic-scope qualifier |
| `C-FEM-001` | The AMG-CG backend reproduced the direct result on the identical diagnostic system and solved the tested refine-3 system within residual tolerance. | Backend implementation evidence, not independent physical validation. | `E-C4-FEM-01` | Yes |
| `C-FEM-002` | On the frozen nine-layout set, the refine-3 comparison between 12 and 16 mm padding passed the median 2% and maximum 5% gates. | Median 0.189658%; maximum 2.491566%; only the tested domain expansion and subset. | `E-C4-CONV-01` | Yes |
| `C-FEM-003` | Refine-3 failed the frozen refine-3/refine-4 mesh-sensitivity gate at 16 mm padding. | Median 8.273879%; maximum 13.886399%. R4 is higher resolution, not continuum or physical truth. | `E-C4-CONV-01` | Yes, as a negative result |
| `C-CPS-DISC-001` | On the frozen deterministic 198-layout registry, with three designs from each of 66 swap-closed turn-count families, every FEM-R3P16 observation exceeded its paired FEM-R4P16 observation; the selected-registry median R3-to-R4 relative discrepancy was 8.479%, with an observed range of 2.754% to 17.517%. | Deterministic selected registry, not a probability sample. Nine anchors were inherited from a label-informed convergence selection; the other 189 entries were geometry-only selections. R4 is a higher-resolution comparator, not truth. No confidence interval, population inference, or global correction is attached. | `E-C4-DISC-01` | Yes, with all stated qualifiers |
| `C-E3-001` | The tested coordinate-update implementation is E(3)-equivariant in its coordinate state and invariant in its scalar output on the encoded graph within numerical tolerance. | 200 encoded-graph transforms; maximum output and coordinate residuals \(3.919\times10^{-7}\) and \(1.407\times10^{-7}\); tolerance \(2\times10^{-5}\). This is not a predictive-accuracy claim. | `E-V2-E3-01` | Yes |

## Validated or finalized artifacts not yet admitted as headline results

| Claim ID | Lifecycle | Permitted status statement | What remains |
|---|---|---|---|
| `C-CPS-R3-001` | `FINALIZED` | All 1,500 planned FEM-R3P16 tasks have accepted artifacts under the frozen execution lock and are included in the joint package. | Scientific interpretation remains fidelity-scoped. |
| `C-CPS-R4-001` | `FINALIZED` | All 198 planned FEM-R4P16 tasks have accepted artifacts under the frozen execution lock and are included in the joint package. | Higher resolution is not continuum or physical truth. |
| `C-CPS-FINAL-001` | `FINALIZED` | The tracked package contains 1,500 R3 and 198 R4 observations over 1,500 geometries with explicit fidelity identifiers. | Corpus closure alone is not an accuracy, convergence, or physical-validation claim. |
| `C-ACC-001` | `BLOCKED` | No current-corpus GNN accuracy claim is admitted. | Family-disjoint crossed split and initialization seeds, plus separate R3/R4 agreement. |
| `C-LAT-001` | `BLOCKED` | No current-corpus end-to-end speedup claim is admitted. | Accepted current model, fixed four-target workflow, paired timings, and scoped uncertainty. |
| `C-VENDOR-001` | `PROPOSED` | The vendor files define a commercial-geometry validation track, not a completed validation result. | License review, segmentation, materials, terminals, convergence, and matching external quantity. |

## Rejected positive claims

The evidence supports the negative statement in `C-FEM-003`; it rejects the
positive statement that FEM-R3P16 is mesh-converged. It does not identify the
continuum error of FEM-R4P16.

The historical EGNN ablation is inconclusive. Neither “EGNN does not help” nor a
predictive superiority statement is admitted.

## Prohibited wording

Do not write:

- “ground-truth capacitance” for either current FEM fidelity;
- “mesh-converged refine-3”;
- “2 to 3% physical accuracy” from surrogate agreement;
- “consistently achieves” from one split or initialization;
- “faster than 3-D solvers” without solver output scope and timing boundary;
- strict E(n) when the executed check establishes the encoded E(3) case;
- the historical approximately 4,300-fold ratio as paired end-to-end evidence;
- a global correction of FEM-R3P16 by the observed median mesh difference;
- an exclusion chosen after inspecting a layout's R3/R4 discrepancy; or
- a current accuracy, ranking, or speed number derived from v0 through v2.

## Required capacitance wording

FEM-R3P16 is the fixed numerical target for bulk capacitance labeling, whereas
FEM-R4P16 is reserved for higher-resolution validation. The refine-3 domain
comparison passed, but the refine-3/refine-4 comparison failed the predeclared
mesh-sensitivity gate. FEM-R3P16 is reproducible under its fixed protocol but is
not treated as mesh-converged or as physical ground truth. On the deterministic
198-layout selected registry, the median R3-to-R4 discrepancy is 8.479%, with an
observed range of 2.754% to 17.517%; this descriptive panel result is not a
full-corpus estimate or a calibration factor.

The [Historical Claim Ledger](Historical-Claim-Ledger.md) preserves earlier
numbers and explains why they cannot be promoted into current statements.
