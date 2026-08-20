# Corpus V4 FEM repeatability evidence

Status: protocol frozen and implementation tested; SLURM execution pending. No
repeatability solve or result is admitted from this directory yet.

This namespace holds the diagnostic prompted by the rejected Corpus V4
paired-latency preflight. It tests whether fresh FEM-R3P16 meshes reproduce the
same discrete system and Cps on the three preselected latency anchors. It is
not a speed or accuracy benchmark, and every shard and final record sets claim
and speed eligibility to false.

The executable protocol is
[`corpus_v4_fem_repeatability_v1.json`](../../../protocols/corpus_v4_fem_repeatability_v1.json).
Its frozen SHA-256 is
`f79129828011ff0ed16ae163cc136d41b67eac0f0cac276fdbdbb3192cadd960`.
The scientific explanation, frozen panel, formulas, gates, and decision rule
are maintained in the
[FEM Mesh Repeatability](../../../wiki/methods/FEM-Repeatability.md) wiki page.
Current execution state belongs in
[Live Execution](../../../wiki/status/Live-Execution.md), while job identifiers
and file hashes belong in the
[Evidence Ledger](../../../wiki/evidence/Evidence-Ledger.md).

## Planned artifact layout

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
