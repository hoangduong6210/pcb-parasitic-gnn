---
title: Project Status
status: active scientific status
last_updated: 2026-08-22
paper_source: false
---

# Project Status

## Scientific state

The superseded v2 corpus was built for rapid feasibility estimation: it tested
whether a GNN-based workflow was promising enough to justify a larger controlled
study. Its results remain an archival snapshot of that stage and are not inputs
to current claims. The replacement program adds explicit geometry contracts,
shared solver topology, passive field-derived targets, fidelity gates, and
family-held-out evaluation for production-oriented evidence.

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
| v0 through v2 layouts and labels | `ARCHIVAL / SUPERSEDED` | Feasibility-stage pipeline history only |
| Geometry-valid 1,500-layout root | `FINALIZED` | Geometry root for current work |
| FEM backend equivalence and residual checks | `ADMITTED` | Solver implementation evidence |
| Refine-3 domain-padding study | `ADMITTED` | Supports the pad-16 bulk specification |
| Refine-3 versus refine-4 mesh study | `ADMITTED NEGATIVE` | Rejects a mesh-converged R3 claim |
| Multi-fidelity protocol, selections, and split registries | `FINALIZED` | Frozen input to production jobs |
| FEM-R3P16 bulk observations | `FINALIZED` | Complete 1,500-layout fixed-fidelity observation set |
| FEM-R4P16 validation observations | `FINALIZED` | Complete higher-resolution 198-layout subset; not ground truth |
| Joint multi-fidelity Cps package | `FINALIZED` | 1,698 explicit-fidelity observations over 1,500 geometries |
| Family-aware R3/R4 discrepancy audit | `ADMITTED DESCRIPTIVE` | Exact 198-layout selected-registry comparison; no population inference or global correction |
| Multi-seed current-corpus accuracy | `ADMITTED` | Complete 5 by 5 family-held-out split and initialization grid with tracked checkpoints, predictions, matrices, and archive closure |
| FEM-R3P16 repeatability diagnostic | `POSTTERMINAL NEGATIVE` | Corrected 30-solve run: the existing 25-thread path failed mesh identity and repeatability on all three anchors; the one-thread diagnostic passed both on all three; paired latency is explicitly not authorized |
| One-thread FEM reference qualification | `R3 ROUTE ADMITTED; R4 ROUTE LOCKED` | Gates A and B are positive postterminal results; R3 v2 generation is authorized but not started; Gate C has no admission and still controls a new multi-fidelity route |
| Current-corpus paired four-target latency | `PREFLIGHT REJECTED / BLOCKED` | Two three-task preflights executed and were rejected; 0 of 3 tasks accepted; the 306-layout full array was not submitted |
| Vendor commercial-geometry track | `PROPOSED` | Requires licensing, segmentation, and matching validation quantities |
| Fabricated-board validation | `NOT STARTED` | Required for hardware-accuracy claims |

Operational progress changes more frequently than scientific status. The dated
[Live Execution](Live-Execution.md) page owns task counts and the next scheduler
transition.

## Next scientific stages

1. Use the admitted
   [family-held-out accuracy result](../results/Corpus-V4-Accuracy.md) as the
   predictive baseline for subsequent current-corpus experiments.
2. Complete Gate C in
   [Decision 0002](../decisions/0002-deterministic-fem-reference.md). Gates A
   and B already authorize full R3 v2 regeneration, but no bulk job will be
   started while the explicit multi-fidelity decision is still open. New
   labels then require retraining and a new accuracy result before a latency
   protocol is designed. The earlier repeatability admission remains negative
   for the old 25-thread path, so `C-LAT-001` and its 306-layout array remain
   closed.
3. Repeat baseline, strict E(3), and ranking studies on the same current corpus
   and split registry.
4. Admit claims in the wiki before generating a new paper snapshot.

There is an admitted geometry-valid synthetic solver-agreement result. There is
no current-corpus paired speed headline or hardware-accuracy claim.
