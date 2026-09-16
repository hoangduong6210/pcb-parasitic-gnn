---
title: Journal Snapshot 1.1
status: RELEASE CANDIDATE
last_updated: 2026-09-16
paper_source: false
---

# Journal Snapshot 1.1

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
<Hoangduong4316@gmail.com>` and normalizes older spelling and email variants
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

The release candidate contains:

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

## Release boundary

The intended immutable tag is `journal-snapshot-1.1`. The old
`journal-snapshot-1` tag must not move. Publication is complete only after the
new tag and `main` resolve to their expected remote commits and the GitHub CI
run passes. Until that verification is recorded, this page remains a release
candidate rather than a publication receipt.
