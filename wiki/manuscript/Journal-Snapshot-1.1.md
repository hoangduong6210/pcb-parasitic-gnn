---
title: Journal Snapshot 1.1
status: PUBLISHED; FIGURE LAYOUT SUPERSEDED BY 1.1.1
last_updated: 2026-09-16
paper_source: false
---

# Journal Snapshot 1.1

The immutable 1.1 artifact retains two figure-layout defects in rendered PDF
Figs. 5 and 7. Use [Journal Snapshot 1.1.1](Journal-Snapshot-1.1.1.md) for the
corrected visual package; scientific claims and citations are unchanged.

## Purpose and lineage

Journal Snapshot 1.1 is the expanded, unlimited-length revision of the first
IEEE journal-format export. It does not modify the immutable conference
submission or the original `journal-snapshot-1` tag. The title retains the
conference lineage while naming the additional evaluation scope:

> A License-Clean Graph Neural Network for Fast Parasitic Extraction in
> PCB-Embedded Planar Magnetics: Numerical Fidelity, Symmetry, and Runtime
> Evaluation

The visible PDF author block contains Duong Viet Hoang and Lun-Min Shih,
followed directly by the Department of Computer Science, Da-Yeh University,
Taiwan, and both conference-snapshot contact addresses. The GitHub release uses
the verified no-reply identity of account `hoangduong6210`; `.mailmap` presents
the single canonical research identity `Hoang Duong
<279267588+hoangduong6210@users.noreply.github.com>` and normalizes older spelling and email variants
without rewriting scientific evidence or published history.

## Scientific scope

The manuscript exports the twelve admitted claims already frozen by the paper
manifest. It connects motivation, research evolution, license boundaries,
prior work, electromagnetic theory, the shared geometry contract, numerical
reference construction, graph and symmetry theory, evaluation protocols,
results, discussion, limitations, and reproducibility. It does not reopen any
solver or training stage.

The headline accuracy values remain bound to the deterministic FEM-v2 and
FastHenry numerical-reference package. The runtime ratio remains bound to the
paired all-four-target sequential FastHenry-plus-electrostatic-FEM workflow.
The coordinate-update result remains a non-establishment result, not an
equivalence claim and not a universal conclusion about equivariant models.
The manuscript continues to distinguish numerical-reference agreement from
mesh convergence and fabricated-board accuracy.

## Publication package

The published package contains:

- an eleven-page IEEEtran journal manuscript with a 201-word abstract;
- nine deterministic monochrome figures, all included in the PDF;
- sixty cited and source-validated bibliography records, with no unused or
  undefined entries;
- embedded fonts, deterministic figure generation, LaTeX build tooling, and a
  frozen package manifest; and
- package checks for bibliography coverage, figure inclusion, grayscale
  output, font embedding, private-path exclusion, abstract length, and claim
  inventory.

The reference-validation working ledger and editorial detector reports remain
internal and are excluded from the release package. The public prose audit is a
deterministic style and disclosure check, not an authorship classifier.

## Visual and editorial gates

All nine figures were inspected individually at source resolution and inside
the rendered two-column paper. The audit found no missing panels, clipped text,
label collisions, or figure-caption overlap. Every figure uses grayscale plus
redundant markers, hatches, or line styles. Two complete figure regenerations
produced byte-identical assets.

The expanded prose contains no raw double hyphens, private machine paths,
scheduler identifiers, internal claim identifiers, or unresolved citation
markers. The Related Work section covers planar magnetics, numerical
extraction, FEM discretization, graph learning, equivariance, machine learning
for electronic design automation, statistical comparison, and reproducible
computational research.

## Publication receipt

Immutable tag `journal-snapshot-1.1` and remote `main` were verified on
2026-09-16 at commit
`1ba75c3d539a67dcecf60013388b138417a2338e`. GitHub identifies both author and
committer as account `hoangduong6210`. Branch and tag CI runs
[`35064045532`](https://github.com/hoangduong6210/pcb-parasitic-gnn/actions/runs/35064045532)
and
[`35064045774`](https://github.com/hoangduong6210/pcb-parasitic-gnn/actions/runs/35064045774)
completed successfully. The remote branch set contains only `main`.

The original `journal-snapshot-1` tag remains unchanged and peels to
`b47bb37288448ee08ed5746ef8b8cd6af7fbb229`. The expanded release therefore
adds a versioned publication boundary without rewriting the first snapshot or
the conference submission.
