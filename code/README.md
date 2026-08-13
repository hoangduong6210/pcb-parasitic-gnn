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

## `solvers/` — 3-D numerical references

| File | Role |
|---|---|
| `fasthenry_ref.py` | Inductance reference via **FastHenry** (external MIT binary) |
| `fastcap_ref.py` | Capacitance via **FastCap**. Did **not** converge on ~0.1 mm gaps — kept as the documented failed path |
| `fastercap_ref.py` | Adaptive-mesh FasterCap; ~3 min/solve, too slow for corpus labelling |
| `fem_capacitance_3d.py` | **The `C_ps` label source** — 3-D electrostatic FEM (scikit-fem + gmsh) |
| `fem_cps_diagnostic_worker.py` | Isolated mesh/domain-sensitivity worker; used only by the SLURM convergence protocol |
| `fem_capacitance_ref.py` | Independent 2-D electrostatic FEM cross-check |
| `fem_inductance_ref.py` | Independent multi-filament **Neumann** double-integral — the third solver used for the cross-solver check |
| `fem_cps_worker.py` | Subprocess wrapper so a gmsh C-level segfault cannot kill the parent run |
| `tools/README.md` | How to build FastHenry / FastCap from source |

## `data/`

| File | Role |
|---|---|
| `generate_synth.py` | Seeded corpus generator (`--seed 42`) for `synth_v0` / `v1` / `v2` |
| `gen_corpus_fh.py` | Corpus v2: larger boards + FastHenry-labelled inductances |
| `gen_corpus_v3.py` | Geometry-valid v3 active-leg layouts; no labels are mixed into generation |
| `audit_legacy_v2_geometry.py` | Reconstructs and quantifies v2 geometry/passivity failures without field solves |

## `experiments/`

### `labels/` — the label-quality thread (the paper's core story)

| File | Claim | Result |
|---|---|---|
| `experiments_selfL.py` | Audit: analytical Grover self-L labels are 51–59 % off FastHenry | `run_selfL` |
| `experiments_fh.py` | Establish FastHenry as the designated inductance reference | `run_fh` |
| `experiments_t1b.py` | GNN retrained on filament labels → 2.2 % vs FastHenry | `run_t1b` |
| `experiments_fhlabels.py` | Historical single-run FastHenry label study (2.8/3.8/2.6 %); superseded by the paired proof for current claims | `run_fhlabels` |
| `experiments_femcps.py` | Historical single-run 3-D FEM study (3.2 %, R²=0.953); superseded by the paired proof for current claims | `run_femcps` |
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

### `proofs/`

| File | Claim | Result |
|---|---|---|
| `experiments_claim_proof.py` | Paired 3-D solver and end-to-end batch-one latency on the same layouts/node | `proof_updates/jobs/claim_proof` |
| `experiments_strict_egnn_ablation.py` | Five-seed strict encoded-graph `E(3)` ablation, symmetry residuals, and hierarchical bootstrap | `proof_updates/jobs/strict_e3` |
| `experiments_reproduce_legacy_latency.py` | Reproduction of the historical pre-collated batch-forward protocol | `proof_updates/jobs/legacy_latency` |
| `experiments_multisplit_accuracy.py` | Five split seeds crossed with five initialization seeds; emits per-design predictions and a state-dict-only inference bundle | `proof_updates/jobs/multisplit_accuracy` |
| `experiments_fem_convergence.py` | Nine-layout, 81-solve mesh-refinement and domain-padding sensitivity study | `proof_updates/jobs/fem_convergence` |
| `experiments_corpus_v3_field_labels.py` | Geometry-gated 30-task array for 1,500 paired FastHenry/FEM labels | `corpus_v3/jobs` |
| `finalize_corpus_v3.py` | Refuses incomplete/dirty/mixed-source arrays and emits the immutable v3 corpus | `corpus_v3/final` |
| `experiments_corpus_v3_accuracy.py` | Ten-task, 50-run random and family-disjoint v3 accuracy study | `corpus_v3/accuracy/jobs` |
| `finalize_corpus_v3_accuracy.py` | Verifies and aggregates crossed split/initialization uncertainty | `corpus_v3/accuracy/final` |
| `experiments_corpus_v3_latency.py` | Same-node paired FastHenry+FEM versus raw-layout batch-one GNN on 100 held-out v3 designs | `corpus_v3/latency/jobs` |
| `experiments_corpus_v3_strict_e3.py` | Five-seed invariant/strict encoded-graph E(3) ablation on a held-out turn-family split | `corpus_v3/strict_e3/jobs` |
| `finalize_corpus_v3_strict_e3.py` | Paired seed/design bootstrap, equivalence test, and symmetry gate | `corpus_v3/strict_e3/final` |
| `experiments_corpus_v3_trees.py` | RandomForest/ExtraTrees on identical random and turn-family v3 splits | `corpus_v3/trees/jobs` |
| `finalize_corpus_v3_trees.py` | Verifies same-corpus/same-split comparison against finalized GNN accuracy | `corpus_v3/trees/final` |

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
| `experiments_v2/v3/v4.py` | Multi-seed validation, ablations, and architecture sweeps | `run_v2`…`run_v4` |

## `figures/`, `quality/`, `jobs/`

| File | Role |
|---|---|
| `make_figures.py` | Regenerates the historical release figures from released result JSONs |
| `make_paper_full_figures.py` | Regenerates the extended manuscript figures from `results/proof_updates/results.json` and released run outputs |
| `dump_predictions.py` | Reloads a checkpoint and dumps per-sample test predictions |
| `quality/build_manifest.py` | Builds or verifies the deterministic SHA-256 inventory of the current tracked repository |
| `quality/verify_corpora.py` | Verifies SHA-256 identities for the v1/v2 claim corpora; optionally requires the large layout files |
| `inference/predict_safe_bundle.py` | Loads numeric NumPy weights with `allow_pickle=False` and predicts all four targets from JSONL layouts |
| `quality/build_proof_updates.py` | Validates job schemas/clean commits and deterministically builds the manuscript aggregate |
| `jobs/submit_*.sh` | SLURM scripts, one per experiment family. No account code — pass `sbatch -A <your-account> …` |
| `jobs/slurm_job_env.sh` | Shared root, Python, and `PYTHONPATH` resolver for portable batch execution |
