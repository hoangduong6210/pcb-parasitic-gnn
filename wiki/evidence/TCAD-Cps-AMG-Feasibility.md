---
title: TCAD AMG Feasibility Evidence
status: VALIDATED; source frozen; publication and execution pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD AMG Feasibility Evidence

## Preparation on 2026-10-02

The owner approved implementation of the next bounded step. The successful
diagnostic is now preserved in a nine-file byte-for-byte
[terminal archive](../../results/tcad/cps_amg_diagnostic_v1/archive/job_7647850/manifest.json).
Its manifest SHA-256 is
`0b6df0554a8ca2f76110af66518175209cf978630622408f29928970ff055a4e`.
The archiver checked exact file/mode coverage, terminal accounting, source,
runtime, geometry, raw-log/result reconstruction and recorded scalar gates.
It performed no numerical solve or replay on login. The
[diagnostic evidence](TCAD-Cps-AMG-Diagnostic.md) owns its scientific limits.

The [new method](../methods/TCAD-Cps-AMG-Feasibility.md) keeps all seven mesh
arms and resource/sensitivity limits, changing only to the already tested AMG
candidate. Every arm, including local0, is rerun under the new source identity.
No previous result is substituted. The [runbook](../operations/TCAD-Cps-AMG-Feasibility.md)
requires a new source-bound smoke before feasibility and afterany finalization.

At this preparation checkpoint no new job is submitted and no source lock
for this study is frozen. Last verified remote `main` is
`6a393612588a2c70e513a6f027e596ba7e5adc39`; earlier local wiki reviews are
retained for inclusion with this implementation. All older source and evidence,
the released paper and the local-only guidance boundary remain unchanged.
No reference, training permission or new paper claim is admitted.

## Frozen-source validation on 2026-10-03

The additive implementation passed all 191 focused tests across the original
pilot, support recovery, AMG diagnostic, new feasibility contracts, wiki, prose,
reproducibility and journal package. The tests use metadata and fake numerical
APIs, not a login-node solver. They check unchanged inherited caps/physics,
exact anchors, source and runtime binding, prerequisite smoke, failure stops,
process-group limits, receipt corruption, incomplete coverage, negative
sensitivity outcomes and false downstream-qualification flags. The copied
assembly and AMG numeric helpers remain byte-identical to the diagnostic source.

The deterministic prose audit, all three batch-wrapper syntax checks and the
nine-file diagnostic archive check passed. The new source lock SHA-256 is
`00f5b0f6b9d825597286edcb2e51ae0ac3c9bb1b557c6f33169c79ad24d31906`.
It binds the inherited source closures, terminal evidence, new protocol,
workers, runner, wrappers and tests. No old source lock was replaced. This
validates implementation contracts, not numerical feasibility. Publication
and a new SLURM smoke are the next gates; no job has been submitted yet.
