---
title: Live Execution Snapshot
status: completed
last_updated: 2026-08-19
paper_source: false
---

# Live Execution Snapshot

Last scheduler observation: 2026-08-20 04:40 UTC.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | Four missing final-array elements recovered as hash-pinned singletons |
| FEM-R4P16 | `VALIDATED` | 198 of 198 accepted | None | One scheduler-preflight miss recovered as a hash-pinned singleton |
| Joint finalizer | `FINALIZED` | 1,698 long-form observations | None | First submission used a wrong helper path; corrected submission completed |
| R3/R4 discrepancy audit | `COMPLETED` | 198 of 198 pairs across 66 families | None | First job failed closed when site policy allocated 3 CPUs for a 2-CPU request; the corrected gate distinguished requested and allocated resources |
| Corpus V4 accuracy | `RUNNING: CHECKPOINT-ONLY RERUN` | 5 tasks running, 20 pending, 0 checkpoints accepted | Array `6904424`; monitor all 25 logical components before accepted-set reconstruction | The earlier attempt completed training but failed closed at admission. The corrected run matches logical identity on `JobID`, canonicalizes complete TRES maps, and passed its compute-node resource gate |

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

The earlier checkpoint-only attempt is operational regression evidence only.
No finalizer or held-out inference ran, and its checkpoints cannot cross the
changed source and execution-lock root. The clean rerun is now active. Its
remaining sequence is accepted-set reconstruction, SLURM finalization, and
archive verification. Completion of training alone will not admit an accuracy
statement. The completed discrepancy audit admits no runtime headline by
itself.
