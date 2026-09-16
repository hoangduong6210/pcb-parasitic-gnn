---
title: Strict E3 Property and EGNN Ablation
status: admitted implementation property and version-scoped predictive ablation
last_updated: 2026-09-15
paper_source: true
prose_reviewed: true
evidence_id: E-V2-E3-01
claim_ids: C-E3-001, C-E3-FEMV2-001
citation_keys: egnn
---

# Strict E3 Property and EGNN Ablation

The coordinate-update network computes messages from invariant node scalars,
edge metadata, and squared pairwise distance. Its coordinate update is a scalar
weight times a relative coordinate vector. Under a rigid transformation

\[
x_i' = Qx_i + t, \qquad Q^TQ=I,
\]

squared distances and scalar messages remain unchanged, while every coordinate
update transforms by \(Q\). The pooled scalar output is invariant. This gives an
E(3)-equivariant coordinate path and an E(3)-invariant graph-level prediction on
the already encoded graph.

The claim is deliberately narrower than strict E(n). The executed proof uses
three-dimensional coordinates. It also holds stored overlap and edge-kind
scalars fixed, so it does not prove that an axis-aligned graph builder commutes
with arbitrary rotations of raw layout files.

## Numerical implementation check

Across 200 transformed encoded-graph cases, the maximum scalar-output residual
was \(3.919\times10^{-7}\) and the maximum coordinate residual was
\(1.407\times10^{-7}\), below the predeclared \(2\times10^{-5}\) tolerance.
This establishes an implementation property within floating-point tolerance.
It does not establish predictive superiority or physical accuracy.

The historical predictive comparison is separate from this implementation
property and remains recorded as `H-E3-001` in the
[Historical Claim Ledger](../claims/Historical-Claim-Ledger.md).

The later controlled FEM-v2 experiment compared learned coordinate updates with
same-width and approximately parameter-matched fixed-coordinate controls. All
three arms retained E(3)-invariant scalar outputs on encoded graphs. Across five
family-split seeds crossed with five initialization seeds, all eight descriptive
crossed-axis intervals for the paired target differences included zero. The
study therefore did not establish a consistent accuracy gain from coordinate
updates under its fixed protocol. This is not equivalence, an
equivariance-versus-non-equivariance comparison, or a universal conclusion about
EGNNs. The admitted values and interpretation are recorded in the
[coordinate-update result](../results/Corpus-V4-FEM-v2-Coordinate-Ablation.md)
under `C-E3-FEMV2-001`.
