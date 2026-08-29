---
title: SLURM Resource Plan
status: frozen execution specification
last_updated: 2026-08-29
paper_source: false
---

# SLURM Resource Plan

Field solves and model training are not executed on a login node. The table
records frozen allocations used or planned across Corpus V4 solver, accuracy,
latency, and diagnostic stages.

The active QOS permits at most 1,000 submitted array elements per user. The
operator uses 950 as a softer ceiling so that monitoring and finalization do
not race the scheduler limit. R4 is submitted first. R3 is divided into four
immutable shards of 400, 400, 400, and 300 tasks, and each later shard waits
for the previous wave's terminal admission. This keeps the project near 600
submitted elements at its busiest point instead of filling 998 slots at once.

| Stage | Tasks | Per-task request | Concurrency | Fail-fast wall | Scheduler wall cap |
|---|---:|---|---:|---:|---:|
| Archived FEM-R3P16 bulk | 1,500 | 25 CPU, 48 GiB | 8 | 1,800 s | 2 h |
| Archived FEM-R4P16 validation | 198 | 25 CPU, 160 GiB | 2 | 7,200 s | 3 h |
| FEM-v2 R3P16 one-thread generation | 1,500 | 1 requested CPU, 48 GiB | 8 | 1,800 s | 2 h |
| FEM-v2 R4P16 one-thread generation | 198 | 1 requested CPU, 160 GiB | 2 | 7,200 s | 3 h |
| FEM-v2 wave or dataset finalizer | 1 per wave | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |
| Cps artifact-set finalizer | 1 | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |
| FEM-v2 accuracy-v2 diagnostic grid | 25 | 8 CPU, 48 GiB | 5 | Not applicable | 4 h |
| FEM-v2 accuracy-v3 sandbox preflight | 1 | 8 CPU, 48 GiB | 1 | Exits before optimizer work | 4 h |
| FEM-v2 accuracy-v3 training grid | 25 | 8 CPU, 48 GiB | 5 | Not applicable | 4 h |
| FEM-v2 accuracy-v3 finalizer | 1 | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |
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

The completed one-thread qualification observed a median elapsed time of 534 s
for R3 and 3,360 s for R4. If queueing, admission gaps, and retries are
excluded, the full planned coverage implies approximately:

| Stage | Median-based active wall estimate |
|---|---:|
| FEM-v2 R3P16 at concurrency 8 | 27.3 h |
| FEM-v2 R4P16 at concurrency 2 | 94.1 h |

These are planning estimates, not promised runtimes. Node placement, scheduler
policy, filesystem load, failed tasks, and memory-based charging can change
elapsed and billed usage. During qualification, the site allocated 13 CPUs for
a 48 GiB task and 41 CPUs for a 160 GiB task even though each job requested one
CPU. The solver remained serialized because the wrapper and child telemetry
both recorded one numerical thread. Requested CPU, allocated CPU, and billing
TRES must therefore remain separate fields.

## Retry accounting

Every initial task writes a start record and a separate completed attempt. A
wave finalizer runs with `afterany`, because failed source elements must still
be classified and retained. The postterminal admission accepts only
byte-hashed tasks whose solver, residual, resource, source, environment,
scheduler, plan, dispatch, and manifest records recompute exactly. It emits a
sparse pending set. A retry maps dense local array indices back to the original
canonical task indices and retains the same frozen identities.

The finalizer requires exact coverage of all 1,500 R3 tasks and all 198 R4 tasks.
Missing tasks, extra tasks, corrupted attempts, or two valid attempts for one
canonical task prevent finalization.

See the [SLURM Submission Playbook](SLURM-Submission-Playbook.md) for the exact
account, immutable-worktree preflight, R3 sharding required by the cluster array
and QOS limits, absolute job-environment export, monitoring commands, and
rejection taxonomy.
