---
title: TCAD Column Feasibility Implementation Evidence
status: PROPOSED candidate; synthetic arithmetic contract validated
last_updated: 2026-10-03
paper_source: false
---

# TCAD Column Feasibility Implementation Evidence

## Source-only checkpoint on 2026-10-03

The preceding [dyadic study](TCAD-Layer-Grid-Dyadic.md) is terminal, rejected
and archived. This continuation implements the separate
[footprint/column contract](../methods/TCAD-Column-Feasibility.md), without
changing any frozen source, protocol or evidence.

Library: `code/solvers/tcad_cps_column_contract.py`.
Tests: `tests/test_tcad_cps_column_contract.py`.
The initial 85 tiny-synthetic cases passed. Expanded coverage then passed 157
cases including 55 wiki/prose tests, after adding exact retained-height bounds
and additional node-order checks. The final expanded library run passed all
**105 tests**, including exact nonrepresentable z differences and the refused
command-line entry. A combined regression against inherited helpers follows.
There is no new native 2D mesh, 3D mesh, field result or qualified reference.

Implemented contracts cover complete projection ownership, including coincident
and triple-overlapping footprints at different heights; an exact area oracle;
canonical z-only midpoint refinement; prospective column counts and exact volume
closure; a globally consistent three-tetrahedra prism template; and a new exact
Frobenius conditioning certificate over all retained heights. Supplied planar
counts are not labelled validated by the counting helper. All scientific
admission flags remain closed and the library refuses command-line execution.

Native 2D construction/provenance/mesh audit and the guarded worker integration
are not implemented in this checkpoint. Their protocol and execution source
are not frozen, and no job has been submitted. Those are the next required
steps before any real-layout computation. This is not a substitute for the
full reference qualification or the eventual TCAD learning/evaluation program.

At continuation start, main was clean and matched GitHub at
`9fe5ea0192b5be4125650787c39660d8be60e464`; the queue was empty. Ten
completed synthetic-fixture roots were inspected and removed to recover file
headroom, documented by the [storage owner](../operations/Repository-Storage.md).
Observed account use afterward was 999,350 of 1,000,000 files. All scientific
artifacts and execution worktrees remain preserved. These new records are local
until publication is verified.

The combined regression passed **376 tests, zero skips**, in 29.95 seconds:
the new exact contracts, both inherited coordinate planners, dielectric
topology and wiki/prose checks. The inherited source/archived-input locks still
pass. The deterministic prose audit also passed. Three completed initial test
directories were removed after inspection; only reproducible test fixtures
were removed. Publication is next; no native or real-layout result is inferred
from these synthetic checks.
