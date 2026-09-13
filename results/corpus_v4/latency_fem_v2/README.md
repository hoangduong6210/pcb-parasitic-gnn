# FEM-v2 paired-latency study

Status: full array `7260429` completed all 306 tasks with exit `0:0`, and
round 00 accepted every observation. Finalizer `7271384` failed at output-path
printing after writing analysis files. Recovery finalization and archive
replay are required; no current speed claim has been admitted.

Execution source commit: `186ba2cbaf6a24bf62641eb2f2eba8ee3530dad6`.
The documentation branch may advance while this detached checkout remains
fixed; never substitute the documentation commit for the execution commit.

This namespace holds the current paired runtime study. It is independent of
the rejected 25-thread experiments in `results/corpus_v4/latency/`. Historical
records are preserved in that directory and cannot be copied into this study.

## Scientific scope

The fixed panel is the full split-42 held-out partition used by accuracy-v3
task 12: 306 layouts from 13 families. The selected checkpoint has split seed
42 and initialization seed 42. It was designated and accepted before held-out
inference.

For every layout, one allocation runs these paths:

1. FastHenry at 100 kHz for `L_pri_nH`, `L_sec_nH`, and `L_mut_nH`.
2. One-thread FEM-v2 R3P16 for `Cps_pF`.
3. Warm-loaded batch-one GNN inference from canonical JSON bytes in memory to
   four physical float64 values.

An outer wall timer encloses the sequential FastHenry and FEM calls. Their
component timers and the orchestration residual are retained. The primary
estimand is the median of 306 per-layout ratios between the paired four-target
solver wall time and the raw-record GNN median. FastHenry-only and
FEM-only ratios are secondary quantities with their target scope stated
explicitly.

The GNN record contains 50 warm-ups and two blocks of 100 observations around
the solver run. A block-median drift above 1.25 rejects the task. A separate
200-observation model-only timing starts from resident, normalized batch-one
graph tensors. It is diagnostic and is never used as the solver-speedup
denominator.

## Numerical gates

Fresh solver outputs must agree with the frozen FEM-v2 and FastHenry labels to
within the protocol tolerance. The FEM replay must also reproduce the admitted
mesh-node count, tetrahedron count, and system SHA-256 for the layout. Gmsh,
BLAS, and Torch scientific work each use one thread. SLURM may allocate more
CPUs to satisfy the 48 GiB request; requested resources, allocated resources,
and scientific thread counts are recorded separately.

Three preflight layouts, task IDs 0, 152, and 305, must complete with exact
`COMPLETED/0:0` accounting before the full array can be submitted. They are
rerun by the full array and excluded from the final statistics. This protocol
does not combine retry attempts: any incomplete full array blocks admission
and requires a separately versioned study.

## Frozen roots

- Protocol: `protocols/corpus_v4_latency_fem_v2_v1.json`, SHA-256
  `6459fb716b79f0a95436691c9430e6505d5590d493f1e7e3ff191cbd602b4bf9`.
- Plan: `results/corpus_v4/latency_fem_v2/plan/v1/plan.json`, SHA-256
  `2ad12cdc11c356716e0cf0422f4e429a25bc1c094fe9a5ead4c7bc0ee0479cfb`.
- Task manifest: `results/corpus_v4/latency_fem_v2/plan/v1/task_manifest.jsonl`,
  SHA-256
  `75ce9cebb34d4288077d38a33d418e5de391ebc94bd8aa3f10e03bee51631d04`.
- Panel records: `results/corpus_v4/latency_fem_v2/plan/v1/panel_records.jsonl`,
  SHA-256
  `a32682b8d6263d0ee256584b66883499883b6fd3ff3511011967743e3c6d4e32`.
- Execution lock: `protocols/corpus_v4_latency_fem_v2_execution_lock_v1.json`,
  SHA-256
  `b5ee0844267f261f7766bd1fb4265f8cf93da55f4194bcd67f81d38ada6061e5`.

These hashes describe a planned computation and are not runtime results.

## Preflight execution and live job

The three immutable job-scoped preflight tasks and their SHA-256 manifests are
in [`preflight/attempts/job_7259818`](preflight/attempts/job_7259818).
The [`preflight admission`](preflight/admission/job_7259818/PREFLIGHT_ADMISSION.json)
has SHA-256
`0cd724afb3b80be4e4b424da511009a0d931dce88b3ab1ba200766ffba47c5cf`.
Its independently replayed gate accepted all three terminal `0:0` tasks for
full-array submission while explicitly setting `claim_eligible=false`.
Six raw SLURM stdout/stderr captures are under [`preflight/logs`](preflight/logs).
The initial relative-output admission invocation saved the file and then
exited nonzero only when printing a relative path as if it were absolute.
No admission artifact was overwritten; an independent exact-SHA replay passed
before full array `7260429` was submitted. Pass an absolute `--out` path when
building another admission, as indexed by the
[SLURM playbook](../../../wiki/operations/SLURM-Submission-Playbook.md).

## Claim boundary

No speed value is currently admitted. A result becomes eligible only after
the preflight admission, complete 306-task execution, terminal accepted set,
SLURM finalizer, archive reconstruction, and wiki claim review all pass.

Historical 1.16845 ms throughput, the rounded 5 s estimate, approximately
4,300-fold, and the archived 670-fold result do not enter this protocol. Their
measurement boundaries remain documented in the Historical Claim Ledger.

## Artifact map

- `plan/v1/`: frozen plan, panel and task order.
- `preflight/`: three-layout qualification and admission.
- `jobs/attempts/job_7260429/`: 306 original timing records and task manifests.
- `logs/full_array_7260429/`: original task stdout and stderr.
- `resume/round_00/`: complete accepted set, candidate index and empty pending set.
- `diagnostics/job_7271384/`: failed analysis attempt; excluded from claims.
- `final/`: successful analysis packages, when admitted through archive replay.

All 306 source tasks completed with exit `0:0`. The original finalizer failed
after writing output because its final path-print combined relative and absolute
paths. Recovery changes analysis provenance and path handling only. It does not
repeat solvers, select new observations, or change the statistical estimand.

The original task execution lock and its 39 source hashes remain unchanged.
A separate finalizer execution lock binds that task lock, its source commit,
the accepted-set hash and the recovery source closure. Finalizer success and
archive verification are required before its output supports a claim.

See the [evidence ledger](../../../wiki/evidence/Evidence-Ledger.md) and
[live execution page](../../../wiki/status/Live-Execution.md) for admission status.
