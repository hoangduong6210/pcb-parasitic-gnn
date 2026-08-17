---
title: FEM R3/R4 Convergence Result
status: admitted negative result
last_updated: 2026-08-15
paper_source: true
prose_reviewed: true
evidence_id: E-C4-CONV-01
claim_ids: C-FEM-002, C-FEM-003
---

# FEM R3/R4 Convergence Result

Nine layouts were selected before the high-resolution run by crossing
trace-count strata with low, median, and high capacitance order statistics. Each
layout was recomputed at refine-3 with 12 and 16 mm domain padding and at
refine-4 with 16 mm padding. All 27 solves satisfied the solver residual and
resource contracts.

| Comparison | Median relative difference | Maximum relative difference | Decision |
|---|---:|---:|---|
| Refine-3, 12 versus 16 mm padding | 0.189658% | 2.491566% | Pass |
| Refine-3 versus refine-4 at 16 mm | 8.273879% | 13.886399% | Reject |

The domain result indicates that the refine-3 solution is insensitive to the
tested expansion from 12 to 16 mm for this subset. The refinement result exceeds
both predeclared thresholds. FEM-R3P16 is therefore not admitted as a
mesh-converged reference.

The result does not identify the continuum error of refine-4. It supports a
multi-fidelity interpretation: FEM-R3P16 is a fixed bulk numerical target and
FEM-R4P16 is a higher-resolution validation observation. Model error against the
bulk target and fidelity discrepancy must be reported separately.
