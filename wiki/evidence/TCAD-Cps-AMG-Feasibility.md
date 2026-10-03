---
title: TCAD AMG Feasibility Evidence
status: REJECTED; incomplete mesh-timeout study; terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD AMG Feasibility Evidence

## Preparation on 2026-10-02

The owner approved implementation of the next bounded step. The successful
diagnostic is now preserved in a nine-file byte-for-byte
[terminal archive](../../results/tcad/cps_amg_diagnostic_v1/archive/job_7647850/manifest.json).
Its manifest SHA-256 is
`0b6df0554a8ca2f76110af66518175209cf978630622408f29928970ff055a4e`.
The archiver checked exact file/mode coverage, terminal accounting, source,
runtime, geometry, raw-log/result reconstruction and recorded scalar gates.
It performed no numerical solve or replay on login. The
[diagnostic evidence](TCAD-Cps-AMG-Diagnostic.md) owns its scientific limits.

The [new method](../methods/TCAD-Cps-AMG-Feasibility.md) keeps all seven mesh
arms and resource/sensitivity limits, changing only to the already tested AMG
candidate. Every arm, including local0, is rerun under the new source identity.
No previous result is substituted. The [runbook](../operations/TCAD-Cps-AMG-Feasibility.md)
requires a new source-bound smoke before feasibility and afterany finalization.

At this preparation checkpoint no new job is submitted and no source lock
for this study is frozen. Last verified remote `main` is
`6a393612588a2c70e513a6f027e596ba7e5adc39`; earlier local wiki reviews are
retained for inclusion with this implementation. All older source and evidence,
the released paper and the local-only guidance boundary remain unchanged.
No reference, training permission or new paper claim is admitted.

## Frozen-source validation on 2026-10-03

The additive implementation passed all 191 focused tests across the original
pilot, support recovery, AMG diagnostic, new feasibility contracts, wiki, prose,
reproducibility and journal package. The tests use metadata and fake numerical
APIs, not a login-node solver. They check unchanged inherited caps/physics,
exact anchors, source and runtime binding, prerequisite smoke, failure stops,
process-group limits, receipt corruption, incomplete coverage, negative
sensitivity outcomes and false downstream-qualification flags. The copied
assembly and AMG numeric helpers remain byte-identical to the diagnostic source.

The deterministic prose audit, all three batch-wrapper syntax checks and the
nine-file diagnostic archive check passed. The new source lock SHA-256 is
`00f5b0f6b9d825597286edcb2e51ae0ac3c9bb1b557c6f33169c79ad24d31906`.
It binds the inherited source closures, terminal evidence, new protocol,
workers, runner, wrappers and tests. No old source lock was replaced. This
validates implementation contracts, not numerical feasibility. Publication
and a new SLURM smoke are the next gates; no job has been submitted yet.

## Verified execution-source publication

Source, archive, protocol/lock and wiki were published as
`b8d4b891d15d4dc7c261e92c310bc3273218daa6`. A remote branch query confirmed
that exact `main` hash after the push. The repository manifest passed for
6,906 tracked files other than itself; precommit validation passed 98
feasibility/wiki/prose tests and the prose audit. A separate detached worktree
at this commit will execute the new chain. This later publication receipt does
not change the frozen execution source or establish a numerical result.

## File-quota recovery and smoke submission on 2026-10-03

Creating a full detached checkout stopped before execution with `Disk quota
exceeded`. The quota report showed approximately 996,000 files against a
1,000,000-file quota, while byte usage remained below its limit. Git rolled
back the failed new worktree; no historical data or existing worktree was
deleted. No numerical job was launched by that failed checkout.

A new detached worktree at the same published commit uses literal sparse
paths for the 128 locked dependencies, the lock itself, `.gitignore` and
`MANIFEST.json`: 131 materialized tracked files. The source checker verified
every locked byte, tracked membership, exact commit, root and wrapper identity,
and a clean tracked diff. The complete repository manifest was checked in the
full main checkout before publication; a full-manifest check is not claimed
for the sparse worktree. Physics, code, protocols, source identity and caps
are unchanged by this storage arrangement.

Source-bound smoke job `7650458` was submitted from that worktree. Feasibility
submission remains conditional on terminal smoke admission. All numerical work
continues on SLURM compute nodes; this recovery performed metadata checks only.

## Smoke admitted; feasibility submitted on 2026-10-03

Smoke `7650458` completed `0:0`, zero restarts, in eight scheduler seconds on
`a0102`, with three allocated CPUs for 8 GiB and one scientific thread. The
[saved result](../../results/tcad/cps_amg_feasibility_v1/smoke/job_7650458/smoke.json)
passed source, geometry, runtime, exact matrix, raw-log reconstruction, residual,
resource and backend-agreement checks. Its toy matrix has 1,481 mesh nodes,
7,917 tetrahedra, 477 free unknowns and 5,595 nonzeros, with SHA-256
`3cd4eda00692dc7dc024d9f9c971b716060e08eb826a4ce0541725c7077d48d2`.

AMG complexity was 1.0536193029490617, with 15 CG iterations and relative
residual 4.4940130640994257e-11. Candidate capacitance was
1.1590918982639615 pF versus 1.1590918982639618 pF for the direct comparator;
solution-relative L2 difference was 2.225369760146916e-11. Parent-observed worker
time was 4.009516671998426 seconds and peak RSS 0.10802841186523438 GiB.
These are toy implementation measurements, not mesh accuracy or physical
validation. The four attempt/arm/raw-log files and two scheduler logs were
copied byte-for-byte into the tracked result tree. The
[terminal receipt](../../results/tcad/cps_amg_feasibility_v1/smoke/job_7650458/terminal.json)
binds attempt SHA-256
`dae0319e5a94fbaad92b92d54405089c9b999a85a2bcd2849d3c2e1e815dc2de`.

After terminal admission, job `7650556` was submitted for seven fresh arms on
layout 597. At 2026-10-03 04:30 UTC it was RUNNING on `a0199`, zero restarts,
with 41 allocated CPUs for 160 GiB and one scientific thread. Finalizer
`7650557` was PENDING with verified dependency `afterany:7650556`. The
[submission receipt](../../results/tcad/cps_amg_feasibility_v1/submissions/job_7650556.json)
pins source, lock, smoke and storage scope. Source remains the published
`b8d4b891d15d4dc7c261e92c310bc3273218daa6` while main-checkout documentation
is updated separately. Next: terminal coverage and sensitivity review, then
preserve every outcome. No panel expansion, reference qualification, training
or paper claim is enabled.

## Terminal inspection and archive on 2026-10-03

Job `7650556` terminated `FAILED/2:0`, zero restarts, after 1,615 scheduler
seconds on `a0199`. Fresh local0 passed with the diagnostic's exact system
identity; the
[local0 receipt](../../results/tcad/cps_amg_feasibility_v1/feasibility/job_7650556/local0.json)
records 410.4705544260796 parent-observed seconds and 3.2724609375 GiB peak RSS.
Its successful backend result does not complete the study.

Local1 exceeded the unchanged 1,200-second worker cap. The parent terminated
its process group, recorded return code -9, elapsed 1200.51880231197 seconds
and observed peak RSS 3.623119354248047 GiB. The
[failed receipt](../../results/tcad/cps_amg_feasibility_v1/feasibility/job_7650556/local1.json)
and raw log end at `mesh_generate_started`; neither `mesh_generated` nor
matrix assembly, AMG setup, CG or a capacitance result was emitted. The log
does not locate the delay within Gmsh's internal meshing substeps. This is a
wall-time failure during meshing, not an observed AMG or mesh-node-cap failure.
No quota error appears in the failed worker's empty stderr.

A small geometry-only check evaluated the dielectric-box center of mass by
subtracting the disjoint conductor-box volumes from the outer box. For layout
597 and pad 16 mm, the center did not fall inside any conductor bounding box
under the inherited classification tolerance. This does not reproduce OCC
classification or validate all meshes; it only rules out that particular
metadata-level suspicion for this input. No meshing or solve ran on login.

Finalizer `7650557` terminated `FAILED/2:0`, zero restarts, after three seconds
on `a0104`. Its
[summary](../../results/tcad/cps_amg_feasibility_v1/finalize/job_7650557/summary.json)
retains local0 success and local1 failure, incomplete coverage, no sensitivity
comparisons, and false reference/training/claim flags. Local2, repeat2, pad20,
far2 and support1 were not run. Both jobs are terminal; no active job remains
in this chain.

The additive collector checked terminal accounting, source/runtime/geometry,
the admitted smoke, exact files, raw-log hashes, per-arm receipts and finalizer
reconstruction without numerical replay. Its
[20-file archive](../../results/tcad/cps_amg_feasibility_v1/archive/feasibility_7650556/manifest.json)
includes the previously collected smoke plus every attempt/finalizer file and
four terminal scheduler logs. Manifest SHA-256:
`d476cbf411192c4b4c109dfcb98551afe2ed39eb994211f19fdda04a65c628bc`.
Attempt SHA-256:
`b65a8c7dcb02c527d8cf05af1cd531a9128d6e37ad95e3109a94cbea4c0e8874`.
Summary SHA-256:
`d4fd2d665f6c5d411374596ac8c3b12951ef3dd4e7ecf40024582f04ec59357d`.
No original source, limit or rejected evidence was overwritten.

Collector preparation passed 79 no-solver archive/wiki/prose tests after the
fixture-quota recovery documented in the
[runbook](../operations/TCAD-Cps-AMG-Feasibility.md); the actual archive check
then passed. A terminal regression test was added for this exact failure.
The subsequent complete focused suite passed all 216 no-solver tests,
including the new terminal regression, earlier frozen-study contracts,
reproducibility, journal, wiki and prose checks; the prose audit also passed.

Next: a separately frozen mesh-generation diagnostic with native meshing-stage
logs and a bounded alternative mesher, before any new field-solver study.
The [continuation plan](../manuscript/TCAD-Research-Plan.md) owns this next
decision. No three-sentinel expansion or training is justified by this outcome.
