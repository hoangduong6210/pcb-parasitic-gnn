---
title: Dataset Registry
status: canonical dataset index
last_updated: 2026-08-18
paper_source: false
---

# Dataset Registry

A dataset version is a scientific scope boundary, not only a file-format
revision. Results from different rows cannot be combined into one accuracy or
latency claim.

| Dataset ID | Repository name | Purpose | Scientific status |
|---|---|---|---|
| `D-V0` | `synth_v0` | Small pipeline smoke test | Historical debugging only |
| `D-V1` | `synth_v1` | Message-passing and scaling feasibility | Historical analytical-teacher study |
| `D-V2` | `synth_v2` | Submitted solver-surrogate feasibility | Archived feasibility snapshot; scope-bound claims only |
| `D-C3` | `corpus_v3` | Geometry-contract repair over 1,500 layouts | Geometry root validated; inherited capacitance fidelity is not mesh-converged |
| `D-C4` | `corpus_v4` | Multi-fidelity capacitance package on the accepted v3 geometry root | R3 validated, R4 running, joint finalization pending |
| `D-VENDOR-750341134` | Local vendor assets | Commercial geometry and datasheet anchor | External validation track; not a training corpus |

Corpus v4 is not a fourth geometry generator. It retains the accepted corpus-v3
geometry and FastHenry inductance observations while replacing the ambiguous
capacitance column with named FEM-R3P16 and FEM-R4P16 observations.

## Role of v2 in the research program

Corpus v2 was designed for a fast feasibility study. Its purpose was to test
whether a graph surrogate could learn the mapping exercised by the reference
workflow and to obtain an initial estimate of the attainable accuracy and
runtime advantage. The study established that the approach was promising
enough to justify a larger, more controlled data program. The submitted
conference paper is retained as the immutable record of that stage.

Corpus v3 and corpus v4 extend the work rather than retroactively replacing the
conference snapshot. The expanded program adds explicit geometry contracts,
family-aware partitions, named capacitance fidelities, mesh and domain gates,
and job-backed provenance. These additions support questions that the rapid v2
study was not intended to answer, including geometry-family generalization,
fidelity sensitivity, and production-oriented reproducibility.

Results from v2 therefore remain valid only within the protocol and scope stated
by the submitted study. They are not pooled with corpus-v3 or corpus-v4 results,
and they are not used as evidence for claims introduced by the expanded
production-oriented evaluation.

## Split boundary

Random splits on v2 and early v3 experiments measure interpolation within a
narrow generator. The current protocol uses swap-closed geometry families and
keeps all fidelities of one geometry in the same partition. Commercial STEP
perturbations require a base-part group split or a declared leave-region-out
test, never a random split of nearby variants.
