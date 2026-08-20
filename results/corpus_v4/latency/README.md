# Corpus V4 paired-latency evidence

Status: diagnostic preflight rejected; FEM repeatability protocol frozen and
SLURM execution pending; `C-LAT-001` blocked and the 306-layout full array
closed.

## Submission status

The first preflight request was rejected before SLURM created a job because
the project account was omitted. No solver, graph construction, or timing code
ran, and the request produced no result artifact. The account-bound preflight
then ran tasks 0, 152, and 305. All three ended nonzero: the first two reached
the solver-reference agreement gate, while task 305 wrote a complete artifact
and then failed during path-label formatting. No task from that job is
admissible. The preserved task-305 files remain operational regression evidence
only. Their immutable [rejection sidecar](preflight/rejections/job_6907776/task_305/REJECTION_RECEIPT.json)
separates artifact integrity from the failed scheduler admission without
modifying the historical result or manifest.

The diagnostic rerun under source commit `1766b27` confirmed that the hardened
failure path works. Tasks 0, 152, and 305 all produced immutable failure
artifacts and ended `FAILED/1:0`; none produced a success artifact. Their
maximum relative Cps drifts were `2.6572226e-4`, `1.6908165e-3`, and
`1.0065129e-3`, respectively, against the unchanged `1e-4` gate. Each record
sets both `admission_eligible` and `claim_eligible` to false. The terminal
[scheduler receipt](preflight/failures/job_6909354/SCHEDULER_RECEIPT.json)
binds those diagnostics to account, node, elapsed time, resource request, exit
status, and file hashes. These values diagnose repeatability only and are not
latency or speed results.

The current evidence indicates that fresh FEM meshes differ across executions,
while the FastHenry-derived inductance targets remain unchanged. The next
scientific step is the frozen
[FEM repeatability study](../../../wiki/methods/FEM-Repeatability.md), protocol
SHA-256
`f79129828011ff0ed16ae163cc136d41b67eac0f0cac276fdbdbb3192cadd960`;
its SLURM execution is pending and the existing tolerance will not be relaxed
post hoc. A future full array additionally
requires an authenticated three-task preflight admission artifact.

This directory is reserved for the current-corpus paired-latency evidence. It
does not contain an admitted speed result. The scientific protocol is owned by
the [Runtime Benchmark Protocol](../../../wiki/methods/Runtime-Benchmark.md),
and current execution state is owned by
[Live Execution](../../../wiki/status/Live-Execution.md).

## Frozen scope

The benchmark uses the accepted checkpoint designated as task 12 before its
accuracy outcome was observed. It covers all 306 layouts and all 13 unseen
families in the split-42 test partition.

For each layout, the reference path sequentially runs FastHenry at 100 kHz for
\(L_p\), \(L_s\), and \(M\), then FEM-R3P16 for \(C_{ps}\). The comparison path
uses warm-loaded, batch-one GNN inference from an in-memory raw JSON record to
four materialized outputs. Model loading is timed separately. Both paths use
the same scheduler allocation for that layout.

There is one timed solver execution per layout. GNN timing uses 50 untimed
warm-ups, 100 recorded repetitions before the solver workflow, and 100 more
after it. The combined 200 observations form the per-layout GNN median. The
primary statistic is the median of the 306 per-layout solver-to-GNN ratios. A
10,000-draw family-cluster bootstrap
produces a descriptive sensitivity interval over the 13 evaluated families.
It does not estimate solver run-to-run noise, system-load variation, other
hardware, retraining, arbitrary PCB layouts, or fabrication variability.

## Required evidence lifecycle

The eventual closure must contain:

1. a frozen protocol, layout registry, checkpoint identity, source identity,
   and execution contract;
2. one complete task record for every canonical layout, including individual
   GNN repetitions and the full solver timing;
3. scheduler-backed acceptance with no missing, substituted, or ambiguously
   repeated layout;
4. a SLURM finalizer that recomputes paired ratios and the family-cluster
   sensitivity interval; and
5. a tracked archive that passes clean-clone verification.

A failure, timeout, resource mismatch, reference drift, or missing record blocks
the result. No current speed value is claim eligible before all five stages
close.

## Frozen roots

The immutable execution inputs are:

- [protocol](../../../protocols/corpus_v4_latency_v1.json), SHA-256
  `5bafd175e5df19f2a94382b543c6a4a9dba2c9e6ecca365b5e9d0b4de00b90a2`;
- [current plan](plan/v2/plan.json), SHA-256
  `9ef641a1ccd3d4a12f72e30971a61eb82813d59e41b9666ebfd6e1602a9d1281`;
- [current task manifest](plan/v2/task_manifest.jsonl), SHA-256
  `db47a120c8113c156d0d7010204721fe2770dda848c4f1a547753de3b046b8c2`;
- [current panel records](plan/v2/panel_records.jsonl), SHA-256
  `dfed7cc0f40f17809f665fd552f1541ccf2d2bd52041d535c67ab189f19b24db`;
  and
- [current execution lock](../../../protocols/corpus_v4_latency_execution_lock_v2.json),
  SHA-256
  `ea758cef72d09aec7514255ddb3bf60323965ae7fd6b57af0d15384d60a65d82`.

These hashes identify the planned computation. They are not a latency result.
The execution commit is pinned separately at submission time after tests and
GitHub synchronization pass. These current roots require a positive
postterminal FEM-repeatability receipt before a new preflight and an
authenticated preflight admission before the full array. Historical rejected
jobs remain bound to immutable `plan/v1` and execution-lock v1 bytes recorded
in the evidence ledger and in their artifacts. Current execution uses the
separately versioned v2 plan and lock.

## Interpretation boundary

Any future result applies only to the evaluated CPU allocation, checkpoint,
held-out split, and sequential four-target reference workflow. It must not be
shortened to “faster than 3-D solvers,” generalized to an inductance-only or
capacitance-only request, or described as a hardware-independent confidence
interval.
