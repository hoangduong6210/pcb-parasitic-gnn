---
title: Manuscript Source — FEM Capacitance Sections
status: admitted source text
last_updated: 2026-08-15
paper_source: true
prose_reviewed: true
claim_ids: C-FEM-002, C-FEM-003
---

# Manuscript Source: FEM Capacitance Sections

## Numerical reference definition

The electrostatic calculation is treated as a hierarchy of numerical
observations rather than an absolute ground-truth label. FEM-R3P16 denotes a
first-order tetrahedral solve with refinement level 3 and 16 mm outer-domain
padding. It is the fixed target selected for bulk surrogate training.
FEM-R4P16 uses the same geometry, material, boundary, and linear-solver contract
at refinement level 4 and is reserved for higher-resolution validation.

## Convergence result

On a frozen nine-layout subset, the refine-3 comparison between 12 and 16 mm
padding yielded a median relative difference of 0.189658% and a maximum of
2.491566%. This passed the predeclared median 2% and maximum 5% criteria. At 16
mm padding, the refine-3-to-refine-4 comparison yielded a median difference of
8.273879% and a maximum of 13.886399%, failing both criteria. The bulk target is
therefore stable to the tested domain expansion but is not demonstrated to be
mesh-converged.

## Interpretation

Surrogate error against FEM-R3P16 measures reproduction of a deterministic
discretized workflow. It does not by itself measure physical capacitance error.
The study consequently reports three quantities separately: GNN agreement with
the bulk FEM-R3P16 target, FEM-R3P16-to-FEM-R4P16 discrepancy, and GNN agreement
with FEM-R4P16 on the held-out higher-fidelity subset. Hardware accuracy remains
outside the validated scope until fabricated-board measurements are available.
