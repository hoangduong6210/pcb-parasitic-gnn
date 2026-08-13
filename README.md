# A License-Clean Graph Neural Network for Fast Parasitic Extraction in PCB-Embedded Planar Magnetics

> **DATA-INTEGRITY HOLD.** A full-corpus audit found that the superseded v2
> generator can assign inconsistent layer and z coordinates, overlapping copper
> volumes, and mixed analytical labels that violate inductance passivity. The v2
> accuracy values and downstream accuracy/ranking claims are quarantined as
> exploratory pipeline records, not current physical-accuracy evidence. Corpus
> v3 repairs the geometry and label consistency, but its capacitance reference is
> not mesh-converged. Corpus v4 and every downstream claim remain gated on a
> predeclared convergence study. The legacy runtime record describes only its
> historical workflow.

A pure-PyTorch, geometry-aware message-passing model for four lumped parasitics
of PCB winding active-leg abstractions. The repository is currently
regenerating its numerical corpus under one geometry contract shared by graph
construction, FastHenry, and electrostatic FEM.

The implementation uses PyTorch without PyG or DGL. Source code is BSD-3-Clause;
external reference solvers are not redistributed.

**Research status:** The released results are
solver-validated, not measurements from a fabricated board. This repository is
an auditable research artifact with regeneration instructions; it is not yet a
download-and-run pretrained reproduction package.

## Manuscript packages

The repository keeps manuscript packages separate from experiment evidence:

| Package | Purpose | Contents |
|---|---|---|
| [`Paper_Summary/`](Paper_Summary/) | **Submitted archival feasibility snapshot** | Immutable source, [`Conference_Submission_ARCHIVE.pdf`](Paper_Summary/Conference_Submission_ARCHIVE.pdf), compatibility build wrapper, and a version-specific [`claim ledger`](Paper_Summary/README.md) |
| [`Paper_Full/`](Paper_Full/) | Extended working manuscript | IEEE LaTeX package, bibliography, publication figures, build script, version metadata, and working PDF |

`Paper_Summary/` preserves exactly what was submitted and is authoritative only
for the wording and arithmetic of that historical version. `Paper_Full/` is the
independent extended study, but it does not become authoritative for numerical
claims until corpus v4 and its downstream evaluations pass their admission
gates. The repository README and [`datasets/README.md`](datasets/README.md)
record the live evidence status.

Build either package from the repository root:

```bash
bash Paper_Summary/build.sh
bash Paper_Full/build.sh
```

The Full Paper package is currently under numerical hold. Building it reproduces
the working document but does not promote its provisional values to accepted
results.

![Pipeline from PCB layout through graph construction and message passing to parasitic estimates](figures/fig1_pipeline.png)

> **Notation.** `M` is the *winding* mutual inductance—a free-space, geometry-driven
> coupling term. It is **not** the magnetizing inductance, which is set by the core
> permeability and is a separate, roughly 37–73× larger quantity (quantified in
> [`results_coremfem.json`](results/run_coremfem/results_coremfem.json)). Earlier drafts of this work wrote `L_m`; that notation was
> ambiguous and has been retired.

## Current evidence status

There is deliberately no current accuracy or speed headline. Corpus v3 contains
1,500 unique geometry-valid, passive, paired-solver records. Multi-split
experiments on that corpus are useful diagnostics, but a subsequent FEM study
found that the stored `C_ps` values are not mesh-converged. Those four-target
accuracy and timing results therefore remain nonfinal.

The next admission gate compares domain and mesh sensitivity on nine stratified
geometries. Only a passing finalizer may select the production FEM setting and
unlock corpus v4 generation. Accuracy, baselines, strict encoded-graph `E(3)`,
cross-solver checks, and paired latency must then be rerun from the same frozen
v4 corpus and split registry. See [`datasets/README.md`](datasets/README.md) for
the version boundaries and [`results/README.md`](results/README.md) for evidence
status.

## Layout

```
code/          source, grouped by role see code/README.md for the file index
├── core/            graph representation, analytical PEEC labels, train/eval driver
├── models/gnn/      the proposed MPNN + the E(n)-equivariant variant
├── solvers/         3-D numerical references: FastHenry, FastCap/FasterCap, scikit-fem
├── data/            seeded corpus generators
├── inference/       safe state-dict-only NumPy bundle loader
├── experiments/     one directory per claim:
│   ├── labels/          the label-quality thread (the paper's core story)
│   ├── baselines/       gradient-boosted trees "why a graph?"
│   ├── architecture/    equivariance (negative result)
│   ├── ranking/         ranking head + layout-decision regret
│   ├── frequency/       R_ac/R_dc(f)
│   ├── scaling/         wall-time scaling
│   ├── anchors/         real commercial core, cross-solver check
│   ├── proofs/          strict-E(3), paired latency, and legacy timing protocols
│   └── rounds/          multi-seed validation and ablation bundles
├── figures/         legacy and extended-paper figure generators
├── quality/         manifest and release-integrity checks
├── jobs/            portable SLURM submit scripts plus shared environment helper
└── env.sh           puts every sub-directory on PYTHONPATH
results/       run outputs plus the proof-update aggregate used by paper figures
figures/       paper figures (PDF + PNG)
Paper_Full/    extended manuscript package only
Paper_Summary/ historical summary manuscript package only
datasets/      per-corpus meta.json + labels.json (see "Data" below)
logs/          available SLURM stderr and selected stdout records
MANIFEST.json  deterministic SHA-256 inventory of the current tracked tree
```

Module files are grouped by directory but their imports stay flat
(`from gnn_baseline import ...`). Several `experiments_*` files are de-facto
libraries  `experiments_v5` is imported by 15 other modules  so splitting them
into packages would have meant rewriting the whole import web. Instead every
sub-directory is placed on `PYTHONPATH`:

```bash
source code/env.sh
```

The SLURM scripts in `code/jobs/` do this themselves.

### Active capacitance-reference protocol

The convergence preflight and all downstream numerical work are intentionally
SLURM-only:

```bash
export PCB_GNN_V3_CORPUS_DIR=/absolute/path/to/finalized/corpus_v3
sbatch -A <your-account> code/jobs/submit_corpus_v4_convergence_preflight.sh
```

The preflight executes four declared FEM settings on each of nine layouts. Its
dependent finalizer accepts a production setting only if both critical domain
and mesh comparisons satisfy median <= 2% and maximum <= 5%. The scripts reject
a non-SLURM solve; `--validate-only` checks only schema and protocol wiring.

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

Core requirements are PyTorch + NumPy/SciPy. The 3-D reference solvers additionally
need `scikit-fem`, `gmsh`, and `meshio`; the tree baselines need
`xgboost` / `lightgbm` / `catboost`. See `THIRD_PARTY_NOTICES.md` for the
dependency boundary.

### External reference solvers

`FastHenry` and `FastCap` are **not** redistributed here. Both are MIT-licensed and
build from source in a couple of minutes:

```bash
git clone https://github.com/ediloren/FastHenry2  && make -C FastHenry2
git clone https://github.com/ediloren/FastCap2    && make -C FastCap2
```

Set the binary paths explicitly, or place the executables under
`code/solvers/tools/`:

```bash
export FASTHENRY_BIN=/absolute/path/to/fasthenry
export FASTCAP_BIN=/absolute/path/to/fastcap
export FASTERCAP_BIN=/absolute/path/to/fastercap  # optional
```

## Data

The tracked v0--v2 metadata and labels are retained only for historical audit.
Their command-line generators stop with an explicit quarantine error and cannot
silently feed a current training run. Corpus v3 derives every physical z
coordinate from `layer`, gives every active leg its own conductor volume, checks
board containment and clearance, and has completed its paired-label finalizer.
The v3 `C_ps` discretization remains nonfinal, so the active pipeline is the
convergence-gated corpus v4 refinement described in
[`datasets/README.md`](datasets/README.md).

```bash
source code/env.sh
python3 code/data/gen_corpus_v3.py --n 20 \
  --out results/smoke/corpus_v3/layouts.jsonl
python3 code/experiments/proofs/experiments_corpus_v3_field_labels.py --validate-only
python3 code/experiments/proofs/finalize_corpus_v3.py \
  --source-array-job-id VALIDATION --validate-only
```

Field labelling is intentionally impossible on a login node.  From a clean
checkout, submit the four-layout preflight with a verified FastHenry executable.
Submit the full array only if both preflight tasks accept every record, then
submit the finalizer only if all 30 full-array tasks succeed:

```bash
export FASTHENRY_BIN=/absolute/path/to/fasthenry
sbatch -A <your-account> code/jobs/submit_corpus_v3_preflight.sh
sbatch -A <your-account> code/jobs/submit_corpus_v3_field_labels.sh
export PCB_GNN_V3_SOURCE_ARRAY_JOB_ID=<completed-array-job-id>
sbatch -A <your-account> code/jobs/submit_finalize_corpus_v3.sh
```

The finalizers reject missing layouts, duplicate geometry, solver failures,
passivity violations, dirty tracked trees, mixed commits, source-hash drift, and
record-hash drift. Full schema, version boundaries, split policy, and the
optional Würth Elektronik 750341134 commercial-anchor track are documented in
[`datasets/README.md`](datasets/README.md).

The same gates can be submitted as one scheduler dependency graph; a downstream
stage starts only when its upstream stage exits successfully:

```bash
FASTHENRY_BIN=/absolute/path/to/fasthenry \
  bash code/jobs/run_v3_pipeline.sh --account <your-account>
```

The graph ends after the 50-run random/family-disjoint accuracy finalizer. It
does not update figures or manuscript claims automatically; those remain a
separate admission step after result review.

## Reproducing a result

Do not rerun a v2 experiment as though it were current evidence.  The active
pipeline is ordered and gated: v3 geometry generation, paired field labelling,
corpus finalization, multi-seed training, baselines/ranking, then paired latency
and manuscript figures.  A downstream submission is created only after the
upstream summary and artifact hashes pass.

Submit from the repository root. `slurm_job_env.sh` resolves the checkout from its
own path, while `PCB_GNN_DATA_ROOT`, `PCB_GNN_PYTHON`, and solver variables make
external corpora, environments, and binaries explicit.

The proof environment is pinned in `requirements-proof.txt`. Reproduction means
identical versioned source, verified input and executable hashes, fixed
splits/seeds, raw records, and declared numerical tolerances. Exact wall time and
last-bit floating-point equality are not portable across CPU models; each record
therefore captures the node, dependency versions, binary hash, and timing
distribution rather than promising identical clocks.

### Provenance

Historical and superseded records remain under `results/` for forensic
traceability and are indexed in [`results/README.md`](results/README.md). No
historical number is copied into a current result row, and no v3 four-target
headline is promoted while the capacitance reference is under refinement.

`MANIFEST.json` carries a SHA-256 for every tracked file except itself and can be
verified with:

```bash
python3 code/quality/build_manifest.py --check
```

## Known limitations

1. **No current accuracy claim.** v3 labels, training, and statistics are not yet
   complete; v2 values are quarantined.
2. **Active-leg abstraction.** v3 contains distinct co-directed winding legs but
   excludes returns, vias, terminals, core windows, planes, and full-board routing.
3. **Solver-validated, not hardware-validated.** Agreement with numerical
   references will not establish agreement with a measured board.
4. **Air-core, uniform-dielectric references.** FastHenry carries no magnetic
   material and the FEM uses a uniform effective permittivity.
5. **Synthetic in-distribution study.** Generalization to fabricated winding
   families must be measured separately after the corpus gate passes.

## License

Project source is BSD-3-Clause; see `LICENSE`. Optional external solvers and
Python packages keep their upstream terms and are documented in
`THIRD_PARTY_NOTICES.md`.
