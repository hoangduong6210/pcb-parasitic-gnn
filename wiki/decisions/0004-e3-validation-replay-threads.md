---
title: Coordinate Ablation Validation Replay Threads
status: recovery execution approved; validation pending
last_updated: 2026-09-15
paper_source: false
---

# Coordinate Ablation Validation Replay Threads

## Observation

The coordinate-update study trained each arm using eight numerical threads.
Its original admission requested two threads and failed while comparing
reconstructed validation metrics with the training receipt. Diagnostic
`7326041` repeated task-zero validation for all three arms, twice at each
thread count on one compute node. Eight threads reproduced every stored metric
exactly. Two threads produced repeatable prediction differences and failed
48 metric leaves under the unchanged comparison rule. The evidence is indexed
in the [Evidence Ledger](../evidence/Evidence-Ledger.md).

## Decision

Use eight numerical threads for a separately versioned recovery execution.
Keep the original trained checkpoint bytes, training protocol, source commit,
split membership, metrics, and comparison tolerances. The recovery must invoke
the original task validator on all 25 tasks and 75 arm checkpoints, including
trained symmetry and terminal scheduler checks, before evaluating held-out
data. Task-zero success alone does not satisfy that requirement.

The recovery source and scheduler profile have their own identities. Admission,
analysis and reconstruction outputs belong in a separate recovery namespace;
the failed original admission remains preserved. The user authorized this
continuation after reviewing the diagnostic result.

## Interpretation

The observed difference is a reproducibility issue in floating-point inference
across thread counts. It does not establish predictive quality or change a
scientific result. Any new held-out result remains subject to complete archive
reconstruction and independent review. No inference-speed claim follows from
the recovery allocation.
