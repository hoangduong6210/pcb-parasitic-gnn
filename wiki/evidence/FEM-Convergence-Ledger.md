---
title: FEM Convergence Ledger
status: finalized
last_updated: 2026-08-15
paper_source: false
---

# FEM Convergence Ledger

The canonical result is stored at
`results/corpus_v4/refine34_convergence/final/job_6843343/results_corpus_v4_refine34_convergence.json`.
Its SHA-256 is
`78ee69aac46fbce3f914617b6d9cbc4ac51cc56b82f7944f34d2bd9c4172daa1`.

| Layout | Domain delta | Mesh delta |
|---:|---:|---:|
| 1055 | 2.491566% | 2.762837% |
| 407 | 0.013956% | 13.886399% |
| 1351 | 0.007005% | 7.664047% |
| 149 | 0.680564% | 5.270305% |
| 275 | 0.063956% | 5.799863% |
| 897 | 0.281907% | 8.273879% |
| 2 | 0.525490% | 8.491533% |
| 173 | 0.189658% | 10.107920% |
| 1400 | 0.112480% | 8.673665% |

The finalizer's `FAILED 1:0` state is the expected encoding of
`gate_pass=false`. It is not a server, memory, solver, or provenance failure.
