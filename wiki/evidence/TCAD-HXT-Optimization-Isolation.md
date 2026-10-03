---
title: TCAD HXT Optimization-Isolation Evidence
status: REJECTED; toy quality gate failed; terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Optimization-Isolation Evidence

## Terminal observation: 2026-10-03

Source `66feef9e04f3186ba76656df0b2869ad3381cd63` was published and remotely
verified before submission. Its separate sparse execution checkout contained
the frozen 179-file dependency closure and passed clean-source validation.
The [submission receipt](../../results/tcad/cps_hxt_isolation_v1/submission.json)
records job `7651659`, submitted at 06:31:25 UTC. Terminal accounting reports
`FAILED/2:0`, zero restarts, 16 seconds, node `a0157`, 41 allocated CPUs and
160 GiB. Scientific threads remained one. No job in this chain remains active.

The toy alone ran. Its worker exited 1 at the predeclared signed-quality gate;
the parent stopped before local1 and repeat1. Parent-observed elapsed time was
5.509851319948211 seconds and peak RSS 0.08797454833984375 GiB. Native HXT
reported optimization disabled and completed 3D generation, but no extracted
mesh fingerprint or successful worker result was produced. These times are
not a solver speedup or a completed-sentinel comparison.

The raw `mesh_generated` observation contains 1,253 nodes and quality metrics
for 6,457 first-order tetrahedra. Counts and minima below come directly from
the [toy stdout](../../results/tcad/cps_hxt_isolation_v1/job_7651659/toy.stdout),
not a numerical replay. Jacobians use native millimetre coordinates.

| Region | Tetrahedra | Minimum signed condition | Minimum Jacobian, mm^3 | Nonpositive signed conditions |
|---|---:|---:|---:|---:|
| Dielectric | 3,643 | -2.295723906874384e-16 | 1.0842021724855044e-18 | 1 |
| Primary | 1,396 | 2.7760338185554328e-15 | 6.505213034913027e-19 | 0 |
| Secondary | 1,418 | 5.5824246747249775e-15 | 2.9680034471790684e-18 | 0 |

All reported quality values were finite, and all determinant values were
positive. The one nonpositive signed condition still fails the unchanged
strict-positive gate. The tiny signed value with positive near-zero determinant
is consistent with a near-degenerate element and floating-point sign sensitivity;
it does not by itself establish an inverted element. No metric was clipped,
rounded to pass, or replaced by its absolute value. Geometry, quality thresholds
and caps remain unchanged. Sentinel feasibility was not observed.

## Terminal preservation

The [archive manifest](../../results/tcad/cps_hxt_isolation_v1/archive/job_7651659/manifest.json)
binds eight members: attempt receipt, toy receipt, toy stdout/stderr, scheduler
stdout/stderr, raw accounting and submission receipt. It was collected only
after exact terminal accounting and frozen-validator review; the collector
does no meshing or field computation.

- Archive SHA-256: `20722df38fb6af937236d942a8b7a4fb89fc4bb1f1bac9d0f3c4b074c375f10a`.
- Attempt SHA-256: `a1a20170f90532ca374615d18dcf194b424ca2080e433bfc30eaa69b8fd9aafb`.
- Raw quality-array fingerprint: `65cdd3392570b76513d994cf86a1ffe3924894155b7cc30c13347ed2c031f21c`.

The array fingerprint was recorded on the compute node; arrays were not saved,
so this archive preserves the logged summary rather than permitting independent
elementwise remeasurement. Ordered final-mesh identity is absent because the
gate stopped extraction. `complete`, `diagnostic_passed`, `mesh_feasible`,
`numerical_quality_qualified`, `field_solver_executed`, `reference_qualified`,
`training_may_start` and `claim_eligible` are all false.

Next: implement the separately specified explicit-optimizer diagnostic in the
[research plan](../manuscript/TCAD-Research-Plan.md), with quality observations
before and after optimization and fresh coordinate extraction. This is not a
retry or an admission of the unoptimized mesh. No follow-up job is submitted
at this checkpoint. Earlier preparation entries below are historical.

Terminal regression passed all 212 selected no-solver tests, including 26
archive/quality-log tests and the unchanged frozen sources. The prose audit
passed. Source/documentation whitespace checks exclude only the byte-preserved
raw native stdout; no scientific output was normalized. Publication requires
complete Git member closure and the refreshed repository manifest.

Publication was subsequently verified at 06:48:14 UTC: remote main and local
HEAD both resolved to `a96a1a953f79af15b8b06f7b580afb5997b15f38`. All eight
archive members are tracked, and the refreshed 6,980-file repository manifest
passed. This publishes negative diagnostic evidence, not a scientific claim.

## Preparation: 2026-10-03

The [method](../methods/TCAD-HXT-Optimization-Isolation.md) and
[runbook](../operations/TCAD-HXT-Optimization-Isolation.md) implement the single
optimization-stage diagnostic recorded after the previous HXT timeout. The
predecessor's 11-file archive remains byte-identical, manifest SHA-256
`76713195d6b46b1197392693408d9ddc268070fb8a137fe3f2cd79a4570eb25c`.
Its terminal/research checkpoint is now published and remotely verified at
`02e1b3b12599feb2f31858c929e6460ee2475554`.

The new implementation has separate protocol, parent, worker and wrapper files.
It adds signed-condition/Jacobian observations before mesh extraction and
checks quality-region counts against the inherited mesh representation.
Initial tests found shared mutable configuration metadata in the new quality
receipt; the metadata is now copied so editing a receipt cannot change its
expected units. The corrected suite passed 48 tests, with the source-closure
check deferred until freeze. Tests use tiny arrays, fake Gmsh and synthetic
receipts; no mesher or solver runs on login.

Freeze, full regression, source publication and scheduler submission remain
pending at this checkpoint. No old source, lock, cap, dataset or paper is
changed. Field computation, reference/training eligibility and new claims
remain closed even if the diagnostic later completes.

## Source freeze

After additional fake-builder integration tests, all 52 new tests passed with
the frozen source. The earlier combined source/archive/wiki/prose suite passed
182 tests with one pre-freeze skip. No previous source was changed.

- Protocol SHA-256: `3ae43c358d362e9aeeb1485f15cb1144eeb114854e544e8d918090b509936dc6`.
- Lock SHA-256: `28c9b79e24703ab916bee4ec81f5d04395efc1767bb7fbc97d721b7c6a594a3c`.
- Source closure: 179 files, excluding the new lock itself.

The closure includes the preceding failed attempt, source validator and archive
checker. This freeze does not validate an actual mesh. Publication and the
single bounded SLURM submission remain pending at this checkpoint.

The combined post-freeze regression then passed all 186 selected tests with no
skips. Prose audit, wrapper syntax and source/documentation diff checks passed.
