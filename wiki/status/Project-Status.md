---
title: Project Status
status: RUNNING; TCAD reference qualification
last_updated: 2026-10-03
paper_source: false
---

# Project Status

The owner set a continuing [Q1 journal goal](Q1-Journal-Goal.md) on 2026-10-03,
with TCAD preferred. Research implementation may proceed through the frozen
scientific gates; journal acceptance, claim admission and author release are
not inferred from that instruction.

The owner approved implementation on 2026-10-02 with TCAD as the target.
Stage 1 of the [TCAD research plan](../manuscript/TCAD-Research-Plan.md) now has
a geometry-selected panel and bounded local-refinement pilot implementation.
The [pilot evidence record](../evidence/TCAD-Cps-Reference-Pilot.md) owns the
current validation, publication and scheduler state; no new result is admitted.
The first pilot is now terminal and incomplete: two sentinels completed, while
the largest sentinel hit the frozen mesh-node cap. No job in this pilot chain
remains active. Terminal evidence is now archived; the owner authorized a
separately versioned [compact-support feasibility study](../methods/TCAD-Cps-Compact-Support-Recovery.md)
on the failed largest sentinel, with original caps unchanged.
That study also closed incomplete, at the local0 AMG-complexity cap before CG.
Its terminal evidence is archived. The subsequent
[same-matrix AMG diagnostic](../methods/TCAD-Cps-AMG-Diagnostic.md) completed
successfully on toy and local0 without widening worker caps. No job in that
chain remains active. Terminal evidence is now archived, and the owner approved
a new [seven-arm sensitivity implementation](../methods/TCAD-Cps-AMG-Feasibility.md).
The frozen source is published and remote-hash verified; its new smoke and
fresh local0 passed. The seven-arm job then closed incomplete at local1's
mesh-generation time cap; its afterany finalizer retained the failure. Both
jobs are terminal and the complete terminal artifact closure is archived. A
sparse execution checkout preserves the locked source while avoiding the
file-count quota that blocked a full checkout. The
[feasibility evidence](../evidence/TCAD-Cps-AMG-Feasibility.md) owns source,
smoke and scheduler receipts. A separately versioned
[mesh-only HXT probe](../methods/TCAD-Cps-Mesh-Probe.md) also closed incomplete:
toy passed, but local1 reached its time cap during 3D improvement and the repeat
was not run. Its 11-file terminal closure is archived. The separate bounded
[optimization-isolation diagnostic](../methods/TCAD-HXT-Optimization-Isolation.md)
also closed incomplete: the unoptimized toy failed its strict signed-quality
gate, so sentinel modes were not run. Its eight-file terminal closure is
checked. The [explicit-optimizer follow-up](../methods/TCAD-HXT-Explicit-Optimization.md)
is now terminal and archived. Toy passed its diagnostic gate with ill-shaped
elements; local1 timed out during explicit optimization and the repeat was
not run. No diagnostic job in this chain remains active. No sensitivity
conclusion is available from these incomplete studies.
Backend agreement does not qualify a reference or authorize training.
The [dielectric-only formulation](../methods/TCAD-Dielectric-Only-Formulation.md)
now has a source-only electrical/topology contract and synthetic classifier
tests. Its bounded native CAD diagnostic now passed toy, selected sentinel and
fresh-repeat gates, with a checked terminal archive. Boundary-aware meshing and
numerical qualification remain unperformed for this new formulation.
Its [boundary-mesh audit](../methods/TCAD-Dielectric-Boundary-Mesh.md) now has
synthetic/fake-native extraction and topology tests. A separate
[guarded integration](../evidence/TCAD-Dielectric-Boundary-Mesh.md) and new
frozen mesh protocol now exist; post-freeze validation and publication remain
before any real mesh run at this checkpoint.
The canonical preservation boundaries remain in
[Research Pause and Handoff](Research-Pause-Handoff.md). Completed pipelines
remain closed; a new protocol does not continue a historical `PENDING` entry.

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
| TCAD reference-qualification continuation | `REJECTED PILOT; REVIEW PENDING` | Smoke validated; two sentinels complete, third stopped at the frozen mesh-node cap; finalizer rejects incomplete coverage; no convergence claim or training authorization |
| TCAD compact-support recovery | `REJECTED; INCOMPLETE` | Local0 exceeded the frozen AMG-complexity cap before CG; terminal failure archived; all sensitivity checks remain unavailable |
| TCAD same-matrix AMG diagnostic | `VALIDATED; TERMINAL ARCHIVE CHECKED` | Toy and local0 passed exact-system/direct comparison within unchanged worker caps; no mesh-converged reference or automatic expansion |
| TCAD AMG seven-arm feasibility | `REJECTED; TERMINAL ARCHIVE CHECKED` | Smoke and local0 passed; local1 hit the mesh-generation time cap; five arms unrun; no sensitivity, training or paper claim |
| TCAD mesh-only HXT probe | `REJECTED; TERMINAL ARCHIVE CHECKED` | Toy passed; local1 timed out in native 3D improvement; repeat unrun; no field solving or cap increase |
| TCAD HXT optimization isolation | `REJECTED; TERMINAL ARCHIVE CHECKED` | Toy failed strict signed quality; sentinel and repeat unrun; no field use or cap/quality relaxation |
| TCAD HXT explicit optimization | `REJECTED; TERMINAL ARCHIVE CHECKED` | Toy diagnostic passed with ill-shaped elements; sentinel optimizer timeout, repeat unrun; no field or reference qualification |
| TCAD dielectric-only formulation | `PROPOSED; CAD PREREQUISITE VALIDATED` | Electrical equivalence boundary and retained CAD domain; mesh and field qualification pending |
| TCAD dielectric-domain CAD diagnostic | `VALIDATED; TERMINAL ARCHIVE CHECKED` | Toy, selected sentinel and exact fresh-repeat CAD contract passed; no meshing, solving or reference qualification |
| TCAD working draft | `WORKING DRAFT` | Author-reported Codex disclosure; inherited scientific results unchanged |
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
| FEM-R3P16 repeatability diagnostic | `POSTTERMINAL NEGATIVE` | Corrected 30-solve run: the existing 25-thread path failed mesh identity and repeatability on all three anchors; the one-thread diagnostic passed both on all three; the 25-thread paired-latency chain is explicitly not authorized |
| One-thread FEM reference qualification | `COMPLETE` | Nine-layout R3 and three-sentinel R4 repeatability passed; finite-panel domain sensitivity passed; finite-panel adjacent-mesh sensitivity was negative |
| Deterministic one-thread FEM-v2 dataset | `FINALIZED; POSTTERMINAL ADMITTED` | 1,500 R3 plus 198 R4 observations over 1,500 geometries; its dataset receipt keeps training closed, while the separate downstream accuracy lock governs model execution |
| FEM-v2 accuracy protocol v2 | `SUPERSEDED; DIAGNOSTIC EXECUTION CLOSED` | 25 checkpoint tasks completed, but the process materialized held-out bytes before acceptance; no held-out inference or model claim was admitted |
| FEM-v2 accuracy protocol v3 | `FINALIZED; ARCHIVE VALIDATED; CLAIM ADMITTED` | The 5 by 5 family-split and initialization grid is complete; all 25 checkpoints were accepted before held-out inference; the tracked archive supports `C-ACC-FEMV2-001` |
| FEM-v2 paired four-target latency | `FINALIZED; ARCHIVE VALIDATED; CLAIM ADMITTED` | All 306 observations accepted; recovery finalizer and clean-tracked archive replay passed. `C-LAT-FEMV2-001` supports the specified warm-loaded GNN versus sequential FastHenry-plus-one-thread-FEM-R3P16 all-four-target comparison |
| Vendor commercial-geometry track | `PROPOSED` | Requires licensing, segmentation, and matching validation quantities |
| FEM-v2 fixed pooled-feature baselines | `ADMITTED; VERSION-SCOPED` | Fixed-budget post-hoc comparison supports `C-BASE-FEMV2-001`; no causal graph advantage or tuned-baseline claim |
| FEM-v2 coordinate-update ablation | `ADMITTED; VERSION-SCOPED` | All 75 checkpoints, held-out analysis and tracked replay passed; `C-E3-FEMV2-001` states that the fixed study did not establish a consistent coordinate-update accuracy gain |
| Fabricated-board validation | `NOT STARTED` | Required for hardware-accuracy claims |
| IEEE Journal Snapshot 1.1 | `PUBLISHED; TAG AND CI VERIFIED` | Expanded eleven-page export of the twelve admitted claims; no research execution was reopened |
| IEEE Journal Snapshot 1.1.1 | `PUBLISHED; TAG AND CI VERIFIED` | Figure-only correction to Figs. 1, 2, 5, 7, and 9; claims, data, and citations unchanged |

The dated [Live Execution](Live-Execution.md) page preserves prior task counts
and scheduler transitions. The [handoff page](Research-Pause-Handoff.md) owns
the historical pause and current restart boundary.

## Preserved results and deferred stages

1. Retain the admitted archived-target
   [family-held-out accuracy result](../results/Corpus-V4-Accuracy.md) under
   `C-ACC-001` without relabelling it as FEM-v2 evidence.
2. Use the current
   [FEM-v2 family-held-out result](../results/Corpus-V4-FEM-v2-Accuracy.md)
   under `C-ACC-FEMV2-001` for the deterministic one-thread target package.
3. Preserve the admitted [paired latency result](../results/Corpus-V4-FEM-v2-Latency.md)
   under `C-LAT-FEMV2-001`, including its timing boundary, fixed fidelity,
   designated checkpoint, and descriptive sensitivity interval.
4. Preserve the admitted, version-scoped [coordinate-update result](../results/Corpus-V4-FEM-v2-Coordinate-Ablation.md)
   without converting it into an equivalence or universal EGNN claim. Preserve the separately admitted
   [fixed-baseline comparison](../results/Corpus-V4-FEM-v2-Baselines.md).
   Any ranking study requires its own FEM-v2 frozen protocol.
5. For any future study, admit claims in the wiki before generating another
   paper snapshot. The current journal export is
   [`Paper/Paper_Journal_Snapshot_1/`](../../Paper/Paper_Journal_Snapshot_1/).

There are separate admitted family-crossed results for the archived 25-thread
target package and the deterministic one-thread FEM-v2 package. There is no
mesh-converged capacitance result or hardware-accuracy claim. The admitted
paired speed result applies only to its explicitly defined workflow.
