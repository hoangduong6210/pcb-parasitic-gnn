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
```

Never derive `EXECUTION_LOCK_SHA256` from `EXECUTION_LOCK` and then treat that
value as an independent trust root.

## 2. Cluster facts to check first

The project account is `pgs0407`, the partition is `nextgen`, and every
submission must contain `-A pgs0407`. The 2026-08-15 cluster configuration has
`MaxArraySize=1001`; therefore an array index of 1499 is invalid.

```bash
scontrol ping
scontrol show config | rg 'MaxArraySize|MaxMemPerCPU'
sacctmgr -n -P show assoc user="$(id -un)" format=Cluster,Account,Partition,DefaultQOS
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

R3 has 1,500 canonical tasks and cannot use `--array=0-1499`. Generate two
dense dispatch sets from the frozen manifest. The local array index is mapped
back to the canonical task index by the runner.

```bash
python3 code/experiments/proofs/plan_corpus_v4_cps_submission_shards.py \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$PLAN_SHA256" \
  --manifest "$PLAN_DIR/r3_manifest.jsonl" \
  --execution-lock "$EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$EXECUTION_LOCK_SHA256" \
  --max-array-size 1001 \
  --out results/corpus_v4/cps_multifidelity/dispatch/r3
jq '.shards' results/corpus_v4/cps_multifidelity/dispatch/r3/submission_shards.json
SHARD_A_SHA256=$(jq -r '.shards[0].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3/submission_shards.json)
SHARD_B_SHA256=$(jq -r '.shards[1].sha256' results/corpus_v4/cps_multifidelity/dispatch/r3/submission_shards.json)
```

The required partition is:

| Shard | Canonical tasks | Local array | Tasks |
|---|---:|---:|---:|
| A | 0–1000 | `0-1000%8` | 1,001 |
| B | 1001–1499 | `0-498%8` | 499 |

The shard sets must be disjoint and their sorted union must equal every
canonical index from 0 through 1499. Record each task-set SHA-256 before
submission. Never hand-edit, renumber, or submit shard B as `1001-1499`.

Validate each shard with the runner's `--validate-only`, adding the concrete
path and the corresponding `SHARD_A_SHA256` or `SHARD_B_SHA256`:

```text
--retry-task-set "$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3/dispatch_shard_000.json"
--expected-retry-task-set-sha256 "$SHARD_A_SHA256"
```

## 6. Submit R3 and R4

Submit shard A first. Submit shard B with `afterany` so total R3 concurrency
never exceeds eight, while failures in A do not suppress independent work in B.

```bash
R3_A_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-1000%8 \
  --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3/dispatch_shard_000.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_A_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)

R3_B_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0-498%8 \
  --dependency="afterany:$R3_A_JOB_ID" \
  --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3/dispatch_shard_001.json",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$SHARD_B_SHA256" \
  code/jobs/submit_corpus_v4_cps_r3.sh)

R4_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON" \
  code/jobs/submit_corpus_v4_cps_r4.sh)
```

Record all returned IDs in the evidence ledger, not in manuscript-source pages.
Scheduler acceptance changes the relevant lifecycle from `PLANNED` to
`RUNNING`; it does not admit an accuracy or speed claim.

## 7. Monitor scheduler and artifact progress

```bash
squeue -j "$R3_A_JOB_ID,$R3_B_JOB_ID,$R4_JOB_ID" \
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

## 9. Retry only pending tasks

Pin each pending set, then use the same shard helper on that set. This prevents
already accepted tasks from being submitted again.

```bash
R3_PENDING=results/corpus_v4/cps_multifidelity/resume/r3_initial/pending_task_set.json
R4_PENDING=results/corpus_v4/cps_multifidelity/resume/r4_initial/pending_task_set.json
R3_ATTEMPT_DIR_ARGS=(
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_A_JOB_ID}"
  --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_B_JOB_ID}"
)
R4_ATTEMPT_DIR_ARGS=(
  --attempt-dir "results/corpus_v4/cps_multifidelity/r4/attempts/job_${R4_JOB_ID}"
)
RETRY_ROUND=1
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
    --max-array-size 1001 \
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
    --max-array-size 1001 \
    --out "results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}"
fi
```

For R3, submit the first retry shard and conditionally submit the second after
the first. At most two shards can exist because the complete manifest has 1,500
tasks.

```bash
R3_RETRY_B_JOB_ID=""
if (( R3_PENDING_COUNT > 0 )); then
  R3_RETRY_SUMMARY="results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}/submission_shards.json"
  R3_RETRY_A_TASKS=$(jq '.shards[0].n_tasks' "$R3_RETRY_SUMMARY")
  R3_RETRY_A_MAX=$((R3_RETRY_A_TASKS - 1))
  R3_RETRY_A_SHA256=$(jq -r '.shards[0].sha256' "$R3_RETRY_SUMMARY")
  R3_RETRY_A_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}/dispatch_shard_000.json"
  R3_RETRY_A_JOB_ID=$(sbatch --parsable -A pgs0407 --array="0-${R3_RETRY_A_MAX}%8" \
    --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$R3_RETRY_A_SET",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$R3_RETRY_A_SHA256" \
    code/jobs/submit_corpus_v4_cps_r3.sh)
  if (( $(jq '.n_shards' "$R3_RETRY_SUMMARY") == 2 )); then
    R3_RETRY_B_TASKS=$(jq '.shards[1].n_tasks' "$R3_RETRY_SUMMARY")
    R3_RETRY_B_MAX=$((R3_RETRY_B_TASKS - 1))
    R3_RETRY_B_SHA256=$(jq -r '.shards[1].sha256' "$R3_RETRY_SUMMARY")
    R3_RETRY_B_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r3_${RETRY_SUFFIX}/dispatch_shard_001.json"
    R3_RETRY_B_JOB_ID=$(sbatch --parsable -A pgs0407 --array="0-${R3_RETRY_B_MAX}%8" \
      --dependency="afterany:$R3_RETRY_A_JOB_ID" \
      --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$R3_RETRY_B_SET",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$R3_RETRY_B_SHA256" \
      code/jobs/submit_corpus_v4_cps_r3.sh)
  fi
fi
```

R4 has at most 198 pending tasks, so its retry dispatch has one shard:

```bash
if (( R4_PENDING_COUNT > 0 )); then
  R4_RETRY_SUMMARY="results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}/submission_shards.json"
  R4_RETRY_TASKS=$(jq '.shards[0].n_tasks' "$R4_RETRY_SUMMARY")
  R4_RETRY_MAX=$((R4_RETRY_TASKS - 1))
  R4_RETRY_SHA256=$(jq -r '.shards[0].sha256' "$R4_RETRY_SUMMARY")
  R4_RETRY_SET="$RUN_ROOT/results/corpus_v4/cps_multifidelity/dispatch/r4_${RETRY_SUFFIX}/dispatch_shard_000.json"
  R4_RETRY_JOB_ID=$(sbatch --parsable -A pgs0407 --array="0-${R4_RETRY_MAX}%2" \
    --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_RETRY_TASK_SET="$R4_RETRY_SET",PCB_GNN_CPS_RETRY_TASK_SET_SHA256="$R4_RETRY_SHA256" \
    code/jobs/submit_corpus_v4_cps_r4.sh)
fi
```

After retry jobs finish, rebuild each candidate index from the original and
retry attempt directories, pin the new index, and run resume into a new output
directory. Never overwrite the initial index or resume output.

```bash
if (( R3_PENDING_COUNT > 0 )); then
  R3_ATTEMPT_DIR_ARGS+=(
    --attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_RETRY_A_JOB_ID}"
  )
  if [[ -n "$R3_RETRY_B_JOB_ID" ]]; then
    R3_ATTEMPT_DIR_ARGS+=(--attempt-dir "results/corpus_v4/cps_multifidelity/r3/attempts/job_${R3_RETRY_B_JOB_ID}")
  fi
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
  R4_ATTEMPT_DIR_ARGS+=(
    --attempt-dir "results/corpus_v4/cps_multifidelity/r4/attempts/job_${R4_RETRY_JOB_ID}"
  )
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
printf -v RETRY_SUFFIX 'retry_%02d' "$RETRY_ROUND"
```

If either updated pending count is nonzero, return to the first sharding block
in this section in the **same Bash shell**. The incremented `RETRY_SUFFIX`, the
updated `R3_PENDING`/`R4_PENDING` paths and digests, and the cumulative
`R3_ATTEMPT_DIR_ARGS`/`R4_ATTEMPT_DIR_ARGS` arrays are the state transition for
round 02 and every later round. Do not reinitialize them from `*_initial`.
Each new candidate index must contain the initial attempt directories and every
prior retry directory. A duplicate valid attempt remains a hard ambiguity;
retry only indices listed in the immediately preceding round's hash-pinned
pending set.

## 10. Finalize exact coverage

Submit the finalizer only when R3 reports 1,500 accepted and zero pending, R4
reports 198 accepted and zero pending, and both rejected-candidate lists are
empty. Completion of the arrays alone is insufficient. After those conditions
hold, pin both accepted sets and submit:

```bash
R3_ACCEPTED="${R3_ACCEPTED:-results/corpus_v4/cps_multifidelity/resume/r3_initial/accepted_artifact_set.json}"
R4_ACCEPTED="${R4_ACCEPTED:-results/corpus_v4/cps_multifidelity/resume/r4_initial/accepted_artifact_set.json}"
R3_ACCEPTED_SHA256=$(sha256sum "$R3_ACCEPTED" | awk '{print $1}')
R4_ACCEPTED_SHA256=$(sha256sum "$R4_ACCEPTED" | awk '{print $1}')
FINAL_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_V3_CORPUS_DIR="$SOURCE_CORPUS_DIR",PCB_GNN_CPS_EXECUTION_LOCK="$EXECUTION_LOCK",PCB_GNN_CPS_EXECUTION_LOCK_SHA256="$EXECUTION_LOCK_SHA256",PCB_GNN_PYTHON="$PCB_PYTHON",PCB_GNN_CPS_R3_ARTIFACT_SET="$RUN_ROOT/$R3_ACCEPTED",PCB_GNN_CPS_R3_ARTIFACT_SET_SHA256="$R3_ACCEPTED_SHA256",PCB_GNN_CPS_R4_ARTIFACT_SET="$RUN_ROOT/$R4_ACCEPTED",PCB_GNN_CPS_R4_ARTIFACT_SET_SHA256="$R4_ACCEPTED_SHA256" \
  code/jobs/submit_finalize_corpus_v4_cps_multifidelity.sh)
```

## 11. Rejection taxonomy

| Symptom | Meaning | Required action |
|---|---|---|
| `Must specify account` | Submission request omitted the project account | Resubmit with `-A pgs0407`; do not edit scientific code |
| `Invalid job array specification` | Array index exceeds `MaxArraySize=1001` | Use the two dense, hash-pinned R3 dispatch sets |
| Dirty or untracked source refusal | Execution worktree is not immutable | Create a fresh detached worktree at the reviewed commit |
| Plan, lock, manifest, or corpus hash mismatch | Provenance drift | Stop; do not recompute expected hashes from observed files |
| Scheduler contract mismatch | Requested or allocated resources differ | Inspect `ReqTRES`, `TresPerTask`, `AllocTRES`, and the environment before resubmission |
| Timeout, signal, OOM, mesh, RSS, complexity, iteration, or residual failure | Frozen numerical/resource gate failed | Retain the failed attempt and classify it; do not widen a cap post hoc |
| Existing start or result path | Attempt collision | Use a new job-scoped attempt; never overwrite |
| Missing task artifact | Incomplete coverage | Emit a pinned pending set and retry only missing canonical tasks |
| Two valid attempts for one task | Ambiguous evidence | Stop for an explicit evidence decision; never choose by value or runtime |
| Finalizer coverage failure | Corpus is incomplete or inconsistent | Do not publish labels or unblock downstream claims |

## 12. Lessons from rejected submissions

- A submission without `-A pgs0407` was rejected before a job was created.
- R3 `0-1499%8` was rejected before a job was created because the maximum array
  index is 1000.
- R4 job `6845922` entered SLURM but ten tasks failed in 0–1 s at the scheduler
  contract gate. No FEM worker ran. The request was 25 CPU/160 GiB and the
  scheduler correctly allocated 41 CPU/160 GiB under memory-per-CPU policy.
  The remaining tasks were canceled, and the validator was corrected to record
  and check requested and allocated resources separately.

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
