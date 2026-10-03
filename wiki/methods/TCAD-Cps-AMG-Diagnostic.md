---
title: TCAD Same-Matrix AMG Diagnostic
status: RUNNING; frozen diagnostic contract; terminal outcome pending
last_updated: 2026-10-02
paper_source: false
---

# TCAD Same-Matrix AMG Diagnostic

## Decision and question

The [compact-support attempt](../evidence/TCAD-Cps-Support-Recovery.md) stopped
at AMG setup, not at mesh size, wall time or memory. Keep that rejection and
its 1.25 complexity cap. Test one predeclared alternative: disable smoothing
of the tentative prolongator by passing `smooth=None` to the pinned PyAMG
5.3.0 aggregation constructor. Retain constant near-nullspace input,
`symmetry="symmetric"`, `max_coarse=50`, all other pinned defaults, CG tolerance
and iteration cap. This changes the preconditioner, not the assembled system.

PyAMG documents `None` as a prolongation-smoothing option; the installed
5.3.0 source sets the prolongator to its tentative value on that branch.
See the [official API](https://pyamg.readthedocs.io/en/latest/generated/pyamg.aggregation.html#pyamg.aggregation.smoothed_aggregation_solver)
and [versioned implementation](https://github.com/pyamg/pyamg/blob/v5.3.0/pyamg/aggregation/aggregation.py).
A smaller hierarchy is a hypothesis, not an observed improvement. Convergence
may worsen, so no candidate grid, relaxed cap or fallback is authorized.

## Fixed diagnostic

The [machine protocol](../../protocols/tcad_cps_amg_diagnostic_v1.json) runs a
toy check before layout 597 local0, each in a fresh process with seed zero.
Reuse the frozen mesher, geometry, sizing callback and physical assembly
recipe; verify exact mesh counts and CSR-system hash against the earlier
attempt before constructing the new hierarchy. A mismatch stops the worker.
This additive diagnostic duplicates the small assembly recipe without changing
or monkeypatching the frozen solver; hash equality checks the actual result.

Require complexity at most 1.25, residual at most 1e-9, CG rtol 1e-10 and at
most 500 iterations. Compare against direct solving of an independently
fingerprinted copy of the same matrix, limited to 25,000 free unknowns. Both
backends must produce finite positive energy-derived capacitance, relative
capacitance difference at most 1e-6 and relative solution-vector L2 difference
at most 1e-6 (direct solution as denominator). These are implementation gates,
not mesh or physical-accuracy gates. Failure stops the chain; no mode is skipped.

All original per-worker node, tetrahedron, time and RSS ceilings remain in
force: the toy inherits smoke limits and local0 inherits feasibility limits.
The direct comparator shares its worker's total time and memory budget.
One 160 GiB, 45-minute SLURM allocation contains at most 600 plus 1,200 worker
seconds, with one scientific thread. There is no array or automatic retry.

## Interpretation boundary

Success qualifies neither the compact-support policy nor any reference label.
It only supports considering this preconditioner for a separately versioned
feasibility protocol. Local1/local2, repeatability, padding, far-field and
support sensitivity remain unmeasured under this candidate. No full pilot,
training, claim admission or paper export follows automatically. Preserve all
rejected bytes and use the [runbook](../operations/TCAD-Cps-AMG-Diagnostic.md)
and [evidence record](../evidence/TCAD-Cps-AMG-Diagnostic.md).
