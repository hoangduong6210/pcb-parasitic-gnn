---
title: Live Execution Snapshot
status: running
last_updated: 2026-08-17
paper_source: false
---

# Live Execution Snapshot

Last scheduler observation: 2026-08-17 14:01 UTC.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | None after singleton recovery |
| FEM-R4P16 | `RUNNING` | 103 of 198 completed | Two array elements running | None observed |
| Joint finalizer | `BLOCKED` | Not started | Waits for exact R4 coverage | Not applicable |

The remaining R4 elements show `JobArrayTaskLimit` while two tasks run. This is
the intended concurrency throttle, not a scheduler fault.

## Why R4 takes longer

For the matched layout 717, R3 used 2,062,878 nodes, 12,477,301 tetrahedra,
18.565 GiB peak memory, and 528.949 s. R4 used 9,241,959 nodes, 56,742,824
tetrahedra, 83.240 GiB, and 3,460.433 s. On this layout, R4 increased the mesh
by about 4.5-fold and wall time by about 6.5-fold. This pair illustrates cost;
it is not reported as a corpus median.

The two source artifacts are indexed under `E-C4-RUN-02` in the
[Evidence Ledger](../evidence/Evidence-Ledger.md).

## Next transition

When R4 finishes, build the cumulative candidate index, run resume validation,
retry only pending canonical indices if necessary, and submit the joint
finalizer only after exact R3 and R4 coverage passes. Do not start training from
partial observations.
