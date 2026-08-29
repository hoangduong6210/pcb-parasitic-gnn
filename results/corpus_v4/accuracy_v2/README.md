# Corpus V4 FEM-v2 accuracy evidence

This directory is the evidence namespace for the family-crossed graph-surrogate
study on `D-C4-FEM-D1-v2`. It currently contains no admitted model-accuracy,
latency, speed, physical-validation, or hardware-validation result.

The archive under [`../accuracy/`](../accuracy/) remains bound to the earlier
25-thread capacitance package and claim `C-ACC-001`. Its numerical values do not
transfer to this namespace.

## Closed lifecycle state

The protocol, deterministic plan, task manifest, executable source, and
admitted FEM-v2 dataset were frozen by the v2 execution lock. Array `7085613`
completed all 25 fixed-epoch checkpoint tasks. The run is retained as diagnostic
execution evidence and is not an admitted model result.

The v2 process loaded the complete joined evaluation artifact before selecting
training and validation membership. Its optimizer used the declared training
partition, and no held-out predictions or finalizer were run, but the process
boundary did not prevent pre-acceptance access to test and R4 bytes. The v2
checkpoint set is therefore closed with `claim_eligible=false` and may not be
resumed, finalized, or reused by a successor protocol. The compact diagnostic
closure is in [`diagnostics/job_7085613/`](diagnostics/job_7085613/).

| Frozen root | SHA-256 |
|---|---|
| Protocol | `938f804d7bb754528c9b7665a815a10b076cb662038738c67cd81d338daf89cc` |
| Plan | `960924bc10ca7e0199dcecb3a2e359624e1895288f0ef45f96f7848e4a82cb49` |
| Task manifest | `e896864c8ced584c3ab526cdffabf99f916734ef7a5fb4a923c706dfb15e076c` |
| Evaluation dataset | `58bbf1e2846696d904c99e7bd998566ea1033c89ea2cba23a535f5f8d0d58a2e` |
| Execution lock | `5e60a112ca077f7a32090a625ab99ea6ab8b8ab769eabee52db5043e03494535` |

## Numerical-reference boundary

The optimization target for `Cps_pF` is `cps_fem_r3_p16_t1_v2`. The sparse
`cps_fem_r4_p16_t1_v2` values are reserved for evaluation after every checkpoint
has been accepted. The three inductance targets use
`fasthenry_100khz_active_leg`. The historical capacitance column in
`datasets/corpus_v3/labels.jsonl` is not read as a model target.

The references are fixed numerical observations on a synthetic active-leg
corpus. They are not fabricated-board measurements, continuum solutions, or
claims of accuracy for arbitrary PCB routing.

## Frozen experimental design

The study crosses five family-disjoint split seeds with five initialization
seeds, producing 25 checkpoint tasks. Each split contains 46 training, 7
validation, and 13 test families. Training runs for a fixed 200 epochs;
validation is diagnostic only. Each task writes a checkpoint without opening
test or R4 values. The finalizer owns the first held-out inference and can run
only after all 25 checkpoint artifacts have passed their source, identity, and
scheduler gates.

Prediction tables will report each target separately. They will also report the
inductance passivity diagnostic

\[
|M| \leq \sqrt{L_p L_s}\,(1+10^{-9}).
\]

A prediction that violates this relation remains in the metrics. The diagnostic
is not a checkpoint acceptance rule.

## Successor boundary

Protocol v3 uses one split-scoped training artifact per split and executes each
training task in a filesystem sandbox. The sandbox exposes only source code,
the selected training-plus-validation artifact, immutable control files, and
the task output directory. The joined test/R4 artifact is not mounted. V3 has
its own plan, lock, result root, checkpoints, accepted set, finalizer, and
archive; no v2 payload is an input.

The revision index is
[`wiki/methods/Corpus-V4-FEM-V2-Accuracy-Protocol.md`](../../../wiki/methods/Corpus-V4-FEM-V2-Accuracy-Protocol.md),
and the active evidence namespace is [`../accuracy_v3/`](../accuracy_v3/).
