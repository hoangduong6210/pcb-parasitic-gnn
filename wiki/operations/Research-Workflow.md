---
title: Research Workflow
status: canonical workflow
last_updated: 2026-08-17
paper_source: false
---

# Research Workflow

## From question to claim

1. State the estimand, population, target definition, fidelity, metric, and
   uncertainty unit.
2. Freeze geometry, data selection, split, seeds, solver settings, resources,
   failure caps, and acceptance criteria.
3. Review the code and protocol hashes in a clean immutable worktree.
4. Submit heavy field solves or training through SLURM. Login nodes are limited
   to validation, hashing, tests, indexing, and document builds.
5. Preserve atomic attempts. A retry writes a new attempt and never overwrites
   the record that motivated it.
6. Finalize exact coverage. Missing, duplicate, extra, hash-drifted, or failed
   records block finalization.
7. Add the result to the evidence ledger, including negative and inconclusive
   outcomes.
8. Review the scientific interpretation and update the claim registry.
9. Update the canonical method or result page.
10. Export a paper snapshot only when the claim set passes the publication gate.

## Priority levels

`P0` is a correctness or integrity defect that invalidates evidence, mixes
scientific scopes, risks data loss, or permits an unsupported claim. Work that
depends on the affected evidence stops until the defect is resolved.

`P1` is a serious reproducibility, coverage, or maintainability weakness that
does not already invalidate the accepted result. It is scheduled before the
next release or paper export.

Lower priorities improve clarity, efficiency, or future scope without changing
the current scientific conclusion.

## Change boundaries

A resource cap failure, convergence rejection, or inconclusive model comparison
is a result. It does not authorize a larger cap, a different mesh, an omitted
layout, or a new metric after inspecting outputs. Such a change starts a new
protocol and is linked by a decision record.

Paper text never drives a result backward into the registry. If a paper sentence
requires wording absent from the claim record, either narrow the sentence or
run the evidence needed to support it.
