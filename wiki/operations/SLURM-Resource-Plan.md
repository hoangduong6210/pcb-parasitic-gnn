---
title: SLURM Resource Plan
status: frozen execution specification
last_updated: 2026-08-15
paper_source: false
---

# SLURM Resource Plan

Field solves and model training are not executed on a login node. The following
allocations are frozen for the current capacitance-label stage.

| Stage | Tasks | Per-task request | Concurrency | Fail-fast wall | Scheduler wall cap |
|---|---:|---|---:|---:|---:|
| FEM-R3P16 bulk | 1,500 | 25 CPU, 48 GiB | 8 | 1,800 s | 2 h |
| FEM-R4P16 validation | 198 | 25 CPU, 160 GiB | 2 | 7,200 s | 3 h |
| Artifact-set finalizer | 1 | 2 CPU, 16 GiB | 1 | Not applicable | 30 min |

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
limit, monitoring commands, and rejection taxonomy.
