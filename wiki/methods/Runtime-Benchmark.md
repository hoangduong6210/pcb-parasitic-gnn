---
title: FEM-v2 Paired Runtime Benchmark Protocol
status: frozen; execution and scoped result admitted
last_updated: 2026-09-13
paper_source: true
prose_reviewed: true
claim_ids: C-LAT-FEMV2-001
---

# FEM-v2 Paired Runtime Benchmark Protocol

This protocol asks a narrow question: on the evaluated CPU class, how long
does the implemented four-target solver workflow take relative to one
warm-loaded GNN query for the same layout? The admitted
[runtime result](../results/Corpus-V4-FEM-v2-Latency.md) follows this protocol.

## Fixed panel and model

The panel contains all 306 layouts in the split-42 held-out partition. These
layouts belong to 13 swap-closed winding-turn families that do not occur in
training or validation for that split. Panel membership follows the accuracy
task manifest and cannot depend on labels, predictions, solver outcomes, or
timings.

The checkpoint is accuracy-v3 task 12, with split seed 42 and initialization
seed 42. It was designated before held-out evaluation and accepted in the
accuracy-v3 artifact set before this runtime protocol was written. The model,
normalization arrays, metadata, smoke examples, and task result are all bound
by SHA-256.

## Compared workflows

The reference workflow starts from canonical JSON bytes already resident in
memory. It parses the layout, runs FastHenry at 100 kHz for \(L_p\), \(L_s\),
and \(M\), then runs the one-thread FEM-v2 R3P16 path for \(C_{ps}\). An outer
wall timer encloses both sequential calls through materialization of all four
float64 values. Component times and the orchestration residual are retained.

The primary GNN boundary also starts from the same in-memory JSON bytes. It
includes strict parsing, geometry validation, graph construction,
normalization, batch-one collation, forward inference, inverse target
transformation, and materialization of four float64 values. Model loading,
Python startup, scheduler queueing, and storage I/O are outside this boundary.
Model-load time is reported separately.

A supporting model-only measurement begins with a normalized batch-one graph
already resident in memory and ends with a standardized four-output CPU tensor.
It helps distinguish neural execution from preprocessing cost. It is not a
denominator for a solver speedup and is not comparable to the historical
400-graph batched-throughput number without stating the different batch size.

## Timing design

For each layout, the GNN receives 50 untimed raw-record warm-ups, 100 timed
calls before the solver workflow, and 100 timed calls after it. The layout-level
GNN time is the median of all 200 raw-record observations. The larger block
median divided by the smaller must not exceed 1.25. The supporting model-only record
uses 50 warm-ups and 200 timed batch-one forward calls.

There is one fresh solver execution per layout. Consequently, the study does
not estimate solver run-to-run variance. Every task retains the individual GNN
durations and the complete solver decomposition.

For layout \(i\), define

\[
S_i^{\mathrm{all4}} =
\frac{T_i^{\mathrm{FH+FEM}}}{\operatorname{median}(T_{i,1:200}^{\mathrm{GNN,raw}})}.
\]

The primary statistic is the median of the 306 values
\(S_i^{\mathrm{all4}}\). Two secondary statistics use the same raw-record GNN
denominator and report FastHenry-only and FEM-only component ratios separately.
They apply to three inductance targets and one capacitance target,
respectively. The ratio of aggregate medians is retained as a diagnostic and
cannot replace the median paired ratio.

The interval calculation performs 10,000 resamples of the 13 held-out families
as whole clusters. Its 2.5 and 97.5 percentiles form a descriptive
family-cluster sensitivity interval on the evaluated split and CPU-node class.
It is not a population or hardware confidence interval. It excludes changes
in software, node class, system load, solver repetition, checkpoint training,
split choice, PCB population, and fabrication.

## Numerical and execution gates

FastHenry and FEM run only inside SLURM tasks. The preflight and full-array
wrappers request one CPU and 48 GiB per task; site policy may allocate more
CPUs for memory. Torch, BLAS, and Gmsh each remain at one scientific thread,
and the worker telemetry must confirm the Gmsh setting.

Fresh solver values must reproduce the frozen four-target references within
relative tolerance \(10^{-4}\). The FEM solve must also match the admitted
mesh-node count, tetrahedron count, and system SHA-256 for that layout. A
timeout, reference drift, mesh-identity drift, nonfinite time, source change,
resource mismatch, missing layout, or nonzero scheduler outcome blocks the
study.

Tasks 0, 152, and 305 form the predesignated preflight. Their observations are
excluded from the final statistics, and the full array reruns them. The current
protocol does not combine retries: incomplete full-array evidence cannot
produce an accepted set. A later attempt would require a new versioned study
instead of selecting among timings.

## Claim language after admission

When every gate closes, the allowable headline has this structure:

> On the frozen 306-layout, 13-family split-42 held-out panel, the predesignated
> accuracy-v3 task-12 checkpoint achieved a median per-layout speedup of
> \(X\)-fold for the sequential FastHenry-100-kHz plus one-thread FEM-v2 R3P16
> workflow used to obtain all four targets, relative to warm-loaded batch-one
> inference from an in-memory raw-layout record to four materialized outputs.
> The 2.5th-to-97.5th-percentile family-cluster resampling sensitivity range
> was \(L\) to \(U\)-fold on the evaluated CPU-node class.

Finalization and archive replay passed. The admitted values are
\(X=70{,}099.076\), \(L=58{,}104.638\), and \(U=93{,}493.252\).
The wording must not be shortened to “faster than 3-D solvers,” applied
to an inductance-only or capacitance-only request, or presented as a universal
hardware result.

The historical 1.16845 ms, rounded 5 s, approximately 4,300-fold, and archived
670-fold values belong only to the
[Historical Claim Ledger](../claims/Historical-Claim-Ledger.md). They are not
priors or evidence for this protocol.
