---
title: Paper Export Contract
status: canonical publication policy
last_updated: 2026-09-16
paper_source: false
---

# Paper Export Contract

`Paper_Summary/` is the immutable submitted conference snapshot.
`Paper_Full/` is a superseded extended-manuscript archive and is not rewritten.
`Paper_Journal_Snapshot_1/` is the journal-format export requested at the research
pause boundary. Its own manifest records the final identity after the package is
built and reviewed. Routine research edits belong in the wiki, not in any paper
package.

The original seven-page export remains immutable at `journal-snapshot-1`.
[Journal Snapshot 1.1](Journal-Snapshot-1.1.md) is a new expanded revision with
its own version and tag; it does not move or overwrite the earlier release.
The [1.1.1 figure correction](Journal-Snapshot-1.1.1.md) supersedes only the
visual layout of Figs. 5 and 7, again under a distinct immutable tag.

## Eligibility gate

A paper may use a scientific statement only when:

- its claim ID is `ADMITTED` or `ADMITTED NEGATIVE`;
- the evidence record resolves to tracked or released artifacts and verified
  hashes;
- the method and result pages carry `paper_source: true` and
  `prose_reviewed: true`;
- uncertainty and limitations accompany the claim where required;
- every citation has been verified against the cited source;
- every figure is generated from the same admitted evidence closure; and
- the prose and package audits pass.

Running, blocked, quarantined, archival, or rejected positive claims may appear
only as clearly labelled history or motivation when the venue requires it. They
cannot appear in an abstract, conclusion, first-screen result table, or CV
summary as current performance.

## Snapshot manifest

Every future paper export records:

```text
snapshot_id
source_wiki_commit
claim_ids and claim versions
evidence_ids and artifact hashes
figure source files and hashes
bibliography file and hash
LaTeX source and PDF hashes
toolchain identity
technical review date
prose review date
```

The manifest lives in the paper package. Raw scheduler logs, job IDs, private
paths, internal AI-detector reports, and working notes remain outside it.

## Export procedure

1. Freeze the admitted claim set at a clean wiki commit.
2. Assemble sections according to the [Paper Outline](Paper-Outline.md).
3. Translate Markdown source into IEEE LaTeX while preserving wording, symbols,
   units, citations, and claim boundaries.
4. Regenerate figures from accepted evidence using monochrome IEEE styling.
5. Build the paper in a clean environment.
6. Run link, claim, citation, package, prose, and visual-overlap audits.
7. Record the snapshot manifest and commit the immutable package.

A later result creates a new snapshot version. It never rewrites the submitted
conference package.
