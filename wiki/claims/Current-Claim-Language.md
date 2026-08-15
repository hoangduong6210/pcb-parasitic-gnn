---
title: Current Claim Language
status: canonical claim registry
last_updated: 2026-08-15
paper_source: true
---

# Current Claim Language

## Admitted claims

| Claim key | Permitted statement |
|---|---|
| `geometry.v3.valid` | The active 1,500-layout corpus passes the shared geometry contract. |
| `fem.backend.amg` | The AMG-CG backend reproduces the direct result on the identical diagnostic system and solves the tested high-resolution systems within the residual tolerance. |
| `fem.domain.r3` | The refine-3 12-to-16 mm domain comparison passes the frozen median and maximum gates. |
| `fem.mesh.r3` | Refine-3 is rejected as a mesh-converged reference under the frozen refine-3/refine-4 gate. |
| `symmetry.strict_e3` | The tested coordinate-update implementation is strictly E(3)-equivariant on the encoded graph within numerical tolerance. This is an implementation property, not an accuracy claim. |

## Pending claims

The following claims require new geometry-valid, fidelity-explicit jobs:

- GNN accuracy against FEM-R3P16 bulk observations;
- GNN agreement with FEM-R4P16 validation observations;
- robustness across split and initialization seeds;
- family-disjoint generalization under swap-closed families;
- current-corpus paired end-to-end speedup;
- a downloadable checkpoint reproducing current results.

## Prohibited wording

Do not write:

- “ground-truth capacitance” for any current FEM level;
- “mesh-converged refine-3”;
- “2–3% physical accuracy” based on surrogate agreement alone;
- “consistently achieves” from one split or one initialization;
- “faster than 3-D solvers” without naming the exact solver workflow and timing
  boundary;
- strict \(E(n)\) when the executed proof establishes the encoded \(E(3)\) case;
- the historical approximately 4,300× ratio as a paired end-to-end result.
- a global correction of FEM-R3P16 by the observed median mesh difference;
- any exclusion chosen after inspecting a layout's R3/R4 discrepancy.

## Required wording for the active Cps protocol

> FEM-R3P16 is the fixed numerical target for bulk capacitance labeling, whereas
> FEM-R4P16 is reserved for higher-resolution validation. The refine-3 domain
> comparison passed, but the refine-3/refine-4 comparison failed the
> predeclared mesh-sensitivity gate. FEM-R3P16 is reproducible under its fixed
> protocol but is not treated as mesh-converged or as physical ground truth.
