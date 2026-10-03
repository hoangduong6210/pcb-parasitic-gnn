---
title: TCAD Mesh-Only HXT Probe Evidence
status: PROPOSED; source frozen and validated; publication pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Mesh-Only HXT Probe Evidence

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
