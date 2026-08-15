---
title: PCB Parasitic GNN Research Wiki
status: canonical
last_updated: 2026-08-15
paper_source: false
---

# PCB Parasitic GNN Research Wiki

This directory is the canonical source for project status, scientific claim
language, dataset contracts, methods, results, limitations, and manuscript
material. Future `Paper_Full/` revisions are rendered derivatives of admitted
wiki content. The checked-in Full Paper predates the active mesh-convergence
decision and is superseded until regenerated and audited. The archival summary
manuscript remains immutable.

The wiki separates scientific prose from execution evidence:

- Pages marked `paper_source: true` contain manuscript-ready language and must
  not contain scheduler identifiers, private paths, or machine-specific logs.
- Pages marked `paper_source: false` may contain experiment identifiers, source
  commits, artifact paths, and SHA-256 values.
- A completed computation is not automatically an admitted scientific claim.
  Admission requires a human-reviewed decision recorded in the claim registry.

## Navigation

| Topic | Canonical page |
|---|---|
| Current lifecycle and blockers | [Project Status](status/Project-Status.md) |
| Dataset versions and fidelity semantics | [Corpus and Target Contract](datasets/Corpus-and-Target-Contract.md) |
| Electrostatic FEM method | [FEM Cps Reference](methods/FEM-Cps-Reference.md) |
| Geometry-family splits | [Geometry Family Splits](methods/Geometry-Family-Splits.md) |
| Current numerical results | [FEM R3/R4 Convergence](results/FEM-R3-R4-Convergence.md) |
| Allowed and prohibited claims | [Current Claim Language](claims/Current-Claim-Language.md) |
| Known limitations | [Limitations](LIMITATIONS.md) |
| Reproduction workflow | [Reproducibility](REPRODUCIBILITY.md) |
| SLURM resources and expected wall time | [SLURM Resource Plan](operations/SLURM-Resource-Plan.md) |
| Exact submission, sharding, monitoring, and recovery procedure | [SLURM Submission Playbook](operations/SLURM-Submission-Playbook.md) |
| Manuscript-ready section source | [FEM Cps Sections](manuscript/FEM-Cps-Sections.md) |
| Raw experiment provenance | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| Current fidelity decision | [Decision 0001](decisions/0001-cps-multifidelity.md) |

## Admission workflow

```text
protocol frozen
      ↓
job-backed artifacts finalized
      ↓
hash and numerical gates audited
      ↓
claim language reviewed in wiki/claims
      ↓
result admitted to manuscript-source pages
      ↓
Paper_Full generated and independently audited
```

Machine-generated tables may refresh coverage, resource, and numerical fields.
They must not overwrite human interpretation or promote a result from
`PENDING` to `ADMITTED`.
