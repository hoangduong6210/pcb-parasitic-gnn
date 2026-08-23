# FEM-v2 bulk production workspace

This versioned namespace is reserved for fresh one-thread R3/P16 and R4/P16
capacitance solves. The checked-in `plan/` directory is an execution input. It
does not contain solver observations and does not authorize training.

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

Only `plan/` exists before submission. Solver tasks may create `attempts/` only
inside SLURM. Finalizers and admissions must preserve every failed attempt and
bind terminal scheduler accounting. An empty queue or a complete-looking file
tree is not sufficient evidence.

## Scientific boundary

Gate C authorized generation of an explicit multi-fidelity package after the
one-thread configurations proved repeatable. The finite nine-layout R3/R4
mesh comparison did not pass its 2% median and 5% maximum thresholds. These
outputs therefore remain distinct numerical fidelities and are not described
as mesh-converged, physical ground truth, or claim eligible.

Training remains closed until a separate postterminal dataset receipt verifies
exact coverage, all accepted source components, and the joint finalizer. The
dataset receipt may authorize freezing a new accuracy protocol, but its own
`training_may_start` field remains false. A later accuracy protocol, plan, and
execution-lock admission must open training explicitly. The
operating contract is documented in
[`wiki/operations/FEM-V2-Production-Pipeline.md`](../../../../../wiki/operations/FEM-V2-Production-Pipeline.md).

Infrastructure-only retries consume the hash-pinned pending set from the last
wave admission and retain the same protocol, plan, manifest, execution lock,
source commit, and resource profile. `TIMEOUT` and `OUT_OF_MEMORY` are terminal
resource outcomes, not retryable infrastructure events. Planned R3 shards open
sequentially only after the preceding postterminal admission is bound by path
and SHA-256.
