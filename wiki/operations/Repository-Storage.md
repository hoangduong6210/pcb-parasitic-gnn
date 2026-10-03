---
title: Repository Storage and Immutable Evidence
status: VALIDATED; incremental packing completed
last_updated: 2026-10-03
paper_source: false
---

# Repository Storage and Immutable Evidence

## Terminal publication headroom on 2026-10-03

At terminal publication the account was near its file limit. Two completed
fixture roots, `sizing-budget-final-wiki.jK3Ufk` and `q1-archive-tests.hybwFZ`,
were inspected and removed: only pytest links/directories and the same three
hash-matched prose fixtures remained. Four further inspected roots contained
only empty fixture directories and pytest links: `tcad-isolation-archive.oxO1rc`,
`tcad-postopt-archive.ST6T2e`, `hxt-archive-tests.c3XniE`, and
`hxt-archive-tests.fzhuVF`. No scientific data/worktree was removed.

Supplementary incremental-pack job `7655163` was submitted at 14:41:44 UTC
against clean published main `b9a4f8c82645652324c435666c5ed70b59336ec6`.
It stayed PENDING for priority. Account usage then fell to 997,844 files at
14:45:42 UTC through activity outside this operation. Since headroom had
returned, the still-PENDING job was cancelled at 14:46:14 UTC. Accounting
reported `CANCELLED by 51204`, zero elapsed time, zero allocated CPUs and no
assigned node. No supplementary packing/fsck occurred. The
[cancelled-operation receipt](../../results/operations/git_pack_sizing_20261003/receipt.json)
preserves that distinction; the earlier successful pack is unchanged.

The owner subsequently authorized deletion of the sibling `Hoang/Da-Yeh Journal/`
directory to recover file quota. Inspection found one independent repository
with uncommitted changes and no linked external worktree. A private single-file
recovery archive under `Hoang/.recovery/` preserved it before deletion.
Guarded SLURM job `7655220`, submitted at 14:50:58 UTC, completed with
`COMPLETED/0:0`, zero restarts, 61 seconds, one CPU and 1 GiB on `a0347`.
No archive generation, comparison or deletion ran on the login node.

The exact requested directory contained 681 directories, 6,244 regular files
and four symlinks (396,762,447 apparent bytes). The source inventory hash was
identical before/after archive creation; `tar --compare` passed before removal.
The 159,340,677-byte private recovery file is
`Hoang/.recovery/dayeh-journal-20261003-job_7655220.tar.gz`, mode 0600,
SHA-256 `a6f670a6e732bc34b776a743be0de110dfc90559cceb98f4f49217b1de853ac7`.
It includes the sibling repository and its uncommitted changes. The original
directory is absent and can be restored from this archive. No GNN scientific
artifact or execution worktree was removed. The
[operation receipt](../../results/operations/dayeh_recovery_delete_20261003/receipt.json)
records the exact checks and outcome. Original script/logs stay in `.internal/`;
no sibling content or recovery archive is committed here. Account file quota
also changes through other activity, so do not equate entry count with a
measured account-wide quota reduction.

## Post-column incremental pack on 2026-10-03

The next continuation began with 999,940 of 1,000,000 account files and 326
loose Git objects. Main was clean and matched GitHub at
`038bc0aeed706438a441453aa9ac07a547d7ce44`. Separate maintenance job
`7654378`, submitted at 13:56:18 UTC, completed with `COMPLETED/0:0`, zero
restarts, 40 seconds, three allocated CPUs and 8 GiB on `a0113`.
The same bounded incremental pack used one thread after a verified RUNNING
allocation/compute-host check; no source editing or committing occurred during
the operation. Full integrity checking passed. All object-ID, ref and worktree
inventory hashes remained identical, and tracked bytes were unchanged.

Loose objects decreased from 326 to 27; packed objects increased from 12,401
to 12,700 in three packs. Only redundant loose copies were removed; their
contents remain in Git packs. No scientific artifact, archive, source worktree,
unreachable-object pruning or history rewrite was involved. The
[operation receipt](../../results/operations/git_pack_column_20261003/receipt.json)
records exact identities. The script and original logs remain in `.internal/`.
This storage operation is not scientific validation. Check current account
headroom before further work because other account activity also changes quota.

Twenty completed synthetic fixture roots were then inspected and removed from
`.internal/`: `q1-wiki-check.QzjN06`, `hxt-wiki-tests.xXLfEj`,
`hxt-receipt-tests.tSdjIC`, `tcad-hxt-publication-tests.8IvJOl`,
`column-publication-receipt.bgzMQw`, `tcad-isolation-publication.H5Sm2R`,
`tcad-postopt-wiki.PIb6Ab`, `tcad-postopt-checkpoint.SJRU8c`,
`tcad-postopt-review-wiki.PjeIUo`, `tcad-wiki-precommit.RWj3oh`,
`tcad-publication-wiki.qVODnE`, `cad-freeze-wiki.IUnbWW`,
`cad-terminal-wiki.2TUs7P`, `cad-publication-receipt.nPP1qZ`,
`dielectric-mesh-receipt.oQo09o`, `dielectric-mesh-freeze-wiki.oZgbmM`,
`dielectric-mesh-wiki.UsQsgK`, `dielectric-mesh-terminal-wiki.bCJJCi`,
`dielectric-mesh-archive-wiki.yPYQG2`, and `dielectric-mesh-publication.q1mEU0`.
Their 200 entries comprised 80 directories, 60 pytest links and 60 small files
matching the same three reproducible prose-test hashes. No pytest process or
job was active during inspection/removal. Only these exact roots were removed,
without following links; tests can regenerate the text. No scientific evidence,
execution worktree or Git content was removed. Observed file use at 14:03:58 UTC
was 999,314 of 1,000,000; other account activity also affects this number.

Three newly completed roots were subsequently inspected and removed:
`sizing-budget-math.IZw3pI`, `sizing-budget-integration.6HvsD7`, and
`sizing-budget-prefreeze.e8IeAM`. They held only pytest links, empty directories
and the three hash-matched prose fixtures. Scientific data/worktrees were
unchanged; the frozen regression used its own separate active fixture root.

After source publication, six more completed fixture roots were inspected and
removed before the sparse checkout: `sizing-budget-frozen.ptrk30`,
`sizing-budget-source-wiki.HQjyht`, `hxt-terminal-tests.UiuAoz`,
`tcad-isolation-terminal.zE4Mui`, `tcad-postopt-terminal-prep.ZAPn0q`, and
`tcad-postopt-corrected.GMjyQb`. Only pytest links/directories and nine files
matching the same three reproducible prose-fixture hashes remained. No pytest
process was active. No scientific artifact or execution worktree was removed.
Observed quota was 999,328 files at 14:28:54 UTC.

After diagnostic completion, four more completed roots were inspected and
removed: `hxt-tests.oQoYXK`, `tcad-postopt-integration.gvOLKJ`,
`tcad-postopt-preflight.D5o4gF`, and `sizing-budget-archive.jTQKkt`. They held
only pytest links and their root directories, with no regular files. All
scientific outputs, source checkouts and archives remain preserved.

The completed `sizing-budget-terminal.K6ubNX` root was also inspected and
removed after its 170-test pass. It held pytest links/directories and the same
three hash-matched prose fixtures; no test process was active. No scientific
data or execution worktree was removed.

## Earlier incremental pack on 2026-10-03

Before another frozen execution checkout, file quota was 999,779 of 1,000,000.
The repository had 1,094 loose objects. The separate non-scientific maintenance
job `7652583`, submitted at 10:45:46 UTC on 2026-10-03, ran
`git repack -d --threads=1 --window-memory=64m` and full `git fsck` on SLURM.
It verified the actual RUNNING allocation/compute host before packing and
checked the main commit and unchanged tracked files. No source editing or
committing occurred during this operation.

At 10:48:47 UTC accounting reported `COMPLETED/0:0`, zero restarts, 70 seconds,
three allocated CPUs and 8 GiB on `a0113`; packing used one thread. The complete
object-ID set, all refs and worktree inventory hashes were identical before
and after. Full integrity checking passed. Loose objects decreased to 22;
packed objects increased from 11,329 to 12,401 in two packs. Only redundant
loose copies were removed; their contents remain recoverable from Git packs.
All scientific files and execution worktrees were retained. No unreachable
object pruning, reflog expiry, history rewrite or full-pack replacement was
requested. The [Git documentation](https://git-scm.com/docs/git-repack) explains
incremental packing and removal of redundant copies.

The [operation receipt](../../results/operations/git_pack_20261003/receipt.json)
records identities and inventory hashes. The submitted script and original
logs remain locally under `.internal/`. This is storage maintenance, not a
scientific result or reference-qualification pass. Observed account file use
afterward was 998,484; other account activity means that delta is not asserted
to be entirely caused by packing. Check quota again before any new checkout.

## Reproducible fixture cleanup on 2026-10-03

The column-feasibility continuation began with 999,879 of 1,000,000 account
files in use. Ten completed pytest fixture roots were inspected before removal:
`dielectric-cad-prefreeze.QQtlWY`, `dielectric-cad-postfreeze.uYrheU`,
`dielectric-cad-expanded.afYfo5`, `cad-terminal-regression.HfAfCF`,
`dielectric-cad-regression.s2eLjZ`, `dielectric-cad-tests.macxP3`,
`dielectric-contract-tests.XxrIRM`, `tcad-postopt-frozen.TBnK9n`,
`hxt-isolation-frozen-regression.WZuqrr`, and `tcad-postopt-regression.bUcijH`,
all directly under the repository's ignored `.internal/` directory.

The exact ten roots contained 528 filesystem entries, including their roots:
24 small text fixtures, 34 directories and 470 pytest links. The regular-file
hashes matched the three reproducible prose-audit fixture forms; all actual
test data had already been cleaned by their fixtures. No pytest process was
running. Only these explicit roots were removed, without following symlinks.
The remaining text can be regenerated by `tests/test_research_prose_audit.py`.
No scientific artifact, archive, Git object or source worktree was removed.

## Column integration fixture cleanup on 2026-10-03

Before the new sparse execution checkout, fourteen more completed fixture roots
were inspected and removed: `hxt-isolation-regression.UUkcw2`,
`hxt-isolation-worker-tests.pUY1uQ`, `hxt-isolation-frozen-tests.eG05yV`,
`hxt-isolation-wiki-tests.VlMLkh`, `tcad-postopt-submission-regression.R13cJM`,
`postopt-terminal-tests.7O0wcG`, `cad-archive-tests.9OzDAT`,
`column-contract-publication.oenG2X`, `column-cad-first.P4PXv6`,
`column-mesh-first.bxiBB3`, `column-planning-first.9NK2u5`,
`layer-grid-dyadic-publication-wiki.zWOn0J`, `column-integration-first.LBGAza`,
and `column-integration-second.dV03Bh`, under the ignored `.internal/` directory.
They contained only completed test directories, pytest links and fifteen tiny
reproducible prose fixtures. The fixture sizes/hashes were checked against the
same test forms above; no test process was active at removal. No scientific
artifact, archive, Git object or execution worktree was removed. Observed file
use afterward was 999,313 of 1,000,000; other account activity can affect quota.

Three new completed integration/regression fixture roots were subsequently
inspected and removed: `column-integration-expanded.aJA6bJ`,
`column-prefreeze-regression.OPi2zN`, and `column-frozen-regression.rJc0Wf`.
After the sparse checkout, four older completed roots were also inspected and
removed: `hxt-isolation-tests.W0cOVg`, `hxt-isolation-tests.vGS9Ma`,
`hxt-frozen-tests.O95t07`, and `hxt-archive-regression.BMcOPG`.
Those four held seven directories, 92 pytest links and the three hash-matched
prose fixtures. Scientific artifacts and execution worktrees were unchanged.
Observed file use after the latter cleanup was 999,689 of 1,000,000.

## Edge preparation fixture cleanup on 2026-10-03

Five completed task-generated roots under `.internal/` were inspected and
removed: `edge-sizing-math.CjigOf`, `edge-sizing-math-fixed.hZaW1J`,
`edge-prefreeze.moio0y`, `edge-prefreeze-fixed.kKFZcK`, and
`edge-feasibility-integration.TddnC8`. Their eight directories, 69 pytest links
and three tiny text fixtures contained no scientific output or worktree.
The three regular files were read and matched the reproducible prose-audit
fixtures. The running frozen regression used a separate untouched root.
No scientific data, Git object, execution worktree or private recovery archive
was removed. Earlier observed account use was 995,578 of 1,000,000 files;
other account activity can change quota independently.

After terminal regression, four further completed roots were inspected and
removed: `edge-frozen.vRLlJk`, `edge-publication-wiki.m8TZWc`,
`edge-archive-tests.6oRm85`, and `edge-terminal-regression.v3xFfp`. Their 13
directories, 101 pytest links and nine tiny regular files contained only
reproducible fixtures; the regular-file contents/hashes matched the three
prose-audit forms. No test process was active. All scientific data, archives
and source worktrees remain preserved.
