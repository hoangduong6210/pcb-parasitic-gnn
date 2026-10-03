---
title: TCAD Native Field Probe API Qualification
status: PROPOSED
last_updated: 2026-10-03
paper_source: false
---

# TCAD Native Field Probe API Qualification

## Purpose and boundary

The [failed edge-local attempt](../evidence/TCAD-Edge-Feasibility.md) stopped
before meshing because its list-based view lacked the model-entity support
required by `Field::putOnView`. This separate tiny synthetic qualification
tests a model-backed adapter, not a new sizing policy. The analytic finite
segment field, linear Threshold and independent exact-distance oracle are
retained from frozen source. No actual dataset geometry is used.

Create temporary discrete point elements and nodes in an isolated named model,
attach a scalar NodeData view, then select the original model before invoking
MeshSizeFieldView so its field manager is used. Read model-backed output with
node tags; verify complete tag/coordinate identity, type, components and finite
values. Remove the view and exactly the temporary model, restore the original
current model, and check the original CAD, fields, options and empty mesh are
unchanged. Record native raw values before applying numeric acceptance gates.
No planar or volume mesh generation, PDE solving or training is allowed.

The [official Gmsh manual](https://gmsh.info/doc/texinfo/) defines model-based
NodeData, discrete entities and explicit node/element insertion. The official
[4.15.2 release source](https://gmsh.info/src/gmsh-4.15.2-source.tgz),
`examples/api/view.py`, demonstrates the model-backed data path;
`src/plugin/MeshSizeFieldView.cpp` resolves fields from the current model.
These support the adapter design, but only the new SLURM study can establish
native compatibility in the pinned runtime. Imports/initialization and every
native operation remain below allocation, source and runtime guards.

## Prospective checks

Use a small fixed synthetic rectangle fixture with duplicate and one-ULP
separated projections. Probe endpoints, interior/boundary, transition/far and
oblique endpoint offsets using the existing independent exact projection.
Retain near/far settings and probe tolerances; test distance and size separately.
Fresh-worker repeat must be byte-identical, excluding runtime telemetry.
The fixture is capped at 512 points. Each fresh worker has a 180-second,
2-GiB watchdog; the SLURM request is one CPU, 8 GiB and ten minutes, no requeue.
Each JSON member is capped at 2 MiB. These are synthetic API-study bounds, not
changes to any real-layout mesh, quality or resource gate. Explicitly inserted
0D probe elements are reported separately from native planar/volume generation.
Fake-native tests must model the entity/view distinction and exercise failed
plugins, invalid data and cleanup/restoration. They are not native proof.

Freeze source, input definition, resource bounds and failure-preservation rules
before one bounded SLURM submission. Stop on failure with no automatic retry.
Even a pass opens only the prerequisite for a newly frozen real-layout probe/
mesh integration; no mesh, reference, field-accuracy or publication gate opens.
The [evidence owner](../evidence/TCAD-Native-Field-Probe.md) records progress.
