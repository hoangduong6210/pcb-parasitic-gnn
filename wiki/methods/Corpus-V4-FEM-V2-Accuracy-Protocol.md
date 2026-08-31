---
title: Corpus V4 FEM-v2 Accuracy Protocol Index
status: revision index
last_updated: 2026-08-31
paper_source: false
---

# Corpus V4 FEM-v2 Accuracy Protocol Index

This page is the stable entry point for the deterministic one-thread FEM-v2
accuracy lifecycle. Protocol revisions have separate inputs, execution locks,
result roots, and admission decisions. Artifacts must not be mixed across
revisions.

| Revision | State | Scope |
|---|---|---|
| [v2](Corpus-V4-FEM-V2-Accuracy-Protocol-v2.md) | `SUPERSEDED; DIAGNOSTIC EXECUTION CLOSED` | All 25 fixed-epoch checkpoint tasks completed, but the process could read held-out bytes before checkpoint acceptance. No held-out inference or scientific result was admitted. |
| [v3](Corpus-V4-FEM-V2-Accuracy-Protocol-v3.md) | `FINALIZED; ARCHIVE VALIDATED; CLAIM ADMITTED` | Split-scoped inputs and a filesystem sandbox enforced the local pre-acceptance byte boundary; all 25 checkpoints were accepted before held-out inference, and the archived result supports `C-ACC-FEMV2-001`. |

The revision boundary and non-reuse rule are recorded in
[Decision 0003](../decisions/0003-accuracy-protocol-revision-boundary.md).
These pages define methods and lifecycle. The admitted model result is maintained
separately in [Corpus V4 FEM-v2 Family-Held-Out Accuracy](../results/Corpus-V4-FEM-v2-Accuracy.md).
