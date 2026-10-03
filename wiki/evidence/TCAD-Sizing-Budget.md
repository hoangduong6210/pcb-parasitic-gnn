---
title: TCAD Sizing Budget Diagnostic Evidence
status: PROPOSED; source frozen, real-input execution pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Sizing Budget Diagnostic Evidence

The [method contract](../methods/TCAD-Sizing-Budget.md) diagnoses the rejected
column policy without regenerating any mesh or changing caps. The previous
[column archive](TCAD-Column-Feasibility.md) remains immutable. No new real-input
diagnosis has run yet; no sizing candidate, 3D mesh, field result, reference or
paper claim is admitted.

## Input bindings

- Parent protocol: `protocols/tcad_cps_column_feasibility_v1.json`, SHA-256
  `0e6451fb9ab44151c46090ef06ef4796bbe4c786a44d264fd545dcce18bd1149`.
- Terminal archive: `results/tcad/cps_column_feasibility_v1/archive/job_7653784/manifest.json`,
  SHA-256 `69e90937ffa35c26ebbea73b583582adc4e88232b375ebdfc358797769362183`.
- Frozen protocol: `protocols/tcad_cps_sizing_budget_v1.json`, SHA-256
  `34084a9ee2555c7c072152b9d178978fc0c7a321b7f6bc5fa3d45eb48cecd7b8`.
- Source/input lock: `protocols/tcad_cps_sizing_budget_v1.lock.json`, 425 dependencies,
  SHA-256 `0302408e78ab97312303cad5cdc4174ac725ab7a86d15e0e47bfd8760d5d5db5`.
- Toy uses archived toy CAD/sizing/stdout; local1 and repeat1 use the same
  archived local1 files. Repeat is not a repeated native-meshing attempt.

## Synthetic verification

Initial arithmetic tests passed 34 cases: hand-counted duplicate projections,
clipping, exact one-ULP strips, rational envelopes, full-owner vertical volumes,
independent capture/3D budgets, zero budgets and invalid/ambiguous log rejection.
The initial integration regression passed 85 tests with one expected pre-freeze
lock skip. It covers guard ordering, unchanged original caps, archived effective
sizing, report mutation rejection, no overwrite, failed-budget retention and
byte/scalar-only review. Additional path-safety and partial-attempt tests passed
in the 304-test pre-freeze regression with one expected lock skip. The frozen
regression then passed **305 tests, zero skips**, in 43.39 seconds. The research
prose audit passed. These are tiny synthetic inputs, not real
layout or mesh analysis on the login node.

Next: publish the frozen source, verify a fresh sparse
execution checkout, then submit one bounded diagnostic job through SLURM.
Retain every complete or partial outcome. The full TCAD goal remains active.
