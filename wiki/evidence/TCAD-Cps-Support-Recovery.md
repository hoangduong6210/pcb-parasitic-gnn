---
title: TCAD Compact-Support Recovery Evidence
status: PROPOSED; implementation and archive prepared; no recovery job submitted
last_updated: 2026-10-02
paper_source: false
---

# TCAD Compact-Support Recovery Evidence

## Owner-authorized preparation

The owner requested the next step after the incomplete pilot. The
[decision](../decisions/0005-tcad-compact-mesh-support.md) authorizes a bounded
largest-sentinel feasibility implementation; the
[method](../methods/TCAD-Cps-Compact-Support-Recovery.md) and
[runbook](../operations/TCAD-Cps-Support-Recovery.md) own its frozen contract.
This does not relabel the old pilot as passed or authorize a new training grid.

The original pilot's terminal task directories, final summary and scheduler
logs were copied byte-for-byte into the main checkout. The
[archive manifest](../../results/tcad/cps_reference_v1/archive/pilot_7641200/manifest.json)
binds 59 files and four terminal scheduler records. Its SHA-256 is
`253a0443a9c46efa5db5dc2dd3c9924196fef7a6aa9504f173081b11ccd9ad76`.
All original raw-log hashes and saved result/log identities were checked,
including the failed task. No numerical replay or solve ran on the login node.

The [geometry/cost receipt](../../results/tcad/cps_reference_v1/archive/pilot_7641200/geometry_cost.json)
records that layout 597 has 26 conductors. Its local2 mesh was generated at
about 1,160 seconds and contained 3,452,236 nodes; the worker stopped before
matrix assembly. The nearest projected interlayer gap is 0.11 mm, up to
floating-point representation. The sum of expanded conductor-box volumes
changes from 538.3658428070789 to 312.7560307049313 cubic millimetres when
expansion changes from 0.11 to 0.055 mm. These sums double-count overlaps and
exclude the transition layer; they are not mesh-node predictions or physical
volumes. The smaller support is a candidate motivated by geometry and cost,
not an established accuracy improvement.

The recovery keeps the original caps and near-size ladder. It changes box
expansion and transition thickness, and adds a fresh original-support arm at
the intermediate level. Only layout 597 is selected. The original two completed
sentinels do not contribute new-policy observations. Full-pilot and training
expansion remain disabled.

Initial no-solver testing passed 42 tests with the new lock check skipped
before freezing. Additional failure-retention and old/new identity tests were
then added before freezing the source. The final frozen suite passed all 122
pilot, recovery, wiki, reproducibility, prose and journal tests. The deterministic
prose audit, shell syntax and archive reconstruction checks passed. The source
lock SHA-256 is
`b79411aeb3e327a96b61c0a746fae3ec2d4774542677eaff8cafa9616f45fd39`.
It includes the original closure and terminal archive; no old execution source
file was edited. Publication and scheduler receipts follow below; no new
numerical result is available at this preparation checkpoint.

An unrelated scheduler job was present during inspection and was left
untouched. No prior worktree, original protocol, original lock, baseline FEM
implementation, released paper or internal agent-guidance tracking was changed.
