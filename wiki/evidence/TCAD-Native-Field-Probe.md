---
title: TCAD Native Field Probe Evidence
status: PROPOSED
last_updated: 2026-10-03
paper_source: false
---

# TCAD Native Field Probe Evidence

## Preparation on 2026-10-03

The previous goal turn made concrete guarded integration, native failure
isolation, archival and publication progress. This continuation reverified
clean local HEAD and GitHub main at
`3feb1b683358bd6336e6eed2ec36e75482fe1839` at 15:36:53 UTC; no job was
active. The full TCAD goal remains active and incomplete.

The [model-backed adapter qualification](../methods/TCAD-Native-Field-Probe.md)
is being specified from the preserved edge-local failure. The parent terminal
archive SHA-256 is
`07a609427373a633f0ef765c3afe53ad88816da0e2383d9d66a89686eb0c0ad8`.
No corrected native adapter has run. Implement and test the isolated-model
adapter, freeze and publish the new source/protocol, then submit through SLURM.
The prior execution worktree, failed adapter, lock and archive remain unchanged.

The isolated-model adapter, guarded worker/parent and bounded protocol are now
implemented. Initial adapter tests passed 19 cases; initial integration passed
53 tests with one pre-lock skip. More negative fixture/protocol tests and the
source freeze remain. Raw request/scaffold/view/cleanup records precede their
gates; malformed nonfinite values are retained with explicit encodings. Main
CAD/field/options/mesh snapshots are preserved even when a probe throws.
No actual native initialization or meshing has run in this continuation.

Expanded pre-freeze regression passed **241 tests with one expected lock skip**
in 75.46 seconds. Frozen regression passed **242 tests, zero skips**, in 108.52
seconds; the prose audit passed. Publication and one SLURM submission are next.
Four inspected
completed fixture roots containing no regular files were removed; scientific
data and execution worktrees remain preserved.

## Frozen source identities

- Protocol: `protocols/tcad_cps_field_probe_api_v1.json`, SHA-256
  `cfb3f73f451e71babdb15c1cb4d97ca61a583a8b0a3ba8b775912a2a7bf69aa5`.
- Lock: `protocols/tcad_cps_field_probe_api_v1.lock.json`, SHA-256
  `50a8967f63cce31cd0ba1d20e45ed4a3ccaba06d6ac8fff3f8ce83553e193541`.
- Source/input dependencies: 476, including the unchanged parent source and
  complete rejected terminal archive.
