---
title: Corpus and Target Contract
status: active specification
last_updated: 2026-08-19
paper_source: false
---

# Corpus and Target Contract

## Geometry root

The active corpus contains 1,500 unique synthetic active-leg layouts. Every
layout satisfies the following contract:

- physical height is derived from layer and stackup;
- conductor boxes are board-contained, distinct, and non-overlapping;
- same-layer conductors meet the declared edge-clearance rule;
- geometry identity is a SHA-256 digest of canonical layout content;
- graph and numerical solvers receive the same boxes and centers;
- label observations must retain the geometry identity that produced them.

The scope is limited to co-directed, series-connected active legs. Returns,
vias, terminals, planes, core windows, and complete routed loops are excluded.

## Fidelity registry

Capacitance is represented as observations rather than one unlabeled truth
column.

| Fidelity ID | FEM setting | Role | Admission state |
|---|---|---|---|
| `FEM-R1P8` | refine-1, pad 8 mm | Archival source-corpus value | Historical |
| `FEM-R2P12` | refine-2, pad 12 mm | Lower-cost numerical observation | Not a validated truth |
| `FEM-R3P16` | refine-3, pad 16 mm | Bulk fixed numerical target | 1,500 tasks validated and jointly finalized |
| `FEM-R4P16` | refine-4, pad 16 mm | Higher-fidelity validation observation | 198 tasks validated and jointly finalized |

`FEM-R3P16` was selected for bulk generation because it is reproducible,
computationally feasible, and stable to the tested domain expansion. Its failed
mesh gate is retained as part of the target definition. `FEM-R4P16` is more
resolved, but it has not been compared with refine-5 and is not called continuum
truth or physical ground truth.

The FastHenry inductance observations remain separate targets and retain their
original full-precision records. A multi-fidelity Cps finalizer must not round
trip those values through graph-training `float32` arrays.

## Observation schema

Each numerical observation must retain:

```text
layout_id, geometry_sha256, geometry_family_id,
target, units, fidelity_id, value,
solver backend and version, refine, pad_mm, eps_r,
mesh nodes and tetrahedra, AMG levels and operator complexity,
iterations, solver info, relative residual,
system fingerprint, wall time, peak RSS,
resource and numerical gate results,
source, environment, protocol, and artifact hashes
```

Missing higher-fidelity data must remain missing. Loaders must never silently
replace FEM-R4P16 with FEM-R3P16.

## Higher-fidelity subset

Families are defined by the unordered turn-count pair. The registry retains all
nine layouts from the frozen convergence study as mandatory anchors. Their
earlier selection used capacitance order statistics. The remaining 189 entries
are selected with geometry-only descriptors and deterministic hash
tie-breaking, yielding three designs per family. The complete registry contains
198 unique designs across 66 families and was hashed before the production R4
solves. No newly observed R3/R4 discrepancy was used to alter membership.

The completed production audit found FEM-R3P16 greater than FEM-R4P16 in all
198 matched entries. The selected-registry median relative discrepancy was
8.479%, with an observed range of 2.754% to 17.517%. These values describe the
exact deterministic panel; they are not a probability-sampled estimate for the
full corpus and do not establish R4 as truth.
