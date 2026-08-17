---
title: Technical Source Map
status: canonical citation map
last_updated: 2026-08-17
paper_source: true
prose_reviewed: true
claim_ids: none
---

# Technical Source Map

The bibliography database remains `Paper_Full/references.bib`. This page records
which source families support each method discussion so a paper editor does not
copy citations from an older manuscript without checking them.

| Topic | Bibliography keys | Use in this project |
|---|---|---|
| Planar magnetics and electromagnetic compatibility | `ouyang`, `hurley`, `mclyman`, `erickson`, `ott`, `paul` | Physical context, winding geometry, coupling, and scope |
| Partial-element and inductance references | `ruehli`, `grover`, `fasthenry` | PEEC background, classical inductance, and FastHenry |
| Electrostatic extraction and FEM tooling | `fastcap`, `skfem`, `gmsh` | Numerical reference methods and implementation tools |
| Frequency-dependent winding effects | `dowell`, `roshen`, `kazimierczuk` | Skin, proximity, and magnetic-component context |
| Graph neural networks | `pytorch`, `gilmer`, `battaglia`, `kipf`, `gin` | Implementation framework and message passing |
| Physics and geometry learning | `sanchez`, `pfaff`, `fno`, `deeponet` | Learned physical systems and operator models |
| Electronic-design learning | `mirhoseini`, `gcnrl`, `net2`, `huang_survey`, `paragraph`, `circuitgnn` | Relation to graph learning in EDA |
| Equivariant graph networks | `egnn` | Coordinate-update architecture and symmetry argument |
| Ranking and optimization | `ranknet`, `lambdamart`, `adamw` | Historical ranking objectives and optimizer |

## Citation review rule

Before export, open each cited primary source and verify that it supports the
sentence, formula, or implementation fact. A software citation supports the
software or method, not the physical accuracy of this project's outputs. A
general GNN citation does not establish the strict E(3) property of the local
implementation; that property requires the project's proof artifact.

New references enter the bibliography once, with stable keys and complete IEEE
metadata. The paper snapshot manifest pins the bibliography hash.
