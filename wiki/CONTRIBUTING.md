---
title: Contributing to the Research Wiki
status: canonical governance
last_updated: 2026-09-15
paper_source: false
---

# Contributing to the Research Wiki

## Mandatory wiki synchronization

Every project task must update the wiki before handoff, including monitoring,
review, implementation, experiment execution, commit, push and recovery tasks.
This is a completion requirement, not optional documentation work. A status
check with no change still records the observation date and unchanged state.

Update the semantic owner and the live execution page with verified outcomes,
evidence links, remaining blockers and the next action. Index every new page.
Distinguish a local commit from a successful push: verify the remote branch
hash and record the last confirmed published commit. Preserve historical
failures, but remove obsolete blockers from the current status statement.
Never copy credentials into documentation.

Run the wiki contract tests and deterministic research-prose audit before
committing the update. An execution failure or external blocker does not waive
wiki synchronization: record what failed and what remains. Paper exports
continue to use admitted wiki claims and are generated only on request.

## Page ownership

Each fact has one semantic owner:

| Information | Canonical owner |
|---|---|
| What may be claimed | `claims/` |
| What a computation produced | `evidence/` and `results/` |
| How a method works | `methods/` |
| Dataset meaning and scope | `datasets/` |
| Current work state | `status/` |
| Why a policy was chosen | `decisions/` |
| How to run or recover work | `operations/` |
| How a paper is assembled | `manuscript/` |

Other pages should link to the owner instead of copying mutable numbers. A short
restatement is acceptable only when the claim ID is given and a contract test
protects the duplicated scalar.

## Required front matter

Every Markdown page in `wiki/` declares `title`, `status`, `last_updated` or
`date`, and `paper_source`. A page marked `paper_source: true` also declares
`prose_reviewed: true` before export. Such pages contain no scheduler IDs,
private paths, machine logs, or operational instructions.

## Claim update sequence

1. Freeze the research question, protocol, input registry, split policy, and
   acceptance gates before running the experiment.
2. Execute heavy work through SLURM and preserve every accepted and rejected
   attempt according to the protocol.
3. Finalize exact coverage and add an evidence entry with artifact hashes.
4. Add or update a claim ID. Record exact wording, scope, dataset, evidence,
   uncertainty, limitations, and publication eligibility.
5. Update the owning method or result page.
6. Run the wiki contract and prose audit tests.
7. Request a scientific review that checks the artifact independently of the
   prose.

Never change a protocol cap, remove an outlier, or alter a split after viewing
the scientific result without recording a new decision and new claim identity.

## Status vocabulary

Use `PROPOSED`, `RUNNING`, `VALIDATED`, `ADMITTED`, `REJECTED`, `QUARANTINED`,
`SUPERSEDED`, `BLOCKED`, or `PAUSED`. `VALIDATED` means the artifact passed its
declared gates. `ADMITTED` is a separate human decision about scientific
wording. `PAUSED` means no execution is active and future work must begin from
the indexed handoff state; it does not reopen or invalidate a closed result.

## Review checklist

- Every number resolves to one evidence entry and machine-readable field.
- Units, denominator, population, split, seed, and timing boundary are explicit.
- Negative and inconclusive results are retained.
- A solver observation is not called physical ground truth.
- Historical results are not mixed with current geometry-valid claims.
- Citations are checked against the cited source rather than copied from an old
  manuscript.
- The prose audit passes and a human editor has removed templated or repetitive
  language.
- The exhaustive index links the new page.
