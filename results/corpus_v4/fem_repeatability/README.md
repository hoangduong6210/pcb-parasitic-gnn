# Corpus V4 FEM repeatability evidence

Status: the corrected execution is complete and has a postterminal negative
receipt. The existing 25-thread Gmsh path failed the frozen mesh-identity and
repeatability gates on all three layouts; the one-thread diagnostic arm passed
those gates on all three. Paired latency remains closed. The rejected first
attempt is preserved without modifying its source artifacts.

This namespace holds the diagnostic prompted by the rejected Corpus V4
paired-latency preflight. It tests whether fresh FEM-R3P16 meshes reproduce the
same discrete system and Cps on the three preselected latency anchors. It is
not a speed or accuracy benchmark, and every shard and final record sets claim
and speed eligibility to false.

The executable protocol is
[`corpus_v4_fem_repeatability_v1.json`](../../../protocols/corpus_v4_fem_repeatability_v1.json).
Its frozen SHA-256 is
`faa71236ce1a77c0d371b2511af2ad3766e57a823c9dd792bee0d4252be438a2`.
The scientific explanation, frozen panel, formulas, gates, and decision rule
are maintained in the
[FEM Mesh Repeatability](../../../wiki/methods/FEM-Repeatability.md) wiki page.
Current execution state belongs in
[Live Execution](../../../wiki/status/Live-Execution.md), while job identifiers
and file hashes belong in the
[Evidence Ledger](../../../wiki/evidence/Evidence-Ledger.md).

## Preserved rejected attempt

Source Job `6915210` completed all 15 elements and wrote the immutable task tree
under [`v1/attempts/job_6915210`](v1/attempts/job_6915210). Finalizer Job
`6915245` rejected a producer-consumer scheduler-record mismatch before it
created a final result. Its
[failure record](v1/failures/finalizer_job_6915245/FAILURE.json),
[scheduler receipt](v1/failures/finalizer_job_6915245/SCHEDULER_RECEIPT.json),
logs, and [failure manifest](v1/failures/finalizer_job_6915245/FAILURE_MANIFEST.json)
are retained as non-admissible operational evidence. They are not a scientific
gate result and are not reused by the corrected rerun.

## Corrected execution result

Source array `6916045` completed all 15 elements with exit code `0:0` under
source commit `64040733763a69c9fe9c0f15423c3ba7ed138cc2`. Finalizer `6916047`
completed with exit code `0:0`, and the solver-free admission validator bound
its terminal accounting to the result. The principal artifacts are:

- [preterminal result](v1/final/source_job_6916045/finalizer_job_6916047/result.json),
  SHA-256 `fb8b6aa0816f8cd37c838968fd4ea93d013ad59a1e6d09cc94271032dad83433`;
- [final manifest](v1/final/source_job_6916045/finalizer_job_6916047/FINAL_MANIFEST.json),
  SHA-256 `8afc59641decccf50cbf2083238703d0cdbe61d236f4d5533bf6a2b5ea8f861a`;
  and
- [postterminal admission](v1/admission/source_job_6916045/finalizer_job_6916047/FINAL_ADMISSION.json),
  SHA-256 `776adb39aaa41dea09972089413977d7762457f453e57dc429d65bd5d0a209fc`.

The maximum pairwise relative Cps spreads for the 25-thread arm were
`5.5882813e-4`, `7.4171889e-3`, and `7.2121703e-3` on layouts 3, 734, and
1,495. All exceed the frozen `1e-4` gate, and each layout produced five
distinct system hashes. The corresponding one-thread spreads were
`4.4273675e-15`, `8.4549511e-15`, and `4.4121269e-15`, with one system hash
per layout and invariant mesh counts. The negative admission therefore sets
`paired_latency_preflight_may_resume=false`. This result supports versioning a
deterministic FEM reference; it does not authorize a speed or accuracy claim.

## Artifact layout

```text
results/corpus_v4/fem_repeatability/v1/
  attempts/job_<source-array>/task_<00..14>/
    started.json
    arm_a_threads25.json
    arm_b_threads1.json
    result.json
    TASK_MANIFEST.json
  final/source_job_<source-array>/finalizer_job_<finalizer>/
    result.json
    FINAL_MANIFEST.json
  admission/source_job_<source-array>/finalizer_job_<finalizer>/
    FINAL_ADMISSION.json
  logs/source_job_<source-array>/
    pcb-v4-fem-repeat-<source-array>_<00..14>.{out,err}
  logs/finalizer_job_<finalizer>/
    pcb-v4-fem-rep-fin-<finalizer>.{out,err}
```

Each of the 15 source-array elements contains two fresh FEM solves, giving 30
arm observations. The SLURM finalizer authenticates every shard, retained raw
worker result, file hash, source binding, logical and raw source-job identity,
and terminal source-array rows before it evaluates the fixed finite-panel
gates. That artifact remains preterminal and cannot open latency execution.
After the finalizer itself reaches `COMPLETED/0:0`, a solver-free admission step
revalidates the preterminal tree and live finalizer accounting, then writes the
only receipt that may authorize a new latency preflight.

Missing, duplicate, partial, resource-invalid, nonterminal, or hash-mismatched
records fail closed. A complete diagnostic may still conclude that the mesh is
not repeatable. Such a negative result is preserved rather than silently
replaced with a retry selected after inspecting its numerical values.
