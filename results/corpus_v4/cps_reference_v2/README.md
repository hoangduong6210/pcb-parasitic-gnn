# Corpus V4 one-thread Cps reference candidate

This directory contains the admitted finite-panel qualification evidence for
the prospective one-thread FEM capacitance reference. It does not contain a
full regenerated dataset yet. The finalized
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
Operational evidence is stored under `qualification/v1/`. Every admitted stage
contains the immutable task records, a preterminal finalizer result, its
manifest, and a separate postterminal admission receipt. The evidence ledger
indexes the terminal receipts rather than treating an empty scheduler queue as
proof of completion.

## Current state

All three qualification gates are postterminal. Gate A completed 45 of 45 R3P16
tasks and passed the nine-layout repeatability rule; its maximum relative Cps
spread was `1.1743017900469024e-14` against the frozen `1e-4` limit. Gate B
completed nine of nine R3P20 tasks. Its R3P16-to-R3P20 domain deltas had median
`0.20585933141613427%` and maximum `1.0860887365856715%`, below the frozen 2%
and 5% limits.

Gate C completed 21 of 21 R4P16 tasks. Its three five-repeat sentinels passed
mesh identity and repeatability. The finite-panel R3P16-to-R4P16 comparison did
not pass the prospectively frozen mesh thresholds: median delta was
`8.004837428851205%` and maximum delta was `13.929354258624992%`, against 2%
and 5%. The terminal receipt therefore records `SCIENTIFIC_NEGATIVE` for mesh
sensitivity while authorizing generation of an explicitly named
multi-fidelity R3/R4 package.

The receipts authorize full R3 v2 and R4 v2 generation, but neither bulk job
has started. No model accuracy, latency, or speed claim is authorized from
this directory. All three receipts admit a qualification stage and numerical
configuration; their
machine-readable `claim_eligible` and `speed_claim_eligible` fields remain
false. The nine selected layouts do not establish corpus-wide domain
convergence, continuum mesh convergence, or physical ground truth.

## Admitted qualification receipts

| Stage | Source and finalizer | Terminal decision | Evidence |
|---|---|---|---|
| Gate A | Source array `6916859`; finalizer job `6916860` | Positive repeatability qualification | [Result](qualification/v1/final/gate_a/source_job_6916859/finalizer_job_6916860/result.json), [manifest](qualification/v1/final/gate_a/source_job_6916859/finalizer_job_6916860/FINAL_MANIFEST.json), [admission](qualification/v1/admission/gate_a/source_job_6916859/finalizer_job_6916860/FINAL_ADMISSION.json) |
| Gate B | Source array `6917229`; finalizer job `6917238` | Positive finite-panel domain-sensitivity qualification; R3 generation authorized | [Result](qualification/v1/final/gate_b/source_job_6917229/finalizer_job_6917238/result.json), [manifest](qualification/v1/final/gate_b/source_job_6917229/finalizer_job_6917238/FINAL_MANIFEST.json), [admission](qualification/v1/admission/gate_b/source_job_6917229/finalizer_job_6917238/FINAL_ADMISSION.json) |
| Gate C | Source array `6923579`; finalizer job `6923586` | Three-sentinel R4 repeatability positive; finite-panel mesh sensitivity negative; explicit multi-fidelity generation authorized | [Result](qualification/v1/final/gate_c/source_job_6923579/finalizer_job_6923586/result.json), [manifest](qualification/v1/final/gate_c/source_job_6923579/finalizer_job_6923586/FINAL_MANIFEST.json), [admission](qualification/v1/admission/gate_c/source_job_6923579/finalizer_job_6923586/FINAL_ADMISSION.json) |

All stages executed from source commit
`4270e11456a575b05f11ec3b67cddda9ce845798` under protocol SHA-256
`912506b638c737b0e87022fb793392ebba5824f50f33fbabdc8913ba3f38908f`.
