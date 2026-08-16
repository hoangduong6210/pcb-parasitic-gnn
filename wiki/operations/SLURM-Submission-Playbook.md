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
  --export=ALL,PCB_GNN_JOB_ENV="$PCB_JOB_ENV",PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_R3_ARTIFACT_SET="$RUN_ROOT/$R3_ACCEPTED",PCB_GNN_CPS_R3_ARTIFACT_SET_SHA256="$R3_ACCEPTED_SHA256",PCB_GNN_CPS_R4_ARTIFACT_SET="$RUN_ROOT/$R4_ACCEPTED",PCB_GNN_CPS_R4_ARTIFACT_SET_SHA256="$R4_ACCEPTED_SHA256" \
  code/jobs/submit_finalize_corpus_v4_cps_multifidelity.sh)
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
