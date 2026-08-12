# Code index

Every module, what it does, and which result directory / paper claim it backs.
Run `source env.sh` once per shell before anything else — it puts all
sub-directories on `PYTHONPATH` (imports are flat by design; see the note in the
top-level README).

## `core/` — imported by nearly everything

| File | Role |
|---|---|
| `pcb_graph.py` | `PCBGraph` representation: nodes = trace segments, edges = couplings |
| `planar_to_graph.py` | Layout → graph; also the honest **O(N²) all-pairs analytical PEEC** labeller. Imported by 20 modules |
| `trace_peec.py` | Trace-level PEEC models for foil conductors (Grover / parallel-plate / skin-effect) |
| `pipeline.py` | GNN training + evaluation driver. Imported by 22 modules |
| `experiments_v5.py` | Round-3 study **and** the shared `Norm` / `mk` sample builder. Imported by 15 modules |

> `pipeline.py` and `experiments_v5.py` are experiment scripts that grew into
> libraries. They are kept under `core/` because that is what they now are.

## `models/gnn/`

| File | Role |
|---|---|
| `gnn_baseline.py` | **The proposed model** — geometry-aware edge-conditioned MPNN, 275,339 params, pure PyTorch (no GPL, no torch-geometric) |
| `gnn_equivariant.py` | Legacy exploratory EGNN-style model. Its unconstrained edge-vector path is frame-dependent, so it is not the strict encoded-graph `E(3)` implementation described by the extended paper |

## `solvers/` — 3-D ground truth

| File | Role |
|---|---|
| `fasthenry_ref.py` | Inductance reference via **FastHenry** (external MIT binary) |
| `fastcap_ref.py` | Capacitance via **FastCap**. Did **not** converge on ~0.1 mm gaps — kept as the documented failed path |
| `fastercap_ref.py` | Adaptive-mesh FasterCap; ~3 min/solve, too slow for corpus labelling |
| `fem_capacitance_3d.py` | **The `C_ps` label source** — 3-D electrostatic FEM (scikit-fem + gmsh) |
| `fem_capacitance_ref.py` | Independent 2-D electrostatic FEM cross-check |
| `fem_inductance_ref.py` | Independent multi-filament **Neumann** double-integral — the third solver used for the cross-solver check |
| `fem_cps_worker.py` | Subprocess wrapper so a gmsh C-level segfault cannot kill the parent run |
| `tools/README.md` | How to build FastHenry / FastCap from source |

## `data/`

| File | Role |
|---|---|
| `generate_synth.py` | Seeded corpus generator (`--seed 42`) for `synth_v0` / `v1` / `v2` |
| `gen_corpus_fh.py` | Corpus v2: larger boards + FastHenry-labelled inductances |

## `experiments/`

### `labels/` — the label-quality thread (the paper's core story)

| File | Claim | Result |
|---|---|---|
| `experiments_selfL.py` | Audit: analytical Grover self-L labels are 51–59 % off FastHenry | `run_selfL` |
| `experiments_fh.py` | Establish FastHenry as the inductance ground truth | `run_fh` |
| `experiments_t1b.py` | GNN retrained on filament labels → 2.2 % vs FastHenry | `run_t1b` |
| `experiments_fhlabels.py` | **All three** inductances against FastHenry (2.8/3.8/2.6 %) | `run_fhlabels` |
| `experiments_femcps.py` | `C_ps` against 3-D FEM (3.2 %, R²=0.953) | `run_femcps` |
| `experiments_allfield.py` | FastCap attempt — **negative** (R² = −0.388) | `run_allfield` |
| `fem_validate_total.py` | GNN vs independent FEM on total `C_ps` | `run_femval` |

### `baselines/` — "why a graph?"

| File | Claim | Result |
|---|---|---|
| `experiments_trees.py` | XGBoost / LightGBM / CatBoost / RF on the identical split, three axes | `run_trees` |

### `architecture/`

| File | Claim | Result |
|---|---|---|
| `experiments_t2.py` | Legacy one-seed EGNN-style comparison; retained as historical evidence, not as the controlled strict-`E(3)` proof | `run_t2` |

### `ranking/`

| File | Claim | Result |
|---|---|---|
| `experiments_t4.py`, `experiments_t4b.py` | The original weak ranking (ρ = 0.26) that motivated a ranking objective | `run_t4`, `run_t4b` |
| `experiments_rank.py` | Pairwise margin-ranking head → ρ = 0.93 | `run_rank` |
| `experiments_ranklat.py`, `experiments_ranklat2.py` | Split by lever: interleaving (z) vs lateral registration (x-y) | `run_ranklat2` |
| `experiments_decision.py`, `experiments_declat.py` | Layout-pick **regret** vs the FEM optimum | `run_decision`, `run_declat` |

### `frequency/`, `scaling/`, `anchors/`, `rounds/`

| File | Claim | Result |
|---|---|---|
| `experiments_t3.py` | `R_ac/R_dc(f)` curve, 0.37 % median | `run_t3` |
| `scaling_experiment.py` | Wall-time scaling; sparse k-NN overtakes PEEC at N ≈ 80 | `scaling_v1` |
| `experiments_pfc.py` | Solver anchored to a **real** EER40 GP95 core (datasheet `A_L` ~5 %) | `run_pfc` |
| `experiments_coremfem.py` | Core-inclusive FEM: magnetizing L is 37–73× the winding `M` | `run_coremfem` |
| `experiments_xsolver.py` | Cross-solver check vs the independent Neumann integral | `run_xsolver` |
| `experiments_v2/v3/v4.py` | Multi-part validation and ablation bundles (seeds, ablations, sweeps) | `run_v2`…`run_v4` |

## `figures/`, `quality/`, `jobs/`

| File | Role |
|---|---|
| `make_figures.py` | Regenerates the historical release figures from released result JSONs |
| `make_paper_full_figures.py` | Regenerates the extended manuscript figures from `results/proof_updates/audited_results.json` and released run outputs |
| `dump_predictions.py` | Reloads a checkpoint and dumps per-sample test predictions |
| `quality/paper_style_audit.py` | Deterministic content/style gate used by `Paper_Full/build.sh`; writes its report under `results/proof_updates/` |
| `quality/build_manifest.py` | Builds or verifies the deterministic SHA-256 inventory of the current tracked repository |
| `jobs/submit_*.sh` | 27 SLURM scripts, one per experiment. No account code — pass `sbatch -A <your-account> …` |
