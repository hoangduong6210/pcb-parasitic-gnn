---
title: TCAD Compact-Support Recovery Evidence
status: REJECTED; incomplete at the frozen AMG operator-complexity cap
last_updated: 2026-10-02
paper_source: false
---

# TCAD Compact-Support Recovery Evidence

## Terminal inspection and archive on 2026-10-02

The feasibility and finalizer jobs are terminal; submission observations below
are historical. Job `7647612` failed `2:0`, zero restarts, after 404 seconds on
`a0102` (41 allocated CPUs, 160 GiB request, one scientific thread). Only local0
was attempted. Its mesh contained 349,777 nodes and 1,903,228 tetrahedra; the
condensed system had 18,629 free unknowns and 179,089 nonzeros. Mesh generation
and assembly completed. AMG setup reported operator complexity
1.2752039488745819, above the frozen 1.25 cap. The worker stopped before CG;
no layout-597 capacitance was emitted. Worker elapsed time was
400.0775431881193 seconds and observed peak RSS was 3.264820098876953 GiB;
neither timeout, memory nor mesh-node limits caused this failure.

Finalizer `7647619` failed `2:0`, zero restarts, after two seconds on `a0196`.
It retained the failed arm and attempt binding, with incomplete coverage,
empty comparisons and all qualification/training/claim flags false. The
remaining six arms, including the support control, were not run.

The [terminal archive](../../results/tcad/cps_support_recovery_v1/archive/feasibility_7647612/manifest.json)
contains ten byte-preserved artifacts and scheduler logs, plus the manifest's
metadata-only diagnosis and terminal accounting. Manifest SHA-256:
`87883064b9d074f6de47485bda3dc08fe00e32eaacc2032a4200ac234496bcc4`.
Attempt SHA-256:
`5ca56cb413484b0301dcd29e5e3cc76c1ccfdfedb4dbd90bb815b74056ed426b`.
Final summary SHA-256:
`5ec5ad7653d0f075efdcbd25a6234b6896c63b76d7f163a63e8b1838d26887eb`.
The old source, lock and caps remain unchanged. The owner requested continuation;
the next step is a separately versioned
[AMG diagnostic](../methods/TCAD-Cps-AMG-Diagnostic.md), not an automatic rerun
or a repair of this rejected study. Preparation and publication status belong
to its [evidence page](TCAD-Cps-AMG-Diagnostic.md).

## Owner-authorized preparation

The owner requested the next step after the incomplete pilot. The
[decision](../decisions/0005-tcad-compact-mesh-support.md) authorizes a bounded
largest-sentinel feasibility implementation; the
[method](../methods/TCAD-Cps-Compact-Support-Recovery.md) and
[runbook](../operations/TCAD-Cps-Support-Recovery.md) own its frozen contract.
This does not relabel the old pilot as passed or authorize a new training grid.

The original pilot's terminal task directories, final summary and scheduler
logs were copied byte-for-byte into the main checkout. The
[archive manifest](../../results/tcad/cps_reference_v1/archive/pilot_7641200/manifest.json)
binds 59 files and four terminal scheduler records. Its SHA-256 is
`253a0443a9c46efa5db5dc2dd3c9924196fef7a6aa9504f173081b11ccd9ad76`.
All original raw-log hashes and saved result/log identities were checked,
including the failed task. No numerical replay or solve ran on the login node.

The [geometry/cost receipt](../../results/tcad/cps_reference_v1/archive/pilot_7641200/geometry_cost.json)
records that layout 597 has 26 conductors. Its local2 mesh was generated at
about 1,160 seconds and contained 3,452,236 nodes; the worker stopped before
matrix assembly. The nearest projected interlayer gap is 0.11 mm, up to
floating-point representation. The sum of expanded conductor-box volumes
changes from 538.3658428070789 to 312.7560307049313 cubic millimetres when
expansion changes from 0.11 to 0.055 mm. These sums double-count overlaps and
exclude the transition layer; they are not mesh-node predictions or physical
volumes. The smaller support is a candidate motivated by geometry and cost,
not an established accuracy improvement.

The recovery keeps the original caps and near-size ladder. It changes box
expansion and transition thickness, and adds a fresh original-support arm at
the intermediate level. Only layout 597 is selected. The original two completed
sentinels do not contribute new-policy observations. Full-pilot and training
expansion remain disabled.

Initial no-solver testing passed 42 tests with the new lock check skipped
before freezing. Additional failure-retention and old/new identity tests were
then added before freezing the source. The final frozen suite passed all 122
pilot, recovery, wiki, reproducibility, prose and journal tests. The deterministic
prose audit, shell syntax and archive reconstruction checks passed. The source
lock SHA-256 is
`b79411aeb3e327a96b61c0a746fae3ec2d4774542677eaff8cafa9616f45fd39`.
It includes the original closure and terminal archive; no old execution source
file was edited. Publication and scheduler receipts follow below; no new
numerical result is available at this preparation checkpoint.

## Verified source publication

The archive, additive implementation, frozen protocol/lock and wiki were
published as `546fb480a451e143178c49b1fa3e4b3ecd39f774`. A remote branch query
confirmed that exact `main` hash after the push. The repository manifest passed
for 6,852 tracked files other than itself; precommit wiki, prose and recovery
validation passed 75 tests and the deterministic prose audit. A clean detached
worktree at that commit passed source-lock and manifest checks before the new
SLURM smoke. This receipt
is a subsequent documentation update and does not change execution source.

## Smoke admission and single-sentinel submission

Smoke `7647608` completed `0:0`, zero restarts, in eight seconds on `a0202`,
with three allocated CPUs for the 8 GiB request and one scientific thread.
Its [attempt receipt](../../results/tcad/cps_support_recovery_v1/smoke/job_7647608/attempt.json)
has SHA-256
`8b0723383c6c840901f60d148a048d1e64eb990d437fdff3a21854cdba66980c`.
Raw worker logs, scheduler logs and terminal accounting are retained beside it.
The compact-support toy mesh has 1,481 nodes and 7,917 tetrahedra. AMG and
direct capacitance are both 1.1590918982639618 pF on the same system; AMG
relative residual is 2.687811032051541e-11. All inherited smoke gates passed.

The earlier wider-support toy mesh yielded 1.0304787645351507 pF, as retained
in the [original evidence](TCAD-Cps-Reference-Pilot.md). The changed value
demonstrates mesh-policy sensitivity on this coarse toy problem. The smoke
only tests agreement between backends on the same matrix; it does not prove
agreement between mesh policies, reference accuracy or convergence. The new
support-sensitivity control remains mandatory, and its result is still pending.

After raw-log reconstruction, source/geometry binding and successful terminal
accounting were verified, feasibility job `7647612` was submitted for layout
597 only. Finalizer `7647619` was submitted with `afterany:7647612`. Both use
the published source and lock above. The
[submission receipt](../../results/tcad/cps_support_recovery_v1/submissions/job_7647612.json)
pins the chain. A scheduler check observed `7647612` RUNNING on `a0102`.
Ongoing artifacts remain in `.internal/tcad-cps-support-recovery-v1/`; do not
copy mutable arm receipts into the terminal archive.

A follow-up check observed the feasibility job still RUNNING with 41 allocated
CPUs for the unchanged 160 GiB request; scientific threads remain one.
The first arm was in mesh generation and no arm had a terminal result at that
observation. Finalizer `7647619` was `PENDING (Dependency)`. The receipt/archive
update passed 75 recovery/wiki/prose tests and the prose audit; the repository
manifest passed for 6,860 tracked files other than itself.

Next: terminal accounting and finalizer review, including the wider-support
check, before considering any separately authorized full-pilot extension.
The numerical gates and all resource caps remain unchanged from their frozen
definitions. No training, full-panel solve, claim admission or paper export
was started. These execution receipts are being synchronized to the wiki and
are not a completed scientific feasibility result.

An unrelated scheduler job was present during inspection and was left
untouched. No prior worktree, original protocol, original lock, baseline FEM
implementation, released paper or internal agent-guidance tracking was changed.
