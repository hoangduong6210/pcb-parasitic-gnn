---
title: Corpus V4 FEM-v2 Accuracy Protocol v3
status: r2 sandbox preflight admitted; checkpoint array active
last_updated: 2026-08-29
paper_source: false
---

# Corpus V4 FEM-v2 Accuracy Protocol v3

## Scientific question

The study measures how closely one fixed message-passing architecture
reproduces four numerical targets on the geometry-valid synthetic active-leg
corpus. It does not measure error against a fabricated board, a continuum
solution, or an unrestricted population of PCB layouts.

The targets are deterministic one-thread `cps_fem_r3_p16_t1_v2` capacitance and
the finalized `fasthenry_100khz_active_leg` primary, secondary, and mutual
inductance observations. Sparse `cps_fem_r4_p16_t1_v2` values are a
higher-resolution comparator used only during held-out finalization. Neither
FEM fidelity is called ground truth.

## Crossed family design

Split seeds 40 through 44 are crossed with initialization seeds 40 through 44,
producing 25 row-major tasks. Each split contains 46 training, 7 validation,
and 13 test families. The five test panels are deterministic and overlap across
splits; they are not independent probability samples.

| Split seed | Training layouts | Validation layouts | Test layouts | R4 test layouts |
|---:|---:|---:|---:|---:|
| 40 | 1,039 | 170 | 291 | 39 |
| 41 | 1,066 | 152 | 282 | 39 |
| 42 | 1,012 | 182 | 306 | 39 |
| 43 | 1,076 | 125 | 299 | 39 |
| 44 | 1,055 | 153 | 292 | 39 |

## Split-scoped training inputs

The deterministic planner emits five training artifacts. Each contains the
geometry, graph input fields, and four target values for one split's training
and validation layouts only. Test layouts, test references, R4 values, and R4
identifiers are absent. Mutating the joined test or R4 records leaves every
training artifact byte-identical; this property is covered by a deterministic
test.

The task manifest retains test membership hashes and an opaque commitment to
the complete held-out artifact. These values identify the future evaluation
without exposing held-out targets to a training process.

## Filesystem isolation

Each task runs under a hash-pinned Bubblewrap executable with `/workspace` as
its root. The mount allowlist contains source code, protocol files, the plan,
the task manifest, exactly one split-scoped training artifact, the Python
environment, and task output paths. It excludes `.git`, `datasets/`, the joined
evaluation artifact, the four other split artifacts, the final result root,
and `/users` from the local mounted filesystem. The host network namespace is
shared because the task authenticates its SLURM allocation. The isolation claim
is therefore limited to the mounted local filesystem; it is not a claim that
the process lacks every network route to externally hosted bytes.

A singleton compute-node preflight must load the selected artifact, construct
all graphs, verify the mount boundary, and exit before the optimizer starts.
Its receipt and terminal accounting are reviewed before the 25-cell array is
submitted. This operational gate tests the actual cluster namespace rather
than relying only on source inspection.

Two infrastructure preflights failed closed. Job `7086917` stopped during
Bubblewrap command parsing because the site executable does not implement
`--clearenv`. It exited before namespace setup, data loading, graph
construction, or optimizer work. Revision r1 used `/usr/bin/env -i` to provide
the same empty-environment contract. Job `7086936` reached the isolated path
but stopped at scheduler self-authentication before data loading or optimizer
work. Revision r2 adds a fixed read-only NSS, Munge, and configless-SLURM
runtime allowlist. It does not change scientific inputs, family membership,
model, optimization, or held-out exclusion. R2 job `7087033` completed in 20 s,
constructed all 1,209 graphs for split 40, passed the local filesystem boundary,
opened no held-out bytes, and started no training. Its admitted receipt
authorizes the frozen checkpoint grid only.

## Model and optimization

The model is a four-layer pure-PyTorch message-passing network with hidden
width 96 and four graph-level outputs. Every cell uses AdamW at learning rate
0.002, weight decay (10^{-5}), batch size 32, gradient clipping at 5, and a
cosine schedule over exactly 200 epochs. Node, edge, and log-target
normalization is fitted on training layouts only. Validation loss is diagnostic
and cannot select an epoch, checkpoint, exclusion, or retry.

Each task writes a safe-NPZ state bundle, learning curve, five validation smoke
examples, source hashes, runtime identity, sandbox receipt, and scheduler
receipt. It emits no test prediction. Checkpoints are never selected by an
accuracy threshold.

## Accepted set and held-out finalizer

Candidate indexing is complete and ordered. Every candidate receives one
machine-readable disposition from a fixed reason-code allowlist. A task is
accepted only when exactly one candidate passes the byte, source, membership,
runtime, sandbox, and terminal scheduler gates. Missing or multiple valid
attempts keep that task pending.

Only a complete 25-task accepted set may authorize held-out finalization. The
finalizer then opens the joined evaluation artifact once, authenticates every
checkpoint again, and writes owned prediction rows for all test layouts. It is
the first process permitted to read test references or R4 values.

## Metrics and interpretation

Family-macro MAPE is the primary summary for each target. Secondary fields are
pooled median, mean, and 95th-percentile APE, physical-unit MAE, signed bias,
(R^2), and counts of nonpositive or nonfinite predictions. Targets are not
averaged across units.

The finalizer also reports violations of

\[
|M| \leq \sqrt{L_pL_s}\,(1+10^{-9}).
\]

Prediction violations remain in the metric table. They are diagnostics, not a
rule for excluding a model or layout.

The complete 5 by 5 metric matrix is retained. A deterministic row-and-column
resampling interval describes sensitivity inside this evaluated seed grid. It
is not a population confidence interval and does not cover machine variation,
alternative protocols, fabricated hardware, or arbitrary PCB layouts.

## Admission states

Protocol freeze, sandbox preflight, checkpoint execution, accepted-set closure,
held-out finalization, archive verification, and scientific claim review are
distinct states. The current lock admits only preflight and, after its review,
checkpoint training. Preflight review is now complete. No model or speed claim
exists until the final archive is independently reviewed and entered in the
claim registry.

The authorized checkpoint grid is array `7087054`. Submission is an operational
state only; individual candidates remain unaccepted until postterminal source,
artifact, sandbox, and scheduler checks close the complete 25-task set.
