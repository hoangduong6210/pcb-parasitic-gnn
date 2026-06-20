# A License-Clean Graph Neural Network for Fast Parasitic Extraction in PCB-Embedded Planar Magnetics

A geometry-aware, message-passing graph neural network (GNN) that predicts the four
lumped parasitics — inter-winding capacitance `C_ps` and the self/leakage inductances
`L_p`, `L_s`, `L_m` - of an 8-layer planar-LLC PCB winding in about **1 ms**, fast
enough to screen hundreds of candidate layouts inside a design loop where a 3-D field
solver is too slow and the analytical model is the wrong number.

The implementation is deliberately **license-clean** (pure PyTorch, no GPL, no
`torch-geometric`) so it can be embedded in an open design tool.

## Highlights

- **Field-grade accuracy vs 3-D solvers.** Trained against 3-D reference solvers
  (a partial-element inductance solver and a 3-D electrostatic finite-element solver),
  the network reaches **3.2 % median error on `C_ps`** (R² ≈ 0.95) and **2.6–3.8 % on
  the inductances** - not just self-consistency with its analytical teacher.
- **Speed–accuracy trade-off.** It returns this solver-grade vector roughly
  **4,300× faster** than the 3-D solvers it matches: ~1,000 interleavings in about a
  second instead of well over an hour.
- **A ranking head where it matters.** A pairwise margin-ranking head orders unseen
  layout variants at family-disjoint Spearman ρ = 0.93; on the *lateral-registration*
  lever (in-plane x–y overlap) the position-blind analytical model cannot rank at all,
  whereas the GNN tracks the 3-D solver at ρ = 0.95.
- **Honest negatives included.** An `E(n)`-equivariant variant gives no gain, and a
  dense all-pairs graph is slower than the analytical baseline (a sparse k-NN variant
  overtakes it). All accuracy here is solver-grade, not yet hardware-anchored.

## Repository layout

```
.
├── code/        # the GNN, the reference solvers, and all experiments (pure PyTorch)
├── results/     # the measured run artifacts (JSON) behind the reported numbers
├── figures/     # the paper figures (PDF + PNG)
└── LICENSE
```

Key modules in `code/`:

| File | Role |
|------|------|
| `gnn_baseline.py`           | geometry-aware message-passing GNN (~275k params, pure PyTorch) |
| `gnn_equivariant.py`        | the `E(n)`-equivariant variant (reported negative) |
| `pcb_graph.py`              | node/edge/graph dataclasses + feature encoding |
| `planar_to_graph.py`        | planar layout → graph + analytical all-pairs PEEC reference labels |
| `generate_synth.py`         | synthetic 8-layer planar-LLC layout generator |
| `fasthenry_ref.py`          | 3-D partial-element inductance reference |
| `fem_capacitance_3d.py`     | 3-D electrostatic finite-element `C_ps` reference |
| `run_research13_pipeline.py`| train/eval: per-target RMSE/R² + measured inference timing |
| `scaling_experiment.py`     | measured wall-time scaling (dense vs sparse k-NN vs O(N²)) |
| `experiments_*.py`          | the field-grade relabel, ranking, decision-regret, and ablation studies |
| `make_figures.py`           | regenerates the figures from the run artifacts |

## Quick start

```bash
cd code
pip install -r requirements.txt          # numpy, scipy, torch (+ scikit-fem/gmsh for the 3-D C_ps reference)
python generate_synth.py                 # build the synthetic layout corpus
python run_research13_pipeline.py        # train + evaluate the GNN, print metrics
python scaling_experiment.py             # measured wall-time scaling
python make_figures.py                   # regenerate the figures
```

The heavier 3-D solver passes (`fasthenry_ref.py`, `fem_capacitance_3d.py`) and the
field-grade relabel experiments are CPU-intensive and are intended to run on a compute
cluster.

## Status & limitations

This is a research prototype. Accuracy is validated **solver-vs-solver** against
trusted 3-D field solvers; a measured hardware-board campaign is the stated next step.
The model is trained on synthetic 8-layer planar-LLC geometries.

## License

Released under the MIT License — see [LICENSE](LICENSE).

## Authors

Duong Viet Hoang, Lun-Min Shih — Department of Computer Science, Da-Yeh University.
