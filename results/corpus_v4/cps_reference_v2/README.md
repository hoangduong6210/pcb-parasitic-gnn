# Corpus V4 one-thread Cps reference candidate

This directory is reserved for the prospective one-thread FEM capacitance
reference. It does not contain an admitted dataset yet. The finalized
25-thread R3/R4 package remains under `results/corpus_v4/cps_multifidelity/`
with its original identities and scope.

## Version boundary

The candidate keeps the accepted Corpus V3 geometry bytes unchanged and uses
new target identifiers:

| Fidelity ID | Numerical setting | Intended role |
|---|---|---|
| `cps_fem_r3_p16_t1_v2` | refine 3, padding 16 mm, one Gmsh thread | Candidate bulk fixed numerical target |
| `cps_fem_r3_p20_t1_v2` | refine 3, padding 20 mm, one Gmsh thread | Qualification-only domain comparator |
| `cps_fem_r4_p16_t1_v2` | refine 4, padding 16 mm, one Gmsh thread | Candidate higher-resolution comparator |

No old Cps observation may be copied into this namespace as a new reference.
No new observation may be joined with an old R3 or R4 row to form a
mixed-version accuracy or mesh-sensitivity result.

## Qualification before generation

The executable qualification is staged:

1. Gate A runs five fresh R3P16 meshes on each of nine frozen layouts.
2. Gate B compares admitted R3P16 repeat zero with one R3P20 solve on each
   layout.
3. Gate C, required for a new multi-fidelity route, tests R4 repeatability on
   three sentinels and reports the nine-layout R3/R4 mesh sensitivity.

The three sentinels are inherited from target-informed positions in the old
convergence panel. They were not reselected from new v2 outcomes and are not
described as a geometry-only or resource-only sample.

The 1,500-layout R3 generation remains locked until Gates A and B have positive
postterminal receipts. A new 198-layout R4 generation also requires valid,
repeatable Gate C evidence. A negative adjacent-mesh comparison is reported as
a scoped result; it does not merge or rename the two fidelities.

The scientific decision, exact panel, formulas, thresholds, and stop rules are
maintained in
[`wiki/decisions/0002-deterministic-fem-reference.md`](../../../wiki/decisions/0002-deterministic-fem-reference.md).
Operational evidence will be written under `qualification/v1/` and indexed in
the evidence ledger only after terminal admission.

## Current state

`PROTOCOL FROZEN / GATE A NOT RUN`. No production label, model accuracy,
latency, or speed claim is authorized from this directory.
