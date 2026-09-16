---
title: Coordinate Ablation Claim Admission
status: ADMITTED
date: 2026-09-15
paper_source: false
---

# Coordinate Ablation Claim Admission

## Decision

The project owner admits `C-E3-FEMV2-001` as a version-scoped result. Across
five family-split seeds crossed with five initialization seeds on the previously
evaluated synthetic FEM-v2 benchmark, the fixed-budget study did not establish
a consistent accuracy gain from coordinate updates relative to same-width and
approximately parameter-matched fixed-coordinate controls. All eight
descriptive crossed-axis 95% intervals included zero.

## Basis

All 75 checkpoints passed their unchanged validation and trained-symmetry
gates. Held-out finalization produced the frozen cardinalities, numerical
reconstruction passed, and a clean checkout reproduced the analysis while
verifying the Git-tracked evidence closure. Independent review checked the
direction of every paired contrast, the interval semantics and the symmetry
scope. The [evidence ledger](../evidence/Evidence-Ledger.md#e-c4-e3-femv2-analysis-01--coordinate-update-ablation)
owns operational provenance.

## Boundary

This decision does not admit equivalence between arms, “EGNN does not help,”
predictive superiority of coordinate updates, arbitrary-PCB generalization,
physical accuracy or an inference-runtime comparison. Both coordinate-update
and fixed-coordinate arms have invariant scalar outputs on encoded graphs, so
the experiment is not an equivariance-versus-non-equivariance comparison.

The admitted wiki result remains operationally linked and is not directly a
paper source. A paper change requires an explicit snapshot request followed by
curation into operational-detail-free IEEE prose under the paper export
contract. The submitted summary snapshot remains unchanged.
