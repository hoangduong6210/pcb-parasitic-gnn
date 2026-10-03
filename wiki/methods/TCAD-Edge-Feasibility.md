---
title: TCAD Edge-Local Planar Feasibility
status: PROPOSED
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Planar Feasibility

## Question and scope

Can a separately defined perimeter-distance size field reduce planar workload
enough for the unchanged column capacity and conditioning gates? The
[archived sizing diagnosis](../evidence/TCAD-Sizing-Budget.md) motivates this
question but does not predict the new native mesh. This is not a retry of the
rejected filled-footprint Box field or a mesh-accuracy claim.

The new protocol is `protocols/tcad_cps_edge_feasibility_v1.json`. All actual
layout calculations, native probes and meshing require a verified running
SLURM allocation, compute hostname, frozen source and runtime. Only tiny
synthetic checks and byte/scalar metadata validation run on the login node.

## Definition fixed before native execution

Retain the four original finite x/y perimeter segments of each conductor,
including owner identity, coincident projections and near-coincident boundaries.
No coordinate snapping, merging or geometry repair is introduced. Decimal
expression literals round-trip to the original stored floating-point value.

For an axis-aligned segment with fixed coordinate c and along-axis interval
[a,b], use the analytic distance
`sqrt((fixed-c)^2 + max(a-along, 0, along-b)^2)`.
One native MathEval field represents each segment; Min combines their distances.
A linear Threshold maps this distance to the inherited nominal near/far sizes.
Its near plateau ends at 0.055 mm and its far plateau begins at that distance
plus the inherited transition thickness. SizeMin/SizeMax, vertical refinement,
planar capture caps, prospective volume caps, quality and geometric tolerances
are unchanged. Conductor-face interiors may become coarser: later field and
sensitivity qualification must test the consequences.

Explicit option changes are `Mesh.AlgorithmSwitchOnFailure=0` and
`Mesh.MeshSizeFactor=1`. The former disables an otherwise default algorithm
fallback; this is not described as an unchanged mesher. All other original
first-order, single-threaded planar options remain fixed.

## Independent field checks and retained audits

Before meshing, preserve effective field metadata and compare native distance
and size values against an independent exact-rational orthogonal-projection
calculation at deterministic endpoints, midpoints, normal offsets, oblique
endpoint extensions, domain corners and box centers. The normal offsets cover
plateau, transition and far regimes. Identical probe coordinates are deduplicated;
geometry is not. Preserve the finite-valued comparison report before applying
the declared relative/absolute tolerances. Malformed native views or nonfinite
values stop execution with logs and earlier artifacts retained, without meshing.
Probe success does not establish electrical or mesh accuracy.

The native MeshSizeFieldView plugin is used twice, once for distance and once
for final size; view identity, coordinates, shape and finiteness are checked.
No Gmsh Distance/curve-sampling approximation is substituted for the formula.
Counts and expression/probe sizes are bounded in the protocol.

The original one-fragment planar CAD, ownership/leakage, manifold topology,
raw array preservation, z-only refinement, complete prism-template condition
certificate and prospective volume/capacity audits are reused unchanged.
Toy, sentinel and fresh-session sentinel repeat run once, with no retries.
Any worker/CAD/planar-audit failure stops subsequent modes. A completed failed
prospective gate remains evidence and does not trigger cap expansion. Repeat
requires byte-identical reports and raw bundle identity, excluding telemetry.

## Source review and remaining qualification

The official [Gmsh manual](https://gmsh.info/doc/texinfo/) documents MathEval,
Min, linear Threshold, MeshSizeFieldView and algorithm-switch defaults. Its
Distance tutorial uses sampled curve points. The official
[4.15.2 release source](https://gmsh.info/src/gmsh-4.15.2-source.tgz), specifically
`src/plugin/MeshSizeFieldView.cpp`, confirms in-place evaluation on the selected
view. `src/numeric/mathEvaluator.cpp` and `contrib/MathEx/mathex.cpp` confirm
the expression parser and Max/Sqrt/power support. These were inspected before
protocol freeze; no native initialization was performed on the login node.

Even a feasible result is not a volume mesh or reference. Next requirements
include full 3D boundary/terminal/volume/conditioning audits, an analytic-box
check, same-mesh field restrictions, charge/energy/residual checks and mesh/
domain sensitivity. Reference, training and manuscript-claim gates stay closed.
The [evidence owner](../evidence/TCAD-Edge-Feasibility.md) records execution state.
