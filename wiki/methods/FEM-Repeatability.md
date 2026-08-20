---
title: FEM Mesh Repeatability Diagnostic
status: frozen design pending execution
last_updated: 2026-08-20
paper_source: false
---

# FEM Mesh Repeatability Diagnostic

This diagnostic asks whether the fixed FEM-R3P16 workflow reproduces the same
discrete mesh system and capacitance when a layout is solved again. It does not
measure GNN accuracy or latency, and it cannot authorize a speed claim.

## Why this study exists

Paired-latency preflight array `6909354` reran three anchors under the unchanged
reference-agreement tolerance of `1e-4`. All three FastHenry-derived
inductance vectors matched their frozen values. Cps drifted by
`2.6572226e-4`, `1.6908165e-3`, and `1.0065129e-3`, so every task failed
closed. The first anchor also produced a different node count, tetrahedron
count, and discrete-system fingerprint from its frozen R3 artifact despite
matching code, dependency, solver, and base thread contracts.

The evidence establishes that a fresh mesh can change the discrete FEM system.
It does not yet establish whether single-thread Gmsh removes that variation.
The following experiment separates those questions without changing the
observed tolerance.

## Frozen panel and mapping

The panel reuses the three latency anchors selected before the failed rerun.
No layout was added or replaced after observing its drift.

| Latency task | Layout | Family | Frozen R3 Cps |
|---:|---:|---|---:|
| 0 | 3 | `turns-06-06` | 12.0332834138 pF |
| 152 | 734 | `turns-05-11` | 39.6048754623 pF |
| 305 | 1,495 | `turns-05-12` | 40.3162368445 pF |

Each layout has five repeat IDs. Array task `i` maps to panel index
`floor(i/5)` and repeat `i mod 5`, giving 15 SLURM elements. Every element runs
two fresh worker subprocesses on the same allocated node:

- Arm A repeats the existing R3P16 path with 25 Gmsh threads.
- Arm B changes only Gmsh meshing to one thread and remains diagnostic.

Even repeat IDs run A then B. Odd repeat IDs run B then A. This fixed ordering
balances any systematic first-run or second-run effect within an allocation.
The full study contains 30 FEM solves.

## Preserved evidence

Each arm record retains the complete bounded-worker execution, raw worker
result, mesh counts, `system_sha256`, `input_system_sha256`, residual,
iterations, resource telemetry, Cps, and hashes of the raw and enclosing
records. The attempt also records the live SLURM allocation, source commit,
protocol hash, bound input hashes, runtime packages, and anonymous hardware
class. All records set claim and speed eligibility to false.

An element writes into a new immutable job and task directory. Source and input
hashes are checked before solving and after each arm. A partial, missing,
duplicate, resource-invalid, or nonterminal element remains a failure; it is
not replaced after inspecting its numerical outcome.

## Statistics and gates

For five values (C_1,\ldots,C_5), the primary within-layout statistic is

\[
\max_{i<j}
\frac{|C_i-C_j|}
{\max(|C_i|,|C_j|,10^{-12})}.
\]

Each layout and arm also reports the median, minimum, maximum, scaled median
absolute deviation divided by the median, all signed reference drifts, all
absolute reference drifts, unique system-hash count, and node and tetrahedron
ranges. The panel headline is the maximum of the three layout values. This is a
fixed-panel diagnostic, not a confidence interval.

The gates are frozen before execution:

1. All 30 planned arm observations must exist and pass the current numerical
   and resource checks.
2. Each layout and arm must have one unique system hash and invariant node and
   tetrahedron counts across five repeats.
3. Maximum pairwise relative Cps spread must not exceed `1e-4` for either arm.
4. Every Arm-A value must remain within `1e-4` of its frozen R3 reference.
5. Arm-B reference drift is reported but cannot relabel or admit an old result.

The SLURM finalizer first writes a non-admissible preterminal result under a
path containing both the source-array and finalizer job identities. Only after
the finalizer reaches exact `COMPLETED/0:0` may the solver-free admission step
replay all 15 source tasks, 30 arm records, hashes, gates, and live finalizer
accounting. Its immutable `FINAL_ADMISSION.json` is the only artifact accepted
by a new latency preflight. Later full-array and archive verification replay
the same evidence offline, so clean-clone checks do not depend on scheduler
accounting retention.

## Decision rule

If Arm A passes every gate, the unchanged paired-latency preflight may be
considered for a new authenticated rerun. If Arm A fails while Arm B passes its
mesh and repeatability gates, the project must version a deterministic FEM-v2
reference, regenerate the Cps corpus, retrain the model, and rerun accuracy and
latency. Old and new labels must not be mixed. If both arms fail repeatability,
the next design must freeze or serialize the mesh before generating new
labels. A tolerance change made after seeing this study is not an admissible
resolution.

The executable contract is
[`corpus_v4_fem_repeatability_v1.json`](../../protocols/corpus_v4_fem_repeatability_v1.json).
Its frozen SHA-256 is
`f79129828011ff0ed16ae163cc136d41b67eac0f0cac276fdbdbb3192cadd960`.
Current execution state and job-backed results belong in
[Live Execution](../status/Live-Execution.md) and the
[Evidence Ledger](../evidence/Evidence-Ledger.md).
