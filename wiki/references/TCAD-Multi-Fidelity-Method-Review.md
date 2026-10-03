---
title: TCAD Multi-Fidelity Method and Comparator Review
status: PROPOSED; original-method review; no novelty admission
last_updated: 2026-10-03
paper_source: false
---

# TCAD Multi-Fidelity Method and Comparator Review

## Access and interpretation

Checked on 2026-10-03 as a follow-up to the
[related-work audit](TCAD-Related-Work-Audit.md). This page records specific
method differences that affect the proposed experiment. Reading a method is
not reproducing its result. No external code, trained model or paper PDF was
copied into this repository. The project still lacks a qualified reference and
an established new algorithm; this review does not open training.

## Original methods

### Paired-resolution graph U-Net

[Gladstone and Meidani, arXiv:2412.15372v1](https://arxiv.org/html/2412.15372v1),
Sections 3.1–3.3 and 4.1, were read in full text. MF-UNet exchanges mesh-node
features in both directions across resolutions using nearest-neighbour maps;
Lite transfers upward only. Encoders, decoders and graph blocks share weights.
Training uses paired solutions at every resolution for each case, with a
weighted per-fidelity loss. The beam experiment equalizes data-generation
compute time across methods. Thus neither multi-fidelity graph coupling nor
matched generation cost is new here. The inspected HTML did not identify a
method-code release; availability remains unresolved, not declared absent.

Project inference: our conductor graph and scalar targets are not these mesh
graphs and field targets. A scalar pooled adaptation must be labelled an
adaptation, not a faithful MF-UNet reproduction. Pairing every level also differs
from a large low-fidelity set with only a selected higher-fidelity subset.

### Low-fidelity latent-feature transfer

[Liu et al., NeurIPS ML4PS workshop 2022](https://ml4physicalsciences.github.io/2022/files/NeurIPS_ML4PS_2022_117.pdf),
Sections 2–3 and the reproducibility checklist, were read in full text. MFT
trains a coarse model, interpolates its latent features and provides them to a
separate fine model. The wheel-contact case predicts a correction to the
projected coarse prediction. Its high-only HF-ST control receives additional
high-fidelity samples to compensate for the coarse-data generation cost.
The checklist identifies the original code and data as proprietary.

Project inference: ordinary weight initialization followed by fine-tuning is
not the full MFT method. Include a clearly labelled scalar latent-conditioning
adaptation alongside simple pretraining/fine-tuning and residual correction.
Give high-only models the same measured generation-cost opportunity; equal
high-fidelity sample counts alone do not answer the cost-efficiency question.

### Finite-element convergence learning

The [Black and Najafi institutional record](https://researchdiscovery.drexel.edu/esploro/outputs/journalArticle/Learning-finite-element-convergence-with-the/991019169785704721)
describes low-fidelity projections and subgraph-based high-fidelity prediction
for two-dimensional elastostatics. This directly overlaps broad claims about
learning FEM convergence. The [author repository](https://github.com/MCMB-Lab/MFGNNs)
contains notebooks and models; its README describes research illustration and
states reserved rights. A licenses directory exists, but its contents were not
retrieved in this session. The NSF-hosted manuscript fetch failed. Therefore
full algorithm review and asset-specific reuse terms remain unresolved; public
repository visibility is not treated as permission to vendor code.

### Circuit optimization with selective simulator verification

The publisher's indexed text for
[Cornetta et al., Electronics 2026, 15(1), 105](https://www.mdpi.com/2079-9292/15/1/105)
exposed Sections 2.1, 3.2, 5 and the data-availability statement; direct page
fetch still failed. It describes uncertainty-guided verification, ensemble or
graph surrogates and cached simulator evaluations. The reported SPICE-only
and surrogate experiments use different population/generation settings;
those speed figures cannot establish a matched-budget benefit for this project.
The paper states that source code is not publicly archived because of pending
IP transfer and identifies a simulation-data supplement. This is more specific
than the earlier abstract-only access, but not independent reproduction.

## Comparator decisions before a training protocol

### Additional original extraction methods checked on 2026-10-03

[CapBench, arXiv:2604.11202v1](https://arxiv.org/html/2604.11202v1), Sections
3.1–3.5 and 4.1–4.2, provides a current extraction comparator. Its GNN maps
conductor cuboids to net-level totals using learned attention pooling, unlike
the node-level supervision it attributes to GNN-Cap. The text describes
virtual-edge construction but explicitly excludes those edges in its baseline
setup. Its model comparison predicts total capacitance, using window-level
80/20 splits and separate training per PDK. Its throughput discussion mixes
per-window GNN calls with per-conductor CNN/PCT calls. These distinctions must
be resolved before translating a reported speed ratio into our task.

[Flash-CNNCap, arXiv:2607.23877v1](https://arxiv.org/html/2607.23877v1), Sections
3.1–3.3 and 4.1–4.3, uses positive dense maps aggregated over conductor masks.
A total model and a master-conditioned coupling model reconstruct a Maxwell-style
matrix with one plus the conductor count in forward passes. Conductor-level
labels supervise the map sums; the maps are latent contributions, not field
solutions. Its window-disjoint split is explicitly not design-disjoint. Timing
separates full-matrix inference from the deployed DEF-to-SPEF pipeline, and
the inference comparison uses the same GPU for its neural baselines.

Read-only repository inspection found the following revisions:

- [CapBench](https://github.com/THU-numbda/CapBench/tree/7a6c24c08c3194e2ba62844a84456641b3e44625):
  `7a6c24c08c3194e2ba62844a84456641b3e44625`.
- [Flash-CNNCap](https://github.com/THU-numbda/flash-cnncap/tree/24e35503cf006ceabae0ba102cf19d1b6f58f7c4):
  `24e35503cf006ceabae0ba102cf19d1b6f58f7c4`.

Repository listings and selected metadata/notices were read; no repository,
dataset or checkpoint was installed, copied or executed. Asset-specific reuse
terms and exact paper/configuration alignment still need resolution before
vendoring or reproduction. Public availability is not a reuse-license finding.
The original GNN-Cap full-method access gap is not closed by another paper's
description or by CapBench's expressly different baseline.

Project decisions, not results of a new experiment:

1. Include a raster/CNN scalar-target control on the same PCB inputs, targets,
   generation budget and family-held-out evaluation. Label adaptations clearly;
   neither an on-chip PDK dataset nor net-total capacitance is a drop-in PCB
   two-terminal energy reference.
2. Keep window-disjoint, design-disjoint and family-disjoint claims separate.
   Published within-PDK tests do not establish our proposed OOD setting.
3. Compare equal output scope and count representation construction, inference,
   aggregation and required numerical verification. Do not credit a full-matrix
   pass-count benefit to a single-scalar task without measuring that task.
4. Positive learned contributions and symmetrized couplings alone do not prove
   matrix positive semidefiniteness, charge conservation or field interpretability.
   Any physical-structure claim needs its own invariant and evidence.

These papers strengthen the comparator requirements; they do not establish
this project's novelty or open training/reference gates.

The following are project design requirements inferred from the review, not
claims that these combinations are novel.

| Control | Question answered | Boundary to freeze |
|---|---|---|
| Tuned high-only graph and pooled models | Does additional low-fidelity data beat spending the same budget on higher-fidelity labels? | Measured label cost, tuning allowance and untouched test geometries |
| Low-only and simple scalar correction | Is a complex model needed beyond the cheaper named target? | No relabelling of fixed-fidelity output as qualified reference |
| Pretrain then fine-tune | Does weight transfer suffice? | Encoder initialization and unfrozen layers specified separately from latent conditioning |
| Latent-conditioned higher-fidelity head | Does coarse learned information help at inference? | Predicted versus observed low-fidelity inputs; no uncharged solver query |
| Residual/discrepancy graph and pooled models | Does graph structure improve correction beyond feature models? | Same paired label subset and no held-out higher-fidelity inputs |
| Compatible statistical multi-fidelity model | Is the improvement specific to the proposed learning method? | Original co-kriging method review still needed; adaptation and tuning explicitly named |

Keep two deployment contracts separate. In geometry-only inference, any
low-fidelity conditioning is predicted without a solver. In a solver-assisted
screening arm, actual low-fidelity queries are allowed but charged, including
meshing, failed attempts and preprocessing. Comparing these contracts under one
unqualified inference-time number would be misleading.

Report label-generation, model selection/training and deployment costs
separately, plus their declared total. Freeze the cost-matching rule before
labels; discrete-query leftovers and failed queries cannot be removed after
results. Separate uncertainty against a numerical target from discretization
discrepancy and from error against an independently qualified reference.

No reference result, novelty statement or acquisition algorithm is admitted
by this page. The next method decision must identify a concrete algorithmic
difference and falsifiable design-selection benefit beyond these controls.
GNN-Cap's original method and the MFSBO-CS equations remain priority access
gaps; an inaccessible fetch is not evidence that a comparator is unavailable.
