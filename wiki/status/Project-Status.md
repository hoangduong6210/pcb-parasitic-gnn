---
title: Project Status
status: active scientific status
last_updated: 2026-08-19
paper_source: false
---

# Project Status

## Scientific state

The superseded v2 corpus is quarantined because its generator can produce
inconsistent layer and vertical coordinates, overlapping conductors, board
overrun, and non-passive mixed analytical labels. Results derived from that
corpus remain historical records. They are not current evidence for
geometry-valid PCB layouts.

The replacement geometry root contains 1,500 unique layouts that pass the shared
geometry contract. Graph construction, FastHenry, and electrostatic FEM consume
the same conductor boxes, centers, and identities. The inductance observations
are finite and passive.

The electrostatic study produced a useful negative result. Refine-3 passed the
tested 12 to 16 mm domain-expansion gate but failed the refine-3/refine-4 mesh
gate. The active capacitance package therefore preserves two named fidelities
instead of calling one column ground truth.

## Lifecycle table

| Work product | Lifecycle | Scientific use |
|---|---|---|
| v0 through v2 layouts and labels | `QUARANTINED` | Pipeline history only |
| Geometry-valid 1,500-layout root | `FINALIZED` | Geometry root for current work |
| FEM backend equivalence and residual checks | `ADMITTED` | Solver implementation evidence |
| Refine-3 domain-padding study | `ADMITTED` | Supports the pad-16 bulk specification |
| Refine-3 versus refine-4 mesh study | `ADMITTED NEGATIVE` | Rejects a mesh-converged R3 claim |
| Multi-fidelity protocol, selections, and split registries | `FINALIZED` | Frozen input to production jobs |
| FEM-R3P16 bulk observations | `FINALIZED` | Complete 1,500-layout fixed-fidelity observation set |
| FEM-R4P16 validation observations | `FINALIZED` | Complete higher-resolution 198-layout subset; not ground truth |
| Joint multi-fidelity Cps package | `FINALIZED` | 1,698 explicit-fidelity observations over 1,500 geometries |
| Family-aware R3/R4 discrepancy audit | `ADMITTED DESCRIPTIVE` | Exact 198-layout selected-registry comparison; no population inference or global correction |
| Multi-seed current-corpus accuracy | `BLOCKED` | Waits for the frozen loader/reporting contract, then crossed family-split evaluation |
| Current-corpus end-to-end speedup | `BLOCKED` | Waits for an accepted current model and fixed workflow |
| Vendor commercial-geometry track | `PROPOSED` | Requires licensing, segmentation, and matching validation quantities |
| Fabricated-board validation | `NOT STARTED` | Required for hardware-accuracy claims |

Operational progress changes more frequently than scientific status. The dated
[Live Execution](Live-Execution.md) page owns task counts and the next scheduler
transition.

## Next scientific stages

1. Freeze the downstream loading and reporting contract from the completed
   fidelity audit.
2. Train five family-split seeds crossed with five initialization seeds.
3. Report GNN agreement with FEM-R3P16 separately from agreement with FEM-R4P16.
4. Repeat baseline, strict E(3), ranking, and paired latency studies on the same
   current corpus and split registry.
5. Admit claims in the wiki before generating a new paper snapshot.

There is no current geometry-valid accuracy or speed headline.
