---
title: TCAD Dielectric Boundary-Mesh Runbook
status: PROPOSED; frozen source regression passed; publication and execution pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric Boundary-Mesh Runbook

This is a separate mesh-only protocol, following the validated native CAD
prerequisite and the [boundary-audit implementation](../methods/TCAD-Dielectric-Boundary-Mesh.md).
The [evidence page](../evidence/TCAD-Dielectric-Boundary-Mesh.md) owns actual
source, submission and terminal observations. Do not submit from this prose
alone or reuse the old CAD-only allocation or failed all-volume source.

1. Complete fake-native, tiny-array, bundle, predecessor/archive and wiki/prose
   tests. Freeze using `code/experiments/proofs/tcad_cps_dielectric_mesh.py
   --freeze-lock`; it must refuse replacing an existing lock. Rerun the source
   closure and full tests after freeze. Old dependencies remain byte-identical.
2. Publish and remotely verify a clean execution commit. Create a sparse,
   detached execution worktree with the full new lock closure, the lock itself,
   `.gitignore` and `MANIFEST.json`. Use the validated sparse-index/materialization
   sequence in the [CAD runbook](TCAD-Dielectric-CAD-Diagnostic.md); do not make
   a full quota-heavy clone or remove scientific worktrees/evidence. Check quota
   before adding the checkout and expected chunk files.
3. Set `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT`,
   `PCB_TCAD_LOCK_SHA256`, `PCB_GNN_PYTHON=/usr/bin/python3` and no-bytecode
   mode. Unset credentials. Create the frozen checkout's log directory, check
   source/runtime and submit `code/jobs/submit_tcad_cps_dielectric_mesh.sh` once.
   Preserve exact submission time, arguments, scheduler reply and source hashes.
4. One node/task, account `pgs0407`, partition `nextgen`, one requested CPU,
   160 GiB and 55 minutes. These are the previous mesh-study allocation limits,
   not the smaller CAD-only allocation. Scientific threads remain one even when
   memory policy allocates more CPUs. Toy/local1/repeat1 worker ceilings remain
   600/1,200/1,200 seconds and 6/120/120 GiB RSS. Node/tetrahedron ceilings remain
   300,000/1,500,000 for toy and 3,000,000/20,000,000 for sentinel modes.
5. Keep HXT, compact Box fields, sizes, padding and seed unchanged; disable
   automatic optimization and call the default explicit optimizer exactly once
   with the frozen arguments. Source/runtime and actual allocation/compute-host
   guards run before numerical/native imports in parent, worker and builder.
   There is no array, requeue, retry, alternative optimizer or cap escalation.
6. Preserve raw and freshly extracted final packets separately. Triangle caps
   are four times the tetrahedron cap; aggregate raw/final array bytes must fit
   2 GiB per mode. Each little-endian chunk is at most 32 MiB. Retain partial
   bundles when interrupted and preserve native stdout/stderr. Never overwrite
   an attempt/bundle or delete a failed raw packet.
7. Stop at first failure. A worker watchdog kills its process group at time/RSS
   caps. Parent receipts hash logs and all produced payload files, including
   partial files. Passed modes also verify CAD and exact bundle metadata/bytes;
   this verification is not a numerical audit replay on login.
8. After terminal accounting, perform metadata-only `terminal_review` in
   `run_tcad_cps_dielectric_mesh.py`. Complete coverage requires `COMPLETED/0:0`;
   controlled incomplete coverage requires `FAILED/2:0`, both with zero restarts.
   Preserve source/submission, complete or partial packets, raw logs and exact
   accounting in a new additive terminal archive before further studies.

A terminal collector must be bound to the actual immutable source and job.
Numerical bundle loading or auditing of real arrays is SLURM-only. Positive
element quality/boundary consistency does not authorize a field solve or paper
claim; field equivalence and sensitivity have separate later protocols.
