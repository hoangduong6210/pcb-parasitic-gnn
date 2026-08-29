# A License-Clean Graph Neural Network for Fast Parasitic Extraction in PCB-Embedded Planar Magnetics

> **SCIENTIFIC SCOPE BOUNDARY.** The submitted v2 package is retained as a
> feasibility-stage snapshot: it tested whether a graph surrogate could learn a
> simplified solver workflow quickly enough to justify a stricter data program.
> It was not designed to satisfy the later geometry, passivity, family-split, and
> multi-fidelity contracts. Current predictive claims therefore start from the
> replacement geometry-valid corpus. The legacy runtime record describes only
> the historical feasibility workflow.

A pure-PyTorch, geometry-aware message-passing model for four lumped parasitics
of PCB winding active-leg abstractions. The repository now has a finalized
1,500-layout geometry-valid corpus under one contract shared by graph
construction, FastHenry, and electrostatic FEM. The earlier admitted accuracy
baseline remains bound to its archived 25-thread capacitance package. A separate
deterministic one-thread FEM-v2 package has now been admitted at the dataset
generation boundary with 1,500 `cps_fem_r3_p16_t1_v2` observations and 198
`cps_fem_r4_p16_t1_v2` observations. That admission authorizes freezing a new
accuracy protocol. The new protocol, deterministic plan, and execution lock
are now frozen and admit checkpoint-only SLURM training. They do not transfer
the earlier model result, open held-out inference, or establish a new claim.

The implementation uses PyTorch without PyG or DGL. Source code is BSD-3-Clause;
external reference solvers are not redistributed.

**Research status:** Current admitted numerical evidence is solver-based, not
measurements from a fabricated board. The tracked closure includes authenticated
checkpoints and held-out predictions for verification. It is not a general
raw-layout inference package for arbitrary routed boards.

## Manuscript packages

The repository keeps manuscript packages separate from experiment evidence:

| Package | Purpose | Contents |
|---|---|---|
| [`Paper_Summary/`](Paper_Summary/) | **Superseded archival** conference snapshot | Immutable source, [`Conference_Submission_ARCHIVE.pdf`](Paper_Summary/Conference_Submission_ARCHIVE.pdf), compatibility build wrapper, and a version-specific [`claim ledger`](Paper_Summary/README.md) |
| [`Paper_Full/`](Paper_Full/) | Extended manuscript package | LaTeX, bibliography, publication figures, build script, version metadata, and final PDF |

The version-controlled [`wiki/`](wiki/) is authoritative for current project
status, protocols, admitted claims, and manuscript-ready source text. New
contributors should begin with [`wiki/START-HERE.md`](wiki/START-HERE.md), and
all maintained pages are listed in [`wiki/INDEX.md`](wiki/INDEX.md). Future
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

> **Notation.** `M` is the *winding* mutual inductance, a free-space,
> geometry-driven coupling term. It is **not** the core magnetizing inductance.
> Earlier drafts wrote `L_m`; that ambiguous notation has been retired. The
> historical core-anchor comparison is indexed as `H-CORE-002` in the
> [Historical Claim Ledger](wiki/claims/Historical-Claim-Ledger.md).

## Current evidence status

There is deliberately no current speed headline. The 1,500-layout v3 corpus has
passed geometry, identity, finite-label, passivity, clean-source, and
artifact-hash gates. A frozen nine-layout numerical study then found that
refine-3 is stable to the tested 12-to-16 mm domain expansion but fails the
predeclared refine-3/refine-4 mesh-sensitivity gate. Consequently, capacitance
is now represented as explicit fidelity observations: `FEM-R3P16` is a fixed
bulk numerical target and `FEM-R4P16` is a higher-resolution validation
observation, not ground truth.

The completed family-aware fidelity audit paired all 198 selected geometries.
Every FEM-R3P16 observation exceeded its FEM-R4P16 counterpart; the selected
registry median relative discrepancy was 8.479%, with an observed range of
2.754% to 17.517%. This is a descriptive result for a deterministic panel, not
an estimate for a probability sample. It does not establish R4 as continuum or
physical truth and is not a global correction for R3.

Every predictive result derived from the v0 through v2 feasibility geometry,
including former accuracy, ranking, EGNN accuracy comparison, and speed ratios,
remains archival and outside current geometry-valid claims. The strict E(3)
encoded-graph check remains an admitted implementation property, not a
predictive claim.

The pre-FEM-v2 accuracy baseline is complete. It crossed five family-held-out splits
with five initialization seeds, admitted all checkpoints before held-out
inference, and preserved every prediction and metric matrix in a tracked
archive. The [accuracy result](wiki/results/Corpus-V4-Accuracy.md) reports
target-specific agreement with the synthetic numerical references and a
matched R3/R4 capacitance view for the archived 25-thread package. It is not an
accuracy result for the newly admitted one-thread FEM-v2 labels and does not
claim physical-board accuracy. The FEM-v2 model stage has frozen and admitted
its own protocol, deterministic plan, and execution lock. Its 25
checkpoint-only training tasks are next; held-out inference and current-corpus
paired latency remain blocked. See the
[archived accuracy protocol](wiki/methods/Corpus-V4-Accuracy-Protocol.md), the
[FEM-v2 accuracy protocol](wiki/methods/Corpus-V4-FEM-V2-Accuracy-Protocol.md), the
[wiki status](wiki/status/Project-Status.md),
[`datasets/README.md`](datasets/README.md), and
[`results/README.md`](results/README.md).

## Layout

```
code/          source, grouped by role see code/README.md for the file index
├── core/            graph representation, analytical PEEC labels, train/eval driver
├── models/gnn/      the proposed MPNN and tested E(3)-equivariant variant
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

The earlier 25-thread execution stage validated all 1,500 `FEM-R3P16`
observations and 198 selected `FEM-R4P16` observations before joint
finalization. A separate job-backed audit paired all 198 fidelities and froze
the descriptive discrepancy record. The later one-thread FEM-v2 production run
also closed all 1,698 planned observations: 1,500 dense R3/P16 targets and the
same frozen 198-layout R4/P16 panel. Its postterminal admission is a dataset
generation result only: `accuracy_protocol_may_be_frozen=true`, while
`training_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. Exact scientific semantics are maintained in
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

The tracked v0 through v2 metadata and labels are retained only for audit. Their
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

Do not rerun a submitted-v2 experiment as though it were current evidence. The
deterministic FEM-v2 dataset, immutable evaluation join, swap-closed split
contract, accuracy protocol, plan, and execution lock are now frozen. The next
ordered stage is multi-seed checkpoint training through SLURM, followed by an
accepted-set gate, held-out finalization, archive verification, and only then
review of any new claim.

Submit from the repository root. `slurm_job_env.sh` resolves the checkout from its
own path, while `PCB_GNN_DATA_ROOT`, `PCB_GNN_PYTHON`, and solver variables make
external corpora, environments, and binaries explicit.

`requirements-proof.txt` pins the direct proof dependencies; it is not a
hash-locked container or a complete transitive environment snapshot.
Reproduction therefore means protocol-and-artifact reproduction from identical
versioned source, verified inputs and executables, fixed splits/seeds, recorded
runtime distributions, raw records, and declared numerical tolerances. Exact
wall time and last-bit floating-point equality are not portable across CPU and
BLAS implementations. New public records retain scheduler partition and
requested/allocated-resource provenance, dependency versions, executable hashes,
and timing distributions. Private compute-node names are deliberately omitted;
the scheduler job identity remains available to authorized operators for cluster
audit.

### Provenance

The finalized v3 corpus, FEM convergence studies, archived v4 multi-fidelity
package and accuracy study, and the distinct deterministic one-thread FEM-v2
dataset closure resolve to job-backed artifacts and immutable hashes recorded in
[`wiki/evidence/Evidence-Ledger.md`](wiki/evidence/Evidence-Ledger.md).
Historical records remain under `results/` for forensic traceability and are
indexed as quarantined in [`results/README.md`](results/README.md). No
historical scalar is promoted into a current result row.

`MANIFEST.json` carries a SHA-256 for every tracked file except itself and can be
verified with:

```bash
python3 code/quality/build_manifest.py --check
python3 code/quality/verify_corpus_v4_archive.py --require-git-tracked
python3 code/quality/verify_corpus_v4_discrepancy_archive.py --require-git-tracked
python3 code/quality/verify_corpus_v4_fem_v2_production_archive.py --require-git-tracked
```

The accuracy verifier has additional frozen hash arguments; its exact
clean-clone command is maintained in the
[accuracy evidence README](results/corpus_v4/accuracy/README.md#clean-clone-verification).

## Known limitations

1. **Numerical-reference scope.** The current family-crossed accuracy result
   measures agreement with fixed synthetic solver workflows. It is not
   fabricated-board or arbitrary-PCB accuracy, and v2 values remain
   scope-bound history.
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
