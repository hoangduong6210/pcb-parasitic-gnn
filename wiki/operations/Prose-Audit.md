---
title: Prose and AI-Detection Audit
status: mandatory publication gate
last_updated: 2026-08-17
paper_source: false
---

# Prose and AI-Detection Audit

Scientific prose is reviewed for authorship quality and evidence integrity
before it is exported. No detector can prove human authorship, so the project
does not optimize wording to deceive a classifier or promise a universal score.
The gate combines deterministic checks with human technical editing. If a venue
requires a named detector, its version and result are recorded in the private
release checklist; the detailed report remains outside the repository and paper
packages.

## Deterministic gate

`code/quality/audit_research_prose.py` checks manuscript-source wiki pages for:

- raw double hyphens in prose;
- generic promotional or templated phrases;
- placeholder text and unresolved drafting notes;
- repeated paragraphs;
- scheduler identifiers and private filesystem paths;
- missing `prose_reviewed: true` metadata; and
- private paths or scheduler identifiers in `Paper_Full/main.tex` and
  `Paper_Summary/main.tex`.

Code blocks, command-line flags, Markdown table separators, and front matter are
excluded from punctuation checks. Sensitive-identifier checks still inspect the
complete page body, including inline and fenced code. The audit is a style and
packaging safeguard, not a semantic authorship classifier.

## Human gate

The editor reads every exported paragraph beside its claim and evidence record.
The review asks:

1. Does the paragraph answer a concrete research question?
2. Does each number name its population, metric, unit, and comparison boundary?
3. Are negative and inconclusive findings stated directly?
4. Are transitions necessary, or are they generic filler?
5. Do sentence lengths and structures vary naturally without sacrificing
   precision?
6. Has every citation been opened and checked against the statement it supports?
7. Could a reader distinguish numerical workflow agreement from hardware
   accuracy?
8. Does the prose sound like the responsible researchers' technical judgment?

The final editor records only the review date and approved wiki commit in the
snapshot manifest. Internal AI reports are not publication artifacts.

## Writing rules

Prefer measured verbs such as “measured,” “failed,” “supports,” and “does not
establish.” Avoid promotional adjectives, vague novelty claims, canned summary
paragraphs, and conclusions that restate the abstract. Use one stable term for
each dataset, fidelity, model, and timing boundary.
