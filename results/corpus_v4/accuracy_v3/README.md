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
| Checkpoint training | Array `7087054` completed; 25 of 25 tasks at `COMPLETED/0:0` |
| Accepted checkpoint set | Round 01 admitted 25 of 25 immutable candidates |
| Held-out finalizer | Provenance lock frozen; SLURM execution not started |
| Scientific claim | Closed |

The sandbox preflight is intentionally solver-free and optimizer-free. Job
`7087033` ran on a compute node, loaded the selected split artifact, constructed
all 1,209 graphs, checked the mounted filesystem boundary, and exited without
starting training. Its receipt records `sandbox_boundary_passed=true`,
`heldout_bytes_opened=false`, and `training_started=false`; terminal accounting
records `COMPLETED/0:0`. This admission opens checkpoint training only.

The frozen checkpoint grid ran as array `7087054` from source commit
`c0ffca0d0637e8fbba81c126c3f56f8316003a9a`. All 25 logical components
completed with exit code `0:0`. Postterminal round 01 admitted every immutable
candidate and left zero pending tasks. Held-out inference has not started, and
every scientific claim remains closed until finalization and archive admission
pass.

## Frozen roots

| Root | Identity |
|---|---|
| Active source commit | `c0ffca0d0637e8fbba81c126c3f56f8316003a9a` |
| Protocol | `d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1` |
| Plan | `04fab5efbc8428682fa0ea572001d95b1179b86e912b03deb4c8d5c4accbb40f` |
| Task manifest | `e5a444204e99bc92462ac87d3b4721d5a4d33db9bd7d3b8e7d274ebe5d723b71` |
| Held-out evaluation commitment | `ff02a28aa41f2526bea1b087e1222479d743f5eb766d13e4dfa48f42cc791046` |
| Active execution lock r2 | `8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c` |
| Accepted artifact set, round 01 | `291a76231ef348d150fcec0f1cb70031537f1db5530ff0813365ed2932e326fe` |
| Finalizer execution lock v1 | `cdb53640f9d9c206b37651e28a04781a19d5dda81d520cf50b77c628468cadf3` |

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
incomplete. Preserve every admission round and never overwrite its inventory.

Round 00 preserved a fail-closed control-plane observation: the planner could
not reach `slurmdbd`, so all 25 candidates received
`SCHEDULER_NOT_COMPLETED`. Its candidate index nevertheless matches round 01
byte for byte. Once accounting access returned, the same original attempt root
was evaluated into round 01 without retraining or changing any checkpoint.
Round 01 records 25 accepted candidates, zero pending tasks, and zero rejected
candidates. The admission artifacts have these hashes:

| Round | Artifact | SHA-256 |
|---:|---|---|
| 00 | Candidate index | `e357c50e9cce1d0d70bf6060754e54e2829566eb4550980873d56405ce31709a` |
| 00 | Accepted set | `bf53ad8ab326ff2317a446fb39cafc7a0a1c08c329195d7a0d6fc4d211349bd6` |
| 00 | Pending set | `a56d38d33da765ce7b0f88e86c3ba3d3a28706453c29c675855ac050fe3db5a7` |
| 01 | Candidate index | `e357c50e9cce1d0d70bf6060754e54e2829566eb4550980873d56405ce31709a` |
| 01 | Accepted set | `291a76231ef348d150fcec0f1cb70031537f1db5530ff0813365ed2932e326fe` |
| 01 | Pending set | `e63aa06ce5247a1a58de1e4dd2a40163aac597484ae1e120f12d782aafb2190e` |

## Finalizer provenance gate

The finalizer now enforces two independent trust roots. The historical
training lock authenticates the unchanged r2 checkpoints and source commit,
while a separate finalizer lock authenticates the accepted set, finalizer
source closure, and finalizer execution commit. This preserves the original
training provenance without modifying or relabelling any r2 artifact.

The production finalizer lock is now frozen at
`protocols/corpus_v4_accuracy_finalizer_execution_lock_v1.json`, SHA-256
`cdb53640f9d9c206b37651e28a04781a19d5dda81d520cf50b77c628468cadf3`.
It binds the round 01 accepted set and historical r2 training provenance.
Held-out finalization remains blocked until this complete boundary is reviewed,
committed, and executed from a clean checkout through SLURM. Checkpoint
completion or accepted-set admission does not authorize a scientific claim.

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
