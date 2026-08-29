---
title: FEM V2 Production Pipeline
status: completed dataset-generation contract
last_updated: 2026-08-29
paper_source: false
---

# FEM V2 Production Pipeline

This page explains why the one-thread capacitance dataset exists, how its
inputs were qualified, and which receipts are required before a model may use
the new values. It is an operating record, not a paper result.

## Why a new numerical version was needed

The earlier Corpus V4 package was useful for testing the complete graph,
solver, training, and timing workflow. Its capacitance meshes were created
with a 25-thread Gmsh configuration. A later paired-latency preflight rebuilt
fresh meshes and found differences larger than its frozen comparison
tolerance. The important issue was numerical repeatability across independent
mesh construction, not whether an existing JSON file could be read twice.

A controlled diagnostic then ran two configurations on the same fixed panel.
The 25-thread arm did not reproduce one mesh identity per layout. The
one-thread arm did. That observation selected a candidate configuration; it
did not, by itself, authorize a replacement dataset.

## The three qualification gates

The candidate was evaluated through three sequential gates. Each source array
was finalized while its accounting was visible and was admitted again after
the finalizer became terminal.

1. Gate A created five fresh R3/P16 meshes for each of nine frozen layouts.
   All 45 tasks completed. The largest within-layout relative capacitance
   spread was `1.1743017900469024e-14`, below the frozen `1e-4` limit.
2. Gate B compared the admitted R3/P16 result with R3/P20 on the same nine
   layouts. The domain delta had median `0.20585933141613427%` and maximum
   `1.0860887365856715%`, below the frozen 2% and 5% limits.
3. Gate C tested R4/P16 repeatability and compared R3/P16 with R4/P16. The
   three repeated R4 sentinels were stable, but the nine-layout mesh delta had
   median `8.004837428851205%` and maximum `13.929354258624992%`. It therefore
   failed the predeclared mesh-sensitivity thresholds.

Gate C has two different conclusions, and both must be retained. The run is a
valid, repeatable qualification result, so an explicitly multi-fidelity
package may be generated. Its mesh comparison is negative, so neither R3 nor
R4 may be called mesh-converged, continuum truth, or physical ground truth.

## Frozen bulk scope

The bulk run creates only fresh observations. None of the qualification values
or old 25-thread values are copied into the new namespace.

| Fidelity | Coverage | Numerical setting | Role |
|---|---:|---|---|
| `cps_fem_r3_p16_t1_v2` | 1,500 | refine 3, padding 16 mm, one Gmsh thread | Dense low-fidelity target |
| `cps_fem_r4_p16_t1_v2` | 198 | refine 4, padding 16 mm, one Gmsh thread | Frozen higher-fidelity comparison set |

R3 task index `0..1499` maps to the same dense layout identifier. R4 task
index `0..197` maps to the pre-existing 198-layout registry sorted by layout
identifier. That registry contains three layouts from each of 66 swap-closed
turn-count families. Membership is authenticated by byte hash; it is not
reselected after seeing new results.

The family registry and the five split registries also remain byte-identical.
For any split, all fidelities of one geometry share its partition. The full
198-layout R4 set is not described as one global holdout; each split evaluates
the R4 members that belong to that split's held-out families.

## Execution closure

Every task authenticates three roots before solving:

```text
protocol
  + plan, manifest, and dispatch hash
  + execution lock over computational source bytes
  + Gate B and Gate C admission hashes
  + clean pushed Git commit
```

The task also checks its exact geometry hash, the live scheduler record, the
requested and allocated resources, package versions, parent thread variables,
and the Gmsh thread count observed inside the child worker. The result is
written atomically to an immutable job and task directory. A failed task keeps
its diagnostics and returns a nonzero scheduler exit code.

## Submission waves

R4 is one 198-element array with concurrency two. R3 uses four arrays of 400,
400, 400, and 300 elements with concurrency eight. The project keeps a
50-element reserve below the scheduler's 1,000 submitted-element limit.

The first R3 wave and R4 may coexist. Later R3 waves wait for the previous R3
wave's postterminal receipt. Each source array has an `afterany` finalizer so
that cancelled, timed-out, or failed tasks are recorded instead of making the
finalizer disappear through an `afterok` dependency.

The login-node controller is allowed to inspect Git, submit jobs, poll SLURM,
hash artifacts, and write status. It never imports or calls a FEM solver. All
mesh construction and field solving occurs inside the requested SLURM array.
It submits only the canonical wrappers whose bytes are named in the execution
lock, writes only the canonical controller-status path, and exports an explicit
environment list instead of inheriting the login shell.

The completed execution used R3 source/finalizer pairs
`6963561/6963562`, `7004761/7004762`, `7022705/7022706`, and
`7057802/7057803`, followed by the admission-pinned pending-set retry
`7064645/7064646`. R4 used source/finalizer `6963559/6963560`.
Postterminal admission closed R3 at 1,500 accepted and R4 at 198 accepted, with
zero pending and zero terminal-negative tasks in both final states.

## Failure and retry rules

An infrastructure or nonterminal failure may be retried only for the same
canonical task under the same protocol, plan, manifest, dispatch ancestry,
execution lock, and source commit. A genuine numerical or resource failure is
a negative outcome and cannot be hidden by a later success. Two valid terminal
attempts for one canonical task are ambiguous and fail closed.

External `TIMEOUT` and `OUT_OF_MEMORY` states remain terminal negative even if
SLURM stopped the process after `started.json` but before the complete task
manifest was written. A successful scheduler component with no complete task
artifact is an integrity failure. A retry dispatch must be the exact pending
set named by the preceding admission; a free-form task list is rejected.

The wave receipt carries a cumulative accepted set and a hash-pinned pending
set. It also carries the cumulative source-attempt inventory, including a
numerically valid artifact whose scheduler component did not finish
successfully; this prevents a later wave from silently dropping attempt
lineage. A directory scan, an empty queue, a task JSON file, or a preterminal
finalizer output is not an admission.

## When training may begin

Dataset generation remained open until a joint dataset admission proved all of
the following:

1. R3 has exactly 1,500 accepted terminal tasks and no pending task.
2. R4 has exactly the frozen 198 accepted terminal tasks and no pending task.
3. Every accepted task maps to one `COMPLETED/0:0` SLURM component with the
   frozen resource contract.
4. The dataset finalizer produces exactly 1,698 long-form observations with
   separate fidelity identifiers.
5. A solver-free postterminal admission verifies the finalizer itself as
   `COMPLETED/0:0` and replays the full hash closure.

All five conditions are now satisfied. Dataset finalizer `7084776` completed
`0:0` and produced 1,698 observations under dataset source-set SHA-256
`f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b`.
The solver-free postterminal admission has SHA-256
`b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed`.

That final receipt sets `dataset_generation_admitted=true` and
`accuracy_protocol_may_be_frozen=true` while retaining
`training_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. It authorizes creation of a new accuracy
protocol, plan, and execution lock; only their own admission may open model
training. It does not transfer the archived 25-thread accuracy, latency, or
speed claims. Those require fresh model training and evaluation jobs under
their own frozen contracts.

## Frozen planning cost

Qualification timing projects about 27.3 active hours for R3 at concurrency
eight and 94.1 active hours for R4 at concurrency two. The R4 path is therefore
the critical path at roughly four days before queueing and retries. These are
planning values retained from before execution, not measured summaries of the
completed bulk run.

See [SLURM Resource Plan](SLURM-Resource-Plan.md) for requested resources and
[Live Execution](../status/Live-Execution.md) for the current scheduler state.
