---
title: Research System Map
status: canonical architecture
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
---

# Research System Map

The project maintains one chain from physical abstraction to publication:

```text
layout contract
    -> conductor boxes and centers
    -> graph representation
    -> FastHenry inductance observations
    -> electrostatic FEM capacitance observations
    -> fidelity-explicit dataset and family splits
    -> GNN training and held-out evaluation
    -> finalized evidence and scoped claims
    -> paper snapshot
```

Geometry is the shared boundary. Graph construction, FastHenry, and FEM receive
the same accepted conductor boxes, centers, net identities, stackup, and units.
This prevents one target from describing a topology different from the graph
seen by the surrogate.

The GNN is evaluated as a surrogate of a declared numerical workflow. Agreement
with that workflow, numerical sensitivity between fidelity levels, and agreement
with hardware are separate questions. The current pipeline addresses the first
two. Fabricated-board validation remains future work.

## Control planes

| Plane | Responsibility |
|---|---|
| Scientific protocol | Dataset scope, solver settings, split policy, seeds, metrics, and acceptance gates |
| Execution protocol | Source commit, environment, batch-script hash, resources, task mapping, retry policy, and finalization |
| Evidence | Immutable task records, raw outputs, summaries, hashes, and negative results |
| Claim governance | Exact permitted language, scope, uncertainty, status, and evidence mapping |
| Publication | Selection and editing of admitted wiki content into an immutable snapshot |

No control plane substitutes for another. A successful scheduler job is not a
scientific result, and a well-written paragraph is not evidence.
