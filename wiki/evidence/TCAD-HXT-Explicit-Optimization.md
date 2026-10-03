---
title: TCAD HXT Explicit-Optimization Evidence
status: PROPOSED; source frozen; no new mesh observation
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Explicit-Optimization Evidence

## Implementation on 2026-10-03

The preceding isolation archive and research decision are published; the later
publication receipt commit `dada417563378cd7a563462d5eb117aac3595944` was also
verified on remote main before this implementation. Its rejected toy evidence
remains unchanged, archive SHA-256
`20722df38fb6af937236d942a8b7a4fb89fc4bb1f1bac9d0f3c4b074c375f10a`.

The new [method](../methods/TCAD-HXT-Explicit-Optimization.md) has a separate
protocol, worker, parent, guarded builder and SLURM wrapper. The builder keeps
the original geometry and extraction source while moving coordinate reads
after the explicit optimizer. New tests exercise the complete worker/builder
with fake native APIs, deliberately changing coordinates and connectivity.
No real Gmsh mesh or field solver was executed on login.

Initial tests passed 43 cases with the source-lock test deferred until freeze.
The expanded fake-builder suite initially had three fixture/assertion mistakes:
a missing phase environment and two overly narrow exception patterns. The
guards themselves failed closed as intended; fixtures were corrected before
freeze. Numerical performance and quality have not yet been observed.

Next: finish regression and freeze, publish/verify source, then submit the
single bounded allocation under the [runbook](../operations/TCAD-HXT-Explicit-Optimization.md).
No prior source, cap, quality gate, dataset or manuscript claim changes.

## Source freeze

After fixture corrections, all 50 new no-solver tests passed, with one deferred
source-lock test. The combined source/archive/wiki/prose regression passed
262 tests with the same single pre-freeze skip. Shell syntax, prose audit and
tracked documentation diff checks passed. Installed Gmsh API text also confirms
the selected keyword argument names; this was read without running Gmsh.

- Protocol SHA-256: `723bb110b8d7c67d0274883583c527827a3326aab88b300d34bf555fa006ecae`.
- Lock SHA-256: `e83ca24c6adb98e20657ef5ae24d7b1d64078282b596eaa9f248f3ee33869c14`.
- Source closure: 198 files, excluding the new lock itself.

The closure includes the predecessor source lock, failed attempt, archive
checker and regression. Freeze does not validate a real mesh. Post-freeze
regression, verified publication and the bounded submission follow next.

The post-freeze regression subsequently passed all 263 selected tests with no
skips, including the 51 new tests and unchanged predecessor archives/sources.
The staged source/documentation diff and prose audit passed. No numerical
mesh, quality or timing result is inferred from these synthetic/source checks.
