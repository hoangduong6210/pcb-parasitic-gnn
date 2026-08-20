---
title: Exhaustive Wiki Index
status: canonical index
last_updated: 2026-08-19
paper_source: false
---

# Exhaustive Wiki Index

## Orientation and governance

| Page | Owns |
|---|---|
| [Wiki Home](README.md) | Authority model and reader routes |
| [Start Here](START-HERE.md) | New-contributor orientation and safe first checks |
| [Glossary](GLOSSARY.md) | Notation, units, fidelity names, and lifecycle terms |
| [Contributing to the Wiki](CONTRIBUTING.md) | Front matter, ownership, review, and update rules |
| [Research System Map](architecture/Research-System-Map.md) | End-to-end data, solver, model, evidence, and publication flow |
| [License and Asset Boundaries](governance/License-and-Assets.md) | Source, dependency, vendor, figure, and publication licensing |
| [Technical Source Map](references/Technical-Source-Map.md) | Bibliography topics, keys, and citation review |

## Status, scope, and decisions

| Page | Owns |
|---|---|
| [Project Status](status/Project-Status.md) | Scientific lifecycle and current blockers |
| [Live Execution](status/Live-Execution.md) | Dated scheduler progress and next operational transition |
| [Limitations](LIMITATIONS.md) | Boundaries that apply across papers and claims |
| [Cps Multi-Fidelity Decision](decisions/0001-cps-multifidelity.md) | Accepted R3/R4 policy and consequences |

## Datasets and geometry

| Page | Owns |
|---|---|
| [Dataset Registry](datasets/Dataset-Registry.md) | v0 through v4 and vendor-track boundaries |
| [Corpus and Target Contract](datasets/Corpus-and-Target-Contract.md) | Active geometry and observation schema |
| [Vendor Geometry Track](datasets/Vendor-Geometry-Track.md) | Commercial STEP, datasheet, macro-model, and perturbation policy |

## Methods

| Page | Owns |
|---|---|
| [Graph Surrogate](methods/Graph-Surrogate.md) | Graph features, MPNN, targets, and training boundary |
| [Strict E3 and EGNN](methods/Strict-E3-and-EGNN.md) | Symmetry proof scope and predictive ablation interpretation |
| [FastHenry Inductance](methods/FastHenry-Inductance.md) | Inductance reference and winding aggregation |
| [FEM Cps Reference](methods/FEM-Cps-Reference.md) | Electrostatic formulation and numerical gates |
| [Geometry Family Splits](methods/Geometry-Family-Splits.md) | Leakage-resistant splits and uncertainty units |
| [Corpus V4 Accuracy Protocol](methods/Corpus-V4-Accuracy-Protocol.md) | Frozen 5 by 5 training, leakage, checkpoint, metric, and reporting contract |
| [Runtime Benchmark](methods/Runtime-Benchmark.md) | Timing boundaries and valid speed comparisons |

## Results and claims

| Page | Owns |
|---|---|
| [Current Claim Language](claims/Current-Claim-Language.md) | Claim IDs, exact wording, status, scope, and evidence mapping |
| [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Submitted and extended-paper claims that are traceable but superseded |
| [FEM R3/R4 Convergence](results/FEM-R3-R4-Convergence.md) | Admitted domain result and rejected mesh claim |
| [Cps R3/R4 Production Discrepancy](results/Cps-R3-R4-Production-Discrepancy.md) | Admitted descriptive fidelity comparison on the frozen selected registry |
| [Corpus V4 Family-Held-Out Accuracy](results/Corpus-V4-Accuracy.md) | Admitted 5 by 5 crossed accuracy result and matched R3/R4 capacitance view |
| [Evidence Ledger](evidence/Evidence-Ledger.md) | Job identifiers, commits, paths, hashes, and claim links |
| [FEM Convergence Ledger](evidence/FEM-Convergence-Ledger.md) | Per-layout convergence values |

## Reproduction and operation

| Page | Owns |
|---|---|
| [Reproducibility](REPRODUCIBILITY.md) | Evidence closure and environment requirements |
| [Research Workflow](operations/Research-Workflow.md) | From question to admitted claim |
| [SLURM Resource Plan](operations/SLURM-Resource-Plan.md) | Frozen allocations and wall-time estimates |
| [SLURM Submission Playbook](operations/SLURM-Submission-Playbook.md) | Exact cluster submission, monitoring, and recovery steps |
| [Prose Audit](operations/Prose-Audit.md) | Technical authorship, citation, style, and AI-detection safeguards |

## Publication source and snapshots

| Page | Owns |
|---|---|
| [Paper Export Contract](manuscript/Paper-Export-Contract.md) | Eligibility gates and immutable snapshot manifest |
| [Paper Outline](manuscript/Paper-Outline.md) | IEEE section map to canonical wiki sources |
| [FEM Cps Sections](manuscript/FEM-Cps-Sections.md) | Existing admitted FEM prose pending consolidation |

## Identifier index

### Current claims

| IDs | Registry | State class |
|---|---|---|
| `C-GEOM-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Admitted with synthetic active-leg scope |
| `C-FEM-001`, `C-FEM-002`, `C-FEM-003` | [Current Claim Registry](claims/Current-Claim-Language.md) | Admitted method, positive domain result, and negative mesh result |
| `C-CPS-DISC-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Admitted deterministic selected-registry fidelity discrepancy |
| `C-E3-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Admitted encoded-graph implementation property |
| `C-CPS-R3-001`, `C-CPS-R4-001`, `C-CPS-FINAL-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Finalized explicit-fidelity artifact lifecycle |
| `C-ACC-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Admitted family-crossed current-corpus accuracy claim |
| `C-LAT-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Blocked current-corpus latency claim |
| `C-VENDOR-001` | [Current Claim Registry](claims/Current-Claim-Language.md) | Proposed external validation track |

### Historical claims

| IDs | Registry | Topic |
|---|---|---|
| `H-ACC-001`, `H-ACC-002`, `H-E3-001`, `H-E3-002` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Accuracy and symmetry |
| `H-LAT-001`, `H-LAT-002`, `H-LAT-003` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Timing boundaries |
| `H-SPD-001`, `H-SPD-002`, `H-SPD-003`, `H-SPD-004` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Derived and paired speed ratios |
| `H-DATA-001`, `H-MODEL-001`, `H-MODEL-002`, `H-TREE-001`, `H-SPARSE-001`, `H-CAPACITY-001`, `H-SIZE-001`, `H-SIZE-002` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Dataset, model, baseline, and generalization studies |
| `H-TARGET-001`, `H-TARGET-002`, `H-FH-001`, `H-FH-002`, `H-ANALYTICAL-001`, `H-CPS-001`, `H-NEUMANN-001` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Label and solver comparisons |
| `H-CORE-001`, `H-CORE-002`, `H-FREQ-001`, `H-RANK-001`, `H-RANK-002`, `H-DECISION-001`, `H-DECISION-002`, `H-SCALE-001` | [Historical Claim Ledger](claims/Historical-Claim-Ledger.md) | Core, frequency, ranking, decision, and scaling studies |

### Evidence, datasets, and decisions

| IDs | Registry |
|---|---|
| `E-C3-GEOM-01`, `E-C4-FEM-01`, `E-C4-CONV-00`, `E-C4-FEAS-01`, `E-C4-CONV-01`, `E-C4-PLAN-01` | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| `E-C4-SUBMIT-00`, `E-C4-SUBMIT-01`, `E-C4-RUN-01`, `E-C4-FINAL-01`, `E-C4-OPS-02`, `E-C4-OPS-03`, `E-C4-RUN-02` | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| `E-C4-DISC-01` | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| `E-C4-ACC-01` | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| `E-V2-PROOF-01`, `E-V2-E3-01`, `E-V2-LAT-01`, `E-V2-GEOM-PENDING` | [Evidence Ledger](evidence/Evidence-Ledger.md) |
| `D-V0`, `D-V1`, `D-V2`, `D-C3`, `D-C4`, `D-VENDOR-750341134` | [Dataset Registry](datasets/Dataset-Registry.md) |
| Decision `0001` | [Cps Multi-Fidelity Decision](decisions/0001-cps-multifidelity.md) |
| Paper snapshots | Package identity and hashes live in each paper directory README; future exports also carry a snapshot manifest. |
