---
title: Strict E3 Property and EGNN Ablation
status: admitted implementation property; predictive result historical
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
evidence_id: E-V2-E3-01
claim_ids: C-E3-001
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

The predictive comparison is not part of this admitted implementation claim.
Its historical result and inconclusive interpretation are recorded as
`H-E3-001` in the [Historical Claim Ledger](../claims/Historical-Claim-Ledger.md).
