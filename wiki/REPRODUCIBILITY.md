---
title: Reproducibility
status: active runbook
last_updated: 2026-08-29
paper_source: false
---

# Reproducibility

Exact OSC account, array sharding, immutable-worktree, monitoring, resume, and
failure-recovery commands are maintained in the operational
[SLURM Submission Playbook](operations/SLURM-Submission-Playbook.md).

Heavy field solves and model training are SLURM-only. Login nodes may be used for
protocol validation, hashing, unit tests, final artifact inspection, and document
building.

Every admitted numerical result must resolve to:

- a frozen protocol and configuration identifier;
- immutable geometry, selection, and split manifests;
- a clean source commit and initial/final source hash maps;
- the exact executed batch-script hash;
- Python, package, scientific-thread, solver, account, partition, request, and
  allocation records; private hostnames are deliberately excluded from public
  artifacts;
- atomic task artifacts with numerical and resource gates;
- an exact finalizer artifact set with no missing, duplicate, or extra records;
- SHA-256 closure over normalized outputs.

`requirements-proof.txt` pins direct dependency versions, not wheel hashes,
transitive packages, a BLAS implementation, or a container digest. The accuracy
pipeline additionally records its exact Python, NumPy, and PyTorch distribution
versions and PyTorch build. Its guarantee is protocol-and-artifact
reproducibility from identical inputs, settings, source, and declared runtime
contract; it does not promise bitwise environment reconstruction, equal wall
time, or last-bit equality across CPU and BLAS implementations.

## Finalized capacitance closure

The tracked closure preserves the canonical corpus-v3 source, all 1,698
accepted R3/R4 task records, dense accepted sets, final summary, and long-form
observation table. A clean clone can therefore verify every accepted artifact
path and hash without rerunning a solver. See the
[closure README](../results/corpus_v4/cps_multifidelity/README.md).

Recomputing the numerical observations still requires the recorded dependency
and runtime contract plus the declared SLURM allocations. The finalizer itself is SLURM-only and
replays against [`datasets/corpus_v3`](../datasets/corpus_v3/README.md).

The derived R3/R4 audit is independently hash-closed. The scientific R3 and R4
outcomes were produced by the recorded SLURM solver jobs. The lightweight
clean-clone verifier does not rerun those solvers; it checks the upstream
1,698-record archive, recomputes all 198 matched-pair and 66-family tables,
byte-compares the derived outputs, validates source and scheduler receipts, and
rejects extra or untracked artifacts:

```bash
python3 code/quality/verify_corpus_v4_discrepancy_archive.py --require-git-tracked
```

## Finalized deterministic FEM-v2 dataset closure

The one-thread FEM-v2 package is a separate closure from the archived
25-thread package above. Its tracked production namespace preserves the 1,500
R3 task results, 198 R4 task results, wave accepted/pending/terminal-negative
sets, postterminal wave admissions, joint observation table, final manifest,
and postterminal dataset admission:

```text
results/corpus_v4/cps_reference_v2/production/v1/
```

The joint source-set SHA-256 is
`f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b`.
Within finalizer job `7084776`, the long-form observation table, summary, final
manifest, and postterminal admission have SHA-256 values
`83a771bf318c0660731c6e5d1e5e91a6b15642e178b8172b2b46dedb656a1784`,
`07ba65109c30469df417c349ce6a25b15d7743c7d14ade3cd858e31ed58a2c43`,
`6ff8d39ecc45fd2bbea9271235f221a7b18006389a45cbbda4b4f2adf450e57e`,
and
`b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed`,
respectively. The admission authenticates finalizer `7084776` as
`COMPLETED/0:0` and records 1,500 geometries, 1,500 R3 observations, 198 R4
observations, and 1,698 total observations.

The tracked `ARCHIVE_MANIFEST.json` has SHA-256
`89b2e235ff5d1aaa06ab589a95578f7a3ef129d60f2386494ea2d1686de6dbbc`.
A clean clone verifies the frozen roots, six wave packages, 1,698 accepted
task-result hashes, joint dataset receipt, exact membership, and absence of
unindexed closure files without running a solver:

```bash
python3 code/quality/verify_corpus_v4_fem_v2_production_archive.py \
  --require-git-tracked
```

This is a dataset-generation closure, not a model closure. Its exact decisions
are `dataset_generation_admitted=true`,
`accuracy_protocol_may_be_frozen=true`, and `training_may_start=false`; it also
retains `claim_eligible=false` and `speed_claim_eligible=false`. Replaying the
hash closure does not establish mesh convergence, physical accuracy, surrogate
accuracy, or speed.

## FEM-v2 accuracy revision boundary

Accuracy protocol v2 completed its 25 checkpoint tasks but is closed as a
diagnostic execution. Its loader materialized the complete R3/R4 join before
training membership was selected. The optimizer used the declared training
partition and no held-out inference ran, but result flags cannot establish a
byte boundary that the process did not enforce. The compact closure is indexed
in the [accuracy-v2 evidence README](../results/corpus_v4/accuracy_v2/README.md).

Protocol v3 is the active successor. Its deterministic planner produces one
train-plus-validation artifact per split and a separate held-out artifact. A
hash-pinned Bubblewrap sandbox mounts exactly one training artifact and does not
mount the held-out join, other splits, repository data, `.git`, or host user
roots. A singleton compute-node preflight must validate that namespace and
construct all graphs before the training array is authorized.

The v3 lock authenticates the upstream archive and dataset admission, all five
training artifacts, the opaque held-out commitment, source files, sandbox
executable, fixed family splits, and complete 5 by 5 seed grid. It retains
`held_out_inference_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. Exact roots are indexed in the
[accuracy-v3 evidence README](../results/corpus_v4/accuracy_v3/README.md) and
[versioned method](methods/Corpus-V4-FEM-V2-Accuracy-Protocol-v3.md).

## Finalized pre-FEM-v2 accuracy closure

The tracked accuracy closure preserves all 25 safe-NPZ checkpoints, training
curves, validation-only smoke fixtures, terminal scheduler receipts, held-out
predictions, metric matrices, and the matched R3/R4 evaluation view. A clean
clone can authenticate the archive and replay its metrics without querying live
scheduler accounting, retraining, or rerunning a field solver. The exact
hash-pinned command and expected output are maintained in the
[accuracy evidence README](../results/corpus_v4/accuracy/README.md#clean-clone-verification).

Recomputing the checkpoints still requires the declared runtime contract and
SLURM allocation. The tracked checkpoints support verification of this frozen
corpus and graph contract; they are not a general inference package for
arbitrary routed PCB layouts.

## Heavy-stage resource contracts

| Stage | Planned allocation | Concurrency |
|---|---|---:|
| FEM-R3P16 bulk, 1,500 layouts — completed | 25 CPU, 48 GiB, 2 h per layout | 8 |
| FEM-R4P16 validation, 198 layouts — completed | 25 CPU, 160 GiB, 3 h per layout | 2 |
| R3/R4 selected-registry audit — completed | 2 CPU, 8 GiB, 5 min | 1 |
| Multi-seed training — completed | 8 CPU requested, 48 GiB, 4 h per split/init model | 5 |
| Accuracy finalizer — completed | 2 CPU requested, 16 GiB, 30 min | 1 |
| FEM-v2 accuracy-v2 checkpoint training — diagnostic execution closed | 8 CPU requested, 48 GiB, 4 h per split/init model | 5 |
| FEM-v2 accuracy-v3 sandbox preflight — pending | 8 CPU requested, 48 GiB, 4 h cap; exits before optimizer work | 1 |
| FEM-v2 accuracy-v3 checkpoint training — blocked until preflight passes | 8 CPU requested, 48 GiB, 4 h per split/init model | 5 |
| FEM-v2 accuracy finalizer — blocked until all 25 checkpoints are accepted | 2 CPU requested, 16 GiB, 30 min | 1 |
| Paired-latency preflight — executed and rejected; 0 of 3 accepted; excluded from statistics | 25 CPU requested, 48 GiB, 2 h per layout | 1 |
| Paired-latency full panel — blocked by negative repeatability admission | 25 CPU requested, 48 GiB, 2 h per layout | 8 |
| Paired-latency finalizer — blocked | 2 CPU requested, 8 GiB, 20 min | 1 |
| FEM repeatability source array — completed; 15 elements with two sequential FEM arms each | 25 CPU requested, 48 GiB, 2 h per element; 1,800 s cap per arm | 3 |
| FEM repeatability finalizer — completed | 2 CPU requested, 8 GiB, 30 min | 1 |
| FEM repeatability postterminal admission — completed negative, solver-free | No compute allocation; live finalizer `sacct` was authenticated when the receipt was minted | Not applicable |
| Deterministic FEM-v2 R3/P16, 1,500 layouts — completed | 1 CPU requested, 48 GiB, 2 h per layout | 8 |
| Deterministic FEM-v2 R4/P16, 198 layouts — completed | 1 CPU requested, 160 GiB, 3 h per layout | 2 |
| Deterministic FEM-v2 dataset finalizer — completed | 2 CPU requested, 16 GiB, 30 min; 5 CPU and 16 GiB allocated | 1 |
| Deterministic FEM-v2 postterminal dataset admission — completed positive, solver-free | Live finalizer accounting authenticated; no solver executed | Not applicable |

Resource caps are part of the frozen protocol. A cap failure is an infeasibility
result and does not authorize changing limits after inspecting outcomes.

The frozen task manifests contain dense indices 0–1499 for FEM-R3P16 and
0–197 for FEM-R4P16. Each array element recomputes the protocol, plan, manifest,
geometry, source, environment, executed-batch, system, residual, and resource
gates before its attempt is accepted. A retry writes a new job-scoped attempt;
it cannot overwrite an earlier attempt.

The accuracy plan adds 25 row-major split/init tasks. Each task trains one fixed
200-epoch model and saves a strict NumPy checkpoint without a test prediction.
Validation is diagnostic only, R4 is evaluation-only, and task 12 was
designated for later latency measurement before outcomes were observed. The
accepted set requires post-run task accounting; the SLURM finalizer owns the
first held-out inference; and the post-run verifier freezes finalizer
accounting for later scheduler-independent clean-clone checks. The complete
contract is specified in
[Corpus V4 Accuracy Protocol](methods/Corpus-V4-Accuracy-Protocol.md).

That accuracy closure remains bound to the archived 25-thread capacitance
package. It is not an accuracy closure for `D-C4-FEM-D1-v2`. The latter requires
a newly versioned evaluation join, protocol, plan, execution lock, model jobs,
finalizer, and postterminal admission before any model result is reported.
