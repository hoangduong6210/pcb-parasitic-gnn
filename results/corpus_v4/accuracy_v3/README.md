# Corpus V4 FEM-v2 accuracy protocol v3

This directory owns the active family-crossed graph-surrogate study on
`D-C4-FEM-D1-v2`. The protocol is frozen for checkpoint training. It contains
no admitted accuracy, latency, speed, or physical-validation result.

## Lifecycle

| Stage | State |
|---|---|
| Dataset and family registries | Frozen upstream inputs |
| Protocol and deterministic plan | Frozen |
| Filesystem sandbox preflight | Admitted by job `7087033` |
| Checkpoint training | Array `7087054` active; 25 tasks, concurrency 5 |
| Accepted checkpoint set | Not created |
| Held-out finalizer | Closed |
| Scientific claim | Closed |

The sandbox preflight is intentionally solver-free and optimizer-free. Job
`7087033` ran on a compute node, loaded the selected split artifact, constructed
all 1,209 graphs, checked the mounted filesystem boundary, and exited without
starting training. Its receipt records `sandbox_boundary_passed=true`,
`heldout_bytes_opened=false`, and `training_started=false`; terminal accounting
records `COMPLETED/0:0`. This admission opens checkpoint training only.

The frozen checkpoint grid was submitted as array `7087054` from source commit
`c0ffca0d0637e8fbba81c126c3f56f8316003a9a`. This is an execution state, not
an accepted checkpoint set. Held-out inference, finalization, and every claim
remain closed until all 25 candidates pass postterminal admission.

## Frozen roots

| Root | Identity |
|---|---|
| Active source commit | `c0ffca0d0637e8fbba81c126c3f56f8316003a9a` |
| Protocol | `d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1` |
| Plan | `04fab5efbc8428682fa0ea572001d95b1179b86e912b03deb4c8d5c4accbb40f` |
| Task manifest | `e5a444204e99bc92462ac87d3b4721d5a4d33db9bd7d3b8e7d274ebe5d723b71` |
| Held-out evaluation commitment | `ff02a28aa41f2526bea1b087e1222479d743f5eb766d13e4dfa48f42cc791046` |
| Active execution lock r2 | `8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c` |

The original execution lock, SHA-256
`f93521a5abed8f7010fdb8050a5f472df19594ba36c83eb97ae750caa7c2397c`,
is retained because preflight `7086917` used it and failed before sandbox
startup. Lock r1, SHA-256
`e8916801d3479f06b6eb71477796c4ae1b15408bf90aa7e516ad8ac7c02adbf0`,
replaced the unsupported Bubblewrap `--clearenv` option with
`/usr/bin/env -i`. Its preflight `7086936` reached the isolated execution path
but stopped at scheduler self-authentication before data loading or optimizer
work. Lock r2 adds a fixed read-only NSS, Munge, and configless-SLURM runtime
allowlist. Scientific inputs, splits, model, optimization, and held-out
exclusion are unchanged. The two failed-closed attempts are preserved under
[`sandbox_probes/job_7086917/`](sandbox_probes/job_7086917/) and
[`sandbox_probes/job_7086936/`](sandbox_probes/job_7086936/).

The r2 singleton `7087033` passed in 20 s. Its exact
[`task_00.json`](sandbox_probes/job_7087033/task_00.json) receipt has SHA-256
`dce1aa2f28a54ab04912f92729ed63942fcf35348bc1ff4a7fa790335796c0a9`.
The cross-bound
[`PREFLIGHT_ADMISSION.json`](sandbox_probes/job_7087033/PREFLIGHT_ADMISSION.json)
has SHA-256
`9e131158e14ec1e4bf41fc20e2326f11b27e8b8bffe283025427975daca52773`.

The five split-scoped training artifacts contain training and validation rows
only. Their hashes are:

| Split seed | Rows | SHA-256 |
|---:|---:|---|
| 40 | 1,209 | `d7c009d4a85e1b84eabc56e716080516ba22add1248359c518466099b9165fdb` |
| 41 | 1,218 | `f439b182c055ad917ed07af2d08d26f656ed42e447eec0ec5c55a9d74e2a5648` |
| 42 | 1,194 | `98bfaef69c79ab882fa9028706df2a858a995e4174b34932c6de08804b5c381d` |
| 43 | 1,201 | `16fa3a32bc231fdb5d50f7229b23554b8e83e0f0fe5831d98ff2cce8e18e493d` |
| 44 | 1,208 | `c7cd0fad11783f934272e831683d16e016e49608aadbb5868578a489cdc64411` |

The row totals vary because family sizes vary. Each split still contains 46
training families, 7 validation families, and 13 held-out test families.

## Byte-access boundary

Training runs under the pinned `/usr/bin/bwrap` executable with sandbox root
`/workspace`. The local mounted filesystem contains:

- the source and protocol directories;
- `plan.json` and `task_manifest.jsonl`;
- exactly one `training_split_<seed>.jsonl` file;
- its writable output directory; and
- the pinned Python site-packages directory.

The local mounted filesystem does not contain the repository `.git` directory,
`datasets/`, the joined evaluation artifact, the four other split artifacts,
the final result directory, or `/users`. The host network namespace remains
shared for SLURM self-authentication; therefore this gate proves local
filesystem exclusion, not network-level non-reachability. The task result
records the selected artifact hash and an opaque commitment to the held-out
artifact. The fixed training program does not open test or R4 values. The
finalizer is the first scheduled project stage that mounts those bytes, and it
remains closed until a complete accepted set authenticates all 25 checkpoints.

## Postterminal checkpoint admission

Array `7087054` must leave `squeue` before admission begins. An empty queue is
not evidence of success. The terminal review must return one logical row for
each component `7087054_0` through `7087054_24`, with state `COMPLETED` and
exit code `0:0`:

```bash
ACC3_JOB_ID=7087054
ACC3_ATTEMPT_ROOT="results/corpus_v4/accuracy_v3/jobs/job_${ACC3_JOB_ID}"
ACC3_RESUME_ROOT=results/corpus_v4/accuracy_v3/resume/round_00

squeue -h -j "$ACC3_JOB_ID"
sacct -X -n -P -j "$ACC3_JOB_ID" \
  --format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES
```

Run the resume planner from the clean detached r2 execution checkout. It is
solver-free and training-free. It validates safe-NPZ bundles and smoke
fixtures, so it performs bounded checkpoint I/O and small inference checks on
the login node.

```bash
test "$(git rev-parse HEAD)" = \
  "c0ffca0d0637e8fbba81c126c3f56f8316003a9a"
test -z "$(git status --short --untracked-files=all -- \
  code protocols requirements-proof.txt)"
test ! -e "$ACC3_RESUME_ROOT"

python3 code/experiments/proofs/plan_corpus_v4_accuracy_resume_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --expected-protocol-sha256 d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1 \
  --plan results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --expected-plan-sha256 04fab5efbc8428682fa0ea572001d95b1179b86e912b03deb4c8d5c4accbb40f \
  --task-manifest results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 e5a444204e99bc92462ac87d3b4721d5a4d33db9bd7d3b8e7d274ebe5d723b71 \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v3r2.json \
  --expected-execution-lock-sha256 8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c \
  --expected-source-git-head c0ffca0d0637e8fbba81c126c3f56f8316003a9a \
  --attempt-root "$ACC3_ATTEMPT_ROOT" \
  --out "$ACC3_RESUME_ROOT"
```

The immutable admission output is:

```text
results/corpus_v4/accuracy_v3/resume/round_00/
|-- candidate_index.json
|-- accepted_artifact_set.json
`-- pending_task_set.json
```

Require 25 candidates, 25 accepted tasks, all dispositions accepted, and zero
pending tasks before any later stage is considered:

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

Missing, corrupt, ambiguous, failed, or nonterminal tasks keep the accepted set
incomplete. Preserve `round_00`; a later retry round must use its pending set as
the allowlist and index both original and retry attempt roots into a new output
directory.

## Finalizer provenance blocker

The current `submit_finalize_corpus_v4_accuracy_v3.sh` names the base
`corpus_v4_accuracy_execution_lock_v3.json`, while array `7087054` and its
future accepted set are bound to execution lock r2. Supplying the r2 hash to
that wrapper fails the lock-file check; supplying the base-lock hash conflicts
with the accepted-set binding. The mismatch is fail-closed.

Held-out finalization therefore remains blocked even if all 25 checkpoints are
accepted. It requires a separately frozen finalizer provenance lock and
entrypoint that authenticate the immutable r2 accepted set without modifying
or relabelling the r2 training artifacts. This documentation does not
authorize a checkpoint rerun, held-out inference, or a scientific claim.

## Rebuild and validate the plan

These commands are solver-free and may run on a login node:

```bash
python3 code/experiments/proofs/plan_corpus_v4_accuracy_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --out results/corpus_v4/accuracy_v3/plan/v1 \
  --check

pytest -q \
  tests/test_plan_corpus_v4_accuracy_v3.py \
  tests/test_corpus_v4_accuracy_v3_dataset.py \
  tests/test_corpus_v4_accuracy_v3_pipeline.py \
  tests/test_corpus_v4_accuracy_v3_archive.py
```

Checkpoint training and held-out finalization are compute-node stages. The
exact submission sequence, environment variables, recovery rules, and
monitoring commands live in the
[SLURM submission playbook](../../../wiki/operations/SLURM-Submission-Playbook.md).

The scientific method is specified in
[protocol v3](../../../wiki/methods/Corpus-V4-FEM-V2-Accuracy-Protocol-v3.md).
The v2 diagnostic execution is a separate immutable namespace and supplies no
checkpoint or metric to this study.
