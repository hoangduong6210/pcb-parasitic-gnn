---
title: Runtime Benchmark Protocol
status: canonical timing policy
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
---

# Runtime Benchmark Protocol

Runtime claims are valid only when the compared outputs and timing boundaries
match. The project distinguishes three GNN boundaries:

| Boundary | Included work |
|---|---|
| Pre-collated batch throughput | Forward execution of an already batched graph bank |
| Prepared single forward | One already constructed graph through the model |
| Raw-layout end to end | Layout parsing, validation, graph construction, collation, and inference |

The reference workflow must also name its output scope. The four-target workflow
combines FastHenry for \(L_p\), \(L_s\), and \(M\) with electrostatic FEM for
\(C_{ps}\). A ratio against this combination cannot be shortened to “faster than
3-D solvers.” It says nothing about a user who needs only inductance or only
capacitance.

The preferred estimand is the median of per-design paired ratios on the same
designs. A ratio of two independent medians is a different quantity. A design
bootstrap interval covers resampling of the evaluated layouts; it does not cover
node variation, system load, software changes, or model retraining.

Hardware, CPU allocation, thread settings, device, batch size, warm-up, repeat
count, timer implementation, source commit, checkpoint, and software versions
are part of every accepted runtime record. Historical timing boundaries and
their exact interpretation are listed in the [Historical Claim Ledger](../claims/Historical-Claim-Ledger.md).
