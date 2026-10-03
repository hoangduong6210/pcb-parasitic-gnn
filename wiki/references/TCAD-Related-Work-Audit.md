---
title: TCAD Related-Work and Contribution Audit
status: PROPOSED; primary-source scoping; novelty not established
last_updated: 2026-10-03
paper_source: false
---

# TCAD Related-Work and Contribution Audit

## Purpose and access boundary

This is a development record for the [TCAD research plan](../manuscript/TCAD-Research-Plan.md),
not an admitted novelty claim or a completed systematic review. Sources were
checked on 2026-10-03. The table distinguishes publisher/author abstracts from
full-text access. An abstract establishes the reported topic, not reproduction
of the method or verification of its performance. No reported cross-paper
speed or error number is treated as directly comparable with this project.

## Primary-source comparison

| Source | Access used and established scope | Consequence for this project |
|---|---|---|
| [ParaGraph, DAC 2020](https://research.nvidia.com/publication/2020-07_paragraph-layout-parasitics-and-device-parameter-prediction-using-graph-neural) | Author-hosted publication abstract: schematic graphs, graph learning and ensembles for layout-dependent parasitics/device parameters | A GNN for parasitic prediction is inherited prior art, not the proposed novelty; distinguish schematic prediction from conductor-geometry extraction |
| [Parasitic-Aware Analog Circuit Sizing, DATE 2021](https://research.nvidia.com/publication/2021-02_parasitic-aware-analog-circuit-sizing-graph-neural-networks-and-bayesian) | Author-hosted abstract: parasitic graph embeddings and dropout uncertainty in Bayesian transistor sizing | Adding uncertainty or a design loop alone is not enough; specify the different PCB target and test a concrete decision benefit |
| [GNN-Cap, TCAD 2024, DOI 10.1109/TCAD.2023.3331942](https://ieeexplore.ieee.org/document/10314730/) | Publisher-indexed abstract available through search; direct page required browser verification. It describes graph-based on-chip interconnect capacitance extraction | Essential extraction comparator; obtain the original method/data/code details before choosing a faithful implementation or declaring incompatibility |
| [Multi-Fidelity Surrogate-Based Optimization for Electromagnetic Simulation Acceleration, TODAES 2020](https://doi.org/10.1145/3398268) | Publisher-indexed abstract available through search; direct fetch denied. Co-kriging combines fast RC extraction and full-wave EM with adaptive sampling for analog/RF design | Multi-fidelity EM optimization and cost reduction already have direct prior art; include a compatible co-kriging/control strategy and matched measured-cost evaluation |
| [A Multi-Fidelity Graph U-Net Model for Accelerated Physics Simulations, arXiv:2412.15372v1](https://arxiv.org/abs/2412.15372v1) | Author-submitted abstract: graph learning across simulation fidelity levels and geometries | Multi-fidelity graph learning itself cannot be claimed new; mesh-field outputs and geometry-level scalar outputs need separate contracts |
| [Multi-Fidelity Surrogate Models for Accelerated Multi-Objective Analog Circuit Design and Optimization, Electronics 2026](https://www.mdpi.com/2079-9292/15/1/105) | Publisher search text and [author-institution record](https://investigacionusp.ceu.es/es/ipublic/item/10260796): graph/ensemble surrogates, uncertainty/diversity-guided high-fidelity verification for analog circuits. Direct publisher fetch was rate-limited | Recent overlap requires full-method review before proposing a new acquisition rule; metadata tracking is supporting infrastructure, not sufficient novelty |

The author-hosted [ASPDAC 2025 invited overview](https://numbda.cs.tsinghua.edu.cn/papers/aspdac253.pdf)
was also opened in full text. It maps pre-layout prediction, post-layout learned
extraction and learning-assisted field solvers, including the authors' CNN-Cap
and NAS-Cap work. It is a discovery map; original papers must support eventual
method and performance comparisons. This record neither redistributes those
papers nor inserts unreviewed citations into a released manuscript.

## Revised working hypothesis, not a novelty assertion

The [subsequent original-method review](TCAD-Multi-Fidelity-Method-Review.md)
now distinguishes joint paired-resolution learning, latent-feature transfer,
simple fine-tuning and FEM-convergence learning. It also establishes that
matched data-generation cost is already used in prior graph/multi-fidelity
work. The access table above is the initial scoping checkpoint; the linked
review owns later full-method access and remaining reproduction constraints.

The inference from these sources is that a generic combination of GNN,
multi-fidelity labels, uncertainty and optimization is not a sufficient TCAD
contribution statement. The narrower question remains whether an explicit
numerical-error and query-cost treatment improves PCB winding design selection
under a fixed compute budget. Any claimed algorithmic difference must be
written down and compared with relevant prior strategies before training.

Keep three quantities separate: discrepancy between named FEM policies,
predictive uncertainty against one policy, and error relative to a separately
qualified reference. Finite mesh agreement must not be converted into a
certified error bound. If qualification fails, retain fixed-fidelity results
and reassess the hypothesis instead of reporting surrogate error as physical
accuracy.

## Pre-experiment comparison requirements

1. Read original methods for the nearest extraction and multi-fidelity design
   papers; record target quantity, geometry inputs, split assumptions, cost
   accounting, code/data availability and licensing. Do not mark a baseline
   unavailable merely because this browsing session could not fetch it.
2. Establish a controlled learning comparison before adaptive selection:
   low-only, high-only, discrepancy/residual multi-fidelity, tuned pooled models
   and graph controls, with identical family-held-out splits and tuning caps.
3. For a later acquisition study, include random, geometry-diversity and a
   compatible multi-fidelity statistical baseline. Charge failed solver
   queries, preprocessing and fitting to the declared cost boundary.
4. Freeze new evaluation geometries and design objectives before labels. The
   inspected development panel cannot become a blind test by changing its name.
5. Require reference-verified design outcomes, not only a prediction metric.
   Report when no method establishes a reliable gain. A negative result does
   not justify post-hoc objective or budget selection.

The [official TCAD submission guidance](https://ieee-ceda.org/publications/tcad/tcad-paper-submissions),
rechecked on the same date, identifies inadequate related work and insufficient
state-of-the-art comparison as potential desk-rejection reasons. The study
above addresses those risks; it does not predict acceptance. Author release
and actual disclosure remain governed by the
[goal record](../status/Q1-Journal-Goal.md) and
[readiness assessment](../manuscript/TCAD-Readiness.md).
