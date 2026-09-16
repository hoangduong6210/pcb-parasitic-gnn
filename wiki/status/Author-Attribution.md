---
title: Repository Author Attribution
status: MAILMAP CORRECTED; HISTORICAL GITHUB LINKS UNRESOLVED
last_updated: 2026-09-16
paper_source: false
---

# Repository Author Attribution

The paper author block is independent of Git commit attribution. The current
journal PDF names Duong Viet Hoang and Lun-Min Shih; this page concerns only the
GitHub repository's commit and contributor display.

## Observed mismatch

On 2026-09-16, the remote Contributors API assigned all 155 mainline commits
to `Binben14`, although the raw Git commit author names were Hoang Duong or
Duong Viet Hoang. The repository's `.mailmap` used
`Hoangduong4316@gmail.com` as its canonical address. GitHub linked historical
commits using that address to `Binben14`, while commits made with
`279267588+hoangduong6210@users.noreply.github.com` resolved to
`hoangduong6210` through the remote commit API.

The canonical `.mailmap` identity is now Hoang Duong at the verified
`hoangduong6210` no-reply address. All four historical name/address pairs map
to that identity. `tests/test_author_identity.py` prevents an accidental
reversion. This changes only how mailmap-aware tools report authors; it does
not alter any commit, evidence hash, paper snapshot, or published tag.
The repository-local `user.email` on this machine is also set to the verified
no-reply address so future commits do not reuse the misattributed Gmail
address. This local Git setting is not part of the tracked repository and must
be checked on each new machine.

## Verification and remaining boundary

Locally, run `git shortlog -sne HEAD` and `pytest -q
tests/test_author_identity.py`. Immediately after this correction was pushed,
the remote commit API still linked 29 of 156 mainline commits to `Binben14`
and 127 to `hoangduong6210`; the Contributors API still reported `Binben14`
for 155 commits. These remote results must not be described as fully fixed.
Inspect the Contributors API again after GitHub recalculates its statistics,
but do not assume `.mailmap` alone will change GitHub's individual-commit
account links. GitHub documents that after a historical author email is moved
to another account, the contribution graph may take up to 24 hours to refresh.
See [GitHub's email-association guidance](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/troubleshooting-adding-an-email)
and [contribution troubleshooting](https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions).

If an individual old commit still links to `Binben14`, changing `.mailmap`
cannot edit its stored author email. A complete account-attribution change
would require the owner to remove the historical Gmail address from the
`Binben14` GitHub account, add and verify it on `hoangduong6210`, then wait for
GitHub to rebuild attribution. GitHub permits an email address on only one
account at a time. This account-setting route preserves every repository SHA
and published tag. The alternative requires explicit approval for a full
history rewrite: it changes every descendant SHA and invalidates immutable
tags, wiki receipts, and evidence references. Do not force-push or move
released tags as a routine attribution fix.
