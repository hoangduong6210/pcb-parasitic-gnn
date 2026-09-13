---
title: FEM-v2 Coordinate-Update Ablation Design
status: proposed; implementation in progress
last_updated: 2026-09-13
paper_source: false
prose_reviewed: true
claim_ids: C-E3-FEMV2-001
---

# FEM-v2 Coordinate-Update Ablation Design

## Research question

Does learning coordinate updates improve numerical-reference prediction over
a fixed-coordinate distance-message network on the existing FEM-v2 benchmark?
Both alternatives have E(3)-invariant scalar outputs on the encoded graph.
This experiment therefore tests coordinate updates, not the presence versus
absence of equivariance. The admitted original GNN and pooled baselines are
contextual comparisons, not controlled arms of this experiment.

## Planned comparison

Three arms use the same train-only inputs and frozen family partitions:

1. A coordinate-update distance-message network of width 96 and four message
   layers. Only the first three layers update coordinates, because a final
   coordinate update after the last message cannot affect the scalar readout.
2. A fixed-coordinate network of the same width. Its shared initial tensors
   are copied to the coordinate-update arm and their equality is recorded.
3. A fixed-coordinate network with width chosen by analytical parameter count
   to be closest to the coordinate-update arm. Width selection never uses
   validation or test performance.

The planned grid reuses five family splits crossed with five initialization
seeds: 25 cells and 75 arm checkpoints. The existing 200-epoch optimization
budget is retained without tuning or early stopping. Each arm starts from
explicitly seeded initialization and uses the same local minibatch-order
sequence within a cell. Validation remains diagnostic. No R4 observation
participates in fitting, selection or the primary comparison.

## Representation and symmetry boundary

Coordinates use one isotropic training-derived scale. The six remaining node
attributes and three retained edge attributes use train-only scalar moments.
Edge columns 1, 5 and 6 are retained as metadata; raw relative-vector channels
and duplicate stored distance are excluded. Every message layer recomputes
squared distance from its coordinate state.

Layer identifiers, conductor dimensions, overlap and edge flags are held
fixed under transformations of the encoded graph. The axis-aligned graph
builder is outside this symmetry statement. Rotating raw CAD or layout files
and rebuilding their graphs is not proved by these checks.

Target preprocessing follows the current positive-reference log1p convention
and inverse expm1 without clipping. It does not reuse the historical signed-log
evaluation or independent x/y/z normalization.

## Planned analysis

The primary metric is family-macro MAPE for each of the four targets. Both
coordinate-update-minus-fixed comparisons are reported in percentage points;
positive differences favor the fixed-coordinate control. Shared crossed-axis
split/initialization resampling produces descriptive sensitivity intervals,
not population confidence intervals. An interval containing zero is not proof
of equivalence or evidence that coordinate updates never help.

Nonpositive predictions and joint inductance PSD diagnostics are retained
without repair. Lower accuracy is not an integrity failure. Symmetry checks,
artifact identity and held-out isolation are integrity gates.

## Implementation review and execution gates

The historical corpus runner constructs its models before setting its seed;
the new implementation must set seeds before construction. Matching seeds
alone does not pair shared tensors when extra coordinate modules consume
random draws. Explicit shared-state copying is required for the same-width
pair. Historical experiment imports also load solver modules, so the new
model module must be solver-free.

The historical last-layer coordinate branch is not prediction-active.
Omitting it changes the architecture and will be recorded as a new version,
not a correction to old evidence. Matching parameter counts is only a capacity
control and does not make different function classes identical.

Training remains disabled until the source and execution lock, task-private
sandbox, safe arm-specific checkpoints, complete admission, held-out finalizer
and archive reconstruction are implemented and reviewed. Synthetic model
checks can qualify implementation behavior but cannot establish predictive
benefit. All corpus training and scientific qualification jobs use SLURM.

The [live status](../status/Live-Execution.md) owns job progress. No predictive
result or new symmetry residual is admitted by this design page.
