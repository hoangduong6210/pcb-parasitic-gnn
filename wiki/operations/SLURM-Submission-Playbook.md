---
title: SLURM Submission Playbook
status: active operational runbook
last_updated: 2026-08-15
paper_source: false
---

# SLURM Submission Playbook

This page is the canonical operational procedure for the Cps multi-fidelity
pipeline. It is not manuscript source. Solver work and model training must run
through SLURM; the login node is used only for validation, submission,
monitoring, hashing, and small artifact-index operations.

## 1. Frozen roots

Copy expected hashes from the reviewed [Evidence Ledger](../evidence/Evidence-Ledger.md),
not from the files being checked. The current plan root is
`419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a`.
The R3 and R4 manifest hashes are respectively
`3eb7931837bcc813523905386a9e9898ee135ababc482e124b927df52f59c7d2`
and `88c15d2489ee069e0b76a1e62074725796c847df5eeaaa0c88a6e0bb10e1df1d`.

Before any submission, define project-specific variables:

```bash
RUN_ROOT=/absolute/path/to/the/detached-clean-worktree
SOURCE_CORPUS_DIR=/absolute/path/to/final/job_6818436
PLAN_DIR="$RUN_ROOT/results/corpus_v4/cps_multifidelity/plan/v1"
PLAN_SHA256=419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a
EXECUTION_LOCK="$RUN_ROOT/protocols/corpus_v4_cps_execution_lock_v1.json"
EXECUTION_LOCK_SHA256=697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb
PCB_PYTHON=/usr/bin/python3
SLURM_ACCOUNT=pgs0407
PCB_JOB_ENV="$RUN_ROOT/code/jobs/slurm_job_env.sh"
```

Never derive `EXECUTION_LOCK_SHA256` from `EXECUTION_LOCK` and then treat that
value as an independent trust root.

### Execution-lock revision boundary

The active corpus and every recovery attempt for it use lock v1 from the
detached source commit recorded in the evidence ledger. Lock v1 pins the
original runner, including its base-array scheduler-query behavior. Do not copy
the patched runner into that worktree: source validation will reject it, and a
new-lock artifact cannot be mixed with the existing v1 artifact set.

Lock v2 (`protocols/corpus_v4_cps_execution_lock_v2.json`, SHA-256
`111ff2347f74afd4a280cc21b8a337387f982341367e6b73550794b13089f081`)
pins the exact-component scheduler query for future complete executions. It is
not used to repair or finalize the active v1 corpus.

## 2. Cluster facts to check first

The project account is `pgs0407`, the partition is `nextgen`, and every
submission must contain `-A pgs0407`. The 2026-08-15 cluster configuration has
`MaxArraySize=1001`; therefore an array index of 1499 is invalid. The active
`ascend-default` QOS also has `MaxSubmitJobsPU=1000`, so the number of running
plus pending array elements for the user must remain below 1,000.

```bash
scontrol ping
scontrol show config | rg 'MaxArraySize|MaxMemPerCPU'
sacctmgr -n -P show assoc user="$(id -un)" format=Cluster,Account,Partition,DefaultQOS
sacctmgr -n -P show qos ascend-default format=Name,MaxSubmitJobsPU,MaxJobsPU,MaxTRESPU
sinfo -p nextgen -o '%P %a %l %D %t %C %m'
```

Observed policy can allocate more CPUs than requested when memory determines
the node share. For example, the R4 request is 25 CPU and 160 GiB, while OSC
may allocate 41 CPU. The pipeline validates both records:

- `ReqTRES` and `TresPerTask` must retain the requested 25 CPU;
- `SLURM_CPUS_PER_TASK`, `NumCPUs`, `CPUs/Task`, and `AllocTRES` must agree on
  the actual allocation;
- requested and allocated memory must remain 160 GiB.

Do not hard-code 41 as a scientific setting. It is a scheduler allocation
caused by the current memory-per-CPU policy.

## 3. Immutable execution worktree

Commit and test the source before creating a dedicated detached worktree:

```bash
REVIEWED_COMMIT="replace-with-reviewed-40-character-commit"
git worktree add --detach "$RUN_ROOT" "$REVIEWED_COMMIT"
cd "$RUN_ROOT"
git status --porcelain
python3 code/quality/build_manifest.py --check
sha256sum "$PLAN_DIR/plan.json" "$EXECUTION_LOCK"
```

`git status --porcelain` must initially be empty. Dispatch, index, log, and
result artifacts are then intentionally created as untracked operational data.
Immediately before submission, the runner's actual clean-source policy must
still produce no output:

```bash
git status --short --untracked-files=no
git status --short --untracked-files=all -- code protocols
```

Do not edit tracked files in this worktree while arrays or the finalizer are
active. No task may overwrite an existing attempt.

Always export the absolute `PCB_GNN_JOB_ENV` shown in Section 1. Slurm's
`--chdir` changes the batch working directory but does **not** change
`SLURM_SUBMIT_DIR`; relying on `--chdir` alone can make the spool copy look for
`code/jobs/slurm_job_env.sh` under the SSH login directory.

## 4. Static validation without a solve

```bash
python3 -m pytest -q
python3 code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$PLAN_SHA256" \
  --manifest "$PLAN_DIR/r4_manifest.jsonl" \
  --execution-lock "$EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
  --validate-only
sbatch --test-only -A pgs0407 code/jobs/submit_corpus_v4_cps_r4.sh
```

Also verify that `logs/` exists, the source corpus hashes match the protocol,
the output paths do not collide with an older attempt, and quota is sufficient.

## 5. Generate and verify R3 dispatch shards

R3 has 1,500 canonical tasks and cannot use `--array=0-1499`. The array-size
limit alone would permit a 1,001-task shard, but the 1,000-task QOS submission
limit rejects it. Generate four 400-task-or-smaller dispatch sets. This also
leaves room to queue two R3 shards and all 198 R4 tasks concurrently:
`400 + 400 + 198 = 998`.

```bash
python3 code/experiments/proofs/plan_corpus_v4_cps_submission_shards.py \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$PLAN_SHA256" \
  --manifest "$PLAN_DIR/r3_manifest.jsonl" \
  --execution-lock "$EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
  --max-array-size 400 \
  --out results/corpus_v4/cps_multifidelity/dispatch/r3_qos400
jq '.shards' results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/submission_shards.json
SHARD_A_SHA256=$(jq -r '.shards[0].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/submission_shards.json)
SHARD_B_SHA256=$(jq -r '.shards[1].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/submission_shards.json)
SHARD_C_SHA256=$(jq -r '.shards[2].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/submission_shards.json)
SHARD_D_SHA256=$(jq -r '.shards[3].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/submission_shards.json)
```

The required partition is:

| Shard | Canonical tasks | Local array | Tasks |
|---|---:|---:|---:|
| A | 0–399 | `0-399%8` | 400 |
| B | 400–799 | `0-399%8` | 400 |
| C | 800–1199 | `0-399%8` | 400 |
| D | 1200–1499 | `0-299%8` | 300 |

The shard sets must be disjoint and their sorted union must equal every
canonical index from 0 through 1499. Record each task-set SHA-256 before
submission. Never hand-edit or renumber a dispatch set.

Validate each shard with the runner's `--validate-only`, adding the concrete
path and the corresponding `SHARD_A_SHA256` or `SHARD_B_SHA256`:

```text
--retry-task-set "$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/dispatch_shard_000.json"
--expected-retry-task-set-sha256 "$SHARD_A_SHA256"
```

## 6. Submit R3 and R4

Submit shard A first. Submit shard B with `afterany` so total R3 concurrency
never exceeds eight, while failures in A do not suppress independent work in B.

```bash
R3_A_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-399%8 \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/dispatch_shard_000.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_A_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)

R3_B_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-399%8 \
  --dependency="afterany:$R3_A_JOB_ID" \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/dispatch_shard_001.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_B_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)

R4_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON" \
  code/jobs/submit_corpus_v4_cps_r4.sh)
```

Do not submit C or D immediately: the first two R3 shards plus R4 already use
998 of the 1,000 submitted-task slots. When earlier tasks leave `squeue`, count
all of the user's remaining array elements and submit the next dependent shard
only if the explicit capacity gate passes:

```bash
SUBMITTED_COUNT=$(squeue -r -h -u "$(id -un)" -o '%i' | wc -l)
if (( SUBMITTED_COUNT > 600 )); then
  echo "Wait: R3 shard C needs 400 free QOS submission slots" >&2
  exit 1
fi
R3_C_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-399%8 \
  --dependency="afterany:$R3_B_JOB_ID" \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/dispatch_shard_002.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_C_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)
```

The `-r` flag is mandatory. Without it, `squeue` prints compressed array ranges
and the line count can be hundreds of tasks smaller than the QOS accounting
count. Treat `QOSMaxSubmitJobPerUserLimit` as a failed capacity preflight: no
job ID exists, and the only valid action is to wait and recompute the expanded
count.

Repeat the live count before D; a 300-task shard requires the current count to
be at most 700:

```bash
SUBMITTED_COUNT=$(squeue -r -h -u "$(id -un)" -o '%i' | wc -l)
if (( SUBMITTED_COUNT > 700 )); then
  echo "Wait: R3 shard D needs 300 free QOS submission slots" >&2
  exit 1
fi
R3_D_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-299%8 \
  --dependency="afterany:$R3_C_JOB_ID" \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_qos400/dispatch_shard_003.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_D_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)
```

Record all returned IDs in the evidence ledger, not in manuscript-source pages.
Scheduler acceptance changes the relevant lifecycle from `PLANNED` to
`RUNNING`; it does not admit an accuracy or speed claim.

## 7. Monitor scheduler and artifact progress

```bash
squeue -j "$R3_A_JOB_ID,$R3_B_JOB_ID,$R3_C_JOB_ID,$R3_D_JOB_ID,$R4_JOB_ID" \
  -o '%.20i %.32j %.2t %.10M %.10l %R'
scontrol show job -o "$R4_JOB_ID"
sacct -j "$R4_JOB_ID" \
  --format=JobIDRaw,JobName,State,ExitCode,Elapsed,MaxRSS,ReqMem,AllocCPUS,NodeList
R4_TASK_JOB_ID=$(squeue -h -r -j "$R4_JOB_ID" -t R -o '%i' | head -n 1)
sstat -j "${R4_TASK_JOB_ID}.batch" \
  --format=JobID,MaxRSS,AveRSS,AveCPU,MaxDiskRead,MaxDiskWrite
rg -n 'Traceback|ERROR|refusing|mismatch|timed.out|task_pass' logs
find results/corpus_v4/cps_multifidelity/r3/attempts -name 'task_[0-9][0-9][0-9][0-9].json' | wc -l
find results/corpus_v4/cps_multifidelity/r4/attempts -name 'task_[0-9][0-9][0-9][0-9].json' | wc -l
```

An empty `squeue` is not proof of success. Inspect `sacct`, task JSON, gate
results, and accepted/pending coverage. Run the `sstat` command only when
`R4_TASK_JOB_ID` is non-empty; completed steps belong in `sacct`, not `sstat`.

## 8. Build candidate indexes and resume safely

Create candidate indexes only from explicit job attempt directories:

```bash
R3_CANDIDATE_INDEX=results/corpus_v4/cps_multifidelity/index/r3_candidates.json
R4_CANDIDATE_INDEX=results/corpus_v4/cps_multifidelity/index/r4_candidates.json
python3 code/experiments/proofs/build_corpus_v4_cps_candidate_index.py \
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_A_JOB_ID}" \
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_B_JOB_ID}" \
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_C_JOB_ID}" \
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_D_JOB_ID}" \
  --out "$R3_CANDIDATE_INDEX"
python3 code/experiments/proofs/build_corpus_v4_cps_candidate_index.py \
  --attempt-dir "results/corpus_v4/cps_multifidelity/r4/attempts/job_${R4_JOB_ID}" \
  --out "$R4_CANDIDATE_INDEX"
R3_CANDIDATE_SHA256=$(sha256sum "$R3_CANDIDATE_INDEX" | awk '{print $1}')
R4_CANDIDATE_SHA256=$(sha256sum "$R4_CANDIDATE_INDEX" | awk '{print $1}')

python3 code/experiments/proofs/plan_corpus_v4_cps_resume.py \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$PLAN_SHA256" \
  --manifest "$PLAN_DIR/r3_manifest.jsonl" \
  --candidate-index "$R3_CANDIDATE_INDEX" \
  --expected-candidate-index-sha256 "$R3_CANDIDATE_SHA256" \
  --execution-lock "$EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
  --out results/corpus_v4/cps_multifidelity/resume/r3_initial
python3 code/experiments/proofs/plan_corpus_v4_cps_resume.py \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$PLAN_SHA256" \
  --manifest "$PLAN_DIR/r4_manifest.jsonl" \
  --candidate-index "$R4_CANDIDATE_INDEX" \
  --expected-candidate-index-sha256 "$R4_CANDIDATE_SHA256" \
  --execution-lock "$EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
  --out results/corpus_v4/cps_multifidelity/resume/r4_initial
jq '{n_accepted,n_expected,rejected_candidates}' results/corpus_v4/cps_multifidelity/resume/r3_initial/accepted_artifact_set.json
jq '{n_accepted,n_expected,rejected_candidates}' results/corpus_v4/cps_multifidelity/resume/r4_initial/accepted_artifact_set.json
jq '.pending | length' results/corpus_v4/cps_multifidelity/resume/r3_initial/pending_task_set.json
jq '.pending | length' results/corpus_v4/cps_multifidelity/resume/r4_initial/pending_task_set.json
```

Pass the pinned candidate index to `plan_corpus_v4_cps_resume.py`. The resume
planner revalidates bytes, task identity, geometry, solver gates, environment,
scheduler records, plan, manifest, execution lock, and source stability. It
emits an accepted artifact set and a new pending task set. Duplicate valid
attempts hard-fail as ambiguous. Missing tasks remain pending and are retried
only through another hash-pinned task set.

## 9. Retry only pending tasks under lock v1

Pin each pending set, then use the same shard helper on that set. This prevents
already accepted tasks from being submitted again. Lock-v1 recovery must use
one canonical task per array. A singleton has exactly one scheduler record, so
the unchanged v1 runner cannot encounter the base-ID multi-record parser bug.
This constraint is operational recovery, not a change to the solver protocol.

Initialize the cumulative state exactly once in the shell that owns the retry
workflow:

```bash
R3_PENDING=results/corpus_v4/cps_multifidelity/resume/r3_initial/pending_task_set.json
R4_PENDING=results/corpus_v4/cps_multifidelity/resume/r4_initial/pending_task_set.json
R3_ATTEMPT_DIR_ARGS=(
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_A_JOB_ID}"
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_B_JOB_ID}"
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_C_JOB_ID}"
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_D_JOB_ID}"
)
R4_ATTEMPT_DIR_ARGS=(
  --attempt-dir "results/corpus_v4/cps_multifidelity/r4/attempts/job_${R4_JOB_ID}"
)
RETRY_ROUND=1
```

For each retry round, begin at this block without re-running the initialization
block above:

```bash
printf -v RETRY_SUFFIX 'retry_%02d' "$RETRY_ROUND"
R3_PENDING_SHA256=$(sha256sum "$R3_PENDING" | awk '{print $1}')
R4_PENDING_SHA256=$(sha256sum "$R4_PENDING" | awk '{print $1}')
R3_PENDING_COUNT=$(jq '.pending | length' "$R3_PENDING")
R4_PENDING_COUNT=$(jq '.pending | length' "$R4_PENDING")

if (( R3_PENDING_COUNT > 0 )); then
  python3 code/experiments/proofs/plan_corpus_v4_cps_submission_shards.py \
    --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
    --plan "$PLAN_DIR/plan.json" \
    --expected-plan-sha256 "$PLAN_SHA256" \
    --manifest "$PLAN_DIR/r3_manifest.jsonl" \
    --execution-lock "$EXECUTION_LOCK" \
    --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
    --task-set "$R3_PENDING" \
    --expected-task-set-sha256 "$R3_PENDING_SHA256" \
    --max-array-size 1 \
    --out "results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}"
fi
if (( R4_PENDING_COUNT > 0 )); then
  python3 code/experiments/proofs/plan_corpus_v4_cps_submission_shards.py \
    --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
    --plan "$PLAN_DIR/plan.json" \
    --expected-plan-sha256 "$PLAN_SHA256" \
    --manifest "$PLAN_DIR/r4_manifest.jsonl" \
    --execution-lock "$EXECUTION_LOCK" \
    --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
    --task-set "$R4_PENDING" \
    --expected-task-set-sha256 "$R4_PENDING_SHA256" \
    --max-array-size 1 \
    --out "results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}"
fi
```

For R3, submit every retry shard as a serial dependency chain. The capacity
loop performs only scheduler monitoring on the login node; each solver remains
a batch task. Append each returned job immediately to the cumulative attempt
list so later candidate indexes cannot forget an earlier retry shard.

```bash
R3_RETRY_JOB_IDS=()
R3_RETRY_PREV_JOB_ID=""
if (( R3_PENDING_COUNT > 0 )); then
  R3_RETRY_SUMMARY="results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}/submission_shards.json"
  R3_RETRY_N_SHARDS=$(jq '.n_shards' "$R3_RETRY_SUMMARY")
  for ((R3_RETRY_SHARD_INDEX=0; R3_RETRY_SHARD_INDEX!=R3_RETRY_N_SHARDS; R3_RETRY_SHARD_INDEX++)); do
    printf -v R3_RETRY_SHARD_NAME 'dispatch_shard_%03d.json' "$R3_RETRY_SHARD_INDEX"
    R3_RETRY_TASKS=$(jq --argjson i "$R3_RETRY_SHARD_INDEX" '.shards[$i].n_tasks' "$R3_RETRY_SUMMARY")
    R3_RETRY_MAX=$((R3_RETRY_TASKS - 1))
    R3_RETRY_SHA256=$(jq -r --argjson i "$R3_RETRY_SHARD_INDEX" '.shards[$i].sha256' "$R3_RETRY_SUMMARY")
    R3_RETRY_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}/${R3_RETRY_SHARD_NAME}"
    while (( $(squeue -r -h -u "$(id -un)" -o '%i' | wc -l) > 1000 - R3_RETRY_TASKS )); do
      echo "Waiting for QOS submission capacity for $R3_RETRY_SHARD_NAME" >&2
      sleep 60
    done
    R3_RETRY_DEPENDENCY_ARGS=()
    if [[ -n "$R3_RETRY_PREV_JOB_ID" ]]; then
      R3_RETRY_DEPENDENCY_ARGS=(--dependency="afterany:$R3_RETRY_PREV_JOB_ID")
    fi
    R3_RETRY_JOB_ID=$(sbatch --parsable -A pgs0407 --array="0-${R3_RETRY_MAX}%8" \
      "${R3_RETRY_DEPENDENCY_ARGS[@]}" \
      --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$R3_RETRY_SET",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$R3_RETRY_SHA256" \
      code/jobs/submit_corpus_v4_cps_r3.sh)
    R3_RETRY_JOB_IDS+=("$R3_RETRY_JOB_ID")
    R3_ATTEMPT_DIR_ARGS+=(--attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_RETRY_JOB_ID}")
    R3_RETRY_PREV_JOB_ID="$R3_RETRY_JOB_ID"
  done
fi
```

Submit every R4 singleton in a serial dependency chain and append every attempt
directory immediately, using the same provenance rule as R3:

```bash
R4_RETRY_JOB_IDS=()
R4_RETRY_PREV_JOB_ID=""
if (( R4_PENDING_COUNT > 0 )); then
  R4_RETRY_SUMMARY="results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}/submission_shards.json"
  R4_RETRY_N_SHARDS=$(jq '.n_shards' "$R4_RETRY_SUMMARY")
  for ((R4_RETRY_SHARD_INDEX=0; R4_RETRY_SHARD_INDEX!=R4_RETRY_N_SHARDS; R4_RETRY_SHARD_INDEX++)); do
    printf -v R4_RETRY_SHARD_NAME 'dispatch_shard_%03d.json' "$R4_RETRY_SHARD_INDEX"
    R4_RETRY_TASKS=$(jq --argjson i "$R4_RETRY_SHARD_INDEX" '.shards[$i].n_tasks' "$R4_RETRY_SUMMARY")
    R4_RETRY_MAX=$((R4_RETRY_TASKS - 1))
    R4_RETRY_SHA256=$(jq -r --argjson i "$R4_RETRY_SHARD_INDEX" '.shards[$i].sha256' "$R4_RETRY_SUMMARY")
    R4_RETRY_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}/${R4_RETRY_SHARD_NAME}"
    while (( $(squeue -r -h -u "$(id -un)" -o '%i' | wc -l) > 1000 - R4_RETRY_TASKS )); do
      echo "Waiting for QOS submission capacity for $R4_RETRY_SHARD_NAME" >&2
      sleep 60
    done
    R4_RETRY_DEPENDENCY_ARGS=()
    if [[ -n "$R4_RETRY_PREV_JOB_ID" ]]; then
      R4_RETRY_DEPENDENCY_ARGS=(--dependency="afterany:$R4_RETRY_PREV_JOB_ID")
    fi
    R4_RETRY_JOB_ID=$(sbatch --parsable -A pgs0407 --array="0-${R4_RETRY_MAX}%2" \
      "${R4_RETRY_DEPENDENCY_ARGS[@]}" \
      --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$R4_RETRY_SET",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$R4_RETRY_SHA256" \
      code/jobs/submit_corpus_v4_cps_r4.sh)
    R4_RETRY_JOB_IDS+=("$R4_RETRY_JOB_ID")
    R4_ATTEMPT_DIR_ARGS+=(--attempt-dir "results/corpus_v4/cps_multifidelity/r4/attempts/job_${R4_RETRY_JOB_ID}")
    R4_RETRY_PREV_JOB_ID="$R4_RETRY_JOB_ID"
  done
fi
```

After retry jobs finish, rebuild each candidate index from the original and
retry attempt directories, pin the new index, and run resume into a new output
directory. Never overwrite the initial index or resume output.

```bash
if (( R3_PENDING_COUNT > 0 )); then
  R3_RETRY_INDEX="results/corpus_v4/cps_multifidelity/index/r3_${RETRY_SUFFIX}_candidates.json"
  python3 code/experiments/proofs/build_corpus_v4_cps_candidate_index.py \
    "${R3_ATTEMPT_DIR_ARGS[@]}" --out "$R3_RETRY_INDEX"
  R3_RETRY_INDEX_SHA256=$(sha256sum "$R3_RETRY_INDEX" | awk '{print $1}')
  python3 code/experiments/proofs/plan_corpus_v4_cps_resume.py \
    --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
    --plan "$PLAN_DIR/plan.json" \
    --expected-plan-sha256 "$PLAN_SHA256" \
    --manifest "$PLAN_DIR/r3_manifest.jsonl" \
    --candidate-index "$R3_RETRY_INDEX" \
    --expected-candidate-index-sha256 "$R3_RETRY_INDEX_SHA256" \
    --execution-lock "$EXECUTION_LOCK" \
    --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
    --out "results/corpus_v4/cps_multifidelity/resume/r3_${RETRY_SUFFIX}"
  R3_ACCEPTED="results/corpus_v4/cps_multifidelity/resume/r3_${RETRY_SUFFIX}/accepted_artifact_set.json"
  R3_PENDING="results/corpus_v4/cps_multifidelity/resume/r3_${RETRY_SUFFIX}/pending_task_set.json"
  R3_PENDING_SHA256=$(sha256sum "$R3_PENDING" | awk '{print $1}')
  R3_PENDING_COUNT=$(jq '.pending | length' "$R3_PENDING")
fi
if (( R4_PENDING_COUNT > 0 )); then
  R4_RETRY_INDEX="results/corpus_v4/cps_multifidelity/index/r4_${RETRY_SUFFIX}_candidates.json"
  python3 code/experiments/proofs/build_corpus_v4_cps_candidate_index.py \
    "${R4_ATTEMPT_DIR_ARGS[@]}" --out "$R4_RETRY_INDEX"
  R4_RETRY_INDEX_SHA256=$(sha256sum "$R4_RETRY_INDEX" | awk '{print $1}')
  python3 code/experiments/proofs/plan_corpus_v4_cps_resume.py \
    --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
    --plan "$PLAN_DIR/plan.json" \
    --expected-plan-sha256 "$PLAN_SHA256" \
    --manifest "$PLAN_DIR/r4_manifest.jsonl" \
    --candidate-index "$R4_RETRY_INDEX" \
    --expected-candidate-index-sha256 "$R4_RETRY_INDEX_SHA256" \
    --execution-lock "$EXECUTION_LOCK" \
    --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
    --out "results/corpus_v4/cps_multifidelity/resume/r4_${RETRY_SUFFIX}"
  R4_ACCEPTED="results/corpus_v4/cps_multifidelity/resume/r4_${RETRY_SUFFIX}/accepted_artifact_set.json"
  R4_PENDING="results/corpus_v4/cps_multifidelity/resume/r4_${RETRY_SUFFIX}/pending_task_set.json"
  R4_PENDING_SHA256=$(sha256sum "$R4_PENDING" | awk '{print $1}')
  R4_PENDING_COUNT=$(jq '.pending | length' "$R4_PENDING")
fi
RETRY_ROUND=$((RETRY_ROUND + 1))
```

If either updated pending count is nonzero, return to the per-round block that
begins with `printf -v RETRY_SUFFIX` in the **same Bash shell**. The incremented
`RETRY_ROUND`, the updated `R3_PENDING`/`R4_PENDING` paths, and the cumulative
`R3_ATTEMPT_DIR_ARGS`/`R4_ATTEMPT_DIR_ARGS` arrays are the state transition for
round 02 and every later round. Do not reinitialize them from `*_initial`,
re-run the initialization block, or reset the attempt arrays.
Each new candidate index must contain the initial attempt directories and every
prior retry directory. A duplicate valid attempt remains a hard ambiguity;
retry only indices listed in the immediately preceding round's hash-pinned
pending set.

## 10. Finalize exact coverage

Submit the finalizer only when R3 reports 1,500 accepted and zero pending, R4
reports 198 accepted and zero pending, and neither accepted set contains a
duplicate valid attempt. Completion of the arrays alone is insufficient.
Rejected candidates are retained audit history; an invalid earlier attempt does
not block finalization after a later valid singleton retry supplies exact
coverage. Review and classify every rejection, but do not delete its source
attempt directory or require the cumulative rejection list to become empty.
After the coverage conditions hold, pin both accepted sets and submit:

```bash
R3_ACCEPTED="${R3_ACCEPTED:-results/corpus_v4/cps_multifidelity/resume/r3_initial/accepted_artifact_set.json}"
R4_ACCEPTED="${R4_ACCEPTED:-results/corpus_v4/cps_multifidelity/resume/r4_initial/accepted_artifact_set.json}"
R3_ACCEPTED_SHA256=$(sha256sum "$R3_ACCEPTED" | awk '{print $1}')
R4_ACCEPTED_SHA256=$(sha256sum "$R4_ACCEPTED" | awk '{print $1}')
FINAL_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$RUN_ROOT" \
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_R3_ARTIFACT_SET="$RUN_ROOT/$R3_ACCEPTED",PCB_GNN_CPS_R3_ARTIFACT_SET_SHA256="$R3_ACCEPTED_SHA256",PCB_GNN_CPS_R4_ARTIFACT_SET="$RUN_ROOT/$R4_ACCEPTED",PCB_GNN_CPS_R4_ARTIFACT_SET_SHA256="$R4_ACCEPTED_SHA256" \
  "$RUN_ROOT/code/jobs/submit_finalize_corpus_v4_cps_multifidelity.sh")
```

## 11. Rejection taxonomy

| Symptom | Meaning | Required action |
|---|---|---|
| `Must specify account` | Submission request omitted the project account | Resubmit with `-A pgs0407`; do not edit scientific code |
| `Invalid job array specification` | Array index exceeds `MaxArraySize=1001` | Use the four dense, hash-pinned R3 dispatch sets |
| `QOSMaxSubmitJobPerUserLimit` | Running plus pending array elements exceed 1,000 | Use at most 400 tasks per R3 shard and pass the live capacity gate before each later shard |
| Missing `code/jobs/slurm_job_env.sh` under the login directory | `SLURM_SUBMIT_DIR` came from the SSH invocation directory | Export the absolute `PCB_GNN_JOB_ENV`; `--chdir` alone is insufficient |
| Dirty or untracked source refusal | Execution worktree is not immutable | Create a fresh detached worktree at the reviewed commit |
| Plan, lock, manifest, or corpus hash mismatch | Provenance drift | Stop; do not recompute expected hashes from observed files |
| Scheduler contract mismatch | Requested or allocated resources differ | Inspect `ReqTRES`, `TresPerTask`, `AllocTRES`, and the environment before resubmission |
| Final array element fails scheduler identity preflight | The final element may reuse the base array job ID; a base-ID query can return multiple records | Query the exact `array-job-id_array-task-id` component and require one identity match; recover a missing element only through a hash-pinned singleton task set |
| Timeout, signal, OOM, mesh, RSS, complexity, iteration, or residual failure | Frozen numerical/resource gate failed | Retain the failed attempt and classify it; do not widen a cap post hoc |
| Existing start or result path | Attempt collision | Use a new job-scoped attempt; never overwrite |
| Missing task artifact | Incomplete coverage | Emit a pinned pending set and retry only missing canonical tasks |
| Two valid attempts for one task | Ambiguous evidence | Stop for an explicit evidence decision; never choose by value or runtime |
| Finalizer coverage failure | Corpus is incomplete or inconsistent | Do not publish labels or unblock downstream claims |

## 12. Lessons from rejected submissions

- A submission without `-A pgs0407` was rejected before a job was created.
- R3 `0-1499%8` was rejected before a job was created because the maximum array
  index is 1000.
- A 1,001-task R3 `--test-only` request passed the array-size rule but was
  rejected by `MaxSubmitJobsPU=1000`. The operational dispatch size is therefore
  400, allowing two R3 shards plus 198 R4 tasks to occupy 998 submission slots.
- R4 job `6845922` entered SLURM but ten tasks failed in 0–1 s at the scheduler
  contract gate. No FEM worker ran. The request was 25 CPU/160 GiB and the
  scheduler correctly allocated 41 CPU/160 GiB under memory-per-CPU policy.
  The remaining tasks were canceled, and the validator was corrected to record
  and check requested and allocated resources separately.
- Arrays `6846270`, `6846287`, and `6846304` were canceled after the first
  tasks failed in 1–3 s. No runner or FEM worker executed: remote submission
  used `--chdir` but did not export `PCB_GNN_JOB_ENV`, while
  `SLURM_SUBMIT_DIR` still pointed to the SSH login directory. The corrected
  submission exports the helper's absolute path.
- Finalizer `6891705` repeated the helper-path failure before Python started;
  no scientific output was created. Finalizer `6893754` used absolute helper,
  corpus, lock, accepted-set, and batch-script paths plus `--chdir`, then closed
  the package successfully. A finalizer must not rely on the caller's current
  directory or an implicit `SLURM_SUBMIT_DIR`.
- Counting `squeue` without `-r` reported compressed array rows and caused one
  R3-D request to be rejected by `QOSMaxSubmitJobPerUserLimit` before job
  creation. Capacity gates must count expanded elements.
- The final element of an array may have `SLURM_JOB_ID` equal to
  `SLURM_ARRAY_JOB_ID`. Querying that raw base ID can return several element
  records. The runner now queries the exact array component once; an audited
  singleton probe demonstrated that sparse recovery can preserve the original
  throttle contract without mixing execution locks.

These are operational preflight failures, not scientific negative results and
not evidence that the solver or cluster is broken.

## 13. Closeout checklist

1. Archive `sacct` state and resource records.
2. Record job IDs, source commit, plan/lock/manifest/task-set hashes, candidate
   index hashes, accepted/pending hashes, and final summary hash in the evidence
   ledger.
3. Move lifecycle through `RUNNING`, `VALIDATING`, and `FINALIZED` only when the
   corresponding evidence exists.
4. Keep job IDs, private paths, logs, and internal diagnostics out of every page
   marked `paper_source: true` and out of manuscript packages.
5. Admit paper claims only through human review of the finalized wiki evidence.

## 14. Submit the derived R3/R4 discrepancy audit

Run this stage only after the joint R3/R4 archive verifier passes. The audit is
lightweight, but its scientific output is still created under SLURM so every
reported value resolves to a job-scoped receipt. Use the reviewed source commit
and a detached clean worktree:

```bash
AUDIT_RUN_ROOT=/absolute/path/to/cps-discrepancy-audit-worktree
AUDIT_SOURCE_COMMIT=f0f60cdf67daf3df6973185d353836677163c02e
AUDIT_PYTHON=/absolute/path/to/the/pinned/python
git worktree add --detach "$AUDIT_RUN_ROOT" "$AUDIT_SOURCE_COMMIT"
AUDIT_JOB_ENV="$AUDIT_RUN_ROOT/code/jobs/slurm_job_env.sh"
git -C "$AUDIT_RUN_ROOT" status --porcelain
python3 "$AUDIT_RUN_ROOT/code/quality/verify_corpus_v4_archive.py" \
  --root "$AUDIT_RUN_ROOT" --require-git-tracked
AUDIT_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$AUDIT_RUN_ROOT" \
  --export=ALL,PCB_GNN_JOB_ENV="$AUDIT_JOB_ENV",PCB_GNN_PYTHON="$AUDIT_PYTHON" \
  "$AUDIT_RUN_ROOT/code/jobs/submit_corpus_v4_cps_fidelity_discrepancy.sh")
```

The site memory-per-CPU policy may allocate more than the requested two CPUs.
The frozen gate therefore requires `ReqTRES` and `TresPerTask` to preserve the
two-CPU request while requiring `AllocTRES`, `NumCPUs`, and
`SLURM_CPUS_PER_TASK` to agree on an allocation of at least two CPUs. It also
requires 8 GiB, the `nextgen` partition, a 15-minute time limit, and the expected
job name.

An empty queue is not completion evidence. Inspect accounting and validate the
job directory before constructing the derived analysis manifest:

```bash
sacct -X -n -P -j "$AUDIT_JOB_ID" \
  --format=JobID,JobName,State,ExitCode,Elapsed,ReqTRES,AllocTRES,MaxRSS
python3 "$AUDIT_RUN_ROOT/code/experiments/proofs/audit_corpus_v4_cps_fidelity_discrepancy.py" \
  --protocol "$AUDIT_RUN_ROOT/protocols/corpus_v4_cps_fidelity_discrepancy_v1.json" \
  --output "$AUDIT_RUN_ROOT/results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1/job_${AUDIT_JOB_ID}" \
  --check
```

Keep failed-closed attempts in the non-paper operational history. The admitted
archive must contain one exact successful job directory, normalized scheduler
completion, a hash-pinned submission history, and an analysis manifest. After
those files are committed, run the tracked clean-clone verifier in Section 13's
closeout environment.

## 15. Submit the Corpus V4 accuracy grid

The accuracy stage uses 25 canonical tasks rather than the solver sharding
scheme. Each array element trains one split/init cell. Do not run the task or
finalizer directly on the login node.

After review, copy the four artifact roots and the reviewed source commit from
the evidence ledger into a clean detached worktree. The source commit is an
external trust root because embedding it in the execution lock would create a
self-reference cycle. Do not calculate a value from a file and then describe
the same value as an independently reviewed root.

```bash
ACC_PROTOCOL=protocols/corpus_v4_accuracy_v1.json
ACC_PLAN=results/corpus_v4/accuracy/plan/v1/plan.json
ACC_TASKS=results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl
ACC_LOCK=protocols/corpus_v4_accuracy_execution_lock_v1.json
ACC_RUN_ROOT=/absolute/path/to/clean-detached-worktree
ACC_SOURCE_COMMIT=replace-with-clean-execution-commit
ACC_PROTOCOL_SHA256=f707eb45e44042bc7231a4393caa1b998a283658ce2c3d4093e7c6c7a3eaf3bf
ACC_PLAN_SHA256=e67509a6a742bb6a936287a79e9622f087a14ba08219a7c9521f05288b704206
ACC_TASKS_SHA256=2c7079fdd844d9e54a76d32a3bee6e623735303d7d59185ee97e3daf40000f20
ACC_LOCK_SHA256=6b212fcbf1112c81c9f21d1f1511dcd5ac473b5492cd29c9bc7f5ecf6b173e61
cd "$ACC_RUN_ROOT"
test "$(git rev-parse HEAD)" = "$ACC_SOURCE_COMMIT"
test -z "$(git status --short --untracked-files=no)"
```

Run static checks and scheduler admission first. The Python validation performs
no graph construction or training.

```bash
python3 code/experiments/proofs/plan_corpus_v4_accuracy.py \
  --protocol "$ACC_PROTOCOL" \
  --out results/corpus_v4/accuracy/plan/v1 \
  --check
python3 code/experiments/proofs/run_corpus_v4_accuracy_task.py \
  --protocol "$ACC_PROTOCOL" \
  --expected-protocol-sha256 "$ACC_PROTOCOL_SHA256" \
  --plan "$ACC_PLAN" \
  --expected-plan-sha256 "$ACC_PLAN_SHA256" \
  --task-manifest "$ACC_TASKS" \
  --expected-task-manifest-sha256 "$ACC_TASKS_SHA256" \
  --execution-lock "$ACC_LOCK" \
  --expected-execution-lock-sha256 "$ACC_LOCK_SHA256" \
  --expected-source-git-head "$ACC_SOURCE_COMMIT" \
  --output-root results/corpus_v4/accuracy/jobs \
  --validate-only
sbatch --test-only -A pgs0407 \
  --chdir="$ACC_RUN_ROOT" \
  "$ACC_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy.sh"
```

Export the absolute execution root, reviewed source commit, and all four
expected hashes. The accuracy wrapper deliberately ignores the generic helper
and Python override variables: it sources the locked helper from the execution
root and uses `/usr/bin/python3`. Scientific thread count remains eight even if
site memory policy allocates additional CPUs.

```bash
ACC_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$ACC_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$ACC_RUN_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$ACC_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256="$ACC_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_PLAN_SHA256="$ACC_PLAN_SHA256",PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256="$ACC_TASKS_SHA256",PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256="$ACC_LOCK_SHA256" \
  "$ACC_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy.sh")
ACC_JOB_ID=${ACC_JOB_ID%%;*}
[[ "$ACC_JOB_ID" =~ ^[0-9]+$ ]]
```

When the array leaves the queue, inspect expanded accounting rather than the
compressed base row. Then create an accepted and pending set from explicitly
named attempt roots.

```bash
sacct -X -n -P -j "$ACC_JOB_ID" \
  --format=JobID,JobName,State,ExitCode,Elapsed,ReqTRES,AllocTRES,MaxRSS
python3 code/experiments/proofs/plan_corpus_v4_accuracy_resume.py \
  --protocol "$ACC_PROTOCOL" \
  --expected-protocol-sha256 "$ACC_PROTOCOL_SHA256" \
  --plan "$ACC_PLAN" \
  --expected-plan-sha256 "$ACC_PLAN_SHA256" \
  --task-manifest "$ACC_TASKS" \
  --expected-task-manifest-sha256 "$ACC_TASKS_SHA256" \
  --execution-lock "$ACC_LOCK" \
  --expected-execution-lock-sha256 "$ACC_LOCK_SHA256" \
  --expected-source-git-head "$ACC_SOURCE_COMMIT" \
  --attempt-root "results/corpus_v4/accuracy/jobs/job_${ACC_JOB_ID}" \
  --out results/corpus_v4/accuracy/resume/round_00
```

Queue disappearance is not a sufficient resume gate. Wait until `sacct`
exposes exactly 25 logical `JobID=arrayID_taskID` rows and every row is
`COMPLETED/0:0`. Accounting can lag queue completion. Do not submit retries
from a failed-closed round while accounting is incomplete; a late successful
record would create two valid attempts for one canonical task. Rebuild a new
immutable resume round from the original attempt root after accounting settles,
and never repeat the same `--attempt-root` argument.

If pending tasks remain, submit only those canonical IDs by overriding the
array expression. Pin the pending set and pass it to the runner. Append every
earlier attempt root when rebuilding the next accepted set.

```bash
ACC_PENDING=results/corpus_v4/accuracy/resume/round_00/pending_task_set.json
ACC_PENDING_SHA256=$(sha256sum "$ACC_PENDING" | awk '{print $1}')
ACC_RETRY_ARRAY=$(jq -r '[.pending[].task_id] | join(",")' "$ACC_PENDING")
ACC_RETRY_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --array="${ACC_RETRY_ARRAY}%5" \
  --chdir="$ACC_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$ACC_RUN_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$ACC_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256="$ACC_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_PLAN_SHA256="$ACC_PLAN_SHA256",PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256="$ACC_TASKS_SHA256",PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256="$ACC_LOCK_SHA256",PCB_GNN_V4_ACCURACY_PENDING_SET="$ACC_PENDING",PCB_GNN_V4_ACCURACY_PENDING_SET_SHA256="$ACC_PENDING_SHA256" \
  "$ACC_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy.sh")
ACC_RETRY_JOB_ID=${ACC_RETRY_JOB_ID%%;*}
[[ "$ACC_RETRY_JOB_ID" =~ ^[0-9]+$ ]]
```

Finalization requires 25 accepted tasks, zero pending tasks, and no ambiguous
duplicate attempt. Pin the accepted set before submission. Training artifacts
contain no held-out predictions. The finalizer independently reloads each
accepted checkpoint, reconstructs train-only normalization, performs the first
test/R4 inference, and writes all prediction-level evidence itself.

```bash
# Point this to the latest resume round after all 25 tasks are accepted.
ACC_ACCEPTED=results/corpus_v4/accuracy/resume/round_00/accepted_artifact_set.json
ACC_ACCEPTED_SHA256=$(sha256sum "$ACC_ACCEPTED" | awk '{print $1}')
sbatch --test-only -A pgs0407 \
  --chdir="$ACC_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$ACC_RUN_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$ACC_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256="$ACC_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_PLAN_SHA256="$ACC_PLAN_SHA256",PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256="$ACC_TASKS_SHA256",PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256="$ACC_LOCK_SHA256",PCB_GNN_V4_ACCURACY_ACCEPTED_SET="$ACC_ACCEPTED",PCB_GNN_V4_ACCURACY_ACCEPTED_SET_SHA256="$ACC_ACCEPTED_SHA256" \
  "$ACC_RUN_ROOT/code/jobs/submit_finalize_corpus_v4_accuracy.sh"
ACC_FINAL_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$ACC_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$ACC_RUN_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$ACC_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256="$ACC_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_PLAN_SHA256="$ACC_PLAN_SHA256",PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256="$ACC_TASKS_SHA256",PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256="$ACC_LOCK_SHA256",PCB_GNN_V4_ACCURACY_ACCEPTED_SET="$ACC_ACCEPTED",PCB_GNN_V4_ACCURACY_ACCEPTED_SET_SHA256="$ACC_ACCEPTED_SHA256" \
  "$ACC_RUN_ROOT/code/jobs/submit_finalize_corpus_v4_accuracy.sh")
ACC_FINAL_JOB_ID=${ACC_FINAL_JOB_ID%%;*}
[[ "$ACC_FINAL_JOB_ID" =~ ^[0-9]+$ ]]
```

After the finalizer leaves the queue, create the closeout manifest only after
exact terminal accounting is available. Creation queries `sacct`; later clean
clones use `--check` and therefore do not depend on scheduler retention.

```bash
sacct -X -n -P -j "$ACC_FINAL_JOB_ID" \
  --format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES
ACC_ANALYSIS=results/corpus_v4/accuracy/final/job_${ACC_FINAL_JOB_ID}/ANALYSIS_MANIFEST.json
ACC_ANALYSIS_SHA256=$(sha256sum "$ACC_ANALYSIS" | awk '{print $1}')
python3 code/quality/verify_corpus_v4_accuracy_archive.py \
  --protocol "$ACC_PROTOCOL" \
  --expected-protocol-sha256 "$ACC_PROTOCOL_SHA256" \
  --plan "$ACC_PLAN" \
  --expected-plan-sha256 "$ACC_PLAN_SHA256" \
  --task-manifest "$ACC_TASKS" \
  --expected-task-manifest-sha256 "$ACC_TASKS_SHA256" \
  --execution-lock "$ACC_LOCK" \
  --expected-execution-lock-sha256 "$ACC_LOCK_SHA256" \
  --expected-source-git-head "$ACC_SOURCE_COMMIT" \
  --accepted-set "$ACC_ACCEPTED" \
  --expected-accepted-set-sha256 "$ACC_ACCEPTED_SHA256" \
  --analysis-manifest "$ACC_ANALYSIS" \
  --expected-analysis-manifest-sha256 "$ACC_ANALYSIS_SHA256" \
  --out results/corpus_v4/accuracy/ARCHIVE_MANIFEST.json
```

For array accounting, match the logical component (`arrayID_taskID`) on
`JobID`. Preserve `JobIDRaw` as the scheduler's receipt identity, but do not use
it as the logical array key: ordinary elements may receive numeric child IDs,
and the final element may carry the base raw ID. Compare complete `ReqTRES` and
`AllocTRES` maps after deterministic key ordering because `scontrol` and
`sacct` can print identical maps in different orders. Do not normalize units or
discard unknown keys.

Record the array, retry, and finalizer identifiers plus every source and
artifact hash in the evidence ledger. Commit every admitted attempt, resume
set, final output, and archive manifest. Then rerun the command above with
`--check --require-git-tracked`. Keep `C-ACC-001` blocked until that clean-clone
check and the claim wording pass scientific review.
