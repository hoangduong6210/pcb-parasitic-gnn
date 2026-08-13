# Evidence registry

Result directories are retained for provenance, but presence in Git does not
make a result current. Every claim belongs to exactly one dataset version and
protocol boundary.

## Admission states

| State | Meaning |
|---|---|
| Historical | Reproduces an earlier experiment or submitted-version calculation |
| Quarantined | Useful for audit or debugging but fails a later geometry, label, convergence, or protocol requirement |
| Diagnostic | Produced by a valid intermediate corpus but not eligible for a final four-target claim |
| Accepted | Passed its declared finalizer against one frozen corpus, source tree, environment, and split registry |
| Superseded | Was accepted for an earlier corpus, then replaced by a stronger protocol or corrected reference |

## Dataset-specific status

- Results derived from `synth_v0`, `synth_v1`, or `synth_v2` are historical or
  quarantined. They may explain the submitted feasibility study but are not
  accuracy evidence for geometry-valid PCB windings.
- Corpus v3 passed geometry, uniqueness, paired-solver, and passivity gates for
  1,500 layouts. Its inductance cross-solver and symmetry diagnostics remain
  informative. Its four-target accuracy, ranking, and paired latency are
  nonfinal because the stored `C_ps` discretization is not mesh-converged.
- Corpus v4 is the production candidate. No v4 accuracy, ranking, latency, or
  manuscript headline exists until its convergence and corpus finalizers pass.
- The Würth Elektronik 750341134 track is an external commercial anchor. Its
  outputs must remain separate from synthetic-corpus metrics and cannot be
  labelled hardware validation unless physical measurements are performed.

## Evidence contract

Accepted result packages must resolve to:

1. an immutable dataset and split-registry hash;
2. a clean source commit and per-file source hashes;
3. executable and dependency identities;
4. complete raw records and task-artifact hashes;
5. declared seeds, tolerances, exclusions, and timing boundaries; and
6. a claim-specific finalizer that rejects partial or mixed-provenance inputs.

Heavy solvers and training run only through SLURM. The paper does not print job
identifiers; the result packages may retain them as machine-readable execution
provenance. Current README tables and paper figures must be generated only from
accepted summaries and must never combine rows from different corpus versions.

See [`datasets/README.md`](../datasets/README.md) for geometry, label, split, and
commercial-anchor definitions. See [`Paper_Summary/README.md`](../Paper_Summary/README.md)
for the immutable submitted-version claim ledger.
