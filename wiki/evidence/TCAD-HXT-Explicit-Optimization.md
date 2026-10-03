---
title: TCAD HXT Explicit-Optimization Evidence
status: REJECTED; terminal archive checked; sentinel optimizer timeout
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Explicit-Optimization Evidence

## Terminal outcome and archive on 2026-10-03

At 07:30:25 UTC, accounting reported job `7651765` terminal `FAILED/2:0`,
zero restarts, 1,226 elapsed seconds, 41 allocated CPUs and 160 GiB on `a0157`;
the queue no longer contained it. Toy passed its diagnostic gate. Local1 hit
the unchanged worker wall-time cap and the parent killed it with return code
`-9` after 1,200.5339847570285 seconds, observing 3.473194122314453 GiB peak RSS.
The repeat was not run. No job in this diagnostic chain remains active.

The last structured local1 stage is `mesh_optimize_started` at
56.61669809999876 worker seconds. There is no optimization-finished stage,
post-quality record, final sentinel mesh or result. The raw counts below are
pre-optimization observations only. The native tail names volume 28, but its
region identity is not independently established by that log. Removing
conductor interiors is therefore a formulation hypothesis, not a demonstrated
remedy for this optimizer bottleneck.

The metadata-only collector checked frozen source, exact mode receipts,
terminal accounting and byte-preserving copies. The
[archive manifest](../../results/tcad/cps_hxt_postopt_v1/archive/job_7651765/manifest.json)
closes 11 members, including raw scheduler logs, accounting and submission:

- Archive SHA-256: `e76884fc13e7b721eb671b995598080031318f1bfc77016ce9039b26196527be`.
- Attempt SHA-256: `2edf43c06bfb4a5980866408cda107d1adaae1001bcbdee75d27e0b584d20dcd`.

Completion, repeatability, diagnostic success, mesh feasibility, numerical
quality, field execution, reference, training and claim flags are all false.
Preserve this negative result without changing caps, tolerances or source.
At 07:49:55 UTC, publication was remotely verified at
`920b8fda435fd0b18e6627b5ae1d48aeead29d0b`, including all 11 archive members
and the 7,008-file repository manifest. Earlier RUNNING entries below are
historical. Next: the separate dielectric-only formulation investigation, not
another submission of this failed protocol.

The expanded archive regression passed all 27 tests, including the exact
terminal archive, failed-worker timing, incomplete stage sequence and raw-only
sentinel counts. It performs metadata/hash checks, not a numerical replay.
The subsequent combined source/archive/topology/wiki regression passed 369
tests with no skips, preserving all predecessor source and archive checks.

## Follow-up checks on 2026-10-03

The submission checkpoint is remotely verified at
`fabb9599d3eefdfa001460725404065963bb4bec`. Scheduler queries at 07:22:11 UTC
and 07:24:47 UTC reported RUNNING, zero restarts; accounting at 07:27:30 UTC
still reported RUNNING with 1,079 elapsed seconds. Local1 remained in explicit
optimization; no post-quality observation, final mesh or repeat existed.
The unchanged native tail identifies volume 28 optimization; it is not proof
of a stopped process. The additive collector now has 25 passing synthetic
tests, including late-sentinel timeout preservation. No job was restarted.

## Submission and initial observation: 2026-10-03

Source `9e6bdf817004436a938fe8bdb99c34b7ccef5d75` was published and remotely
verified. Its sparse detached execution checkout passed the 198-dependency
source lock, tracked closure and clean-source check. The main manifest passed
with 6,991 files. The [submission receipt](../../results/tcad/cps_hxt_postopt_v1/submission.json)
distinguishes the 07:08:59 UTC sbatch invocation from the scheduler's 07:09:00
UTC acceptance of job `7651765`.

At 07:11:42 UTC, `squeue` and `sacct` agreed the job was RUNNING on `a0157`,
zero restarts, 41 allocated CPUs and 160 GiB. Scientific threads remain one.
Toy passed the bounded diagnostic; local1 had generated its raw mesh and
reached explicit native optimization. The repeat had not started. No final
sentinel result or terminal accounting existed at this observation.

Toy observations in the execution checkout's `job_7651765/toy.json`:

- 1,253 nodes and 6,249 post-optimization tetrahedra.
- Parent-observed time 12.016543281031772 seconds; worker-reported time
  7.668135181069374 seconds; peak RSS 0.08782958984375 GiB. Worker timing
  includes source checks and quality work, not pure mesher latency.
- Final mesh SHA-256: `7b42ddc71d75b3db9c329e00bd050739955970ccd411f7b0f029631e2ba2a3ee`.
- Raw quality SHA-256: `65cdd3392570b76513d994cf86a1ffe3924894155b7cc30c13347ed2c031f21c`;
  it matches the rejected isolation toy's raw quality observation.
- Post-quality SHA-256: `227d8ad1fd344e9b78e3ed0eb88fc1d8b56afde9c14c85a86bd8ef15104c4e8c`.

The raw quality gate is still false; the post-optimization finite/positive
gate passed. This is not numerical-quality qualification: native stderr still
warns about ill-shaped tetrahedra. Four dielectric and three primary elements
have signed condition below 0.01; the minimum dielectric signed condition is
6.398856084358075e-15 and its minimum Jacobian is 4.445228907190568e-18 mm^3.
No tolerance was changed to obtain the positive observation. Near-degenerate
positive elements still prevent inferring reliable conditioning or reference
accuracy from this mesh-only test.

An additive terminal collector and 24 passing synthetic archive tests now
exist in main, separate from the running frozen source. Collection requires
terminal accounting and exact frozen receipt/log checks; no archive has yet
been collected at this checkpoint. Field/reference/training/claim gates remain
closed. Earlier preparation entries below are historical.

At 07:15:33 UTC both scheduler queries still reported RUNNING, zero restarts,
362 elapsed seconds. Local1's latest stage was `mesh_optimize_started`;
neither its final quality/result nor the repeat was available. Its already
logged raw stage (not a final mesh) reports 724,661 nodes and 4,147,907
tetrahedra at 56.61642072885297 worker seconds, peak RSS 3.473194122314453 GiB:
1,986,363 dielectric, 1,064,316 primary and 1,097,228 secondary tetrahedra.
Raw signed conditions include 111 nonpositive primary and 129 nonpositive
secondary observations, but none in dielectric; all raw determinants are
positive. The raw strict-quality outcome remains false. These observations
do not qualify any region or remove the all-region post-optimization gate.

The combined submission/collector regression subsequently passed 287 tests
with no skips. Only synthetic, source and metadata work ran on login. The
[research plan](../manuscript/TCAD-Research-Plan.md) now records a source-only
investigation of the cost of meshing fixed-potential conductor interiors; it
does not alter or cancel this allocation.

The submission/collector checkpoint was published and remote-hash verified as
`e8b3da2bf4925f79945384216e5b60283d65645d`. At 07:19:25 UTC the same job was
still RUNNING, zero restarts, 594 elapsed seconds. Its attempt receipt still
contains only the passed toy; local1 remains in explicit optimization. Unchanged
native log output is not a terminal observation. No timeout, final sentinel
mesh or repeat result is inferred from that unchanged log.

## Implementation on 2026-10-03

The preceding isolation archive and research decision are published; the later
publication receipt commit `dada417563378cd7a563462d5eb117aac3595944` was also
verified on remote main before this implementation. Its rejected toy evidence
remains unchanged, archive SHA-256
`20722df38fb6af937236d942a8b7a4fb89fc4bb1f1bac9d0f3c4b074c375f10a`.

The new [method](../methods/TCAD-HXT-Explicit-Optimization.md) has a separate
protocol, worker, parent, guarded builder and SLURM wrapper. The builder keeps
the original geometry and extraction source while moving coordinate reads
after the explicit optimizer. New tests exercise the complete worker/builder
with fake native APIs, deliberately changing coordinates and connectivity.
No real Gmsh mesh or field solver was executed on login.

Initial tests passed 43 cases with the source-lock test deferred until freeze.
The expanded fake-builder suite initially had three fixture/assertion mistakes:
a missing phase environment and two overly narrow exception patterns. The
guards themselves failed closed as intended; fixtures were corrected before
freeze. Numerical performance and quality have not yet been observed.

Next: finish regression and freeze, publish/verify source, then submit the
single bounded allocation under the [runbook](../operations/TCAD-HXT-Explicit-Optimization.md).
No prior source, cap, quality gate, dataset or manuscript claim changes.

## Source freeze

After fixture corrections, all 50 new no-solver tests passed, with one deferred
source-lock test. The combined source/archive/wiki/prose regression passed
262 tests with the same single pre-freeze skip. Shell syntax, prose audit and
tracked documentation diff checks passed. Installed Gmsh API text also confirms
the selected keyword argument names; this was read without running Gmsh.

- Protocol SHA-256: `723bb110b8d7c67d0274883583c527827a3326aab88b300d34bf555fa006ecae`.
- Lock SHA-256: `e83ca24c6adb98e20657ef5ae24d7b1d64078282b596eaa9f248f3ee33869c14`.
- Source closure: 198 files, excluding the new lock itself.

The closure includes the predecessor source lock, failed attempt, archive
checker and regression. Freeze does not validate a real mesh. Post-freeze
regression, verified publication and the bounded submission follow next.

The post-freeze regression subsequently passed all 263 selected tests with no
skips, including the 51 new tests and unchanged predecessor archives/sources.
The staged source/documentation diff and prose audit passed. No numerical
mesh, quality or timing result is inferred from these synthetic/source checks.
