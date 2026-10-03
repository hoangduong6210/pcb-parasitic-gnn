---
title: TCAD Mesh-Only HXT Probe Evidence
status: RUNNING; published frozen source; terminal coverage pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Mesh-Only HXT Probe Evidence

## Source publication and submission

Source commit `3a680844d06a46fcf0c8c3698a2a169a86990c00` was published and
verified against remote main before submission. The full main manifest passed
with 6,942 files excluding itself. The separate sparse checkout passed clean
source and all 158 locked dependencies; no historical data were removed.

Job `7651463` was submitted at 2026-10-03 05:35:11 UTC and observed RUNNING
on `a0157` at 05:35:29 UTC, zero restarts. Memory policy allocated 41 CPUs for
160 GiB despite the one-CPU request; all scientific threads remain one. The
[submission receipt](../../results/tcad/cps_mesh_probe_v1/submission.json)
binds source, protocol, lock, wrapper and resource limits.

The toy mode passed. Its ordered mesh has 1,253 nodes and 6,199 tetrahedra,
SHA-256 `d812442abf9c9756cbbbfa2900e789e84b483eec4282a1b9d458b452c80b53df`.
Worker elapsed time was 3.416435627033934 seconds and peak RSS
0.0904083251953125 GiB; the parent measured 5.510262751020491 seconds including
process startup and checks. Local1 subsequently completed 2D meshing and
entered 3D meshing. These are interim observations, not complete coverage or
repeatability. No field solver ran and no reference, training or claim gate
opened. Next: terminal accounting, exact closure and fresh-repeat review.

The preparation entries below retain their historical meaning.

## Implementation checkpoint: 2026-10-03

The new [method](../methods/TCAD-Cps-Mesh-Probe.md) and
[runbook](../operations/TCAD-Cps-Mesh-Probe.md) implement the previously recorded
single-candidate mesh diagnostic. The preceding incomplete study remains
unchanged in its checked 20-file archive, whose manifest SHA-256 is
`d476cbf411192c4b4c109dfcb98551afe2ed39eb994211f19fdda04a65c628bc`.
That archive and the previous protocol are dependencies of the new source lock.

The parent, worker and wrapper are additive files. Login-node guards, exact
source binding, resource limits, stage and mesh fingerprint checks, raw-log
integrity, repeatability, rejected outcomes and claim boundaries have no-solver
tests. Initial validation passed 44 tests with one source-closure check deferred
until freeze; further source-guard tests were then added. This is software
validation only. Lock, full validation, publication and scheduler receipts will
be recorded when verified; no new job is submitted at this checkpoint.

## Frozen-source validation

The selected TCAD, wiki and prose suite passed 247 tests before freeze, with
only the post-freeze source-closure test deferred. All 54 mesh-probe tests then
passed after freezing. The deterministic prose audit, shell syntax, diff check
and preceding 20-file terminal-archive check also passed. No meshing or solver
ran on login.

- Protocol SHA-256: `6d578ef74dc41d73b6ecde70415f18a8b33e6daa8d498ad5d8d8effa71c4a04a`.
- Lock SHA-256: `7c9b9f79a85444b5bb4c8620a48810bb3a6da6b493a77f546752f866c5aa0af8`.
- Locked dependency closure: 158 files, excluding the lock itself.

Source publication and the single bounded SLURM submission remain pending.
The file-count quota is close to its ceiling; execution will use a sparse
checkout, preserving all older studies and data.

Last remotely verified main before implementation:
`c3072822369878798bd903dfefdc00313dad1131`. No previous source, failed result,
paper snapshot, scientific cap or unrelated scheduler job is changed.
