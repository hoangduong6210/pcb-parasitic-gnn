---
title: TCAD Compact-Support Feasibility with the Tested AMG Candidate
status: REJECTED; initial execution incomplete; source preserved
last_updated: 2026-10-03
paper_source: false
---

# TCAD Compact-Support Feasibility with the Tested AMG Candidate

The first execution closed incomplete at the local1 mesh-generation wall-time
cap. Its [terminal evidence](../evidence/TCAD-Cps-AMG-Feasibility.md) is archived.
The specification below remains frozen; no gate is relaxed after the failure.

## Decision and unchanged scope

The owner approved the next implementation after the successful
[AMG diagnostic](../evidence/TCAD-Cps-AMG-Diagnostic.md). Test whether its fixed
unsmoothed-prolongation candidate can complete the seven-arm largest-sentinel
study within the original caps and pass the prescribed sensitivity checks.
The [new machine protocol](../../protocols/tcad_cps_amg_feasibility_v1.json)
inherits the rejected support protocol and the successful diagnostic by hash.
No earlier source, lock, result or scientific interpretation is rewritten.

Use layout 597 only. Keep its canonical geometry, uniform dielectric, terminal
potentials, boundary treatment, energy definition, mesh fields and numerical
threads unchanged. Replace only the original default prolongation smoothing
with the tested candidate: `smooth=None`, symmetric aggregation, constant
near-nullspace input, `max_coarse=50`, other pinned PyAMG defaults unchanged.
CG tolerance, iteration limit and operator-complexity cap stay unchanged.

## Fresh execution and gates

Run a new source-bound toy smoke with same-matrix direct comparison before any
feasibility job. Preserve the diagnostic's toy matrix identity, direct-solve
dimension cap and vector-agreement check, plus the original smoke resource,
residual and capacitance-agreement gates. A prior smoke receipt cannot satisfy
this prerequisite under a different source identity.

Then run seven fresh processes in order: local0, local1, local2, repeat2, pad20,
far2 and support1. The [support method](TCAD-Cps-Compact-Support-Recovery.md)
owns their inherited exact mesh settings and comparison denominators. All
seven use the same new AMG candidate; support1 changes mesh support, not the
solver. The fresh local0 must reproduce the diagnostic's mesh/system identity.
Do not copy its earlier capacitance as a new arm or reuse old sentinel results.

Require complete coverage, successful zero-restart terminal accounting and all
per-arm gates before assessing sensitivity. Adjacent fine-mesh, padding,
far-mesh and intermediate support differences must each be at most 5%.
Repeat2/local2 must have identical mesh counts and system hashes and relative
capacitance difference at most 1e-4. No three-layout median is computed; the
future three-sentinel 2% median and 5% maximum gates are not replaced.

A failed worker stops the chain and retains its logs. A complete negative
sensitivity result is retained as such; successful finalization alone is not
a feasibility pass. The finalizer runs after any terminal feasibility outcome
and retains failure and missing-coverage evidence. No automatic retry, cap
increase, geometry exclusion or downstream expansion is permitted.

## Interpretation

Even a complete pass only supports considering another explicitly versioned
panel study. The level-1 support control is not a finest-level error bound.
Reference qualification, continuum convergence, physical accuracy, training
and paper claims remain closed. The [runbook](../operations/TCAD-Cps-AMG-Feasibility.md)
owns submission and preservation; the [evidence page](../evidence/TCAD-Cps-AMG-Feasibility.md)
owns outcomes. A future paper is exported only from an admitted wiki snapshot.
