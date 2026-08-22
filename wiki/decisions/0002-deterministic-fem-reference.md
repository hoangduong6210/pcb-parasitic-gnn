---
title: Deterministic FEM Reference Qualification
status: Gates A and B admitted; Gate C not admitted
last_updated: 2026-08-22
paper_source: false
---

# Deterministic FEM Reference Qualification

## Decision

The one-thread Gmsh configuration will be evaluated as a new numerical
reference. It will not replace files, identifiers, or claims from the existing
multi-fidelity package. The candidate uses `cps_fem_r3_p16_t1_v2`,
`cps_fem_r3_p20_t1_v2`, and `cps_fem_r4_p16_t1_v2` as fidelity identifiers.
Qualification artifacts live under
`results/corpus_v4/cps_reference_v2/qualification/v1`. Geometry membership
remains fixed to the accepted
1,500-layout corpus, and any later R4 package must retain the existing
198-layout registry.

The earlier three-layout experiment established that the candidate was worth
qualifying. It did not establish production repeatability, domain adequacy, or
mesh convergence. The 1,500-layout R3 route is locked behind Gates A and B. A
new R4 package is also locked behind the Gate C task-validity and repeatability
checks.

## Frozen panel

The qualification panel is the nine-layout set used by the completed
refine-3/refine-4 study. Its task order and geometry identities are:

| Panel index | Layout | Geometry SHA-256 |
|---:|---:|---|
| 0 | 1055 | `b1d837fc6357a278ef823510dd7c5e162fa5b686c8e4827ec383d2d14fe2c590` |
| 1 | 407 | `5cc53be678ba4bb99fb0ea35a8cf5ef32c94bb5a44b4210a595f7ed46e0a3d4f` |
| 2 | 1351 | `4222c3ba94b2ebd609325a5cbbaecf72ed6857a9053b84b5b35cb7d77396114d` |
| 3 | 149 | `0e2aef8a6ec688d3b271569091cd9a3d8ad786a1bc5f54bb3456ec292eda96b4` |
| 4 | 275 | `4c4fd2bb497d7ff0dd0230c8ba2de38edc1a5cf6bdeebb66d5f5362b60400eaa` |
| 5 | 897 | `b3c7d59b256d0c8be29350058f32a6f6fb3f1904300e6329bd5b6e8989d9c8b3` |
| 6 | 2 | `10814d8ca1c0e84e6991ec01a56d862a9068ef2e3f4b1484c25bddd26fe81ad0` |
| 7 | 173 | `46c646aa28dc248a0e0d1c2017ba88d4f99c4a574905622998611f41613364f5` |
| 8 | 1400 | `c4e6703313879d673d12f5eefb0c2a0fbc0a5b556d05300cfcfa209dc86f311f` |

Membership is inherited without reselection. Layouts 407, 275, and 173 are the
three R4 repeatability sentinels. They are the historical median-Cps member of
each trace-count triplet in the earlier label-informed convergence panel. This
selection uses no new v2 output, but it is not described as label-blind or
resource-only.

The panel is deterministic and selected. It is not a probability sample from
the corpus. The geometry file SHA-256 is
`17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b`.
The inherited panel source is bound by SHA-256
`78ee69aac46fbce3f914617b6d9cbc4ac51cc56b82f7944f34d2bd9c4172daa1`.
If Gate C proceeds, the unchanged 198-layout registry is bound by SHA-256
`675f46e1777c2f07d4774853d0fa78f89851e3abc78acd184771832ec0973da9`.

## Gate A: R3 repeatability

Each of the nine layouts receives five fresh R3P16 meshes under the pinned
one-thread environment. Array task \(t\) maps to panel index
\(\lfloor t/5\rfloor\) and repeat `t mod 5`, for task IDs 0 through 44. A
layout passes only if all five solves satisfy the
solver, residual, resource, source, environment, and scheduler contracts and
also have:

- one system SHA-256 value;
- invariant node and tetrahedron counts; and
- a maximum pairwise relative Cps spread no larger than \(10^{-4}\).

Every Cps value must be finite and positive; `solver_info` must be zero; and the
final relative residual must not exceed \(10^{-9}\). All 45 source tasks must
finish with terminal state `COMPLETED` and exit code
`0:0`. A valid group that violates identity, count, or spread criteria is a
negative repeatability result. Missing, corrupt, or nonterminal evidence makes
the gate indeterminate. Neither state opens Gate B, and a panel summary cannot
mask an individual layout failure.

## Gate B: domain sensitivity

Gate B may run only after a positive postterminal Gate A receipt. Its task ID is
the panel index, 0 through 8. It computes one R3P20 observation for each panel
layout and compares it with `repeat_id=0` of the admitted R3P16 group:

\[
\Delta_{\mathrm{domain},i}
=
100\frac{|C_{i,\mathrm{R3P16}}-C_{i,\mathrm{R3P20}}|}
{|C_{i,\mathrm{R3P20}}|}.
\]

The machine-readable thresholds are 2% for the median and 5% for the maximum.
Exactly nine finite, positive observations must satisfy all numerical,
resource, provenance, and terminal-accounting gates. If this valid comparison
exceeds either threshold, P16 is scientifically rejected. A missing, corrupt,
timed-out, resource-exceeded, or numerically invalid task makes the gate
indeterminate and not admitted; it does not establish domain inadequacy. A
failure does not authorize an automatic switch to P20. A P20 candidate would
require a new, prospectively frozen P20-versus-P24 protocol.

## Gate C: R4 qualification

Gate C may run only after a positive postterminal Gate B receipt and is required
only for a new multi-fidelity package. The three sentinels receive five fresh
R4P16 meshes each; the other six panel layouts receive one R4P16 mesh each, for
exactly 21 tasks. Every task must satisfy the Gate B finite-value, numerical,
resource, provenance, and terminal-accounting rules. Every sentinel must also
pass the Gate A identity and repeatability criteria. `repeat_id=0` is the
canonical R4 value for each sentinel; the sole observation is canonical for
every other layout. These values are compared with `repeat_id=0` from R3P16 on
all nine layouts:

\[
\Delta_{\mathrm{mesh},i}
=
100\frac{|C_{i,\mathrm{R3P16}}-C_{i,\mathrm{R4P16}}|}
{|C_{i,\mathrm{R4P16}}|}.
\]

The machine-readable median and maximum thresholds are 2% and 5%. R4
repeatability or task-validity failure blocks a new R4 package. A valid
comparison that exceeds the mesh thresholds is retained as a terminally
authenticated negative mesh-sensitivity observation; it does not block an
explicit multi-fidelity package whose two targets remain separately named.
Passing this finite adjacent-mesh test does not establish continuum convergence
or physical ground truth. Gate C tests R4 at fixed padding and makes no
independent R4 domain sensitivity claim.

## Execution and admission

The stages are separate SLURM arrays. Each stage has a lightweight finalizer
that writes a preterminal result. A solver-free admission step runs only after
the finalizer has left the queue and verifies its terminal accounting. The
receipt, rather than an empty queue or a preterminal file, opens the next stage.

The numerical environment requests one compute thread. Gmsh, OpenMP, BLAS,
MKL, BLIS, and NumExpr are pinned to one thread and read back by the worker.
R3 requests 48 GiB and two hours per task. R4 requests 160 GiB and three hours.
Scheduler-inflated CPU allocation caused by a memory request is recorded as
allocation provenance; it is not interpreted as solver thread count.

No tolerance may be changed after outputs are inspected. Failed and incomplete
attempts remain evidence and are never overwritten. Infrastructure failure may
be retried only with the same frozen protocol. A numerical failure remains a
failure and is not replaced by a successful repeat. Accepted sets reject
ambiguous duplicate valid attempts.

The execution protocol pins `rtol=1e-10`, `maxiter=500`,
`solver_info=0`, a residual limit of `1e-9`, positivity, finite values, package
versions, source hashes, exact task mappings, and fail-fast resource ceilings.
The protocol's deterministic task expansion and computational-source map are
the combined plan and execution lock. The executable authority is the protocol
SHA-256 together with the clean source commit supplied at submission; both are
retained by every task. Until manifest closure, clean tests, commit, push, and
CI are complete, this page freezes the scientific design but is not a
submission root. Node placement is retained in task and accounting receipts;
no minimum node count is assumed because placement is controlled by the
scheduler.

## Execution state

The executable protocol was committed and pushed before execution. [GitHub
Actions run 32473093332](https://github.com/hoangduong6210/pcb-parasitic-gnn/actions/runs/32473093332) passed for source commit
`4270e11456a575b05f11ec3b67cddda9ce845798`; the protocol used by every task
has SHA-256
`912506b638c737b0e87022fb793392ebba5824f50f33fbabdc8913ba3f38908f`.

Gate A source array `6916859` completed all 45 elements with exit code `0:0`;
finalizer `6916860` also completed normally. The postterminal receipt records a
positive repeatability result across all nine layouts. Gate B source array
`6917229` completed all nine elements with exit code `0:0`; finalizer `6917238`
also completed normally. Its postterminal receipt records median and maximum
domain deltas of `0.20585933141613427%` and `1.0860887365856715%`, so the R3
generation route is open.

Gate C was submitted as source array `6923579` with finalizer job `6923586`
under the same source and protocol lock. This commit contains no Gate C
admission, so it asserts no Gate C outcome. Mutable scheduler state belongs in
the [live execution snapshot](../status/Live-Execution.md).

## Consequences

If Gate A fails, production stops and the mesher must be serialized more
strictly or its mesh must be frozen as an input artifact. If a valid Gate B
comparison exceeds its thresholds, P16 is rejected. If Gates A and B pass, a
new R3-only fixed numerical target may be generated. Gate C repeatability and a
complete one-thread regeneration of the fixed 198-layout registry are
additionally required for a new multi-fidelity package. A negative adjacent
mesh result remains a scoped result rather than a reason to merge the two
fidelities.

New capacitance observations require new training, accuracy, and latency
protocols. Accuracy and speed values attached to the archived package do not
transfer to the candidate reference.
