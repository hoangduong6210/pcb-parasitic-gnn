---
title: Dataset Registry
status: canonical dataset index
last_updated: 2026-08-17
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
| `D-V2` | `synth_v2` | Submitted solver-surrogate feasibility | Quarantined for current scientific claims |
| `D-C3` | `corpus_v3` | Geometry-contract repair over 1,500 layouts | Geometry root validated; inherited capacitance fidelity is not mesh-converged |
| `D-C4` | `corpus_v4` | Multi-fidelity capacitance package on the accepted v3 geometry root | R3 validated, R4 running, joint finalization pending |
| `D-VENDOR-750341134` | Local vendor assets | Commercial geometry and datasheet anchor | External validation track; not a training corpus |

Corpus v4 is not a fourth geometry generator. It retains the accepted corpus-v3
geometry and FastHenry inductance observations while replacing the ambiguous
capacitance column with named FEM-R3P16 and FEM-R4P16 observations.

## Why v2 is quarantined

The submitted study was a rapid feasibility test of whether a graph surrogate
could imitate a computational workflow. A later audit found inconsistent layer
and vertical coordinates, overlapping conductor volumes, board overrun, and a
mixed analytical inductance convention that violated passivity. FastHenry and
FEM could also interpret overlapping traces differently. These findings prevent
using v2 to support geometry-valid, production, generalization, or hardware
accuracy claims.

The detailed defect counts remain provisional until the audit is preserved as
a finalized job-backed artifact in the repository. They must not be copied into
a paper from chat notes or an untracked result directory.

## Split boundary

Random splits on v2 and early v3 experiments measure interpolation within a
narrow generator. The current protocol uses swap-closed geometry families and
keeps all fidelities of one geometry in the same partition. Commercial STEP
perturbations require a base-part group split or a declared leave-region-out
test, never a random split of nearby variants.
