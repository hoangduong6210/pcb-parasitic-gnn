---
title: Corpus V4 FEM-v2 Accuracy Protocol v2
status: superseded; diagnostic execution closed
last_updated: 2026-08-29
paper_source: false
---

# Corpus V4 FEM-v2 Accuracy Protocol v2

## Scope and terminal state

V2 crossed split seeds 40 through 44 with initialization seeds 40 through 44.
All 25 tasks completed 200 fixed epochs and wrote checkpoint bundles. No
held-out predictions or finalizer were run. The terminal and artifact receipts
are preserved as diagnostic execution evidence only.

## Byte-access boundary

The v2 runner loaded the complete joined dataset before selecting training and
validation membership. That join contained all 1,500 R3 references and all 198
R4 observations. The optimizer was indexed by the declared training split, but
the process namespace had already materialized held-out bytes. Result flags
that report no held-out optimization or prediction do not prove process-level
isolation.

This distinction closes the scientific lifecycle:

- checkpoint execution completed;
- held-out inference did not run;
- no accuracy, latency, speed, or physical-validation result is admitted;
- v2 checkpoints cannot be finalized, resumed, or warm-started; and
- no v2 artifact can enter the v3 accepted set.

The machine-readable closure is
[`results/corpus_v4/accuracy_v2/diagnostics/job_7085613/`](../../results/corpus_v4/accuracy_v2/diagnostics/job_7085613/).
Its purpose is provenance, not model evaluation.

## Frozen identities

| Root | Identity |
|---|---|
| Source commit | `5a1026985a06e8a120b52e28e4cbc6d17d939c0f` |
| Protocol SHA-256 | `938f804d7bb754528c9b7665a815a10b076cb662038738c67cd81d338daf89cc` |
| Plan SHA-256 | `960924bc10ca7e0199dcecb3a2e359624e1895288f0ef45f96f7848e4a82cb49` |
| Task manifest SHA-256 | `e896864c8ced584c3ab526cdffabf99f916734ef7a5fb4a923c706dfb15e076c` |
| Evaluation join SHA-256 | `58bbf1e2846696d904c99e7bd998566ea1033c89ea2cba23a535f5f8d0d58a2e` |
| Execution lock SHA-256 | `5e60a112ca077f7a32090a625ab99ea6ab8b8ab769eabee52db5043e03494535` |

V2 is not a source for manuscript metrics.
