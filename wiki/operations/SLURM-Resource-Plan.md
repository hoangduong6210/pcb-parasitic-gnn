---
title: SLURM Resource Plan
status: frozen execution specification
last_updated: 2026-08-22
paper_source: false
---

# SLURM Resource Plan

Field solves and model training are not executed on a login node. The table
records frozen allocations used or planned across Corpus V4 solver, accuracy,
latency, and diagnostic stages.

The active QOS permits at most 1,000 submitted array elements per user. R3 is
therefore dispatched as 400, 400, 400, and 300 tasks. Only the first two R3
shards are queued with the 198-task R4 array (`400 + 400 + 198 = 998`); later
R3 shards pass a live submission-capacity gate before they are queued.

| Stage | Tasks | Per-task request | Concurrency | Fail-fast wall | Scheduler wall cap |
|---|---:|---|---:|---:|---:|
| FEM-R3P16 bulk | 1,500 | 25 CPU, 48 GiB | 8 | 1,800 s | 2 h |
| FEM-R4P16 validation | 198 | 25 CPU, 160 GiB | 2 | 7,200 s | 3 h |
| Cps artifact-set finalizer | 1 | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |
| Accuracy training grid | 25 | 8 CPU, 48 GiB | 5 | Not applicable | 4 h |
| Accuracy finalizer | 1 | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |
| Paired-latency preflight | 3 | 25 CPU, 48 GiB | 1 | 1,800 s FEM; 300 s FastHenry | 2 h |
| Paired-latency full panel — blocked | 306 | 25 CPU, 48 GiB | 8 | 1,800 s FEM; 300 s FastHenry | 2 h |
| Paired-latency finalizer — blocked | 1 | 2 CPU, 8 GiB | 1 | Not applicable | 20 min |
| FEM repeatability diagnostic — completed negative | 15 elements, 2 FEM solves per element | 25 CPU, 48 GiB | 3 | 1,800 s per FEM arm | 2 h |
| FEM repeatability finalizer — completed | 1 | 2 CPU, 8 GiB | 1 | Not applicable | 30 min |
| One-thread FEM v2 Gate A qualification | 45 | 1 requested CPU, 48 GiB | 8 | 1,800 s | 2 h |
| One-thread FEM v2 Gate B qualification | 9 | 1 requested CPU, 48 GiB | 8 | 3,600 s | 2 h |
| One-thread FEM v2 Gate C qualification | 21 | 1 requested CPU, 160 GiB | 2 | 7,200 s | 3 h |
| One-thread FEM v2 stage finalizer | 1 per executed gate | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |

Gate A contains five fresh R3P16 meshes for each of nine layouts. Gate B is one
R3P20 mesh per layout and was executed only after Gate A admission. Gate C
contains five R4P16 meshes for each of three sentinels and one for each of the
other six layouts; it was executed only after Gate B admission for the new
multi-fidelity route. Lifecycle and current scheduler state are maintained in
[Live Execution](../status/Live-Execution.md). Requested CPU, allocated CPU,
and billing TRES are retained separately because the scheduler may increase
CPU allocation to satisfy a large memory request.

The fail-fast caps are scientific protocol fields. A task that exceeds a cap is
an infeasibility result and is not silently rerun with a wider limit.

## Expected active wall time

The completed nine-layout study observed median worker wall times of about 520 s
for FEM-R3P16 and 3,452 s for FEM-R4P16. If queueing and retry time are excluded,
these medians imply approximately:

| Stage | Median-based active wall estimate |
|---|---:|
| FEM-R3P16 at concurrency 8 | 27.1 h |
| FEM-R4P16 at concurrency 2 | 94.9 h |

These are planning estimates, not promised runtimes. Node placement, scheduler
policy, filesystem load, failed tasks, and memory-based charging can change
elapsed and billed usage. In particular, a scheduler may charge more CPU
equivalents than the requested 25 CPUs when a 160 GiB memory request determines
the allocation.

## Retry accounting

Every initial task writes a start checkpoint and then a separate completed
attempt. The resume planner accepts only explicitly indexed, byte-hashed tasks
whose solver, residual, resource, source, environment, scheduler, plan, and
manifest records recompute exactly. It emits a sparse pending task set. A retry
array maps dense retry indices back to the original canonical task indices and
retains the original plan and manifest identities.

The finalizer requires exact coverage of all 1,500 R3 tasks and all 198 R4 tasks.
Missing tasks, extra tasks, corrupted attempts, or two valid attempts for one
canonical task prevent finalization.

See the [SLURM Submission Playbook](SLURM-Submission-Playbook.md) for the exact
account, immutable-worktree preflight, R3 sharding required by the cluster array
and QOS limits, absolute job-environment export, monitoring commands, and
rejection taxonomy.
