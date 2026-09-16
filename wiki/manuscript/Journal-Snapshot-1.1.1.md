---
title: Journal Snapshot 1.1.1 Figure Correction
status: RELEASE CANDIDATE
last_updated: 2026-09-16
paper_source: false
---

# Journal Snapshot 1.1.1 Figure Correction

This patch revision corrects two visual defects reported after publication of
[Journal Snapshot 1.1](Journal-Snapshot-1.1.md). The immutable 1.1 tag is retained;
the corrected PDF will use a new tag, `journal-snapshot-1.1.1`.

The numbering below follows the rendered PDF, not the figure-source filenames.
Fig. 5 is the graph/symmetry contract: text in the trace and graph-encoding
boxes previously extended into the arrow gaps. The five boxes now use shorter
lines, more balanced widths, and a drawing-time assertion that every title and
body text bounding box lies inside its containing panel. Fig. 7 is the paired
latency plot: the two approximately 523-second labels previously sat directly
on the horizontal bars. They now sit above the bars, with a drawing-time
clearance assertion. Reviewing the other figures also found and corrected a
pipeline title outside its box in Fig. 1, a geometry key below its frame in
Fig. 2, and numbered bubbles colliding with titles in Fig. 9. The generator
checks text containment for Figs. 1, 5, and 9.

The correction does not change figure data, manuscript claims, the sixty
references, or numerical evidence. The PDF remains eleven pages with nine
monochrome figures. All nine figures were inspected at source resolution; the
five corrected figures were also inspected on the rendered IEEE pages 2, 3, 5,
7, and 8. A new manifest freezes the corrected
generator, graphic files, and PDF after verification.

Publication requires a clean package verifier, deterministic prose and wiki
audits, repository tests, remote `main` and tag hash checks, and a successful CI
run. Until those checks finish, this page describes a release candidate.
