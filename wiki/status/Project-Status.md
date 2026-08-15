---
title: Project Status
status: active
last_updated: 2026-08-15
paper_source: true
---

# Project Status

## Current scientific state

The superseded v2 corpus is quarantined because its geometry generator can
produce inconsistent layer and vertical coordinates, overlapping conductor
volumes, and non-passive analytical inductance labels. Results trained or
timed on that corpus remain historical records and are not current evidence for
geometry-valid PCB layouts.

A replacement geometry corpus contains 1,500 unique layouts that pass the
shared geometry contract. Graph construction, FastHenry, and electrostatic FEM
consume the same conductor boxes and centers. The inherited inductance labels
are finite, passive, and tied to the geometry hashes.

The electrostatic reference study has reached a clear but negative conclusion.
Increasing the outer-domain padding from 12 to 16 mm at refine-3 satisfies the
predeclared sensitivity criterion. Increasing the mesh from refine-3 to
refine-4 at 16 mm does not. Refine-3 is therefore stable to the tested domain
expansion but is not demonstrated to be mesh-converged.

## Lifecycle table

| Work product | Lifecycle | Scientific use |
|---|---|---|
| v0–v2 layouts and labels | `QUARANTINED` | Pipeline archaeology only |
| Geometry-valid 1,500-layout corpus | `FINALIZED` | Geometry root for current work |
| FEM backend equivalence and residual checks | `ADMITTED` | Solver implementation evidence |
| Refine-3 domain-padding study | `ADMITTED` | Supports pad-16 bulk specification |
| Refine-3 versus refine-4 mesh study | `REJECTED` | Prohibits a mesh-converged r3 claim |
| Multi-fidelity protocol, family selection, and split registries | `FINALIZED` | Frozen input to new solver jobs |
| FEM-R3P16 bulk labels | `RUNNING` | Fixed low-fidelity numerical target; not admitted until finalized |
| FEM-R4P16 validation observations | `RUNNING` | Higher-fidelity subset, not ground truth |
| Multi-seed GNN accuracy on current corpus | `BLOCKED` | Waits for finalized fidelity corpus |
| Current-corpus end-to-end speedup | `BLOCKED` | Waits for accepted model and fixed workflow |
| Fabricated-board validation | `NOT STARTED` | Required for hardware-accuracy claims |

## Immediate execution plan

1. Use the frozen multi-fidelity protocol, selection registry, and split registry.
2. Produce FEM-R3P16 observations for all 1,500 geometries.
3. Produce three preselected higher-fidelity observations per swap-closed
   geometry family, giving 198 FEM-R4P16 validation layouts across 66 families.
4. Keep every fidelity for a geometry in the same train, validation, or test
   partition.
5. Train five split seeds crossed with five initialization seeds.
6. Report agreement with the fixed low-fidelity target separately from
   agreement with the higher-fidelity validation observations.

No current headline accuracy or speedup is admitted until these stages finish.
