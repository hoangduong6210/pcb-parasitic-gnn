# FEM-v2 bulk production workspace

This versioned namespace contains the frozen one-thread R3/P16 and R4/P16
capacitance production closure. The run is complete and its postterminal
dataset admission is tracked. The package authorizes freezing a separate
accuracy protocol; it does not authorize training by itself.

## Frozen scope

| Manifest | Fidelity | Tasks | Dispatch shards |
|---|---|---:|---|
| `plan/r3_manifest.jsonl` | `cps_fem_r3_p16_t1_v2` | 1,500 | 400, 400, 400, 300 |
| `plan/r4_manifest.jsonl` | `cps_fem_r4_p16_t1_v2` | 198 | 198 |

The R3 manifest covers the verified geometry corpus in dense layout order. The
R4 manifest uses the frozen 198-layout registry without reselection. All task
rows bind the new protocol and a fidelity-specific solver contract.

## Directory lifecycle

```text
plan/                         tracked execution inputs
attempts/r3/job_*/task_*/     immutable R3 task attempts
attempts/r4/job_*/task_*/     immutable R4 task attempts
waves/                        cumulative wave finalization and admission
dataset/                      joint 1,500 plus 198 package and admission
```

The tracked closure retains the 1,698 accepted `result.json` files, all six
wave finalizer/admission packages, and the joint dataset package. Start files,
task-local manifest copies, bulk scheduler logs, and the rejected duplicate
attempts are operational history rather than scientific inputs and are not
part of this Git archive. Their job identities remain in the final receipts
and living Evidence Ledger. An empty queue or a complete-looking file tree is
not sufficient evidence.

## Scientific boundary

Gate C authorized generation of an explicit multi-fidelity package after the
one-thread configurations proved repeatable. The finite nine-layout R3/R4
mesh comparison did not pass its 2% median and 5% maximum thresholds. These
outputs therefore remain distinct numerical fidelities and are not described
as mesh-converged, physical ground truth, or claim eligible.

The postterminal dataset receipt verifies exact coverage, all accepted source
components, and the joint finalizer. It authorizes freezing a new accuracy
protocol, but its own `training_may_start` field remains false. A later accuracy
protocol, plan, execution lock, and downstream admission must open training
explicitly. The
operating contract is documented in
[`wiki/operations/FEM-V2-Production-Pipeline.md`](../../../../../wiki/operations/FEM-V2-Production-Pipeline.md).

Infrastructure-only retries consume the hash-pinned pending set from the last
wave admission and retain the same protocol, plan, manifest, execution lock,
source commit, and resource profile. `TIMEOUT` and `OUT_OF_MEMORY` are terminal
resource outcomes, not retryable infrastructure events. Planned R3 shards open
sequentially only after the preceding postterminal admission is bound by path
and SHA-256.

## Final closure

| Artifact | Result |
|---|---|
| R3 final admission | 1,500 accepted, 0 pending, 0 terminal-negative; SHA-256 `98cb1dc5950584fa05e71ac162c231b3e68f8c17e76de9053260ddbcab50a2bb` |
| R4 final admission | 198 accepted, 0 pending, 0 terminal-negative; SHA-256 `b5a02396de010c7534d61c251f54e4f7a79335a0fa775663a29135a6092c9bc6` |
| Dataset observation table | 1,698 rows; SHA-256 `83a771bf318c0660731c6e5d1e5e91a6b15642e178b8172b2b46dedb656a1784` |
| Dataset admission | `dataset_generation_admitted=true`, `accuracy_protocol_may_be_frozen=true`, `training_may_start=false`; SHA-256 `b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed` |
| Archive manifest | SHA-256 `89b2e235ff5d1aaa06ab589a95578f7a3ef129d60f2386494ea2d1686de6dbbc` |

The observation table joins all layouts by `(layout_id, geometry_sha256)`.
R3 is the dense training-candidate fidelity; the 198 R4 values remain a
higher-resolution evaluation comparator. Neither fidelity is represented as
continuum truth or independently validated physical ground truth.

## Clean-clone verification

The canonical audit reads hashes and receipts only; it does not run a solver:

```bash
python3 code/quality/verify_corpus_v4_fem_v2_production_archive.py \
  --require-git-tracked
```

It verifies the frozen protocol, plan, execution lock, all wave packages, the
dataset receipt, exact R3/R4 membership, every accepted task-result hash, and
the absence of unindexed files inside the tracked closure.

## Public provenance boundary

Accepted results preserve scheduler-generated account, numeric user/group,
node, job, and absolute execution-path fields because those bytes are part of
the admitted artifact hashes. They contain no access token, password, private
key, or redistributed solver binary. This machine provenance is public research
evidence under `results/`; it is excluded from paper packages and every wiki
page marked `paper_source: true`. Altering or redacting those JSON files in
place would invalidate the final accepted-set and observation-table chain.
