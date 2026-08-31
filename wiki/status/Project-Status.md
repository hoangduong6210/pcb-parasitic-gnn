---
title: Project Status
status: active scientific status
last_updated: 2026-08-31
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
| Archived 25-thread FEM-R3P16 bulk observations | `FINALIZED` | Complete 1,500-layout fixed-fidelity observation set |
| Archived 25-thread FEM-R4P16 validation observations | `FINALIZED` | Complete higher-resolution 198-layout subset; not ground truth |
| Archived 25-thread joint multi-fidelity Cps package | `FINALIZED` | 1,698 explicit-fidelity observations over 1,500 geometries |
| Family-aware R3/R4 discrepancy audit | `ADMITTED DESCRIPTIVE` | Exact 198-layout selected-registry comparison; no population inference or global correction |
| Pre-FEM-v2 multi-seed accuracy baseline | `ADMITTED; VERSION-SCOPED` | Complete 5 by 5 family-held-out split and initialization grid bound to the archived 25-thread capacitance package; it is not an FEM-v2 model result |
| FEM-R3P16 repeatability diagnostic | `POSTTERMINAL NEGATIVE` | Corrected 30-solve run: the existing 25-thread path failed mesh identity and repeatability on all three anchors; the one-thread diagnostic passed both on all three; paired latency is explicitly not authorized |
| One-thread FEM reference qualification | `COMPLETE` | Nine-layout R3 and three-sentinel R4 repeatability passed; finite-panel domain sensitivity passed; finite-panel adjacent-mesh sensitivity was negative |
| Deterministic one-thread FEM-v2 dataset | `FINALIZED; POSTTERMINAL ADMITTED` | 1,500 R3 plus 198 R4 observations over 1,500 geometries; its dataset receipt keeps training closed, while the separate downstream accuracy lock governs model execution |
| FEM-v2 accuracy protocol v2 | `SUPERSEDED; DIAGNOSTIC EXECUTION CLOSED` | 25 checkpoint tasks completed, but the process materialized held-out bytes before acceptance; no held-out inference or model claim was admitted |
| FEM-v2 accuracy protocol v3 | `FINALIZED; ARCHIVE VALIDATED; CLAIM ADMITTED` | The 5 by 5 family-split and initialization grid is complete; all 25 checkpoints were accepted before held-out inference; the tracked archive supports `C-ACC-FEMV2-001` |
| Current-corpus paired four-target latency | `PREFLIGHT REJECTED / BLOCKED` | Two three-task preflights executed and were rejected; 0 of 3 tasks accepted; the 306-layout full array was not submitted |
| Vendor commercial-geometry track | `PROPOSED` | Requires licensing, segmentation, and matching validation quantities |
| Fabricated-board validation | `NOT STARTED` | Required for hardware-accuracy claims |

Operational progress changes more frequently than scientific status. The dated
[Live Execution](Live-Execution.md) page owns task counts and the next scheduler
transition.

## Next scientific stages

1. Retain the admitted archived-target
   [family-held-out accuracy result](../results/Corpus-V4-Accuracy.md) under
   `C-ACC-001` without relabelling it as FEM-v2 evidence.
2. Use the current
   [FEM-v2 family-held-out result](../results/Corpus-V4-FEM-v2-Accuracy.md)
   under `C-ACC-FEMV2-001` for the deterministic one-thread target package.
3. Design and freeze a new paired-latency protocol around the admitted
   designated checkpoint. `C-LAT-001` remains closed until that separate
   execution and admission chain completes.
4. Repeat baseline, strict E(3), and ranking studies only under their own
   FEM-v2 frozen protocols.
5. Admit claims in the wiki before generating a new paper snapshot.

There are separate admitted family-crossed results for the archived 25-thread
target package and the deterministic one-thread FEM-v2 package. There is no
current-corpus paired speed headline, mesh-converged capacitance result, or
hardware-accuracy claim.
