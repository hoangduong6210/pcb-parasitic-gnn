---
title: Live Execution Snapshot
status: active operational snapshot
last_updated: 2026-08-22
paper_source: false
---

# Live Execution Snapshot

Last scheduler observation: 2026-08-22 02:13 UTC.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | Four missing final-array elements recovered as hash-pinned singletons |
| FEM-R4P16 | `VALIDATED` | 198 of 198 accepted | None | One scheduler-preflight miss recovered as a hash-pinned singleton |
| Joint finalizer | `FINALIZED` | 1,698 long-form observations | None | First submission used a wrong helper path; corrected submission completed |
| R3/R4 discrepancy audit | `COMPLETED` | 198 of 198 pairs across 66 families | None | First job failed closed when site policy allocated 3 CPUs for a 2-CPU request; the corrected gate distinguished requested and allocated resources |
| Corpus V4 accuracy | `FINALIZED AND ADMITTED` | 25 of 25 checkpoints accepted; 25 prediction tables; 7,350 full-test rows | None | The earlier attempt failed closed at admission. The corrected run, finalizer, archive replay, and Git-tracked gate all passed |
| FEM mesh repeatability | `POSTTERMINAL NEGATIVE` | Corrected source Job `6916045`: 15 of 15 elements `COMPLETED/0:0`; Finalizer Job `6916047`: `COMPLETED/0:0`; 30 arm records and terminal admission preserved | Version a deterministic one-thread FEM reference and regenerate Cps labels before retraining | Existing 25-thread arm failed all three mesh/repeatability gates; one-thread diagnostic arm passed all three; paired latency remains closed |
| One-thread FEM qualification | `GATES A/B ADMITTED; GATE C RUNNING` | Gate A: 45 of 45 admitted; Gate B: 9 of 9 admitted; Gate C: 4 of 21 complete, two running | Complete Gate C, terminal finalizer, and postterminal admission | R3 generation is authorized but not started; multi-fidelity generation remains locked until Gate C closes |
| Corpus V4 paired latency | `PREFLIGHT REJECTED / BLOCKED` | 0 of 3 preflight tasks accepted; frozen full scope remains 306 layouts across 13 held-out families | Await a versioned deterministic FEM reference, regenerated labels, model, accuracy evidence, and new latency protocol | Repeatability admission explicitly records `paired_latency_preflight_may_resume=false` |

The successful finalizer closed 1,500 R3 observations and 198 R4 observations
over 1,500 unique geometries. Its output keeps fidelity identifiers explicit.
It does not call either fidelity ground truth, mesh-converged, or physically
validated.

## Why R4 took longer

For the matched layout 717, R3 used 2,062,878 nodes, 12,477,301 tetrahedra,
18.565 GiB peak memory, and 528.949 s. R4 used 9,241,959 nodes, 56,742,824
tetrahedra, 83.240 GiB, and 3,460.433 s. On this layout, R4 increased the mesh
by about 4.5-fold and wall time by about 6.5-fold. This pair illustrates cost;
it is not reported as a corpus median.

The source artifacts are indexed under `E-C4-RUN-02`; complete execution and
finalization closure are indexed under `E-C4-RUN-01` and `E-C4-FINAL-01` in the
[Evidence Ledger](../evidence/Evidence-Ledger.md).

## Next transition

The accuracy pipeline has no remaining execution stage. The paired-latency
scope is now frozen around the designated split-42/init-42 checkpoint, all 306
held-out layouts, and the sequential FastHenry-at-100-kHz plus FEM-R3P16
four-target workflow. The GNN boundary is warm-loaded, batch one, and begins
from an in-memory raw JSON record; model loading is reported separately.

The task runner, accepted-set planner, finalizer, archive verifier, and
deterministic 306-layout plan are implemented. The initial submission request
was rejected before SLURM created a job because it omitted account `pgs0407`.
The account-bound retry entered the scheduler, but all three elements ended
nonzero. Tasks 0 and 152 reached the reference-agreement gate; the old runner
discarded their numerical diagnostics. Task 305 passed that gate and wrote an
artifact, then failed while printing a relative path. Terminal failure makes
the entire preflight ineligible.

The diagnostic rerun used the same frozen tolerance and tasks under source
commit `1766b27`. All three elements produced authenticated, non-admissible
failure artifacts and ended `FAILED/1:0`. Only Cps changed; the three
FastHenry-derived inductance targets matched their frozen references in every
task. Maximum relative Cps drift was `2.6572226e-4`, `1.6908165e-3`, and
`1.0065129e-3` for canonical tasks 0, 152, and 305, respectively, against the
unchanged `1e-4` gate. These are diagnostic values from rejected job `6909354`,
not performance results.

The evidence points to fresh Gmsh meshes changing across executions. A
separately frozen, SLURM-only repeatability study therefore evaluated the same
three preselected anchors with five fresh-mesh repeats under the existing
25-thread meshing path and five under a one-thread diagnostic candidate. The
executable protocol is frozen at SHA-256
`faa71236ce1a77c0d371b2511af2ad3766e57a823c9dd792bee0d4252be438a2`.
The first source array, Job `6915210`, completed all 15 elements and preserved
30 arm records. Finalizer Job `6915245` failed closed before aggregation because
the source producer did not retain three scheduler identities that it had
already authenticated, while the finalizer required their nested copies. The
source artifacts remain unchanged and non-admissible. The corrected contract
retained the identity projection and reran all 30 solves from source commit
`6404073`; no numerical setting or tolerance changed. All 15 source elements
and the finalizer completed with exit code `0:0`. Arm A failed mesh identity
and repeatability on all three layouts, while Arm B passed both on all three.
The terminal admission therefore records
`paired_latency_preflight_may_resume=false`. The next transition is a versioned
one-thread FEM reference followed by complete Cps-label, training, accuracy,
and latency regeneration. Until that sequence closes, `C-LAT-001` remains
blocked and no current speed value is permitted. Baseline, strict E(3), and
ranking comparisons also require their own frozen protocols and jobs.

The new reference is governed by
[Decision 0002](../decisions/0002-deterministic-fem-reference.md). Its first
two gates are now terminal and admitted. Gate A completed all 45 R3P16 solves
with a maximum within-layout relative Cps spread of
`1.1743017900469024e-14`. Gate B completed all nine R3P20 solves; the selected
panel's domain delta had median `0.20585933141613427%` and maximum
`1.0860887365856715%`. Source arrays `6916859` and `6917229`, their finalizers,
and both admission receipts retain the exact commit, protocol, scheduler, and
resource records.

Gate C source array `6923579` and dependency-held finalizer `6923586` are the
active transition. The R4 array runs at concurrency two because each task
requests 160 GiB. At the observation time, tasks 0 through 3 had complete,
integrity-passing artifacts; tasks 4 and 5 were running and the remaining
tasks were held by the array limit. This is an operational snapshot, not a Gate
C result.
