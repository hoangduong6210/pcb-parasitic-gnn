---
title: Corpus V4 Accuracy Protocol Revision Boundary
status: canonical decision
last_updated: 2026-08-29
paper_source: false
---

# Corpus V4 Accuracy Protocol Revision Boundary

## Decision

The Corpus V4 accuracy v2 execution is closed as a checkpoint-only diagnostic
run. Its 25 training tasks and terminal scheduler records are retained as
provenance. No held-out prediction, model-selection decision, accuracy result,
or speed result may be derived from this closed execution. The reason is an
input-access boundary, not a failed optimizer or a failed scheduler run: the
v2 process could read held-out bytes before checkpoint acceptance.

A successor accuracy study must use a new protocol version, plan, execution
lock, task manifest, result root, and claim-admission record. V2 checkpoints
must not be imported, resumed, relabeled, or combined with successor artifacts.
This boundary keeps each result attached to one prospectively frozen contract.

## Closed v2 evidence

Array `7085613` contains 25 logical tasks. Every task reached terminal state
`COMPLETED` with exit code `0:0`. The task artifact validator accepted the
complete byte closure for all 25 checkpoint bundles. Each task records 200
epochs, a fixed final epoch, validation used only for diagnostics, no test
predictions, and no held-out inference. No held-out finalizer was run.

Those task fields do not prove split isolation. Before training, the v2 loader
materialized the full 1,500-layout R3 input and the full 198-layout R4 input.
The process therefore had byte-level access to held-out data even though it
did not emit test predictions or held-out metrics. Statements in the task
records that test or R4 data were not used for normalization, optimization, or
acceptance are retained as recorded execution metadata, but they are not
accepted as evidence that held-out bytes were unavailable.

The compact closure is stored under
`results/corpus_v4/accuracy_v2/diagnostics/job_7085613`:

- `terminal_accounting.json` records the exact logical SLURM rows;
- `artifact_index.json` binds all 25 task manifests and their 125 files by
  SHA-256 without copying checkpoint payloads; and
- `DIAGNOSTIC_CLOSURE.json` binds both ledgers and states the downstream gates.

The frozen source commit is
`5a1026985a06e8a120b52e28e4cbc6d17d939c0f`. The v2 protocol, execution lock,
plan, task manifest, and joined evaluation dataset remain independently bound
by SHA-256 in the machine-readable closure.

## Claim boundary

Terminal completion proves that the checkpoint tasks ran under the recorded
resources and exited successfully. Artifact validation proves that the
checkpoint bundles satisfy the v2 byte, identity, runtime, learning-curve, and
smoke-test contracts. Neither fact is an accuracy measurement.

Artifact closure also does not repair the input-access boundary. V2 did not
enforce split-scoped byte visibility, so its checkpoints cannot establish a
prospective held-out protocol even in the absence of a finalizer or emitted
test predictions.

The closure therefore keeps `claim_eligible`, `model_result_eligible`,
`scientific_result_eligible`, and `speed_claim_eligible` false. It also keeps
`held_out_inference_may_start` false. The v2 execution is evidence about the
diagnostic training run only.

## Successor requirements

Before a successor execution is submitted, its changed scientific contract
must be explicit and immutable. At minimum, the successor must freeze:

- model and optimization semantics;
- split membership and every dataset hash;
- split-scoped input construction and the worker's readable-path allowlist;
- normalization and model-selection boundaries;
- the single held-out evaluation rule;
- task mapping, resource requests, runtime identity, and source commit; and
- fail-closed admission rules for missing, ambiguous, nonterminal, or mixed
  artifacts.

V3 changes the execution boundary rather than only changing result metadata.
Its planner produces split-scoped training inputs, and its training worker runs
inside a sandbox that exposes training and validation bytes only. Held-out R3
and R4 inputs are unavailable to that worker. A separately admitted one-shot
finalizer may receive the held-out input only after the full checkpoint set has
passed artifact and terminal-accounting admission. R4 access remains a
separate, explicitly gated evaluation path.

The successor starts from training under its own lock. It cannot inherit
scientific eligibility from v2. A later result may enter the claim registry
only after its own terminal accounting, artifact closure, held-out evaluation,
and archive verification are complete.

## Consequences

The v2 checkpoint payloads do not need to be copied into the repository. Their
task manifests provide transitive SHA-256 bindings, while the compact index and
accounting ledger preserve the execution identity. This avoids publishing
large diagnostic weights and prevents the closed run from being mistaken for
a reusable pretrained package.

This page is an internal protocol decision and is not a paper source. It does
not report model performance and does not change any existing paper claim.
