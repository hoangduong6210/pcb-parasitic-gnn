# Corpus V4 paired-latency evidence

Status: protocol, plan, and source lock frozen; SLURM preflight pending;
`C-LAT-001` blocked.

## Submission status

The first preflight request was rejected before SLURM created a job because
the project account was omitted. No solver, graph construction, or timing code
ran, and the request produced no result artifact. The replacement execution
contract pins account `pgs0407` in the protocol, all three batch wrappers, the
active scheduler receipt, and terminal accounting.

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
- [plan](plan/v1/plan.json), SHA-256
  `983f2427ebc808e1ae681df4f719df07aacf7064a13cd841c363d69a3cfe3c25`;
- [task manifest](plan/v1/task_manifest.jsonl), SHA-256
  `db47a120c8113c156d0d7010204721fe2770dda848c4f1a547753de3b046b8c2`;
- [panel records](plan/v1/panel_records.jsonl), SHA-256
  `dfed7cc0f40f17809f665fd552f1541ccf2d2bd52041d535c67ab189f19b24db`;
  and
- [execution lock](../../../protocols/corpus_v4_latency_execution_lock_v1.json),
  SHA-256
  `f5f4e14f843505ff4eefb51febdd70e8b051bd893b08d4a7483b8168f8558c74`.

These hashes identify the planned computation. They are not a latency result.
The execution commit is pinned separately at submission time after tests and
GitHub synchronization pass.

## Interpretation boundary

Any future result applies only to the evaluated CPU allocation, checkpoint,
held-out split, and sequential four-target reference workflow. It must not be
shortened to “faster than 3-D solvers,” generalized to an inductance-only or
capacitance-only request, or described as a hardware-independent confidence
interval.
