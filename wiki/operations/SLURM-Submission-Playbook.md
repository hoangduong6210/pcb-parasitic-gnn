---
title: SLURM Submission Playbook
status: active operational runbook
last_updated: 2026-08-31
paper_source: false
---

# SLURM Submission Playbook

This page is the canonical operational procedure for the Cps multi-fidelity
pipeline and its deterministic FEM qualification. It is not manuscript source.
Solver work and model training must run through SLURM; the login node is used
only for validation, submission, monitoring, hashing, and small artifact-index
operations.

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

## 4A. Deterministic FEM v2 qualification

This chain is independent of the archived multi-fidelity execution above. Use
one detached, clean worktree at one reviewed source commit for Gates A, B, and
C. Do not advance that worktree between stages. A documentation branch may
advance elsewhere, but its files must not be copied into the execution tree.

Set the trust roots from the reviewed commit and verify them before submission:

```bash
FEM_V2_ROOT=/absolute/path/to/detached-clean-worktree
FEM_V2_PROTOCOL="$FEM_V2_ROOT/protocols/corpus_v4_fem_v2_qualification_v1.json"
FEM_V2_PROTOCOL_SHA256=912506b638c737b0e87022fb793392ebba5824f50f33fbabdc8913ba3f38908f
FEM_V2_SOURCE_COMMIT=replace-with-reviewed-40-character-commit
cd "$FEM_V2_ROOT"
git status --porcelain
git rev-parse HEAD
sha256sum "$FEM_V2_PROTOCOL"
python3 code/quality/build_manifest.py --check
python3 -m pytest -q -p no:cacheprovider tests
mkdir -p logs
```

The first two commands must return an empty status and the exact reviewed
commit. The protocol digest must equal `FEM_V2_PROTOCOL_SHA256`. Validate all
three task expansions without invoking a solver:

```bash
python3 code/experiments/proofs/run_corpus_v4_fem_v2_qualification.py \
  --stage gate_a \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --validate-only
python3 code/experiments/proofs/run_corpus_v4_fem_v2_qualification.py \
  --stage gate_b \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --validate-only
python3 code/experiments/proofs/run_corpus_v4_fem_v2_qualification.py \
  --stage gate_c \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --validate-only
sbatch --test-only -A pgs0407 code/jobs/submit_corpus_v4_fem_v2_gate_a.sh
```

The validate-only receipts must report 45, 9, and 21 tasks, respectively,
`verified_geometry_records=1500`, and `solver_executed=false`. Submit only Gate
A at this point:

```bash
GATE_A_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT" \
  code/jobs/submit_corpus_v4_fem_v2_gate_a.sh)
GATE_A_FINALIZER_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --dependency="afterany:$GATE_A_JOB_ID" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT",PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID="$GATE_A_JOB_ID" \
  code/jobs/submit_finalize_corpus_v4_fem_v2_gate_a.sh)
```

Wait until the finalizer is absent from `squeue` and its main `sacct` row is
`COMPLETED|0:0`. An empty queue alone is insufficient. Then run the solver-free
postterminal admission on the login node:

```bash
python3 code/experiments/proofs/admit_corpus_v4_fem_v2_qualification.py \
  --stage gate_a \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --expected-source-git-head "$FEM_V2_SOURCE_COMMIT" \
  --source-array-job-id "$GATE_A_JOB_ID" \
  --finalizer-job-id "$GATE_A_FINALIZER_JOB_ID"
GATE_A_ADMISSION="$FEM_V2_ROOT/results/corpus_v4/cps_reference_v2/qualification/v1/admission/gate_a/source_job_${GATE_A_JOB_ID}/finalizer_job_${GATE_A_FINALIZER_JOB_ID}/FINAL_ADMISSION.json"
GATE_A_ADMISSION_SHA256=$(sha256sum "$GATE_A_ADMISSION" | awk '{print $1}')
jq '.decision' "$GATE_A_ADMISSION"
```

Gate B is authorized only when `qualification_stage_pass` and
`next_stage_may_run` are both true. Propagate the exact admission path and hash:

```bash
GATE_B_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION="$GATE_A_ADMISSION",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256="$GATE_A_ADMISSION_SHA256" \
  code/jobs/submit_corpus_v4_fem_v2_gate_b.sh)
GATE_B_FINALIZER_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --dependency="afterany:$GATE_B_JOB_ID" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT",PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID="$GATE_B_JOB_ID",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION="$GATE_A_ADMISSION",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256="$GATE_A_ADMISSION_SHA256" \
  code/jobs/submit_finalize_corpus_v4_fem_v2_gate_b.sh)
```

After the same terminal check, admit Gate B and bind its receipt:

```bash
python3 code/experiments/proofs/admit_corpus_v4_fem_v2_qualification.py \
  --stage gate_b \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --expected-source-git-head "$FEM_V2_SOURCE_COMMIT" \
  --source-array-job-id "$GATE_B_JOB_ID" \
  --finalizer-job-id "$GATE_B_FINALIZER_JOB_ID"
GATE_B_ADMISSION="$FEM_V2_ROOT/results/corpus_v4/cps_reference_v2/qualification/v1/admission/gate_b/source_job_${GATE_B_JOB_ID}/finalizer_job_${GATE_B_FINALIZER_JOB_ID}/FINAL_ADMISSION.json"
GATE_B_ADMISSION_SHA256=$(sha256sum "$GATE_B_ADMISSION" | awk '{print $1}')
jq '.decision' "$GATE_B_ADMISSION"
```

Only `qualification_stage_pass=true` together with
`r3_v2_generation_may_start=true` authorizes new R3 v2 generation. Gate C is
needed only for a new R4 or explicit multi-fidelity package:

```bash
GATE_C_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION="$GATE_B_ADMISSION",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256="$GATE_B_ADMISSION_SHA256" \
  code/jobs/submit_corpus_v4_fem_v2_gate_c.sh)
GATE_C_FINALIZER_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --dependency="afterany:$GATE_C_JOB_ID" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_V2_ROOT",PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256="$FEM_V2_PROTOCOL_SHA256",PCB_GNN_V4_SOURCE_COMMIT="$FEM_V2_SOURCE_COMMIT",PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID="$GATE_C_JOB_ID",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION="$GATE_B_ADMISSION",PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256="$GATE_B_ADMISSION_SHA256" \
  code/jobs/submit_finalize_corpus_v4_fem_v2_gate_c.sh)
```

After Gate C and its finalizer are terminal, create the last receipt:

```bash
python3 code/experiments/proofs/admit_corpus_v4_fem_v2_qualification.py \
  --stage gate_c \
  --expected-protocol-sha256 "$FEM_V2_PROTOCOL_SHA256" \
  --expected-source-git-head "$FEM_V2_SOURCE_COMMIT" \
  --source-array-job-id "$GATE_C_JOB_ID" \
  --finalizer-job-id "$GATE_C_FINALIZER_JOB_ID"
GATE_C_ADMISSION="$FEM_V2_ROOT/results/corpus_v4/cps_reference_v2/qualification/v1/admission/gate_c/source_job_${GATE_C_JOB_ID}/finalizer_job_${GATE_C_FINALIZER_JOB_ID}/FINAL_ADMISSION.json"
jq '.decision' "$GATE_C_ADMISSION"
```

Missing accounting, a nonterminal finalizer, a missing receipt, or any
admission error is operationally `INDETERMINATE`; absence of a positive receipt
never opens the next stage. A valid Gate-C receipt may combine
`qualification_stage_pass=true` with `scientific_outcome=SCIENTIFIC_NEGATIVE`
when R4 is repeatable but the R3/R4 mesh-sensitivity threshold fails. That
combination permits separately named fidelities and does not support a
mesh-convergence claim.

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

## 15A. Submit FEM-v2 accuracy protocol v3

Protocol v2 is closed as diagnostic evidence and must not be resumed. V3 has a
separate source commit, result root, split-scoped inputs, sandbox, accepted set,
and finalizer. Start from the exact clean source commit below. Do not substitute
the documentation commit at the tip of the branch.

```bash
ACC3_RUN_ROOT=/absolute/path/to/clean-detached-v3-worktree
ACC3_SOURCE_COMMIT=c0ffca0d0637e8fbba81c126c3f56f8316003a9a
ACC3_PROTOCOL_SHA256=d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1
ACC3_PLAN_SHA256=04fab5efbc8428682fa0ea572001d95b1179b86e912b03deb4c8d5c4accbb40f
ACC3_TASKS_SHA256=e5a444204e99bc92462ac87d3b4721d5a4d33db9bd7d3b8e7d274ebe5d723b71
ACC3_LOCK_SHA256=8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c
cd "$ACC3_RUN_ROOT"
test "$(git rev-parse HEAD)" = "$ACC3_SOURCE_COMMIT"
test -z "$(git status --short --untracked-files=all)"
sha256sum /usr/bin/bwrap
```

The Bubblewrap digest must be
`9dba99a1fa3be3b0d3e5cb7d6d297742b56a3b1749465f520503c651b38d99aa`.
Validate the complete frozen closure without training:

```bash
python3 code/experiments/proofs/plan_corpus_v4_accuracy_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --out results/corpus_v4/accuracy_v3/plan/v1 \
  --check
python3 code/experiments/proofs/run_corpus_v4_accuracy_task_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --expected-protocol-sha256 "$ACC3_PROTOCOL_SHA256" \
  --plan results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --expected-plan-sha256 "$ACC3_PLAN_SHA256" \
  --task-manifest results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$ACC3_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v3r2.json \
  --expected-execution-lock-sha256 "$ACC3_LOCK_SHA256" \
  --expected-source-git-head "$ACC3_SOURCE_COMMIT" \
  --output-root results/corpus_v4/accuracy_v3/jobs \
  --validate-only
```

First submit only the sandbox preflight. The singleton retains the frozen
training resource profile and array throttle, but exits before optimizer work.
Preflight `7086917` used the original lock and failed at CLI parsing because
the site Bubblewrap lacks `--clearenv`. Lock r1 used `/usr/bin/env -i`, but its
job `7086936` stopped at scheduler self-authentication before data loading or
optimizer work because the isolated client could not resolve the active SLURM
component. The active r2 lock adds a fixed read-only NSS, Munge, and configless
SLURM runtime allowlist. Do not reuse either rejected lock or source commit.

The authoritative r2 singleton is job `7087033`. It reached
`COMPLETED/0:0` in 20 s. Its receipt SHA-256 is
`dce1aa2f28a54ab04912f92729ed63942fcf35348bc1ff4a7fa790335796c0a9`,
and its cross-bound admission SHA-256 is
`9e131158e14ec1e4bf41fc20e2326f11b27e8b8bffe283025427975daca52773`.
Do not submit another preflight unless a new execution-lock revision makes the
existing admission inapplicable.

```bash
sbatch --test-only -A pgs0407 --array=0%5 \
  --chdir="$ACC3_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT="$ACC3_RUN_ROOT",PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT="$ACC3_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_V3_PROTOCOL_SHA256="$ACC3_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_V3_PLAN_SHA256="$ACC3_PLAN_SHA256",PCB_GNN_V4_ACCURACY_V3_TASK_MANIFEST_SHA256="$ACC3_TASKS_SHA256",PCB_GNN_V4_ACCURACY_V3_EXECUTION_LOCK_SHA256="$ACC3_LOCK_SHA256",PCB_GNN_V4_ACCURACY_V3_SANDBOX_PROBE_ONLY=true \
  "$ACC3_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy_v3.sh"
ACC3_PROBE_JOB_ID=$(sbatch --parsable -A pgs0407 --array=0%5 \
  --chdir="$ACC3_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT="$ACC3_RUN_ROOT",PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT="$ACC3_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_V3_PROTOCOL_SHA256="$ACC3_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_V3_PLAN_SHA256="$ACC3_PLAN_SHA256",PCB_GNN_V4_ACCURACY_V3_TASK_MANIFEST_SHA256="$ACC3_TASKS_SHA256",PCB_GNN_V4_ACCURACY_V3_EXECUTION_LOCK_SHA256="$ACC3_LOCK_SHA256",PCB_GNN_V4_ACCURACY_V3_SANDBOX_PROBE_ONLY=true \
  "$ACC3_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy_v3.sh")
ACC3_PROBE_JOB_ID=${ACC3_PROBE_JOB_ID%%;*}
[[ "$ACC3_PROBE_JOB_ID" =~ ^[0-9]+$ ]]
```

Wait for the exact logical component to reach `COMPLETED/0:0` and inspect the
receipt before training:

```bash
sacct -X -n -P -j "$ACC3_PROBE_JOB_ID" \
  --format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
jq . \
  "results/corpus_v4/accuracy_v3/sandbox_probes/job_${ACC3_PROBE_JOB_ID}/task_00.json"
```

The receipt must record `sandbox_boundary_passed=true`,
`heldout_bytes_opened=false`, and `training_started=false`. Its selected
artifact must be `training_split_40.jsonl`, with four hidden split artifacts.
Reject the protocol if the task fails because a required cluster mount is
missing; do not weaken the filesystem allowlist after observing any model
outcome.

The review of job `7087033` passed, so the full grid is authorized. Explicitly
disable probe mode so an inherited shell variable cannot change the workload.

```bash
ACC3_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$ACC3_RUN_ROOT" \
  --export=ALL,PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT="$ACC3_RUN_ROOT",PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT="$ACC3_SOURCE_COMMIT",PCB_GNN_V4_ACCURACY_V3_PROTOCOL_SHA256="$ACC3_PROTOCOL_SHA256",PCB_GNN_V4_ACCURACY_V3_PLAN_SHA256="$ACC3_PLAN_SHA256",PCB_GNN_V4_ACCURACY_V3_TASK_MANIFEST_SHA256="$ACC3_TASKS_SHA256",PCB_GNN_V4_ACCURACY_V3_EXECUTION_LOCK_SHA256="$ACC3_LOCK_SHA256",PCB_GNN_V4_ACCURACY_V3_SANDBOX_PROBE_ONLY=false \
  "$ACC3_RUN_ROOT/code/jobs/submit_corpus_v4_accuracy_v3.sh")
ACC3_JOB_ID=${ACC3_JOB_ID%%;*}
[[ "$ACC3_JOB_ID" =~ ^[0-9]+$ ]]
```

Array `7087054` is the frozen r2 checkpoint grid. Wait until it is absent from
`squeue`, then require one terminal logical row for every task. Empty `squeue`
output alone is not success evidence.

```bash
ACC3_JOB_ID=7087054
ACC3_ATTEMPT_ROOT="results/corpus_v4/accuracy_v3/jobs/job_${ACC3_JOB_ID}"
ACC3_RESUME_ROOT=results/corpus_v4/accuracy_v3/resume/round_00

squeue -h -j "$ACC3_JOB_ID"
sacct -X -n -P -j "$ACC3_JOB_ID" \
  --format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES
```

The accounting table must contain exactly `7087054_0` through `7087054_24` as
`JobID`, each with `COMPLETED/0:0`. `JobIDRaw` must match the numeric in-run
`JobId`; `ReqTRES` and `AllocTRES` must be field-equivalent to the in-run
receipt. The resume planner checks these rules again for every candidate.

Build the initial candidate inventory and accepted/pending sets in a new
directory. This command hashes and validates existing checkpoints, runs their
small smoke fixtures, and queries accounting. It neither trains a model nor
invokes a field solver.

```bash
test "$(git rev-parse HEAD)" = "$ACC3_SOURCE_COMMIT"
test -z "$(git status --short --untracked-files=all -- \
  code protocols requirements-proof.txt)"
test ! -e "$ACC3_RESUME_ROOT"

python3 code/experiments/proofs/plan_corpus_v4_accuracy_resume_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --expected-protocol-sha256 "$ACC3_PROTOCOL_SHA256" \
  --plan results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --expected-plan-sha256 "$ACC3_PLAN_SHA256" \
  --task-manifest results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$ACC3_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v3r2.json \
  --expected-execution-lock-sha256 "$ACC3_LOCK_SHA256" \
  --expected-source-git-head "$ACC3_SOURCE_COMMIT" \
  --attempt-root "$ACC3_ATTEMPT_ROOT" \
  --out "$ACC3_RESUME_ROOT"
```

The planner creates exactly this admission tree:

```text
results/corpus_v4/accuracy_v3/resume/round_00/
|-- candidate_index.json
|-- accepted_artifact_set.json
`-- pending_task_set.json
```

Inspect the fail-closed decisions and freeze their hashes:

```bash
jq -e '.entries | length == 25' \
  "$ACC3_RESUME_ROOT/candidate_index.json"
jq -e '
  .n_accepted == 25 and
  .n_expected == 25 and
  .decision.checkpoint_set_complete == true and
  .decision.held_out_inference_may_start == true and
  .decision.claim_eligible == false and
  .decision.speed_claim_eligible == false and
  ([.candidate_dispositions[].outcome] | all(. == "accepted"))
' "$ACC3_RESUME_ROOT/accepted_artifact_set.json"
jq -e '.n_pending == 0 and (.pending | length == 0)' \
  "$ACC3_RESUME_ROOT/pending_task_set.json"
sha256sum "$ACC3_RESUME_ROOT"/*.json
```

Every indexed candidate receives one fixed-code disposition. Free-form
rejection text is forbidden. If any task is pending, preserve `round_00`, use
its `pending_task_set.json` as the retry allowlist, and later build `round_01`
with separate `--attempt-root` arguments for the original and retry job roots.
Do not overwrite or omit an earlier candidate inventory.

For array `7087054`, all 25 tasks reached `COMPLETED/0:0`. Round 00 then
recorded 25 `SCHEDULER_NOT_COMPLETED` dispositions because that planner process
could not reach `slurmdbd`. This was a control-plane observation, not an
artifact failure. After accounting access returned, the unchanged original
attempt root was evaluated into round 01 without a task retry. The candidate
index hash remained
`e357c50e9cce1d0d70bf6060754e54e2829566eb4550980873d56405ce31709a`;
round 01 accepted all 25 candidates and left zero pending. Re-evaluating an
unchanged attempt root is valid only for a transient accounting-access failure.
Artifact, identity, smoke, or terminal-state failures still require the normal
pending-set recovery path.

The finalizer uses two independent trust roots. The historical training lock
authenticates the unchanged r2 checkpoints and source commit. A separate
finalizer lock authenticates the accepted-set hash, finalizer source closure,
and finalizer execution commit. The wrapper validates both locks and must not
modify, relabel, or silently rerun any r2 checkpoint.

Do not create the production finalizer lock before the 25-task accepted set is
complete and its hash is frozen. Afterward, generate the lock with
`build_corpus_v4_accuracy_finalizer_lock_v3.py`, review and commit the complete
boundary, and submit the finalizer from a clean checkout through SLURM. Until
those steps pass, do not submit a finalizer. No accuracy, latency, speed, or
physical-validation claim follows from checkpoint completion or accepted-set
construction alone.

For this execution, round 01 accepted-set SHA-256 is
`291a76231ef348d150fcec0f1cb70031537f1db5530ff0813365ed2932e326fe`.
The generated finalizer lock SHA-256 is
`cdb53640f9d9c206b37651e28a04781a19d5dda81d520cf50b77c628468cadf3`.
Finalizer job `7102842` ran from clean source commit
`cdd3a7555377360208e1c582b6e94aca8fbfdd60` and reached `COMPLETED/0:0` in
61 s. Its archive manifest binds 31 analysis files and passed the clean-tracked
verification command recorded in the
[v3 evidence README](../../results/corpus_v4/accuracy_v3/README.md#clean-clone-verification).
Scientific review then admitted `C-ACC-FEMV2-001` only. Latency, speed, mesh
convergence, and physical-validation claims remain closed.

## 16. Submit the Corpus V4 paired-latency study

**Dependency:** complete the FEM repeatability source array, finalizer, and
postterminal admission in Section 17 before running any command in this
section. A positive `FINAL_ADMISSION.json` is mandatory; the ordering of these
reference sections is not an authorization to skip that prerequisite.

The paired-latency pipeline is bound to account `pgs0407`. The batch wrappers
also declare the account, but every admission command repeats `-A pgs0407` so a
missing or stale wrapper fails during review. Exporting an account variable is
not a substitute for the scheduler account option.

Copy the reviewed hashes from the latency evidence README after the plan and
execution lock are regenerated. The source commit remains an external trust
root because placing it inside its own source lock would create a cycle.

```bash
LAT_ROOT=/absolute/path/to/clean-detached-worktree
LAT_SOURCE_COMMIT=replace-with-reviewed-40-character-commit
LAT_PROTOCOL_SHA256=5bafd175e5df19f2a94382b543c6a4a9dba2c9e6ecca365b5e9d0b4de00b90a2
LAT_PLAN_SHA256=9ef641a1ccd3d4a12f72e30971a61eb82813d59e41b9666ebfd6e1602a9d1281
LAT_TASKS_SHA256=db47a120c8113c156d0d7010204721fe2770dda848c4f1a547753de3b046b8c2
LAT_LOCK_SHA256=e54b9ef326006a60a62446d90c43d6565cf1d52bbbef5315fc0bdc28d109de13
FASTHENRY_BIN=/absolute/path/to/verified-fasthenry
: "${FEM_REP_ADMISSION:?Complete Section 17 and export its canonical receipt path}"
: "${FEM_REP_ADMISSION_SHA256:?Complete Section 17 and export its receipt SHA-256}"
cd "$LAT_ROOT"
test "$(git rev-parse HEAD)" = "$LAT_SOURCE_COMMIT"
test -z "$(git status --short --untracked-files=no)"
test -z "$(git status --short --untracked-files=all -- code protocols requirements-proof.txt)"
```

Admission validation is solver-free. Run it before the three-layout preflight.

```bash
python3 code/experiments/proofs/plan_corpus_v4_latency.py --check
sbatch --test-only -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,FASTHENRY_BIN="$FASTHENRY_BIN",PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION="$FEM_REP_ADMISSION",PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION_SHA256="$FEM_REP_ADMISSION_SHA256" \
  "$LAT_ROOT/code/jobs/submit_corpus_v4_latency_preflight.sh"
LAT_PREFLIGHT_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,FASTHENRY_BIN="$FASTHENRY_BIN",PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION="$FEM_REP_ADMISSION",PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION_SHA256="$FEM_REP_ADMISSION_SHA256" \
  "$LAT_ROOT/code/jobs/submit_corpus_v4_latency_preflight.sh")
LAT_PREFLIGHT_JOB_ID=${LAT_PREFLIGHT_JOB_ID%%;*}
[[ "$LAT_PREFLIGHT_JOB_ID" =~ ^[0-9]+$ ]]
```

The preflight tasks are 0, 152, and 305 and are excluded from the final
statistics. Inspect their terminal accounting and artifacts. If all three pass
the unchanged contract, build the canonical admission artifact. The builder
independently requires exact `COMPLETED/0:0` accounting, account and TRES
agreement, immutable task artifacts, the current clean source commit, and the
frozen roots. A failed preflight cannot create this artifact.

```bash
sacct -X -n -P -j "$LAT_PREFLIGHT_JOB_ID" \
  --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
find "results/corpus_v4/latency/preflight/attempts/job_${LAT_PREFLIGHT_JOB_ID}" \
  -maxdepth 2 -type f -print
LAT_PREFLIGHT_ADMISSION="results/corpus_v4/latency/preflight/admission/job_${LAT_PREFLIGHT_JOB_ID}/PREFLIGHT_ADMISSION.json"
python3 code/experiments/proofs/admit_corpus_v4_latency_preflight.py \
  --protocol protocols/corpus_v4_latency_v1.json \
  --expected-protocol-sha256 "$LAT_PROTOCOL_SHA256" \
  --plan results/corpus_v4/latency/plan/v2/plan.json \
  --expected-plan-sha256 "$LAT_PLAN_SHA256" \
  --task-manifest results/corpus_v4/latency/plan/v2/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$LAT_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_latency_execution_lock_v3.json \
  --expected-execution-lock-sha256 "$LAT_LOCK_SHA256" \
  --expected-source-git-head "$LAT_SOURCE_COMMIT" \
  --array-job-id "$LAT_PREFLIGHT_JOB_ID" \
  --out "$LAT_PREFLIGHT_ADMISSION"
LAT_PREFLIGHT_ADMISSION_SHA256=$(sha256sum "$LAT_PREFLIGHT_ADMISSION" | awk '{print $1}')
sbatch --test-only -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,FASTHENRY_BIN="$FASTHENRY_BIN",PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION="$LAT_PREFLIGHT_ADMISSION",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION_SHA256="$LAT_PREFLIGHT_ADMISSION_SHA256" \
  "$LAT_ROOT/code/jobs/submit_corpus_v4_latency.sh"
LAT_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,FASTHENRY_BIN="$FASTHENRY_BIN",PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION="$LAT_PREFLIGHT_ADMISSION",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION_SHA256="$LAT_PREFLIGHT_ADMISSION_SHA256" \
  "$LAT_ROOT/code/jobs/submit_corpus_v4_latency.sh")
LAT_JOB_ID=${LAT_JOB_ID%%;*}
[[ "$LAT_JOB_ID" =~ ^[0-9]+$ ]]
```

After all logical components have terminal accounting, build an accepted set.
Do not submit a retry while accounting is incomplete. A retry uses only the
hash-pinned pending set emitted by the resume planner and keeps all original
resource limits.

```bash
sacct -X -n -P -j "$LAT_JOB_ID" \
  --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
python3 code/experiments/proofs/plan_corpus_v4_latency_resume.py \
  --protocol protocols/corpus_v4_latency_v1.json \
  --expected-protocol-sha256 "$LAT_PROTOCOL_SHA256" \
  --plan results/corpus_v4/latency/plan/v2/plan.json \
  --expected-plan-sha256 "$LAT_PLAN_SHA256" \
  --task-manifest results/corpus_v4/latency/plan/v2/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$LAT_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_latency_execution_lock_v3.json \
  --expected-execution-lock-sha256 "$LAT_LOCK_SHA256" \
  --expected-source-git-head "$LAT_SOURCE_COMMIT" \
  --preflight-admission "$LAT_PREFLIGHT_ADMISSION" \
  --expected-preflight-admission-sha256 "$LAT_PREFLIGHT_ADMISSION_SHA256" \
  --attempt-root results/corpus_v4/latency/jobs/attempts \
  --out-dir results/corpus_v4/latency/resume/round_00
```

If `pending_task_ids` is nonempty, submit only that frozen sparse set. After
terminal accounting arrives, rerun the resume planner into `round_01` with the
same shared attempt root. Repeat with a new round name; never overwrite a prior
round.

```bash
LAT_PENDING=results/corpus_v4/latency/resume/round_00/pending_task_set.json
LAT_PENDING_SHA256=$(sha256sum "$LAT_PENDING" | awk '{print $1}')
LAT_RETRY_ARRAY=$(jq -r '.pending_task_ids | join(",")' "$LAT_PENDING")
if [[ -n "$LAT_RETRY_ARRAY" ]]; then
  LAT_RETRY_JOB_ID=$(sbatch --parsable -A pgs0407 \
    --array="${LAT_RETRY_ARRAY}%8" \
    --chdir="$LAT_ROOT" \
    --export=ALL,FASTHENRY_BIN="$FASTHENRY_BIN",PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION="$LAT_PREFLIGHT_ADMISSION",PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION_SHA256="$LAT_PREFLIGHT_ADMISSION_SHA256",PCB_GNN_V4_LATENCY_PENDING_SET="$LAT_PENDING",PCB_GNN_V4_LATENCY_PENDING_SET_SHA256="$LAT_PENDING_SHA256" \
    "$LAT_ROOT/code/jobs/submit_corpus_v4_latency.sh")
  LAT_RETRY_JOB_ID=${LAT_RETRY_JOB_ID%%;*}
  [[ "$LAT_RETRY_JOB_ID" =~ ^[0-9]+$ ]]
fi
```

Finalization is allowed only when all 306 canonical tasks are accepted and the
pending set is empty. The finalizer runs on SLURM and repeats the same account
gate. Point `LAT_FINAL_ROUND` to the latest immutable resume round.

```bash
LAT_FINAL_ROUND=round_00
LAT_ACCEPTED="results/corpus_v4/latency/resume/${LAT_FINAL_ROUND}/accepted_artifact_set.json"
LAT_ACCEPTED_SHA256=$(sha256sum "$LAT_ACCEPTED" | awk '{print $1}')
sbatch --test-only -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_LATENCY_ACCEPTED_SET="$LAT_ACCEPTED",PCB_GNN_V4_LATENCY_ACCEPTED_SET_SHA256="$LAT_ACCEPTED_SHA256" \
  "$LAT_ROOT/code/jobs/submit_finalize_corpus_v4_latency.sh"
LAT_FINAL_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$LAT_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$LAT_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$LAT_SOURCE_COMMIT",PCB_GNN_V4_LATENCY_PROTOCOL_SHA256="$LAT_PROTOCOL_SHA256",PCB_GNN_V4_LATENCY_PLAN_SHA256="$LAT_PLAN_SHA256",PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256="$LAT_TASKS_SHA256",PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256="$LAT_LOCK_SHA256",PCB_GNN_V4_LATENCY_ACCEPTED_SET="$LAT_ACCEPTED",PCB_GNN_V4_LATENCY_ACCEPTED_SET_SHA256="$LAT_ACCEPTED_SHA256" \
  "$LAT_ROOT/code/jobs/submit_finalize_corpus_v4_latency.sh")
LAT_FINAL_JOB_ID=${LAT_FINAL_JOB_ID%%;*}
[[ "$LAT_FINAL_JOB_ID" =~ ^[0-9]+$ ]]
```

Wait for exact `COMPLETED/0:0` accounting, then create the archive manifest.
The first command queries live accounting; after the artifacts are committed,
the second invocation is scheduler-independent and requires every closure file
to be Git-tracked and clean.

```bash
sacct -X -n -P -j "$LAT_FINAL_JOB_ID" \
  --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
LAT_ANALYSIS="results/corpus_v4/latency/final/job_${LAT_FINAL_JOB_ID}/ANALYSIS_MANIFEST.json"
LAT_ANALYSIS_SHA256=$(sha256sum "$LAT_ANALYSIS" | awk '{print $1}')
python3 code/quality/verify_corpus_v4_latency_archive.py \
  --protocol protocols/corpus_v4_latency_v1.json \
  --expected-protocol-sha256 "$LAT_PROTOCOL_SHA256" \
  --plan results/corpus_v4/latency/plan/v2/plan.json \
  --expected-plan-sha256 "$LAT_PLAN_SHA256" \
  --task-manifest results/corpus_v4/latency/plan/v2/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$LAT_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_latency_execution_lock_v3.json \
  --expected-execution-lock-sha256 "$LAT_LOCK_SHA256" \
  --expected-source-git-head "$LAT_SOURCE_COMMIT" \
  --accepted-set "$LAT_ACCEPTED" \
  --expected-accepted-set-sha256 "$LAT_ACCEPTED_SHA256" \
  --analysis-manifest "$LAT_ANALYSIS" \
  --expected-analysis-manifest-sha256 "$LAT_ANALYSIS_SHA256" \
  --out results/corpus_v4/latency/ARCHIVE_MANIFEST.json
```

```bash
python3 code/quality/verify_corpus_v4_latency_archive.py \
  --protocol protocols/corpus_v4_latency_v1.json \
  --expected-protocol-sha256 "$LAT_PROTOCOL_SHA256" \
  --plan results/corpus_v4/latency/plan/v2/plan.json \
  --expected-plan-sha256 "$LAT_PLAN_SHA256" \
  --task-manifest results/corpus_v4/latency/plan/v2/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$LAT_TASKS_SHA256" \
  --execution-lock protocols/corpus_v4_latency_execution_lock_v3.json \
  --expected-execution-lock-sha256 "$LAT_LOCK_SHA256" \
  --expected-source-git-head "$LAT_SOURCE_COMMIT" \
  --accepted-set "$LAT_ACCEPTED" \
  --expected-accepted-set-sha256 "$LAT_ACCEPTED_SHA256" \
  --analysis-manifest "$LAT_ANALYSIS" \
  --expected-analysis-manifest-sha256 "$LAT_ANALYSIS_SHA256" \
  --out results/corpus_v4/latency/ARCHIVE_MANIFEST.json \
  --check --require-git-tracked
```

Keep `C-LAT-001` blocked until the finalizer artifact, archive manifest,
terminal account and resource receipts, Git-tracked clean-clone verifier, and
claim wording all pass.

## 17. Submit the FEM mesh-repeatability diagnostic

This diagnostic must be submitted only from the reviewed clean detached
checkout. It runs 15 array elements with two sequential FEM arms per element,
for 30 heavy solves. It cannot authorize an accuracy or speed claim.

```bash
FEM_REP_ROOT=/absolute/path/to/clean-detached-worktree
FEM_REP_SOURCE_COMMIT=replace-with-reviewed-40-character-commit
FEM_REP_PROTOCOL_SHA256=faa71236ce1a77c0d371b2511af2ad3766e57a823c9dd792bee0d4252be438a2
cd "$FEM_REP_ROOT"
test "$(git rev-parse HEAD)" = "$FEM_REP_SOURCE_COMMIT"
test -z "$(git status --short)"
python3 code/experiments/proofs/experiments_corpus_v4_fem_repeatability.py \
  --expected-protocol-sha256 "$FEM_REP_PROTOCOL_SHA256" \
  --validate-only
sbatch --test-only -A pgs0407 \
  --chdir="$FEM_REP_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_REP_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$FEM_REP_SOURCE_COMMIT",PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256="$FEM_REP_PROTOCOL_SHA256" \
  "$FEM_REP_ROOT/code/jobs/submit_corpus_v4_fem_repeatability.sh"
FEM_REP_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --chdir="$FEM_REP_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_REP_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$FEM_REP_SOURCE_COMMIT",PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256="$FEM_REP_PROTOCOL_SHA256" \
  "$FEM_REP_ROOT/code/jobs/submit_corpus_v4_fem_repeatability.sh")
FEM_REP_JOB_ID=${FEM_REP_JOB_ID%%;*}
[[ "$FEM_REP_JOB_ID" =~ ^[0-9]+$ ]]
```

Queue exactly one scheduler-managed finalizer after the source array is
accepted. Use `afterany`, not `afterok`: a source element intentionally exits
nonzero after preserving a failed integrity observation, and that negative
diagnostic still requires structured finalization. The dependency controls
only when the finalizer starts. It does not relax any scientific gate. The
finalizer still requires exactly 15 terminal source rows, authenticates every
artifact, and permits a positive provisional decision only when all rows are
`COMPLETED/0:0` and Arm A passes.

```bash
FEM_REP_FINAL_SOURCE_ROOT="results/corpus_v4/fem_repeatability/v1/final/source_job_${FEM_REP_JOB_ID}"
FEM_REP_ADMISSION_SOURCE_ROOT="results/corpus_v4/fem_repeatability/v1/admission/source_job_${FEM_REP_JOB_ID}"
if [[ -e "$FEM_REP_FINAL_SOURCE_ROOT" || -e "$FEM_REP_ADMISSION_SOURCE_ROOT" ]]; then
  printf '%s\n' "Stop: this source array already has finalizer or admission artifacts" >&2
  exit 1
fi
if squeue -h -u "$(id -un)" -n pcb-v4-fem-rep-fin -o '%i' | rg -q '.'; then
  printf '%s\n' "Stop: a FEM-repeatability finalizer is already pending or running" >&2
  exit 1
fi
sbatch --test-only -A pgs0407 \
  --dependency="afterany:${FEM_REP_JOB_ID}" \
  --chdir="$FEM_REP_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_REP_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$FEM_REP_SOURCE_COMMIT",PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256="$FEM_REP_PROTOCOL_SHA256",PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID="$FEM_REP_JOB_ID" \
  "$FEM_REP_ROOT/code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh"
FEM_REP_FINAL_JOB_ID=$(sbatch --parsable -A pgs0407 \
  --dependency="afterany:${FEM_REP_JOB_ID}" \
  --chdir="$FEM_REP_ROOT" \
  --export=ALL,PCB_GNN_V4_EXECUTION_ROOT="$FEM_REP_ROOT",PCB_GNN_V4_SOURCE_COMMIT="$FEM_REP_SOURCE_COMMIT",PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256="$FEM_REP_PROTOCOL_SHA256",PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID="$FEM_REP_JOB_ID" \
  "$FEM_REP_ROOT/code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh")
FEM_REP_FINAL_JOB_ID=${FEM_REP_FINAL_JOB_ID%%;*}
[[ "$FEM_REP_FINAL_JOB_ID" =~ ^[0-9]+$ ]]
```

A watcher may report progress, but it must not submit another finalizer.
Preserve both `JobID` and `JobIDRaw`; the finalizer authenticates their exact
relationship.

```bash
squeue -j "$FEM_REP_JOB_ID,$FEM_REP_FINAL_JOB_ID" \
  -o '%.20i %.32j %.2t %.10M %.10l %R'
sacct -X -n -P -j "$FEM_REP_JOB_ID" \
  --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
find "results/corpus_v4/fem_repeatability/v1/attempts/job_${FEM_REP_JOB_ID}" \
  -maxdepth 2 -type f -print
sacct -X -n -P -j "$FEM_REP_FINAL_JOB_ID" \
  --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS
```

An `afterany` dependency may release before the accounting database exposes
all 15 source rows. The finalizer must fail closed if `sacct` is incomplete,
duplicated, ambiguous, or nonterminal. Preserve that failed finalizer job and
its logs. Wait until live accounting exposes logical tasks 0 through 14 as
terminal, confirm that no finalizer is pending or running, and rerun the
guarded submission block to obtain a new immutable finalizer job ID. Do not
switch to `afterok`, synthesize accounting, relax the exact-row check, delete
the failed attempt, or overwrite an existing preterminal directory.

Run admission only after the selected finalizer itself has exact
`COMPLETED/0:0` accounting.

```bash
FEM_REP_ADMISSION="results/corpus_v4/fem_repeatability/v1/admission/source_job_${FEM_REP_JOB_ID}/finalizer_job_${FEM_REP_FINAL_JOB_ID}/FINAL_ADMISSION.json"
python3 code/experiments/proofs/admit_corpus_v4_fem_repeatability.py \
  --protocol protocols/corpus_v4_fem_repeatability_v1.json \
  --expected-protocol-sha256 "$FEM_REP_PROTOCOL_SHA256" \
  --expected-source-git-head "$FEM_REP_SOURCE_COMMIT" \
  --source-array-job-id "$FEM_REP_JOB_ID" \
  --finalizer-job-id "$FEM_REP_FINAL_JOB_ID"
test -f "$FEM_REP_ADMISSION"
FEM_REP_ADMISSION_SHA256=$(sha256sum "$FEM_REP_ADMISSION" | awk '{print $1}')
export FEM_REP_ADMISSION FEM_REP_ADMISSION_SHA256
```

The postterminal command performs no field solve. It replays all preterminal
artifacts, re-queries the finalizer's live `sacct` row, and creates the sole
receipt accepted by the latency preflight. Commit the immutable source-array,
finalizer, and admission artifacts before updating the evidence ledger. A
passing Arm A permits only a new authenticated three-task latency preflight. A
passing Arm B with failing Arm A requires a versioned FEM reference and
complete label, training, accuracy, and latency regeneration. If both arms
fail, freeze or serialize the mesh before generating new labels.

## One-thread FEM-v2 production controller

The FEM-v2 bulk run uses a dedicated detached checkout at the exact pushed
commit. Its controller is a login-safe scheduler client: its only external
operations are submission, queue inspection, and accounting. The controller
submits R4 first and the first R3 shard second, while keeping the projected
expanded-job count at or below 950. It never calls a field solver.

From the detached execution checkout, authenticate the fixed roots and preview
the exact commands before the first real tick:

```bash
FEMV2_ROOT=$(pwd -P)
FEMV2_SOURCE_COMMIT=$(git rev-parse HEAD)
FEMV2_PROTOCOL_SHA256=$(sha256sum protocols/corpus_v4_fem_v2_production_v1.json | awk '{print $1}')
FEMV2_PLAN_SHA256=$(sha256sum results/corpus_v4/cps_reference_v2/production/v1/plan/plan.json | awk '{print $1}')
FEMV2_LOCK_SHA256=$(sha256sum protocols/corpus_v4_fem_v2_production_lock_v1.json | awk '{print $1}')
test -z "$(git status --short --untracked-files=no)"
python3 code/experiments/proofs/corpus_v4_fem_v2_production.py run \
  --expected-protocol-sha256 "$FEMV2_PROTOCOL_SHA256" \
  --expected-plan-sha256 "$FEMV2_PLAN_SHA256" \
  --expected-execution-lock-sha256 "$FEMV2_LOCK_SHA256" \
  --manifest results/corpus_v4/cps_reference_v2/production/v1/plan/r4_manifest.jsonl \
  --dispatch results/corpus_v4/cps_reference_v2/production/v1/plan/r4_dispatch_000.json \
  --expected-dispatch-sha256 897cf14c87e167115e364f3e8ffcf9f62bd0c5e3205cb81f6ec6c0ed76a4330a \
  --output-root results/corpus_v4/cps_reference_v2/production/v1/attempts/r4 \
  --validate-only
python3 code/operations/corpus_v4_fem_v2_controller.py \
  --execution-root "$FEMV2_ROOT" \
  --source-commit "$FEMV2_SOURCE_COMMIT" \
  --protocol-sha256 "$FEMV2_PROTOCOL_SHA256" \
  --plan-sha256 "$FEMV2_PLAN_SHA256" \
  --lock-sha256 "$FEMV2_LOCK_SHA256" \
  --dry-run
```

Run the same controller without `--dry-run` exactly once to submit the R4 and
R3 shard-zero source/finalizer pairs. The immutable controller state records
the four returned job identifiers and every later accounting snapshot.

```bash
python3 code/operations/corpus_v4_fem_v2_controller.py \
  --execution-root "$FEMV2_ROOT" \
  --source-commit "$FEMV2_SOURCE_COMMIT" \
  --protocol-sha256 "$FEMV2_PROTOCOL_SHA256" \
  --plan-sha256 "$FEMV2_PLAN_SHA256" \
  --lock-sha256 "$FEMV2_LOCK_SHA256"
```

Monitor without solving on the login node:

```bash
squeue -r -u "$(id -un)" -o '%.20i %.34j %.10T %.10M %R'
sacct -X -n -P -j SOURCE_JOB_ID,FINALIZER_JOB_ID \
  --format=JobID,JobIDRaw,State,ExitCode,Account,Partition,Timelimit,NodeList,Restarts,ElapsedRaw,ReqTRES,AllocTRES
python3 code/operations/corpus_v4_fem_v2_controller.py \
  --execution-root "$FEMV2_ROOT" \
  --source-commit "$FEMV2_SOURCE_COMMIT" \
  --protocol-sha256 "$FEMV2_PROTOCOL_SHA256" \
  --plan-sha256 "$FEMV2_PLAN_SHA256" \
  --lock-sha256 "$FEMV2_LOCK_SHA256"
```

The next R3 shard is not released merely because its predecessor finalizer
returned zero. First create the solver-free postterminal wave admission. Then
bind its canonical path and SHA-256 in the release tick:

```bash
python3 code/operations/corpus_v4_fem_v2_controller.py \
  --execution-root "$FEMV2_ROOT" \
  --source-commit "$FEMV2_SOURCE_COMMIT" \
  --protocol-sha256 "$FEMV2_PROTOCOL_SHA256" \
  --plan-sha256 "$FEMV2_PLAN_SHA256" \
  --lock-sha256 "$FEMV2_LOCK_SHA256" \
  --release-r3-through 1 \
  --prior-admission results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_000/admission/SOURCE_SET/FINALIZER/FINAL_ADMISSION.json \
  --expected-prior-admission-sha256 ADMISSION_SHA256
```

Replace the uppercase receipt placeholders only with values emitted by the
immutable finalizer/admission artifacts. Never infer them from directory
counts. Planned source shards use frozen plan dispatches; infrastructure retry
arrays may use only the pending set named by the preceding admission. External
`TIMEOUT` and `OUT_OF_MEMORY` states are terminal resource outcomes and cannot
be retried into a positive result.
