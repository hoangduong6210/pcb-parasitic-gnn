---
title: Decision 0001 — Cps Multi-Fidelity Policy
status: accepted for implementation
date: 2026-08-15
paper_source: false
---

# Decision 0001: Cps Multi-Fidelity Policy

## Decision

Use FEM-R3P16 as the fixed bulk low-fidelity capacitance target and FEM-R4P16
as a sparse higher-fidelity validation observation. Preserve both observations
under explicit fidelity identifiers. Do not flatten them into one unlabeled
capacitance truth column.

Select three FEM-R4P16 layouts per swap-closed turn-count family, for 198 layouts
across 66 families. Selection must be geometry-only, deterministic, and frozen
before new solves. The nine canonical convergence layouts are mandatory anchors.

## Rationale

Refine-3 is affordable across the full corpus and passes the tested domain
sensitivity gate. It fails the refine-3/refine-4 mesh gate and therefore cannot
serve as a convergence-certified physical reference. Refine-4 is more resolved
but is too expensive for immediate full-corpus generation and is not itself
certified against refine-5.

## Consequences

- Bulk GNN accuracy is explicitly agreement with FEM-R3P16.
- Higher-fidelity evaluation uses geometries excluded from training.
- All fidelities for one geometry share one split partition.
- Current historical accuracy and speed numbers remain quarantined.
- The observed median R3/R4 difference is not a global calibration factor, and
  no validation layout may be removed after its discrepancy is observed.
- Uniform refine-5/refine-6 is not scheduled; adaptive refinement remains a
  future reference-development track.
