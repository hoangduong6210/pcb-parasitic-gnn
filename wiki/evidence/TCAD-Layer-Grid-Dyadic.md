---
title: TCAD Dyadic Layer-Grid Planning Evidence
status: REJECTED capacity candidate; diagnostic complete and terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dyadic Layer-Grid Planning Evidence

## Terminal observation on 2026-10-03

At **11:55:57 UTC**, accounting showed job `7653000` terminal
`COMPLETED/0:0`, zero restarts, 58 elapsed seconds, three allocated CPUs and
8 GiB on `a0113`. The queue was empty. One CPU was requested and scientific
thread settings stayed one. Toy/local1/repeat1 all completed and the sentinel
fresh repeat matched exactly. **Diagnosis completed, but the candidate is
infeasible under its unchanged capacity gates.** No 3D mesh or field was created.

| Prospective grid quantity | Toy | Selected sentinel, layout 597 |
|---|---:|---:|
| Axis point counts (x, y, z) | 23, 21, 16 | 376, 412, 93 |
| Total Cartesian cells | 6,600 | 14,179,500 |
| Dielectric cells | 6,440 | 14,104,011 |
| Full tensor-node upper bound | 7,728 | 14,406,816 |
| Prospective dielectric tetrahedra | 38,640 | 84,624,066 |
| Unchanged node cap | 300,000 | 3,000,000 |
| Unchanged tetrahedron cap | 1,500,000 | 20,000,000 |
| Node/tetrahedron checks | pass / pass | fail / fail |
| Conservative condition check | pass | pass |
| Complete report bytes | 14,288 | 220,269 |

Unlike the preceding candidate, the base-plane lists contain only canonical
geometry. Both actual-width condition screens pass, but fixing the auxiliary
plane problem did not solve tensor-product capacity. For the sentinel, the
smallest canonical gap is exactly `402305991763/562949953421312` mm on x.
The frozen width-budget rule therefore clips the global far target to
`251441244851875/422212465065984` mm instead of the nominal 4 mm. That same
budget applies to all three axes, including the padding direction. The new
plan has more z points and more prospective tetrahedra than the preceding plan.
This is an observed construction/count comparison, not an isolated causal
ablation of the band, midpoint and budget changes. A failed conservative node
bound alone could be inconclusive, but the declared tetrahedron count also
exceeds its cap. None of these are measured mesh or extraction counts.

Parent-observed times for toy/local1/repeat1 were 9.518325794953853,
11.522620193194598 and 9.518942645052448 seconds. Worker-reported times were
4.511652525048703, 4.763177453074604 and 4.664523443905637 seconds, including
metadata/report/source checks. Peak worker RSS was below 0.026 GiB. These are
planning-pipeline timings, not mesh/solver latency or speedup measurements.

## Checked terminal archive

The additive collector passed 24 synthetic cases before preserving all
**17 terminal members**: complete reports, mode receipts/stdout/stderr, attempt,
submission, scheduler logs and accounting. Byte/source/identity/coverage/repeat
checks passed without regenerating real axes on login.

- [Archive manifest](../../results/tcad/cps_layer_grid_dyadic_v1/archive/job_7653000/manifest.json)
  SHA-256: `9aea1951ed736c490dcd9b283d5b0508c8c176e3ecdc125e847dd383b1e07873`.
- Attempt SHA-256: `1f8862db9d9cfabb676e66203109cbd9550b72fe97011301f4e9da22538c7b02`.
- Toy report SHA-256: `3e8a4eef881764915ff29285cce6a98dfb112cfca6a3051ba344cf34a743d5d4`.
- Local1/repeat1 report SHA-256:
  `396529a86b3f8ecbefb16b293953e0a4d0e9f562cfbc5919700a43916f1ea811`.

Collector: `code/experiments/proofs/archive_tcad_cps_layer_grid_dyadic_v1.py`.
It was added after execution freeze; frozen source remains unchanged. Terminal
regression/publication follow. Historical submission statements below do not
mean the job is still running. All scientific admission flags remain false.

The terminal regression subsequently passed **180 tests, zero skips**, in
91.58 seconds, including the actual new/preceding archive closures, prospective
planner guards, recorded outcome scalars and wiki/prose contracts. All 17
terminal members are tracked. The source suite had already passed 338 cases.
Final wiki/prose and deterministic manifest checks precede terminal publication.
The completed collector and terminal synthetic-fixture directories were removed
after inspection; all scientific artifacts and execution worktrees are retained.

## Next decision

Do not instantiate or retry this global tensor grid, increase caps, or alter its
frozen width budget. The next candidate should avoid taking the full Cartesian
product of all x/y conductor-face planes. Assess a conforming planar footprint
arrangement with locally sized triangles and prospective layer-column extrusion.
The [method owner](../methods/TCAD-Layer-Grid-Dyadic.md#next-candidate-boundary)
states the design hypothesis and prerequisites. This is not implemented or
validated yet. Preserve all canonical conductor geometry and terminal physics;
2D native work and extrusion feasibility must also run through SLURM. A new
prospective protocol must precede any real input, and no learning gate opens.

## Preparation on 2026-10-03

The preceding projected-support candidate remains rejected and preserved in
its [terminal archive](TCAD-Layer-Grid-Planning.md). Its archive SHA-256 is
`8b66fc27509b53f3f42e7da1b546926666b9da1a64b507a75384acab198b4d4c`.
The new [dyadic method](../methods/TCAD-Layer-Grid-Dyadic.md) separates mandatory
canonical faces from nonmandatory refinement bands, with a prospective width
budget and unchanged condition/capacity gates. No real-layout numerical plan
has yet been computed for this candidate.

Implementation includes a separate stdlib planner, guarded workers, bounded
runner, protocol/source lock and report metadata review. Tests use only tiny
explicit synthetic boxes. The first run passed 73 cases with one pre-freeze
skip and exposed an incorrect parent-level lookup in a cap-inheritance test;
that test was corrected before source freeze. No frozen scientific source or
evidence was changed. Full regression, freeze and verified publication precede
one bounded SLURM planning job. All mesh/field/reference/training/claim gates
remain closed, and the full TCAD goal is incomplete.

The corrected pre-freeze suite passed **129 tests, one expected lock skip**,
including 74 new planner/worker/metadata cases and 55 wiki/prose tests. The
guarded runner's watchdog and receipt control flow matches its frozen parent
by AST. Synthetic tests cover hand-counted cells, one-ULP canonical preservation,
noninserted auxiliary band edges, stricter width budgets, leaf targets and
metadata mutation rejection. Freeze and post-freeze regression follow.

## Source freeze

The immutable lock contains **347 dependencies**, including the preceding
source lock and terminal archive. Protocol SHA-256:
`508a31650285e6c45b568d0763984ad3a910e6080147f4d920e80a36e376d8f0`.
Lock SHA-256:
`4e9f7d0ab7e9a3cee1ac54f2a8f1f38776914d3f60745be06735db7c271b2ea9`.
Post-freeze regression is running before publication. Four completed tiny
synthetic-fixture directories were removed after inspection; they can be
regenerated from tests. No scientific files or execution worktrees were removed.

The frozen regression passed **338 tests, zero skips**, in 69.66 seconds.
Coverage includes new planning/metadata guards, the preceding planner/archive,
exact tiny-synthetic arithmetic, original allocation checks, bundle boundaries
and wiki/prose contracts. Real-layout numerical work did not run on login.
Verified source publication and one bounded SLURM study follow.

## Verified source and submission

At **11:52:15 UTC**, GitHub main and local HEAD were verified as
`5443917c74e3e56c7afd55b845d5116f1c6e90e7`. The 7,157-file manifest and
final 55-test wiki/prose recheck passed. The detached sparse execution checkout
materialized 350 tracked files: all 347 dependencies, lock, ignore rules and
manifest. Source/wrapper/runtime checks passed without real-layout planning.
Two completed regression-fixture directories were removed; all scientific
evidence and execution worktrees remain preserved.

One submission at **11:54:09 UTC** returned job **`7653000`**. Its
[receipt](../../results/tcad/cps_layer_grid_dyadic_v1/submission.json) binds the
source, protocol and frozen 8-GiB/15-minute profile. At 11:54:24 UTC it was
pending. Monitor the same job and retain every terminal outcome. Submission
does not imply planning success, and there is no automatic retry or mesh/field
generation. The additive terminal collector is being tested separately; it
does not alter the frozen execution source. Submission records are still local.
