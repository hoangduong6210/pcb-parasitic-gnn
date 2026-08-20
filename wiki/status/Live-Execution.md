---
title: Live Execution Snapshot
status: active operational snapshot
last_updated: 2026-08-20
paper_source: false
---

# Live Execution Snapshot

Last archive observation: 2026-08-20 06:15 UTC.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | Four missing final-array elements recovered as hash-pinned singletons |
| FEM-R4P16 | `VALIDATED` | 198 of 198 accepted | None | One scheduler-preflight miss recovered as a hash-pinned singleton |
| Joint finalizer | `FINALIZED` | 1,698 long-form observations | None | First submission used a wrong helper path; corrected submission completed |
| R3/R4 discrepancy audit | `COMPLETED` | 198 of 198 pairs across 66 families | None | First job failed closed when site policy allocated 3 CPUs for a 2-CPU request; the corrected gate distinguished requested and allocated resources |
| Corpus V4 accuracy | `FINALIZED AND ADMITTED` | 25 of 25 checkpoints accepted; 25 prediction tables; 7,350 full-test rows | None | The earlier attempt failed closed at admission. The corrected run, finalizer, archive replay, and Git-tracked gate all passed |
| Corpus V4 paired latency | `DIAGNOSTIC REFREEZE / BLOCKED` | 0 of 3 preflight tasks accepted; frozen full scope remains 306 layouts across 13 held-out families | Push the diagnostic source lock, then rerun the unchanged three-layout preflight | Tasks 0 and 152 failed the reference-agreement gate; task 305 wrote an artifact but returned nonzero on path formatting; all three are ineligible |

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

The diagnostic refreeze keeps every scientific setting unchanged. It writes a
separate non-admissible failure artifact after reauthenticating the source and
fixes only the path-label conversion. The next transition is the same
three-layout preflight from the new committed source. The full array remains
closed.
If it passes, the same lock authorizes the full array, followed by accepted-set
construction, SLURM finalization, and archive verification. Until that sequence
closes, `C-LAT-001` remains blocked and no current speed value is permitted.
Baseline, strict E(3), and ranking comparisons also require their own frozen
protocols and jobs.
