---
title: Graph Surrogate Method
status: current implementation description
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
citation_keys: pytorch, gilmer, battaglia
---

# Graph Surrogate Method

Each conductor trace becomes a graph node. The nine node features are its center
coordinates, width, length, thickness, logarithmic conductivity, surrounding
relative permittivity, and normalized layer index. Directed coupling edges carry
distance, overlap area, signed relative coordinates, and capacitive or inductive
type flags.

The baseline model is a four-layer PyTorch message-passing network. Each layer
forms edge-conditioned messages from source state, destination state, and edge
features. Destination nodes receive the mean of incoming messages and apply a
residual normalized update. Graph readout concatenates mean, maximum, and
log-compressed sum pooling before a two-hidden-layer regression head returns four
scalars.

The outputs are \(C_{ps}\), \(L_p\), \(L_s\), and \(M\). Target normalization is
fitted on the active training partition and inverted at evaluation time. A model
result is meaningful only with its dataset, split registry, initialization seed,
checkpoint, target fidelity, and timing boundary.

## Representation caveat

The baseline receives absolute coordinates and signed relative vectors. It is
permutation-invariant at graph readout, but it is not invariant to an arbitrary
change of coordinate frame. The separate coordinate-update network provides the
tested strict E(3) property. Whether that inductive bias improves prediction is
an empirical question and is not implied by the algebraic property.

Current evaluation status and planned experiments are maintained in
[Project Status](../status/Project-Status.md), which is not paper-source prose.
