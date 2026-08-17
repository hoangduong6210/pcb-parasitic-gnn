---
title: FastHenry Inductance Reference
status: current numerical method
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
citation_keys: ruehli, grover, fasthenry
---

# FastHenry Inductance Reference

FastHenry receives one rectangular conductor segment for every accepted trace.
The segment uses the same center, length, width, thickness, layer-derived height,
and net identity as the graph and geometry contract. Each trace is exposed as a
port. The complex impedance matrix at frequency \(f\) gives

\[
L_{ij}=\frac{\operatorname{Im}(Z_{ij})}{2\pi f}.
\]

Primary and secondary self-inductances sum the diagonal terms and twice the
within-winding mutual terms. Winding mutual inductance sums the primary to
secondary matrix block. The reported \(M\) is therefore a free-space winding
quantity. It is not the core magnetizing inductance.

The geometry contract and passivity gate require finite positive self terms and

\[
|M| \leq \sqrt{L_pL_s}
\]

within the declared numerical tolerance. Cross-checks with an independent
Neumann implementation test the inductance computation, but neither route
models a nonlinear ferrite magnetic circuit, frequency-dependent permeability,
or a complete routed return path unless a later protocol explicitly adds them.
