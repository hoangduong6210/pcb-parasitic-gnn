---
title: Manuscript Source — FEM Capacitance Sections
status: admitted source text
last_updated: 2026-08-21
paper_source: true
prose_reviewed: true
claim_ids: C-FEM-002, C-FEM-003, C-FEM-004, C-CPS-DISC-001
---

# Manuscript Source: FEM Capacitance Sections

## Numerical reference definition

The electrostatic calculation is treated as a hierarchy of numerical
observations rather than an absolute ground-truth label. FEM-R3P16 denotes a
first-order tetrahedral solve with refinement level 3 and 16 mm outer-domain
padding. Its archived observations form the fixed target used by the completed
bulk surrogate study.
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

## Production fidelity discrepancy

The full selected-registry audit paired the 198 layouts with both fidelities.
FEM-R3P16 exceeded FEM-R4P16 in all 198 pairs. The selected-registry median
relative discrepancy was 8.479%, and the observed range was 2.754% to 17.517%.
The panel is deterministic rather than probability sampled. Nine layouts are
anchors inherited from a convergence selection that used capacitance order
statistics, while the other 189 were selected from geometry descriptors. The
result is reported descriptively without a population confidence interval or a
global R3 correction.

## Mesh repeatability result

A separate frozen diagnostic evaluated three preselected layouts with five
fresh meshes per layout. Under the existing 25-thread Gmsh path, the maximum
pairwise relative Cps spreads were `5.5882813e-4`, `7.4171889e-3`, and
`7.2121703e-3`; all three layouts also produced five distinct discrete-system
hashes. The same experiment with one Gmsh thread produced one system hash per
layout and maximum spreads no larger than `8.4549511e-15`. Thus the existing
multithreaded path failed the frozen `1e-4` repeatability gate, whereas the
one-thread candidate passed on this finite panel. This result does not
retroactively relabel the archived observations. It motivates a versioned
deterministic reference and complete downstream regeneration.

## Interpretation

Surrogate error against the archived FEM-R3P16 observations measures agreement
with a fixed discretized artifact set. It does not establish fresh-mesh
repeatability or physical capacitance accuracy.
The study consequently reports three quantities separately: GNN agreement with
the bulk FEM-R3P16 target, the full 198-layout selected-registry
FEM-R3P16-to-FEM-R4P16 discrepancy, and GNN agreement with FEM-R4P16 on the 39
test-panel layouts of each family split. The complete 198-layout registry is not
globally held out from every training split. Hardware accuracy remains outside
the validated scope until fabricated-board measurements are available.
