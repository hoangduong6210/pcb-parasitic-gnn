---
title: TCAD Native Field Probe Evidence
status: VALIDATED; synthetic native API only
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

## Source publication and submission

Source `aae46d310a92c0da6dff02ca6cf9e82e1586adb6` was verified against
GitHub main at 15:56:50 UTC. Final checks passed the 7,301-file manifest, prose
audit and 55 wiki/prose tests. The fresh 479-file sparse checkout passed source,
wrapper and runtime metadata preflight. One submission at 15:57:40 UTC returned
**job 7655811**. The receipt is
`results/tcad/cps_field_probe_api_v1/submission.json`. Monitor this attempt;
do not retry. Source is published; submission/monitoring receipts remain local.

## Terminal native API result

At 15:59:03 UTC job **7655811** was terminal `COMPLETED/0:0`, zero restarts,
63 seconds on `a0113`, and absent from the queue. Both fresh workers passed.
Each checked **73 points**, evaluating the minimum distance over **12 original
finite segments** and the linear size field separately. The threshold used
DistMin 0.055 mm, DistMax 0.555 mm, SizeMin 0.12 mm and SizeMax 1 mm; these
were fixed before execution. Relative and absolute probe tolerances were
1e-12 and 1e-12 mm. This is API/value agreement on a tiny synthetic fixture,
not mesh resolution, physical accuracy or a real-layout result.

The two complete report files are byte-identical, SHA-256
`e3df67aab34d890a7beddefb213858b7d8425fe1ac67dd3c1bbc375d4c00d562`.
Each binds 15 payload members. The main-state before/after files have identical
bytes, SHA-256
`a0efcc6e854f09ba7c72adda8c3a0c07ac483e3154e387a78a4ef93334f5a3be`:
observed CAD, field definitions, options, model/view identities and empty mesh
are unchanged. Only explicit temporary 0D probe elements were inserted and
removed; no native planar/volume generation or PDE solve ran. The result does
not certify hidden native caches or behavior on arbitrary geometries.

The additive collector passed 24 synthetic tests with one pre-collection skip.
All **43 terminal members** are preserved in
`results/tcad/cps_field_probe_api_v1/archive/job_7655811/manifest.json`, SHA-256
`b4d339befd6993abfd9a36316fb155cfe11afd90b5d4142230aab8e645eb17bd`.
Review checks bytes, scalar closures and the same fixed tiny synthetic fixture;
it imports no native library and replays no actual layout/mesh. All earlier
failed source and evidence remain intact. Terminal regression passed **215
tests, zero skips**, in 92.39 seconds, including actual archive validation.
The prose audit passed. Final manifest/member checks and publication are next;
no scientific job remains active.

## Next scientific action

The subsequently frozen [real-layout integration](TCAD-Edge-Feasibility-v2.md)
has now passed its own native probe, planar audit and prospective column gates
with exact fresh repeat. Its evidence owner records the separate scope and
remaining 3D/field qualification. The original prospective integration plan
below is retained as the transition boundary, not an unrun current task.

Integrate the qualified model-backed adapter into a **newly versioned/frozen
edge-local feasibility study**, preserving the original failed source and
archive. Keep the same distance/size definition, inherited near/far/transition,
geometry, 2D capture limits, prospective column counts, conditioning and volume
gates. Preserve each actual-layout native probe and main-state before/after
snapshot, and require those gates before meshing every mode. This synthetic pass
does not waive actual-layout probes. Then submit the toy/sentinel/fresh repeat
once through SLURM. No automatic retry, cap increase or accuracy claim follows.
Full 3D boundary/terminal/volume and field/sensitivity qualification still
precede references, learning and paper claims. The full TCAD goal is incomplete.

## Terminal publication receipt

At 16:05:01 UTC on 2026-10-03, local HEAD and GitHub main were verified as
`8079beef10b4cbb2df73c4f865d0838048b1cb0a`. The 43-member archive,
collector/tests and scoped API result are published. Final checks passed the
7,347-file manifest, prose audit and 55 wiki/prose tests. No scientific job is
active. The next step is newly frozen real-layout integration; no paper export,
reference admission or relaxation of a prior failed gate occurred.
