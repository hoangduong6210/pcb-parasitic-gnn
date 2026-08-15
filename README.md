# A License-Clean Graph Neural Network for Fast Parasitic Extraction in PCB-Embedded Planar Magnetics

> **DATA-INTEGRITY HOLD.** A post hoc audit found that the superseded v2
> generator can assign inconsistent layer and z coordinates, overlapping copper
> volumes, and mixed analytical labels that violate inductance passivity. The v2
> accuracy values and downstream accuracy/ranking claims are quarantined as
> pipeline-debugging records, not current scientific evidence. The replacement
> v3 geometry corpus has passed its gates, but current accuracy remains blocked
> until the fidelity-explicit capacitance corpus and new evaluation protocol are
> finalized. The legacy runtime record describes only that historical workflow.

A pure-PyTorch, geometry-aware message-passing model for four lumped parasitics
of PCB winding active-leg abstractions. The repository now has a finalized
1,500-layout geometry-valid corpus under one contract shared by graph
construction, FastHenry, and electrostatic FEM. Its capacitance labels are
planned for rebuild as an explicit multi-fidelity dataset because the latest
mesh study rejected refine-3 as a mesh-converged reference.

The implementation uses PyTorch without PyG or DGL. Source code is BSD-3-Clause;
external reference solvers are not redistributed.

**Research status:** Current admitted numerical evidence is solver-based, not
measurements from a fabricated board. This repository is
an auditable research artifact with regeneration instructions; it is not yet a
download-and-run pretrained reproduction package.

## Manuscript packages

The repository keeps manuscript packages separate from experiment evidence:

| Package | Purpose | Contents |
|---|---|---|
| [`Paper_Summary/`](Paper_Summary/) | **Superseded archival** conference snapshot | Immutable source, [`Conference_Submission_ARCHIVE.pdf`](Paper_Summary/Conference_Submission_ARCHIVE.pdf), compatibility build wrapper, and a version-specific [`claim ledger`](Paper_Summary/README.md) |
| [`Paper_Full/`](Paper_Full/) | Extended manuscript package | LaTeX, bibliography, publication figures, build script, version metadata, and final PDF |

The version-controlled [`wiki/`](wiki/) is authoritative for current project
status, protocols, admitted claims, and manuscript-ready source text. Future
`Paper_Full/` revisions will be rendered from admitted wiki content; the
currently checked-in Full Paper predates the active mesh-convergence decision
and is superseded until regenerated and audited. `Paper_Summary/` is retained as
an immutable archival snapshot; its timing and equivariance wording is
superseded by the wiki claim registry.

Build either package from the repository root:

```bash
bash Paper_Summary/build.sh
bash Paper_Full/build.sh
```

The current extended build still regenerates its figures from
[`results/proof_updates/results.json`](results/proof_updates/results.json).
That aggregate contains historical material and must not be interpreted as a
current-result admission. New paper content is admitted through the wiki first.

![Pipeline from PCB layout through graph construction and message passing to parasitic estimates](figures/fig1_pipeline.png)

> **Notation.** `M` is the *winding* mutual inductance—a free-space, geometry-driven
> coupling term. It is **not** the magnetizing inductance, which is set by the core
> permeability and is a separate, roughly 37–73× larger quantity (quantified in
> [`results_coremfem.json`](results/run_coremfem/results_coremfem.json)). Earlier drafts of this work wrote `L_m`; that notation was
> ambiguous and has been retired.

## Current evidence status

There is deliberately no current accuracy or speed headline. The 1,500-layout
v3 corpus has passed geometry, identity, finite-label, passivity, clean-source,
and artifact-hash gates. A frozen nine-layout numerical study then found that
refine-3 is stable to the tested 12-to-16 mm domain expansion but fails the
predeclared refine-3/refine-4 mesh-sensitivity gate. Consequently, capacitance
is now represented as explicit fidelity observations: `FEM-R3P16` is a fixed
bulk numerical target and `FEM-R4P16` is a higher-resolution validation
observation, not ground truth.

Every result derived from v0--v2 geometry, including former accuracy, ranking,
strict-symmetry comparison, and speed ratios, remains quarantined from current
geometry-valid claims. After the fidelity corpus is finalized, current accuracy
must be rerun using the frozen swap-closed family registries and crossed split
and initialization seeds. See the [wiki status](wiki/status/Project-Status.md),
[`datasets/README.md`](datasets/README.md), and
[`results/README.md`](results/README.md).

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
wiki/          canonical status, methods, claim language, and evidence ledgers
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

### Robustness and capacitance-reference protocols

Heavy field solves and training are SLURM-only. The completed frozen
refine-3/refine-4 study executed 27 solves over nine layouts: refine-3 at 12 and
16 mm padding and refine-4 at 16 mm. Domain sensitivity passed with median
0.189658% and maximum 2.491566%; mesh sensitivity failed with median 8.273879%
and maximum 13.886399% under the declared 2%/5% gates.

The next execution stage under the frozen protocol generates 1,500
`FEM-R3P16` observations and 198
geometry-selected `FEM-R4P16` observations, three per swap-closed turn family.
It uses one layout and one fidelity per atomic array task, immutable selection
and split registries, and safe resume across job attempts. Exact scientific
semantics are maintained in
[the corpus target contract](wiki/datasets/Corpus-and-Target-Contract.md); job
identifiers and hashes stay in [the evidence ledger](wiki/evidence/Evidence-Ledger.md).

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

The tracked v0--v2 metadata and labels are retained only for audit.  Their
command-line generators now stop with an explicit quarantine error; they cannot
silently feed a current training run.  Corpus v3 derives every physical z
coordinate from `layer`, gives every active leg its own conductor volume, checks
board containment and clearance, and emits geometry without labels.

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

The completed finalizer rejects missing layouts, duplicate geometry, solver failures,
passivity violations, dirty tracked trees, mixed commits, source-hash drift, and
record-hash drift.  Full schema and status details are in
[`datasets/README.md`](datasets/README.md).

The same gates can be submitted as one scheduler dependency graph; a downstream
stage starts only when its upstream stage exits successfully:

```bash
FASTHENRY_BIN=/absolute/path/to/fasthenry \
  bash code/jobs/run_v3_pipeline.sh --account <your-account>
```

This historical v3 graph ended after the corresponding accuracy stages, but
those stages are not admitted as current capacitance evidence after the mesh
gate result. No pipeline updates figures or manuscript claims automatically;
admission remains a separate wiki-reviewed step.

## Reproducing a result

Do not rerun a v2 experiment as though it were current evidence. The active
pipeline is ordered and gated: frozen v3 geometry, explicit R3/R4 observation
generation, multi-fidelity finalization, swap-closed split construction,
multi-seed training, paired evaluation, and only then admitted manuscript
assets. A downstream submission is created only after the upstream summary and
artifact hashes pass.

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

The finalized v3 corpus and FEM convergence studies resolve to job-backed
artifacts and immutable hashes recorded in
[`wiki/evidence/Evidence-Ledger.md`](wiki/evidence/Evidence-Ledger.md).
Historical records remain under `results/` for forensic traceability and are
indexed as quarantined in [`results/README.md`](results/README.md). No
historical scalar is promoted into a current result row.

`MANIFEST.json` carries a SHA-256 for every tracked file except itself and can be
verified with:

```bash
python3 code/quality/build_manifest.py --check
```

## Known limitations

1. **No current accuracy claim.** The geometry corpus is complete, but the
   fidelity-explicit capacitance corpus, training, and statistics are not; v2
   values remain quarantined.
2. **Active-leg abstraction.** v3 contains distinct co-directed winding legs but
   excludes returns, vias, terminals, core windows, planes, and full-board routing.
3. **Solver-validated, not hardware-validated.** Agreement with numerical
   references will not establish agreement with a measured board.
4. **Air-core, uniform-dielectric references.** FastHenry carries no magnetic
   material and the FEM uses a uniform effective permittivity.
5. **Synthetic in-distribution study.** Generalization to fabricated winding
   families must be measured separately from the finalized synthetic corpus.
6. **Unresolved mesh convergence.** FEM-R3P16 is a fixed reproducible numerical
   target, not a mesh-converged or physical ground-truth capacitance reference.

## License

Project source is BSD-3-Clause; see `LICENSE`. Optional external solvers and
Python packages keep their upstream terms and are documented in
`THIRD_PARTY_NOTICES.md`.
