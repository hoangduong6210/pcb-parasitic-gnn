---
title: TCAD Sizing Budget Diagnostic Evidence
status: VALIDATED diagnostic; conditional sentinel budget exceeded, no candidate admitted
last_updated: 2026-10-03
paper_source: false
---

# TCAD Sizing Budget Diagnostic Evidence

The [method contract](../methods/TCAD-Sizing-Budget.md) diagnoses the rejected
column policy without regenerating any mesh or changing caps. The previous
[column archive](TCAD-Column-Feasibility.md) remains immutable. The real-input
diagnosis completed with byte-identical sentinel repeats. No sizing candidate,
3D mesh, field result, reference or paper claim is admitted.

## Input bindings

- Parent protocol: `protocols/tcad_cps_column_feasibility_v1.json`, SHA-256
  `0e6451fb9ab44151c46090ef06ef4796bbe4c786a44d264fd545dcce18bd1149`.
- Terminal archive: `results/tcad/cps_column_feasibility_v1/archive/job_7653784/manifest.json`,
  SHA-256 `69e90937ffa35c26ebbea73b583582adc4e88232b375ebdfc358797769362183`.
- Frozen protocol: `protocols/tcad_cps_sizing_budget_v1.json`, SHA-256
  `34084a9ee2555c7c072152b9d178978fc0c7a321b7f6bc5fa3d45eb48cecd7b8`.
- Source/input lock: `protocols/tcad_cps_sizing_budget_v1.lock.json`, 425 dependencies,
  SHA-256 `0302408e78ab97312303cad5cdc4174ac725ab7a86d15e0e47bfd8760d5d5db5`.
- Toy uses archived toy CAD/sizing/stdout; local1 and repeat1 use the same
  archived local1 files. Repeat is not a repeated native-meshing attempt.

## Synthetic verification

Initial arithmetic tests passed 34 cases: hand-counted duplicate projections,
clipping, exact one-ULP strips, rational envelopes, full-owner vertical volumes,
independent capture/3D budgets, zero budgets and invalid/ambiguous log rejection.
The initial integration regression passed 85 tests with one expected pre-freeze
lock skip. It covers guard ordering, unchanged original caps, archived effective
sizing, report mutation rejection, no overwrite, failed-budget retention and
byte/scalar-only review. Additional path-safety and partial-attempt tests passed
in the 304-test pre-freeze regression with one expected lock skip. The frozen
regression then passed **305 tests, zero skips**, in 43.39 seconds. The research
prose audit passed. These are tiny synthetic inputs, not real
layout or mesh analysis on the login node.

The source was frozen and published before one bounded SLURM submission.
Every complete output is retained. The full TCAD goal remains active.

## Source publication

At 14:28:53 UTC on 2026-10-03, GitHub main and local HEAD were verified as
`707ccae71b035294116a37c05ef9f22c3479f27c`. The final 55-test wiki/prose
recheck, prose audit and 7,242-file manifest passed. A new sparse execution
worktree passed source/wrapper/runtime preflight with 428 materialized tracked
files. One submission at 14:30:25 UTC returned **job 7655072**. No retries or
policy changes occurred. Source is published; terminal records remain local
pending a later push.

## Terminal observations on 2026-10-03

Accounting at 14:32:24 UTC reported `COMPLETED/0:0`, zero restarts, 78 seconds,
three allocated CPUs and 8 GiB on `a0113`. The job requested one scientific
CPU/thread; allocation CPU count follows the partition memory policy.
Toy, local1 and repeat1 all completed the frozen diagnostic. Sentinel reports
are byte-identical; this repeats arithmetic on the same archived inputs and
does not test native mesh repeatability.

| Reported quantity | Toy | Sentinel layout 597 |
|---|---:|---:|
| Canonical z-point count | 16 | 43 |
| Full-column planar-node allowance, including capture cap | 18,750 | 69,767 |
| Planar-triangle sufficient budget | 33,333 | 158,730 |
| Planar-triangle necessary ceiling | 38,461 | 175,438 |
| Nodes in archived native stdout, not audited by this study | 321 | 261,884 |
| Conditional full-column node bound from that log | 5,136 | 11,261,012 |
| Original 3D-node cap | 300,000 | 3,000,000 |
| Conditional full-column bound within cap | Yes | No |

The sentinel owner groups retain 38 to 42 vertical intervals. Its original
planar-node capture cap remains 200,000, but the full-column 3D budget permits
only 69,767 planar nodes. Increasing capture capacity alone would therefore
not make the same logged mesh pass the existing conservative full-column gate.
This does not prove that every different or node-pruned construction is infeasible.
The mixed native total of 550,830 elements is not a verified triangle count.

Sentinel projected areas below are rounded renderings of exact rational report
values in mm²; the domain area is 6,397.630576 mm². The index is dimensionless
and is not a mesh-count prediction.

| Projected rectangle set | Exact-union area, rounded mm² | Step-field workload index, rounded |
|---|---:|---:|
| Canonical conductor footprints | 1,226.537539 | 191,969.683811 |
| Archived near-size Box cores | 1,284.194579 | 200,974.992779 |
| Coordinate-expanded Thickness envelope | 1,744.631985 | 272,889.560014 |

Each sentinel set has 26 distinct clipped rectangles and 2,809 reference
endpoint cells. These are area-bookkeeping cells, not mesh cells. The complete
core/footprint area already dominates the step-field index; this motivates
examining where fine sizing is needed instead of attributing all cost to the
transition envelope. The diagnostic does not quantify native transition cost
or demonstrate that shrinking a halo would deliver any specified node count.

## Preserved terminal evidence

The additive collector passed 24 synthetic tests with one expected pre-collection
skip, then preserved and byte/metadata-checked 17 members: all three reports,
mode receipts/stdout/stderr, the attempt, submission receipt, scheduler logs
and raw accounting. No geometry/mesh replay was done on the login node.
The terminal regression passed **170 tests, zero skips**, in 70.88 seconds,
including actual archive byte/metadata validation; the prose audit passed.

- Archive: `results/tcad/cps_sizing_budget_v1/archive/job_7655072/manifest.json`,
  SHA-256 `da1c2edd357cf7fa85ddbf5fc37e962391d42bd421ef5bdd44e15da723c5c790`.
- Toy report SHA-256: `f6bbf261446366ea25aa6a377f1c87847fb02dc4cdf93d1a502465209ed77971`.
- Local1 and repeat1 report SHA-256:
  `d02a4e400059459e4c46c6e83d8fd9f8bf5e016ea36a0e7163c8d649aa54b43a`.

## Next research step

After terminal regression/publication, separately specify an edge-local planar
sizing candidate: retain canonical conductor perimeters and fine near-edge
resolution while investigating coarser face interiors, instead of imposing the
near size over every projected conductor interior. This is a hypothesis, not
an admitted policy or an accuracy guarantee. Freeze its distance/transition
definition, every parameter, original count caps and condition/topology gates
before native work; do not tune or retry the rejected Box policy in place.

First test exact/synthetic ownership and field coverage, then a new bounded
SLURM toy/sentinel/repeat feasibility study if justified. If a candidate passes,
it still needs full 3D boundary/terminal/volume and element-quality audits,
analytic-box and same-mesh field checks, and mesh/domain sensitivity before
reference qualification. Coarser interior sizing must not be assumed electrically
accurate. No field solve or learning run is authorized by this diagnostic pass.
