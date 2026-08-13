# Dataset registry and geometry contract

This directory separates exploratory corpora, geometry-validated corpora, and
external commercial anchors. A dataset version is a scientific scope boundary,
not merely a file-format revision. Results from different rows below must not be
combined in one accuracy or latency claim.

## Version registry

| Dataset | Purpose | Geometry and labels | Scientific status |
|---|---|---|---|
| `synth_v0` | Small pipeline smoke test | Rapid synthetic geometry and analytical labels | Historical debugging only |
| `synth_v1` | Message-passing and scaling feasibility | Synthetic geometry and analytical labels | Historical teacher-fidelity study only |
| `synth_v2` | Submitted-version solver-surrogate feasibility | Rapid synthetic geometry; mixed analytical and numerical labels; a 332-layout solver-labelled subset | Immutable historical input, invalid for physical-accuracy claims |
| `corpus_v3` | Geometry-contract repair | 1,500 unique layouts; paired FastHenry and electrostatic-FEM labels; all geometry and passivity gates pass | Valid for pipeline evaluation, but its published `C_ps` setting is not mesh-converged |
| `corpus_v4` | Production-candidate reference corpus | Same accepted v3 geometry and inductive labels; `C_ps` recomputed only after a predeclared convergence gate selects the FEM setting | Pending; no current headline result until finalization |
| Vendor `750341134` | Commercial-geometry anchor | Manufacturer datasheet, mechanical STEP assembly, and LTspice macro-model | External validation track; not a training corpus and not hardware measurement performed by this project |

The tracked `synth_v0` through `synth_v2` metadata and label files are retained
for provenance. Large generated layouts and current solver records live in
job-scoped result packages rather than being silently substituted into these
historical directories.

## Why v2 is preserved but quarantined

The submitted study began as a rapid proof of concept: could a graph surrogate
learn the outputs of a computational reference workflow and evaluate much faster
than that workflow? It was not constructed as a production geometry corpus. A
later full-corpus audit found:

- 15,571 of 58,709 traces had inconsistent `layer` and `z_mm` values, affecting
  1,382 of 1,500 layouts;
- 149,099 conductor-volume overlap pairs occurred across 1,498 layouts;
- 407 traces exceeded the board boundary, affecting 86 layouts; and
- all 1,500 public mixed-label records violated
  `|M| <= sqrt(L_p L_s)` because incompatible inductance conventions were
  combined.

These defects do not erase the historical engineering observation that a GNN
can approximate a fixed numerical pipeline. They do prevent interpreting the
reported error as accuracy on physically valid PCB windings. They also prevent
calling the old four-target labels one consistent physical ground truth because
the capacitance and inductance solvers did not see the same effective topology.

Accordingly, v2 may support only an explicitly labelled exploratory
solver-surrogate or throughput statement. It must not support production,
generalization, or hardware-accuracy claims.

## Shared geometry contract

Corpus v3 and later use schema `pcb-planar-active-legs.v3` and the contract in
`code/core/geometry_contract.py`. Every accepted layout must satisfy:

- `layer` is the stackup identity and physical `z_mm` is derived from it;
- every trace has a stable ID and positive length, width, and thickness;
- every conductor box is contained by the declared board envelope;
- conductor volumes are unique and do not overlap;
- same-layer conductors satisfy the declared edge-clearance rule;
- graph construction, FastHenry, and electrostatic FEM consume the same boxes,
  centers, net identities, and units; and
- labels are finite, positive where required, and passive within the declared
  numerical tolerance.

The present scope is still narrower than a fabricated transformer: co-directed,
series-connected active-leg abstractions are modelled. Complete routed return
paths, vias, terminals, core windows, frequency-dependent materials, and
manufacturing tolerances are excluded unless a dataset version explicitly adds
them.

## Record structure and units

Each layout contains a board/stackup description and a list of conductor traces.
The graph exposes conductor geometry, net and layer identities, and relative
spatial relations. The four regression targets are:

| Field | Unit | Meaning | Reference path |
|---|---|---|---|
| `Cps_pF` | pF | Primary-to-secondary winding capacitance under the declared electrostatic boundary conditions | Volume FEM |
| `L_pri_nH` | nH | Primary winding self-inductance | FastHenry |
| `L_sec_nH` | nH | Secondary winding self-inductance | FastHenry |
| `L_mut_nH` | nH | Winding mutual inductance `M`, not core magnetizing inductance | FastHenry |

The solver outputs are numerical references, not absolute ground truth. In
particular, the v3 FEM setting is byte-reproducible but a nine-layout sensitivity
study found a 14.53% median and 23.36% maximum difference from the highest tested
mesh/domain setting. This is why v4 is gated on convergence before its labels or
downstream GNN results can be admitted.

## Split policy

Random splits are reported only as in-distribution interpolation. Robustness and
generalization studies use immutable split registries and preserve groups:

- geometry-family-disjoint splits keep variants of one base construction on one
  side of the split;
- perturbation-family splits keep all nearby changes derived from one nominal
  design together; and
- leave-region-out tests reserve a declared portion of the parameter space,
  such as large offsets or extreme insulation spacing, exclusively for testing.

Near-duplicate perturbations of one STEP model must never be randomly divided
between training and test sets.

## Commercial anchor: Würth Elektronik 750341134

The optional local inputs were downloaded from the manufacturer's WE-PLN product
library. They are intentionally not redistributed by this repository until their
redistribution terms are confirmed. `vendor_750341134.manifest.json` records the
expected filenames and SHA-256 values so a locally acquired copy can be checked.

Official sources:

- product family and CAD/simulation downloads:
  <https://www.we-online.com/en/components/products/WE-PLN?sq=750341134>
- manufacturer datasheet:
  <https://www.we-online.com/components/products/datasheet/750341134.pdf>
- component-library description:
  <https://www.we-online.com/en/support/design-tools/libraries>

Read-only inspection of the downloaded STEP found 15 solid volumes with an
assembly envelope of approximately 29.40 x 25.20 x 10.15 mm. The assembly names
identify the product and several subparts, but they do not provide a trustworthy
electromagnetic material and terminal-net assignment. Therefore importing the
STEP is not equivalent to obtaining a solver-ready winding model. Copper,
dielectric, ferrite permeability, gap, winding connectivity, and terminal
conditions must be assigned and documented independently.

The datasheet supplies product-level constraints, including a 65 uH minimum
inductance for `N1+N2`, a 2:2:4 turns ratio, and a 200 nH maximum leakage
inductance under its stated test conditions. The LTspice archive contains a
vendor macro-model, including lumped winding, leakage, resistance, and
capacitance elements. These quantities are useful external anchors, but they do
not map one-to-one to this project's air-core `L_p`, `L_s`, `M`, and inter-winding
`C_ps` targets. In particular, the product inductance is core-inclusive and the
macro-model capacitances are circuit-model elements.

### What one STEP can establish

A correctly segmented and parameterized STEP track can strengthen the study by
showing:

- that the geometry/meshing pipeline accepts a real commercial package rather
  than only the synthetic active-leg template;
- whether a model trained on synthetic layouts transfers to a commercial
  geometry, which is an out-of-distribution test;
- sensitivity and ranking over physically constrained modifications of one
  commercial design; and
- agreement, after material and boundary calibration, with independent vendor
  datasheet bounds or a measured component.

One STEP cannot by itself establish population-level generalization, exact
material fidelity, or agreement with hardware. A comparison with a datasheet
bound is a product-level sanity check; measurement on physical parts remains the
stronger validation.

### Commercial-geometry-preserving perturbations

One nominal STEP can generate multiple samples without pretending they are
independent products. Candidate controlled variables include:

- lateral registration between winding subassemblies;
- inter-layer and insulation spacing;
- copper thickness;
- winding offset and core-to-winding alignment;
- a documented core-gap variation for core-inclusive solves; and
- mesh/discretization settings for numerical convergence studies, which are
  solver settings rather than new physical samples.

Every variant must retain a `base_part_id`, `geometry_family_id`, perturbation
vector, material assignment, net mapping, source-artifact hash, and mesh protocol.
Training evaluation should use group-disjoint or leave-region-out splits. Mesh
levels of the same physical geometry belong to one convergence record and must
not be treated as separate machine-learning samples.

## Reproduction gates

Heavy generation and all numerical solves are SLURM-only. Lightweight schema
validation may run on a login node. The production sequence is:

1. validate the source geometry and artifact hashes;
2. pass the predeclared FEM convergence gate;
3. generate all solver labels from one frozen commit and environment;
4. finalize only complete, unique, passive, hash-consistent records;
5. freeze split registries before training; and
6. admit a number to the manuscript only after its result package passes the
   claim-specific finalizer.

Current scripts reject heavy execution outside SLURM. See the repository README
for the active submission chain.
