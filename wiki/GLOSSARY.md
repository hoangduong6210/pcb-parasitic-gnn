---
title: Scientific Glossary
status: canonical terminology
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
---

# Scientific Glossary

| Term | Definition |
|---|---|
| \(C_{ps}\) | Primary-to-secondary winding capacitance in pF under the declared electrostatic boundary and material model. |
| \(L_p\), \(L_s\) | Primary and secondary winding self-inductance in nH. |
| \(M\) | Winding mutual inductance in nH. It is not the core magnetizing inductance. |
| Active leg | A straight conductor segment representing one side of a winding loop. Current corpora omit the return route. |
| Geometry family | A swap-closed group keyed by the unordered primary and secondary turn-count pair. |
| Family-macro MAPE | Mean absolute percentage error computed by first averaging within each held-out geometry family and then averaging the family means. |
| Crossed-axis seed-grid sensitivity interval | A descriptive interval obtained by resampling the evaluated split and initialization axes independently. It is not a population confidence interval. |
| Fidelity | A named numerical observation protocol, including mesh level and outer-domain padding. |
| FEM-R3P16 | Electrostatic FEM at refinement level 3 and 16 mm padding. It is the fixed bulk numerical target. |
| FEM-R4P16 | Electrostatic FEM at refinement level 4 and 16 mm padding. It is the sparse higher-resolution observation. |
| Domain delta | Relative capacitance change caused by enlarging the outer domain at fixed mesh refinement. |
| Mesh delta | Relative capacitance change caused by increasing mesh refinement at fixed outer domain. |
| Solver agreement | Difference between a surrogate and a declared numerical workflow. It is not hardware error. |
| Strict E(3) property | Equivariance of coordinate states and invariance of scalar outputs under three-dimensional rotations, reflections, and translations on the encoded graph. |
| Timing boundary | The exact operations included in a runtime measurement, such as pre-collated forward pass or raw-layout end-to-end inference. |
| Admitted claim | A scoped statement whose protocol, evidence, interpretation, and wording have passed review. |
| Historical claim | A traceable statement tied to a superseded dataset or protocol and excluded from current headline use. |
| Paper snapshot | An immutable exported manuscript package pinned to one reviewed wiki commit and claim set. |
