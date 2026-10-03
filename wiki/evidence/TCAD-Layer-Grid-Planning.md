---
title: TCAD Layer-Grid Planning Evidence
status: REJECTED candidate; planning diagnostic complete; terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD Layer-Grid Planning Evidence

## Terminal observation on 2026-10-03

At **11:13:19 UTC**, accounting showed job `7652593` terminal
`COMPLETED/0:0`, zero restarts, 61 elapsed seconds, three allocated CPUs and
8 GiB on `a0113`. It was absent from the queue. One CPU was requested and
scientific thread settings remained one. Toy/local1/repeat1 all completed;
local1 and repeat1 reports match byte-for-byte. Diagnosis completion is true,
but **planning feasibility is false**. No 3D mesh was allocated or generated.

| Prospective grid quantity | Toy | Selected sentinel, layout 597 |
|---|---:|---:|
| Axis point counts (x, y, z) | 24, 16, 12 | 696, 436, 39 |
| Total Cartesian cells | 3,795 | 11,488,350 |
| Dielectric cells after exact conductor-range exclusion | 3,489 | 11,198,620 |
| Full tensor-node upper bound | 4,608 | 11,834,784 |
| Prospective dielectric tetrahedra | 20,934 | 67,191,720 |
| Unchanged node cap | 300,000 | 3,000,000 |
| Unchanged tetrahedron cap | 1,500,000 | 20,000,000 |
| Node/tetrahedron preflight checks | pass / pass | fail / fail |
| Conservative Jacobian-condition screen | fail | fail |
| Complete report bytes | 6,148 | 75,124 |

The node count is conservative because unused metal-interior nodes could later
be removed. The tetrahedron count is the exact prospective count for the declared
six-simplices-per-dielectric-cell rule, so the failed tetrahedron cap is not an
artifact of that node bound. None of these are measured mesh/solver counts.

Both plans contain adjacent **auxiliary support planes**, not conductor/domain
faces, separated by exactly `1/36028797018963968` mm. Toy's pair is stored as
`0.19` and `0.19000000000000003`; the sentinel pair is
`0.13999999999999999` and `0.14`. The reports preserve hexadecimal coordinates
and show that neither pair belongs to the canonical-plane list. This follows
from inserting independently rounded expanded-projection endpoints into the
grid, rather than from a demonstrated tiny gap in the physical conductor
geometry. The planner correctly retained, exposed and rejected these intervals.
Do not snap canonical geometry to conceal this mesh-policy defect.

The global projected near-spacing rule also propagates fine spacing across the
whole tensor product, producing the sentinel capacity failure. Addressing only
the tiny auxiliary gap would not establish capacity or field accuracy. The
original caps and condition threshold have not been relaxed.

Parent-observed worker times were 14.023236042121425, 9.016345812007785 and
9.019290708005428 seconds for toy/local1/repeat1. Worker-reported times were
6.832780083175749, 4.326879068976268 and 4.333569512935355 seconds, including
metadata/review/report/source checks; peak worker RSS stayed below 0.025 GiB.
These timings are not meshing, field-extraction or speedup measurements.

## Checked terminal archive

The additive collector passed 24 synthetic tests before collecting all
**17 terminal members**: three complete plans with receipts/stdout/stderr,
attempt metadata, scheduler logs, accounting and submission. Byte/source/
identity/coverage/repeat checks passed without regenerating real axes on login.

- [Archive manifest](../../results/tcad/cps_layer_grid_plan_v1/archive/job_7652593/manifest.json)
  SHA-256: `8b66fc27509b53f3f42e7da1b546926666b9da1a64b507a75384acab198b4d4c`.
- Attempt SHA-256: `d0b86a059f1ba67cfb3626d609d442c97a5ad381fd1ae2862b2f963609c96c06`.
- Toy report SHA-256: `64330ad79a9957f3b677685ae8ca4ca348e26b4de48f94ecf676c3ab17c5907f`.
- Local1 and repeat1 report SHA-256:
  `ff1169e210776597963a067d12748f9876f6321539c16d65410b27416c977c91`.

Collector: `code/experiments/proofs/archive_tcad_cps_layer_grid_plan_v1.py`.
Its `--check` path is metadata/byte-only. The frozen execution source is
unchanged; the collector was added afterward. Terminal regression and
publication follow. Historical preparation/submission statements below do not
mean a job is still running. All scientific admission flags remain false.

The terminal regression subsequently passed **167 tests, zero skips**, in
48.62 seconds, including actual new/preceding archive metadata, planner guards,
exact tiny-synthetic arithmetic and wiki/prose contracts. The execution-source
regression had already passed 263 tests. Two completed collector/wiki fixture
directories were removed; scientific files/worktrees were retained. Final
wiki/prose and tracked-manifest checks precede terminal publication.

## Next decision

Do not generate this tensor grid or retry the frozen source. Separate mandatory
canonical geometry planes from optional mesh-size-field breakpoints in a new
candidate. The next implementation should subdivide canonical intervals by
midpoints, applying refinement near conductor-face bands without inserting all
expanded-support endpoints as mandatory planes. This targets both observed
failure mechanisms: near-coincident auxiliary planes and whole-projection
over-refinement. It must retain every canonical plane, reject collapsed floating
subdivisions and preserve geometry, original capacity caps and quality gates.

Before real-layout execution, separately freeze the face-band rule, subdivision
limits and any deterministic width-budget rule used to satisfy the condition
screen. No post-result tolerance adjustment or geometric snapping is allowed.
A revised plan can still fail, and a successful plan would still need a full
3D boundary/quality audit before analytic field and sensitivity studies.

## Preparation on 2026-10-03

The preceding exact-arithmetic diagnostic completed and remains archived. Its
archive SHA-256 is `9cad8aa54f37f7f356a08c890878bab4a449d31a75842a119facec1eee5bef31`.
The [new planning method](../methods/TCAD-Layer-Grid-Planning.md) retains exact
canonical planes, uses a predeclared projected-support spacing rule and computes
prospective tensor capacity and a conservative Jacobian condition bound.

Implementation includes a stdlib-only axis planner, guarded fresh workers,
source/runtime contracts, bounded parent, full deterministic reports and
metadata-only review. Its watchdog/receipt control flow is checked against the
unchanged arithmetic runner by AST. Initial synthetic tests passed 61 cases,
with one expected pre-freeze lock skip. No real-layout planning, native geometry,
meshing, field solving or fitting has run for this candidate. Freeze, regression
and verified publication precede one bounded SLURM submission.

The separate [Git storage operation](../operations/Repository-Storage.md)
restored file headroom while preserving all objects, refs, worktrees and
scientific files. It is not a scientific prerequisite result. All previous
execution locks and rejected evidence remain unchanged.

## Source freeze

The immutable lock contains 320 dependencies, including prior source locks and
the complete arithmetic archive. Protocol SHA-256:
`308d9ef2100c70410fdbaaba68734e93688a1fda46233f8026084b9678b48148`.
Lock SHA-256:
`5addbbdb9f155f25f334493e719033fa845c4bba43ce58f6c575f9cb9e07f43f`.
Post-freeze regression is running before publication and SLURM submission.
The count caps and conditioning screen have not been changed after observing
real-layout plans, because none has yet been computed.

The frozen regression passed **263 tests, zero skips**, in 51.24 seconds. It
includes new planner/worker/metadata tests, inherited arithmetic watchdog and
source/actual-archive checks, bundle guards, original allocation checks and
wiki/prose contracts. Only synthetic coordinate planning ran in tests. The two
completed initial/frozen fixture directories were removed; scientific evidence
and execution worktrees remain preserved. Publication and submission follow.

## Verified source and submission

At 11:10:40 UTC GitHub main and local HEAD were verified as
`4454a3178ab247e81dafd9d5ae4e29ef0c2a95e7`. The 7,127-file manifest and
final 55-test wiki/prose recheck passed. A clean detached sparse checkout
materialized 323 tracked files: all 320 locked dependencies, the lock, ignore
rules and repository manifest. Source/wrapper/runtime preflight passed without
computing actual coordinate plans on login.

One `sbatch` invocation at **11:11:31 UTC** returned job **`7652593`** under
the frozen 8-GiB/15-minute profile. The
[submission receipt](../../results/tcad/cps_layer_grid_plan_v1/submission.json)
binds that source and protocol. No retry or 3D mesh generation is included.
Terminal results and preservation remain pending at this submission checkpoint.
