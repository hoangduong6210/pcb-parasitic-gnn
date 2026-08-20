# Corpus V4 paired-latency evidence

Status: protocol, plan, and source lock frozen; SLURM preflight pending;
`C-LAT-001` blocked.

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
  `53a8026920adf1c902d3379506bd66cd6f27f1e6ad26b3ebb6ab007a8befc90e`;
- [plan](plan/v1/plan.json), SHA-256
  `1385d9c2a035790927cafbf9ce2164b04851e212078db159bbf3ee0b819e0842`;
- [task manifest](plan/v1/task_manifest.jsonl), SHA-256
  `5720fa35b609fb9783909061f50c6dafc164877a56b51d3c0e974de5aa0cdc00`;
- [panel records](plan/v1/panel_records.jsonl), SHA-256
  `dfed7cc0f40f17809f665fd552f1541ccf2d2bd52041d535c67ab189f19b24db`;
  and
- [execution lock](../../../protocols/corpus_v4_latency_execution_lock_v1.json),
  SHA-256
  `10935acc48e4c1f6fffe19975ec30fdb80e112fd96bb6ebbeab7ddaa508b3e18`.

These hashes identify the planned computation. They are not a latency result.
The execution commit is pinned separately at submission time after tests and
GitHub synchronization pass.

## Interpretation boundary

Any future result applies only to the evaluated CPU allocation, checkpoint,
held-out split, and sequential four-target reference workflow. It must not be
shortened to “faster than 3-D solvers,” generalized to an inductance-only or
capacitance-only request, or described as a hardware-independent confidence
interval.
