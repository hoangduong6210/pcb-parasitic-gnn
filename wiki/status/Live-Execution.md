---
title: Live Execution Snapshot
status: active operational snapshot
last_updated: 2026-08-29
paper_source: false
---

# Live Execution Snapshot

Last scheduler-backed admission: 2026-08-29 11:13 UTC.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| Archived 25-thread FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | Four missing final-array elements recovered as hash-pinned singletons |
| Archived 25-thread FEM-R4P16 | `VALIDATED` | 198 of 198 accepted | None | One scheduler-preflight miss recovered as a hash-pinned singleton |
| Archived 25-thread joint finalizer | `FINALIZED` | 1,698 long-form observations | None | First submission used a wrong helper path; corrected submission completed |
| R3/R4 discrepancy audit | `COMPLETED` | 198 of 198 pairs across 66 families | None | First job failed closed when site policy allocated 3 CPUs for a 2-CPU request; the corrected gate distinguished requested and allocated resources |
| Pre-FEM-v2 Corpus V4 accuracy | `FINALIZED AND ADMITTED` | 25 of 25 checkpoints accepted; 25 prediction tables; 7,350 full-test rows | None | Version-scoped to the archived 25-thread capacitance package; does not transfer to FEM-v2 |
| FEM mesh repeatability | `POSTTERMINAL NEGATIVE` | Corrected source Job `6916045`: 15 of 15 elements `COMPLETED/0:0`; Finalizer Job `6916047`: `COMPLETED/0:0`; 30 arm records and terminal admission preserved | None; its one-thread successor dataset is finalized | Existing 25-thread arm failed all three mesh/repeatability gates; one-thread diagnostic arm passed all three; paired latency remains closed |
| One-thread FEM qualification | `ALL STAGES ADMITTED` | Gate A: 45 of 45 source tasks completed; Gate B: 9 of 9 completed; Gate C: 21 of 21 completed; one postterminal stage admission per gate | None | Gate C passed three-sentinel R4 repeatability but returned a negative finite-panel mesh-sensitivity observation; both fidelities remain explicit |
| One-thread FEM-v2 production | `FINALIZED AND POSTTERMINAL ADMITTED` | 1,500 of 1,500 R3; 198 of 198 R4; 1,698 long-form observations; no pending or terminal-negative task | None; downstream accuracy-v2 preparation is frozen separately | Infrastructure cancellations were recovered only through hash-pinned pending sets; final admission SHA-256 `b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed` |
| FEM-v2 accuracy preparation | `FROZEN; TRAINING ADMITTED` | Deterministic 1,500-row evaluation join and 25-task 5 by 5 plan | Submit checkpoint-only SLURM array from the clean execution commit | Held-out inference, model claims, and speed claims remain closed |
| Corpus V4 paired latency | `PREFLIGHT REJECTED / BLOCKED` | 0 of 3 preflight tasks accepted; frozen full scope remains 306 layouts across 13 held-out families | Await a new FEM-v2 model, admitted accuracy evidence, and separately frozen latency protocol | Repeatability admission explicitly records `paired_latency_preflight_may_resume=false` |

Two versioned capacitance packages now exist. The archived 25-thread package
owns `C-ACC-001` and the admitted selected-registry discrepancy. The new
one-thread FEM-v2 finalizer `7084776` closed 1,500 R3 observations and 198 R4
observations over the unchanged 1,500 geometries. Its postterminal receipt sets
`dataset_generation_admitted=true` and
`accuracy_protocol_may_be_frozen=true`, but retains
`training_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. Neither fidelity is ground truth, mesh-converged,
or physically validated.

## Why the archived R4 run took longer

For the matched layout 717, R3 used 2,062,878 nodes, 12,477,301 tetrahedra,
18.565 GiB peak memory, and 528.949 s. R4 used 9,241,959 nodes, 56,742,824
tetrahedra, 83.240 GiB, and 3,460.433 s. On this layout, R4 increased the mesh
by about 4.5-fold and wall time by about 6.5-fold. This pair illustrates cost;
it is not reported as a corpus median.

The source artifacts are indexed under `E-C4-RUN-02`; complete execution and
finalization closure are indexed under `E-C4-RUN-01` and `E-C4-FINAL-01` in the
[Evidence Ledger](../evidence/Evidence-Ledger.md).

## Next transition

Dataset generation and accuracy-v2 preparation are closed. The only authorized
next transition is to submit the frozen 25-task checkpoint-only array from its
clean execution commit. The accepted-set gate must close all checkpoints before
held-out inference. The existing accuracy protocol, checkpoints, and
`C-ACC-001` remain immutable evidence for the archived 25-thread package and
must not be relabelled as FEM-v2 results.

The completed production chain used R3 sources/finalizers
`6963561/6963562`, `7004761/7004762`, `7022705/7022706`, and
`7057802/7057803`, followed by the exact 55-task hash-pinned retry
`7064645/7064646`. The final R3 admission closed 1,500 accepted, zero pending,
and zero terminal-negative tasks. R4 source/finalizer `6963559/6963560`
closed 198 accepted, zero pending, and zero terminal-negative tasks. Dataset
finalizer `7084776` then completed `0:0`; the solver-free admission replayed the
full closure.

The frozen adjacent-mesh result remains negative, so the new package is still
multi-fidelity rather than mesh-converged. Paired latency, baseline, strict
E(3), and ranking results require their own FEM-v2 protocols and jobs after a
new model is admitted. `C-LAT-001` remains blocked and no current speed value is
permitted.
