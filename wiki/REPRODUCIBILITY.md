---
title: Reproducibility
status: active runbook
last_updated: 2026-08-19
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

## Finalized accuracy closure

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
| Paired-latency preflight — pending, excluded from statistics | 25 CPU requested, 48 GiB, 2 h per layout | 1 |
| Paired-latency full panel — pending | 25 CPU requested, 48 GiB, 2 h per layout | 8 |
| Paired-latency finalizer — pending | 2 CPU requested, 8 GiB, 20 min | 1 |

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
