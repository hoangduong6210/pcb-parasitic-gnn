---
title: Start Here
status: canonical onboarding
last_updated: 2026-08-17
paper_source: false
---

# Start Here

## What this project studies

The project asks whether a graph surrogate can reproduce a declared numerical
workflow for four lumped quantities of synthetic PCB winding active-leg
geometries: inter-winding capacitance, primary and secondary self-inductance,
and winding mutual inductance. It does not yet claim hardware-calibrated
parasitic extraction for arbitrary routed boards.

The current work repairs the geometry and label weaknesses discovered after the
conference snapshot. Corpus v3 supplies geometry-valid layouts and inductance
observations. Corpus v4 adds explicit capacitance fidelities and a family-aware
evaluation protocol.

## Read these five pages first

1. [Project Status](status/Project-Status.md) states what is complete and what is
   blocked.
2. [Dataset Registry](datasets/Dataset-Registry.md) prevents accidental mixing
   of historical and current corpora.
3. [Claim Registry](claims/Current-Claim-Language.md) defines what may be said.
4. [Limitations](LIMITATIONS.md) defines what has not been demonstrated.
5. [Reproducibility](REPRODUCIBILITY.md) defines the evidence required for a
   numerical result.

## Repository map

| Path | Purpose |
|---|---|
| `code/core/` | Geometry, graph representation, analytical utilities, and shared contracts |
| `code/models/gnn/` | Baseline MPNN and coordinate-update EGNN implementations |
| `code/solvers/` | FastHenry and electrostatic FEM interfaces |
| `code/experiments/` | Experiment, finalizer, and proof entry points |
| `code/jobs/` | SLURM submission wrappers; heavy work begins here |
| `protocols/` | Frozen machine-readable scientific and execution contracts |
| `datasets/` | Tracked historical datasets and dataset-facing documentation |
| `results/` | Job-scoped evidence and finalized summaries |
| `wiki/` | Canonical scientific knowledge and publication source |
| `Paper_Summary/` | Immutable submitted conference snapshot |
| `Paper_Full/` | Superseded paper snapshot until regenerated from the wiki |

## Safe first checks

The following operations are lightweight and may run on a login node:

```bash
python3 code/quality/build_manifest.py --check
python3 -m pytest -q -p no:cacheprovider tests/test_wiki_contract.py
python3 code/quality/audit_research_prose.py
```

Do not execute field solves or model training on a login node. Before submitting
anything, read the [SLURM Submission Playbook](operations/SLURM-Submission-Playbook.md).
It records cluster limits, failed submission patterns, monitoring commands, and
the recovery procedure.

## How to change scientific knowledge

Open a focused branch and update the evidence, claim, method or result page that
owns the statement. Do not begin by editing a paper. A scientific number needs
a claim ID and an evidence ID before it can enter manuscript-source prose. Run
the wiki contract tests, request technical review, and only then update an
exported paper snapshot.

Terminology and units are defined in the [Glossary](GLOSSARY.md). The complete
page inventory is in the [Exhaustive Index](INDEX.md).
