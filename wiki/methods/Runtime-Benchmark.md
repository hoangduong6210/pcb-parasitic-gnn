---
title: Runtime Benchmark Protocol
status: frozen current-corpus protocol; execution pending
last_updated: 2026-08-20
paper_source: true
prose_reviewed: true
claim_ids: C-LAT-001
---

# Runtime Benchmark Protocol

Runtime claims are valid only when the compared outputs and timing boundaries
match. The project distinguishes three GNN boundaries:

| Boundary | Included work |
|---|---|
| Pre-collated batch throughput | Forward execution of an already batched graph bank |
| Prepared single forward | One already constructed graph through the model |
| Warm-loaded raw-record end to end | Parse one in-memory raw JSON record, validate it, construct and normalize the graph, collate a batch of one, run inference, invert the target transform, and materialize four outputs |

The current benchmark uses the third boundary. The model and normalization are
loaded and authenticated before timing. Model-load time is measured and
reported separately; process startup and storage I/O are outside the primary
per-query boundary. Each timed repetition begins from the same immutable JSON
bytes in memory. It does not reuse a parsed layout, graph, or collated batch.

## Frozen comparison

The benchmark uses the accepted checkpoint designated as task 12 before any
accuracy outcome was observed. Its split seed and initialization seed are both
42. The evaluation set is the complete 306-layout test partition: 13
swap-closed geometry families that are absent from training and validation. No
layout is sampled from, or substituted into, this partition for timing.

For each layout, the reference path runs FastHenry at 100 kHz to obtain
\(L_p\), \(L_s\), and \(M\), followed by FEM-R3P16 to obtain \(C_{ps}\). The two
solvers are executed sequentially, so the reference time is their summed wall
time. The GNN path returns all four quantities from one warm-loaded, batch-one
call at the raw-record boundary above. Both paths run within the same scheduler
allocation for that layout.

This is a comparison with the implemented sequential four-target workflow. It
does not describe a parallel solver deployment, an inductance-only request, a
capacitance-only request, or every program that may be called a 3-D solver.

## Timing and estimator

Each layout has one timed execution of the complete solver workflow. This
choice controls compute cost but does not estimate solver run-to-run variation.
The GNN receives 50 untimed warm-up calls, followed by 100 timed repetitions
before the solver workflow and 100 timed repetitions after it. Warm-up outputs
are checked but excluded. The combined 200 observations define the layout's
GNN median, while the two block medians remain available as an order and load
diagnostic. Every timed repetition begins from the raw JSON bytes, uses batch
size one, and retains its individual duration.

Let \(T_i^{\mathrm{ref}}\) be the FastHenry wall time plus the FEM-R3P16 wall
time for layout \(i\), and let \(T_i^{\mathrm{gnn}}\) be the median of its 200
GNN repetitions. The paired ratio is

\[
S_i=\frac{T_i^{\mathrm{ref}}}{T_i^{\mathrm{gnn}}}.
\]

The primary result is the median of the 306 values \(S_i\). The median reference
time and median GNN time may be reported as supporting summaries, but their
ratio is not the paired-speedup estimator.

The uncertainty calculation uses 10,000 family-cluster bootstrap draws. Each
draw resamples the 13 held-out families as whole clusters and recomputes the
median paired ratio. The resulting 95% range is called a family-cluster
bootstrap sensitivity interval on the evaluated split and allocation. It is
not a population confidence interval. In particular, it excludes solver
run-to-run variation, system load, other hardware, software changes, model
retraining, other split choices, arbitrary PCB layouts, and fabrication
variability.

## Execution and failure gates

The timer is monotonic and high resolution. The record freezes the CPU model,
requested and allocated resources, affinity, scientific thread settings,
device, batch size, warm-up and repeat counts, timer, software versions, solver
settings, checkpoint identity, and source identity. Public records omit private
node names.

A layout is accepted only when both solvers complete, reproduce their frozen
references within the declared numerical tolerances, and emit one complete
timing record. A missing layout, timeout, nonfinite duration, solver failure,
reference drift, resource mismatch, or non-successful scheduler outcome blocks
the final result. Recovery repeats the same layout under the same protocol in a
new attempt. It does not replace the layout, change the timeout, discard a slow
observation, or select the fastest attempt.

The claim remains blocked until all 306 layouts enter one accepted set, the
SLURM finalizer completes, and the tracked archive passes clean-clone
verification.

## Prohibited wording

Do not write:

- “faster than 3-D solvers” without naming the sequential FastHenry-plus-
  FEM-R3P16 four-target workflow;
- “end-to-end including model load” for the warm-loaded per-query boundary;
- a ratio of aggregate medians as the median paired speedup;
- an inductance-only or capacitance-only speedup from the four-target ratio;
- the historical approximately 4,300-fold or 670-fold values as current-corpus
  evidence;
- a universal hardware or PCB speedup from the evaluated allocation;
- “95% confidence interval” for the family-cluster sensitivity range; or
- a current speed value before finalization and archive closure.

Historical timing boundaries and their exact interpretation are listed in the
[Historical Claim Ledger](../claims/Historical-Claim-Ledger.md).
