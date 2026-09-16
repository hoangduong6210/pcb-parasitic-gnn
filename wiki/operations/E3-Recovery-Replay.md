---
title: Coordinate Ablation Recovery Replay
status: VALIDATED execution procedure
last_updated: 2026-09-15
paper_source: false
---

# Coordinate Ablation Recovery Replay

## Purpose and boundary

Decision [0004](../decisions/0004-e3-validation-replay-threads.md) separates
numerical replay recovery from the immutable training experiment. All 25
training receipts and 75 checkpoint bundles remain unchanged. Recovery uses
eight numerical threads and the original validation tolerance. It does not
train, select checkpoints, change splits, or establish an inference-time claim.

The worker is `code/experiments/proofs/recover_strict_e3_fem_v2_v1.py`;
its protocol is `protocols/corpus_v4_strict_e3_fem_v2_recovery_v1.json`.
The latter pins each original task receipt and the diagnostic evidence.

## Ordered gates

| Stage | Required evidence | Output and permission |
|---|---|---|
| `admit` | Frozen source, protocol, lock, all 25 task receipts and terminal accounting | Replays validation and trained symmetry for all 75 checkpoints; emits an accepted set without opening held-out inputs |
| `finalize` | Pinned accepted set from a successfully completed admission | Rechecks all tasks, then computes held-out predictions and paired contrasts |
| `verify` | Pinned accepted set and analysis manifest, completed finalizer | Numerically reconstructs outputs and writes an archive manifest |
| Tracked `verify` | Existing archive plus one clean evidence checkout | Reconstructs again and checks that the full evidence closure is Git-tracked |

Every numerical stage runs through SLURM with eight requested CPUs, 48 GiB,
30 minutes, account `pgs0407`, partition `nextgen`, and requeue disabled.
Memory-driven allocation may provide more CPUs; numerical libraries still use
eight threads. An accepted artifact is not an admitted scientific claim.

## Submission and monitoring

Use a clean, committed recovery checkout. Set `PCB_GNN_RECOVERY_ROOT`,
`PCB_GNN_RECOVERY_COMMIT`, `PCB_GNN_RECOVERY_PROTOCOL_SHA256`, and
`PCB_GNN_E3_ROOT` to verified paths and hashes. The scientific root initially
remains the original frozen execution checkout. Create its recovery checkout's
`logs/` directory before submission. Select `PCB_GNN_RECOVERY_STAGE=admit`.

```bash
sbatch -A pgs0407 --export=ALL code/jobs/submit_recover_strict_e3_fem_v2_v1.sh
squeue -u "$(id -un)" -o '%.20i %.28j %.10T %.10M %R'
sacct -X -n -P -j JOB_ID --format=JobIDRaw,State,ExitCode,Restarts,ElapsedRaw,NodeList,ReqTRES,AllocTRES
```

Do not run the worker directly on a login node. Admission prints one progress
line per validated task. A successful receipt alone is insufficient: its job
must also reach `COMPLETED/0:0` with zero restarts before finalization.

For `finalize`, additionally set `PCB_GNN_RECOVERY_ACCEPTED_SET` and
`PCB_GNN_RECOVERY_ACCEPTED_SHA256`. For `verify`, also set
`PCB_GNN_RECOVERY_ANALYSIS_MANIFEST` and `PCB_GNN_RECOVERY_ANALYSIS_SHA256`.
For tracked replay, copy and commit the completed evidence, create a clean
checkout, use that checkout as both roots, set `PCB_GNN_RECOVERY_ARCHIVE`,
and set `PCB_GNN_RECOVERY_REQUIRE_GIT_TRACKED=1`. Preserve the original
training bindings; do not relabel checkpoints with the recovery commit.

Record job identifiers, terminal accounting, receipt hashes, local commits
and remotely verified publication in [Live Execution](../status/Live-Execution.md).
If a gate fails, preserve its logs and stop the next stage. Do not loosen
tolerances or overwrite failed evidence to obtain a passing result.

## Shared-filesystem visibility

During the first archive replay, accounting reported successful completion
before the login node could see the newly written receipt directory. A later
read exposed both files and independent hashes agreed. If this occurs, wait
briefly and repeat read-only checks of the exact logged output path. Do not
resubmit a successful computation merely because one immediate file lookup
fails. Completion is accepted only after both terminal accounting and the
expected validated artifact are available.
