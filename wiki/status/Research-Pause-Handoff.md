---
title: Research Pause and Handoff
status: PAUSED; HANDOFF READY
last_updated: 2026-09-16
paper_source: false
---

# Research Pause and Handoff

## Current state

The active research program is intentionally paused. All dataset-generation,
accuracy, latency, fixed-baseline, and coordinate-update execution chains listed
in [Project Status](Project-Status.md) are closed. A scheduler check at the pause
audit found no active jobs for the project user. No solver run, model training,
recovery, admission, or finalizer should be resumed merely because an older
status entry says `RUNNING`, `PENDING`, or "next". Those entries are dated
historical observations.

The canonical scientific state is the admitted claim set in the
[Current Claim Registry](../claims/Current-Claim-Language.md). The journal
export is packaged separately in [`Paper_Journal_Snapshot_1/`](../../Paper_Journal_Snapshot_1/).
Its package README and snapshot manifest own the final source revision, claim
inventory, artifact hashes, build identity, and PDF identity. The latest
restart anchor is immutable tag `journal-snapshot-1.1.1`; verify it against the
published remote and package manifest before beginning new work. Publication
was remotely verified on 2026-09-16: the tag peels to
`d96dbb02664b3e0aab09b60a67c67872a3fa8762`, both release CI runs passed, and
GitHub exposes only the `main` branch. The earlier `journal-snapshot-1.1` and
`journal-snapshot-1` tags remain preserved at
`1ba75c3d539a67dcecf60013388b138417a2338e` and
`b47bb37288448ee08ed5746ef8b8cd6af7fbb229`, respectively. The 1.1.1
revision corrects figure layout only; scientific claims are unchanged. Tags,
rather than an intermediate worktree branch, define stable handoff identities.

## What is complete

- The 1,500-layout geometry root and both explicit capacitance-fidelity packages
  are finalized under their versioned contracts.
- The one-thread FEM-v2 accuracy study, paired all-four-target latency study,
  fixed pooled-feature baseline comparison, and coordinate-update ablation have
  completed their accepted-set, held-out, archive, and scientific-admission
  stages.
- The coordinate-update study supports only the scoped non-establishment wording
  in `C-E3-FEMV2-001`; it does not establish equivalence or a universal result
  about EGNNs.
- Negative mesh-sensitivity and multithreaded-mesh repeatability findings remain
  part of the scientific record. Neither FEM fidelity is physical ground truth.
- Historical v0--v2 results and the rejected 25-thread latency chain remain
  archival and cannot be promoted into current claims.

## Read order for a new owner

1. Read [Start Here](../START-HERE.md) for scope and repository structure.
2. Read [Project Status](Project-Status.md) for the lifecycle table.
3. Read the [Dataset Registry](../datasets/Dataset-Registry.md) before opening a
   result so target versions are not mixed.
4. Read the [Current Claim Registry](../claims/Current-Claim-Language.md) and
   [Limitations](../LIMITATIONS.md) before reusing any number.
5. Use the [Evidence Ledger](../evidence/Evidence-Ledger.md) to resolve a claim
   to jobs, immutable inputs, source identities, and machine-readable outputs.
6. Read [Reproducibility](../REPRODUCIBILITY.md) and the
   [SLURM Submission Playbook](../operations/SLURM-Submission-Playbook.md) before
   executing anything.

## Safe verification after checkout

These commands inspect tracked artifacts and documentation; they do not train a
model or run a field solver:

```bash
python3 code/quality/build_manifest.py --check
python3 -m pytest -q -p no:cacheprovider tests/test_wiki_contract.py
python3 code/quality/audit_research_prose.py
git status --short
```

Result-specific clean-checkout verification commands live in the owning evidence
README files linked from [Reproducibility](../REPRODUCIBILITY.md). Some archive
verifiers are lightweight, while recomputing checkpoints or field observations
is heavy work and remains SLURM-only.

## Deferred research tracks

These are new studies, not incomplete stages of the closed pipelines:

1. Commercial-geometry transfer under `C-VENDOR-001`, after redistribution,
   segmentation, material, terminal, and matched-quantity review.
2. Fabricated-board measurement with documented fixtures and de-embedding,
   required before any hardware-accuracy claim.
3. A versioned FEM-v2 ranking study with its own estimand, protocol, split and
   admission chain.
4. Stronger capacitance discretization evidence, such as additional refinement
   or an adaptive error estimator; the existing R3/R4 negative mesh result must
   not be overwritten.
5. New model studies only when they state a question not already answered by
   the fixed-baseline and coordinate-update experiments.

## Resume procedure

1. Start from immutable tag `journal-snapshot-1.1.1`, verify it against the published
   remote, then verify the journal snapshot and repository manifests recorded by
   that release. Do not resume from an old detached execution worktree.
2. Choose exactly one deferred question and give it a new protocol identity.
   Existing accepted artifacts remain immutable inputs or comparators.
3. Update the owning dataset, method, status, and decision pages before running
   new work. Add the page to the [Exhaustive Index](../INDEX.md).
4. Freeze inputs, source, execution resources, acceptance gates, and retry rules
   in a clean worktree. Heavy computation must be submitted through SLURM.
5. Preserve failed attempts, finalize exact coverage, update the Evidence and
   Claim registries, and request scientific admission before exporting another
   paper snapshot.

## Boundaries that must survive handoff

- Never combine `D-C4` with `D-C4-FEM-D1-v2` in one result.
- Never call either current capacitance fidelity mesh-converged or physical
  ground truth.
- Never shorten `C-LAT-FEMV2-001` to a generic "faster than 3-D solvers" claim.
- Never treat descriptive crossed-axis or family-cluster intervals as population
  confidence intervals.
- Never interpret the coordinate-update ablation as an equivariant-versus-
  non-equivariant comparison.
- Never place credentials, private paths, raw scheduler logs, or internal
  detector reports in a paper package.
