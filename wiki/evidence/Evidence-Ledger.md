---
title: Evidence Ledger
status: canonical execution ledger
last_updated: 2026-08-15
paper_source: false
---

# Evidence Ledger

## E-C3-GEOM-01 — Geometry-valid corpus root

| Field | Value |
|---|---|
| Finalizer job | `6818436` |
| Source array | `6818133` |
| Layout count | 1,500 |
| Unique geometry count | 1,500 |
| Source commit | `df8a113f7c78c31da578268877da7f5a493d2031` |
| Summary SHA-256 | `05f83c708bc287bcc51b04f74bb1ec72332b57bbe18107d491caa242af03d12b` |
| Layout SHA-256 | `17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b` |
| Label SHA-256 | `48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327` |

## E-C4-FEM-01 — Native backend diagnostic

| Field | Value |
|---|---|
| Array | `6832704` |
| Finalizer | `6832706` |
| Summary SHA-256 | `f0b5510cf76325f5aefd8ad599f393cacacfc745d5413b351a5fe4c553513b89` |
| Direct/AMG relative Cps difference | `2.1663128521249161e-16` |
| Refine-3 AMG residual | `6.218617941378876e-11` |

## E-C4-CONV-00 — Refine-2/refine-3 rejection

| Field | Value |
|---|---|
| Array | `6833715` |
| Finalizer | `6833716` |
| Final artifact SHA-256 | `d38b0f1f3b22d3dd2580a334f34e001aedae72707e1b298f1600d8cb68d4785b` |
| Decision | Refine-2/pad-16 rejected |

## E-C4-FEAS-01 — Refine-4 feasibility

| Layout | Job | Artifact SHA-256 | Scheduler MaxRSS | Decision |
|---:|---:|---|---:|---|
| 149 | `6834616` | `6115d234071dfd8884f5d88c575c4baf695fc911abb9980f8ba5f965360fd32b` | 86.13 GiB | Pass |
| 407 | `6837051` | `397074e8690bbff4b4b29ef7f3567b90493f45910dc438dee1c1e34290ec80e3` | 83.29 GiB | Pass |

## E-C4-CONV-01 — Frozen refine-3/refine-4 study

| Field | Value |
|---|---|
| Array | `6843340` |
| Finalizer | `6843343` |
| Scientific source commit | `53c56a8aea57727be2b62364428bf95cc49745bc` |
| Evidence commit | `1c6de1af6933827680ef6901fbd15459a9ee998f` |
| Final artifact SHA-256 | `78ee69aac46fbce3f914617b6d9cbc4ac51cc56b82f7944f34d2bd9c4172daa1` |
| Domain median / maximum | 0.189658% / 2.491566% |
| Mesh median / maximum | 8.273879% / 13.886399% |
| Scientific decision | Refine-3 rejected as mesh-converged |

The finalizer exited nonzero only after atomically writing the rejection
artifact. All nine source tasks completed with clean, stable source and passing
solver/resource gates.

## E-C4-PLAN-01 — Multi-fidelity geometry and split plan

| Field | Value |
|---|---|
| Protocol SHA-256 | `36bbda0935c3bbc7c3f61de3ac67c603430e05df65551823ad6eabed37051c4b` |
| Plan SHA-256 | `419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a` |
| Execution lock SHA-256 | `697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb` |
| Family registry SHA-256 | `adb015939c5dcc29f63e5068e843c65bacde046591f30619612a15ebd3c6589d` |
| HF selection registry SHA-256 | `675f46e1777c2f07d4774853d0fa78f89851e3abc78acd184771832ec0973da9` |
| Split registry SHA-256 | `c30e06e33a58f03336c02d04fc9081d58ac7663338afe355610cfc0fdc7aa641` |
| R3 / R4 task counts | 1,500 / 198 |
| HF families / mandatory anchors | 66 / 9 |

## E-C4-SUBMIT-00 — Rejected scheduler preflight

| Field | Value |
|---|---|
| R4 array | `6845922` |
| Source commit | `00eb8ea68ab6fd588bcf160b0229516a67fb9eaf` |
| Outcome | Ten tasks failed at the scheduler contract gate in 0–1 s; remainder canceled |
| Solver execution | None |
| Requested resources | 25 CPU, 160 GiB |
| Allocated resources | 41 CPU, 160 GiB |
| Root cause | Validator conflated requested CPU count with memory-inflated allocation |
| Scientific use | None; operational regression evidence only |

Two earlier submission attempts created no job. One omitted the required
`pgs0407` account; the other requested the invalid R3 array index range
`0-1499` on a cluster with `MaxArraySize=1001`. The corrected procedure is
maintained in the [SLURM Submission Playbook](../operations/SLURM-Submission-Playbook.md).
