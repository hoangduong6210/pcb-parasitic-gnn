# Extended manuscript package

`Paper_Full` is an independent, page-unlimited extension of the submitted
four-page summary. It follows IEEE two-column formatting and contains only the
manuscript source, bibliography, publication figures, build support, version
metadata, and rendered paper.

## Current status

The package is a working manuscript under a numerical admission hold. Corpus v3
repairs the historical geometry and passivity defects, but its electrostatic-FEM
capacitance labels are not mesh-converged. Corpus v4 must pass the predeclared
convergence, corpus-finalization, multi-seed accuracy, cross-solver, and paired
latency gates before the corresponding values become authoritative.

The manuscript itself does not contain scheduler identifiers or cluster paths.
Scientific provenance and version status live in the repository-level
[`results/`](../results/) and [`datasets/`](../datasets/) documentation.

## Relationship to the submitted summary

| Package | Role | Numerical interpretation |
|---|---|---|
| [`Paper_Summary`](../Paper_Summary/) | Immutable submitted feasibility snapshot | Historical claims are interpreted only through its version-specific ledger |
| `Paper_Full` | Independent extended study | Current values are admitted only from the finalized production corpus |

The Full Paper explains the research progression from exploratory corpus to
geometry-validated corpus without silently rewriting the archived submission.

## Build

From the repository root:

```bash
bash Paper_Full/build.sh
```

The build must complete without missing references, overfull text, color-only
figures, or generated files outside the package build directory. A successful
build reproduces the working document; it does not by itself certify that every
provisional numerical claim has passed its evidence gate.
