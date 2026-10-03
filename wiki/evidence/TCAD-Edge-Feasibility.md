---
title: TCAD Edge-Local Feasibility Evidence
status: REJECTED; native probe integration, sizing hypothesis untested
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Feasibility Evidence

## Preparation on 2026-10-03

The [new method](../methods/TCAD-Edge-Feasibility.md) tests an explicit finite
perimeter-distance policy after the archived Box sizing-budget diagnosis.
Original sources, rejected attempts, caps and tolerances remain untouched.
Initial integration passed 74 synthetic tests with one expected pre-lock skip.
Expanded pre-freeze regression passed 495 tests with one expected lock skip.
The fixed source/input lock passed **496 frozen tests, zero skips**, in 107.56
seconds. The prose audit passed. No actual layout probe, native mesh or
scientific job has run.

The parent protocol SHA-256 is
`34084a9ee2555c7c072152b9d178978fc0c7a321b7f6bc5fa3d45eb48cecd7b8`;
the parent terminal archive is
`da1c2edd357cf7fa85ddbf5fc37e962391d42bd421ef5bdd44e15da723c5c790`.
The new study retains the original worker limits and requested SLURM resources,
not the shorter diagnostic-only limits. Publication verification and one
sparse-worktree submission are next.

## Frozen identities

- Protocol SHA-256:
  `16472fe0dc5f6ca880df1e7766330b3a884276ae5c4d1fdce5ba61b4e5027cea`.
- Source/input lock SHA-256:
  `7427e553dba07e8e8ba565342b27a7e891ed6e04d0fc00ac0bbd126fb641af6c`.
- Locked dependencies: 454; earlier locks and archive members are unchanged.

## Published source and submission

Source `5afbe79dd138208eb423dabe652c4afda8498af4` was verified against
GitHub main at 15:25:49 UTC on 2026-10-03. Final manifest verification covered
7,276 files; the prose audit and 55 wiki/prose tests passed. A fresh 457-file
sparse worktree passed source/wrapper/runtime metadata preflight without native
initialization. One submission at 15:26:49 UTC returned **job 7655656**.
The receipt is `results/tcad/cps_edge_feasibility_v1/submission.json`.
Monitor this attempt; do not retry or tune it. Execution source is published;
submission/monitoring receipts remain local pending the next publication.

## Terminal integration failure

At 15:27:37 UTC job **7655656** was terminal `FAILED/2:0`, zero restarts,
31 seconds on `a0113`, and absent from the queue. Toy alone ran. Its canonical
and planar CAD gates passed and effective sizing metadata was preserved. The
first MeshSizeFieldView call then reported `Cannot get entity from this view`,
followed by `Unknown plugin or plugin action`. The latter is the wrapper's
generic error, not evidence that the plugin is absent: stdout records its start.
No field comparison report or raw mesh was produced, and planar generation
never began. Sentinel and repeat were correctly unrun.

The parent observed 12.520117882872 seconds and 0.044429779052734375 GiB for
the failed worker. Stage telemetry separately reported 0.059078216552734375 GiB
peak RSS; these are different sampling boundaries. The recorded failure was
an API exception, not a time/RSS/capacity rejection. Complete, repeatability,
diagnostic and planning-feasible flags are false; all volume/field/reference/
training/claim gates remain closed. The sizing hypothesis itself is untested.

The byte-only collector passed 24 synthetic tests with one pre-collection skip.
All **11 terminal members** are preserved and checked in
`results/tcad/cps_edge_feasibility_v1/archive/job_7655656/manifest.json`, SHA-256
`07a609427373a633f0ef765c3afe53ad88816da0e2383d9d66a89686eb0c0ad8`.
This includes both scheduler logs, raw accounting, submission/attempt/mode
receipts, worker logs and all three partial JSON payloads. Nothing was removed
from the immutable execution worktree. Terminal regression passed **248 tests,
zero skips**, in 133.70 seconds, including the actual archive byte/metadata
check. The prose audit passed. Publication is next; no job remains active.

## Source-backed diagnosis and next step

Inspection of the official
[Gmsh 4.15.2 source](https://gmsh.info/src/gmsh-4.15.2-source.tgz) after failure
found the missing constraint in `src/mesh/Field.cpp`: `Field::putOnView` calls
`getEntity` before walking view elements/nodes. `src/post/PViewData.cpp` emits
the observed error in its default `getEntity`; `PViewDataGModel.cpp` provides
the model-backed implementation. This explains why the list-based scalar-point
view is unsuitable for this path. The earlier review stopped at the plugin
entry point; fake-native tests omitted this entity requirement. Their success
was not native compatibility evidence.

Next: separately specify a bounded, tiny synthetic **native API qualification**
under SLURM before another real-layout attempt. Test a model-backed point view
with actual element/entity support, preserve raw values and model/view metadata,
check independent distances/sizes and prove cleanup/restoration leaves the main
CAD and fields unchanged. An isolated probe model is a candidate, not a verified
fix. Native code must not run on login. Preserve this failure and create new
source/protocol identities; do not edit its lock, bypass probes, tune sizing,
raise caps or automatically resubmit this attempt.

No accuracy, feasibility, reference qualification or paper claim is admitted.

## Terminal publication receipt

At 15:35:09 UTC on 2026-10-03, local HEAD and GitHub main were verified as
`820c77f9c71cd715c4b0adfe3ee13fe344da5cfa`. The terminal archive,
collector/tests and source-backed diagnosis are published. Final verification
passed the 7,290-file manifest, prose audit and 55 wiki/prose tests. No job is
active. The next step remains the separately frozen native API qualification;
no execution retry, reference admission or paper export was performed.
