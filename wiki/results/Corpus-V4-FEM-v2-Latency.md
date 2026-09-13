---
title: Corpus V4 FEM-v2 Paired Latency
status: admitted version-scoped result
last_updated: 2026-09-13
paper_source: true
prose_reviewed: true
claim_ids: C-LAT-FEMV2-001
---

# Corpus V4 FEM-v2 Paired Latency

## Evaluation scope

The study compares one GNN call returning \(C_{ps}, L_p, L_s, M\) with a
sequential FastHenry plus electrostatic FEM workflow obtaining the same four
targets. It covers all 306 layouts from the frozen split-42 test partition,
which contains 13 held-out, swap-closed turn-count families. The checkpoint
uses split seed 42 and initialization seed 42 and was designated before the
latency measurements. All measurements use the evaluated AMD EPYC 7H12 CPU
class with one scientific thread per timing task.

FastHenry evaluates the three inductance targets at 100 kHz. Capacitance uses
the admitted one-thread FEM-v2 R3P16 reference configuration, with refinement
level 3 and a 16 mm domain padding. These are synthetic active-leg geometries;
the timing result applies to this reference implementation and configuration.

## Timing boundary

Both workflows start from the same canonical JSON bytes already in memory.
The GNN timer includes JSON parsing, geometry validation, graph construction,
feature normalization, batch-one collation, the forward pass, inverse target
transformation and materialization of four physical output values. The model
is already loaded. Each design receives 50 warm-up calls and 200 measured
calls, with 100 measurements before and 100 after its solver workflow.

The solver timer encloses one sequential FastHenry and FEM execution per
design. It includes input construction, temporary-file handling, subprocess
execution, result parsing, numerical checks and four-value materialization.
No previously computed solver result is reused. Model loading, training,
application startup and reading the initial layout from storage are outside
the GNN timing boundary. Internal solver file operations remain inside the
solver boundary. The comparison therefore describes repeated use of a loaded
surrogate against this complete numerical reference workflow.

## Paired result

For design \(i\), let \(g_i\) be the median of its 200 GNN latencies and
\(s_i\) its single observed four-target solver latency. The primary statistic
is

\[
S = \operatorname{median}_{i=1}^{306}\left(\frac{s_i}{g_i}\right).
\]

The observed value is **70,099.076 times** for the sequential FastHenry plus
one-thread FEM-v2 R3P16 workflow used to obtain all four targets.

| Comparison against the same four-output GNN call | Median per-design ratio | 95% family-cluster descriptive sensitivity interval |
|---|---:|---:|
| Sequential four-target workflow, primary | 70,099.076 | 58,104.638 to 93,493.252 |
| FastHenry, three inductance targets, secondary | 10.367 | 10.292 to 10.598 |
| One-thread FEM-v2 R3P16 capacitance, secondary | 70,086.935 | 58,092.504 to 93,479.634 |

The secondary rows describe component costs relative to the same GNN call.
They do not establish timings for separately optimized single-target models.
Capacitance dominates the observed four-target solver cost.

| Timing component | Median across designs |
|---|---:|
| Loaded GNN, resident raw JSON to four outputs | 7.41936 ms |
| Sequential four-target solver workflow | 522.98245 s |
| FastHenry component | 80.96604 ms |
| One-thread FEM-v2 R3P16 component | 522.90512 s |
| Model-only forward pass, supporting diagnostic | 2.76481 ms |
| Authenticated model loading, reported separately | 59.25445 ms |

The component medians are descriptive. Their ratio is not the primary
statistic, and component medians need not sum to the median total. The
model-only forward time excludes graph preparation and is not used in any
solver-to-GNN ratio.

## Sensitivity and numerical checks

The descriptive interval resamples the 13 held-out families with replacement,
retains every design within each selected family, and recomputes the median
per-design ratio. The reported endpoints are the 2.5th and 97.5th percentiles
of 10,000 draws. The primary statistic weights designs equally; family sizes
are retained during resampling. This interval describes sensitivity to family
composition on the evaluated split and CPU class. It is not a population or
hardware confidence interval and does not quantify variation across training
seeds, retraining, software environments or repeated solver executions.

All 306 designs satisfy the frozen numerical and timing gates. The largest
pre/post GNN block-median ratio is 1.23910, below the 1.25 limit. Fresh solver
outputs agree with the pinned reference values to a maximum relative
difference of \(1.39\times10^{-14}\), within the \(10^{-4}\) tolerance, and
the FEM mesh and system identities match their admitted references. These
checks establish consistency of the measured computation with the numerical
reference; they do not establish physical accuracy or mesh convergence.

## Claim interpretation

The result measures runtime for a designated checkpoint and numerical
workflow. It does not establish a universal speedup over 3-D solvers, a
comparison with optimized parallel solvers, or fabricated-board performance.
The single solver observation per design also leaves run-to-run system-load
variation unquantified. Earlier runtime studies used different geometries,
fidelities and timing boundaries, so this value is not evidence of an
improvement over their reported ratios.

Predictive accuracy has a separate evidence basis in the
[FEM-v2 family-held-out accuracy study](Corpus-V4-FEM-v2-Accuracy.md).
The latency claim is owned by `C-LAT-FEMV2-001`; its admission and execution
provenance are maintained in the [evidence ledger](../evidence/Evidence-Ledger.md).
