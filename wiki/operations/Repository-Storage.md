---
title: Repository Storage and Immutable Evidence
status: VALIDATED; incremental packing completed
last_updated: 2026-10-03
paper_source: false
---

# Repository Storage and Immutable Evidence

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
