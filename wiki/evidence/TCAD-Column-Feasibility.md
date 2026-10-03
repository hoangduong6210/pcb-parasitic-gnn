---
title: TCAD Column Feasibility Implementation Evidence
status: PROPOSED candidate; guarded native integration under synthetic validation
last_updated: 2026-10-03
paper_source: false
---

# TCAD Column Feasibility Implementation Evidence

## Native integration preparation on 2026-10-03

The continuation reverified GitHub main at
`c95e76ff58d0ce43cb5b1046f49c952494a4b09a`. The queue was empty.
New source implements planar CAD provenance/metadata review, raw mesh
capture and independent topology/ownership audit, deterministic binary bundles,
packet-to-column capacity/conditioning, and guarded fresh native orchestration.
No earlier frozen source, protocol or archive was changed. The new protocol
is `protocols/tcad_cps_column_feasibility_v1.json`; it is now source-locked.

Initial CAD tests passed 30 cases. The combined CAD/mesh suite passed all
82 cases; packet-to-column integration passed 11 more. These use hand-built
rectangles and a 16-node/18-triangle fixture, never actual layouts or Gmsh.
Coverage includes overlapping projection owners, independent incidence,
aggregate conservative clipping-error bounds, edge and vertex manifold checks,
raw-orientation preservation, exact height differences and retained negative
capacity/condition reports. The expanded fake-native orchestration suite passed
44 cases with one pre-freeze lock skip. An initial test-helper name collided
with pytest's legacy setup hook; renaming it corrected the harness before
freeze. No scientific execution occurred during these tests.

The combined pre-freeze regression passed **555 tests, one expected lock
skip**, in 37.16 seconds; the prose audit passed. After creating the new lock,
the frozen regression passed **556 tests, zero skips**, in 64.54 seconds.
This includes inherited source/input locks and planar, arithmetic, byte-bundle,
guard, resource-stop, retained-partial-output and wiki/prose coverage.

Frozen bindings:

- Protocol SHA-256: `0e6451fb9ab44151c46090ef06ef4796bbe4c786a44d264fd545dcce18bd1149`.
- Source/input lock SHA-256: `72900550aba333843037e28239fcedae83f8109e35470bba48815494dc3effb0`.
- Exact locked dependency count: 384.

Publication and sparse-checkout verification are next. No native candidate
has run, and current implementation records remain local until publication
is verified. Fourteen inspected completed test roots were removed as recorded
by the [storage owner](../operations/Repository-Storage.md); all scientific
evidence and execution worktrees remain preserved.

The [method owner](../methods/TCAD-Column-Feasibility.md) specifies the guards,
audit scope and prospective resource/capture limits. No new native mesh,
volume mesh, field, reference or learning result exists. Publish and verify
the frozen source, then run one bounded SLURM study and retain every
outcome. This engineering checkpoint is not a TCAD contribution or paper claim.

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

## Verified publication

At **12:32:35 UTC**, GitHub main and local HEAD were verified as
`141fe2cf6b34de48a44f98f19f3602b3416ec5fc`. The 7,181-file manifest,
376-test combined regression, final 55-test wiki/prose recheck and standalone
prose audit passed. Internal agent instructions remain ignored/untracked.
Two final completed regression/wiki fixture directories were removed after
inspection; all scientific evidence and execution worktrees remain preserved.
The queue was empty at 12:32:37 UTC. Publication confirms the source checkpoint,
not native geometry/mesh feasibility or protocol freeze. The next required work
remains native 2D provenance and mesh audit, then a bounded guarded integration
with a prospectively frozen execution protocol.
