# Dataset status and geometry contract

The v0, v1, and v2 directories are immutable historical artifacts. They are
retained so the public integrity audit can reconstruct the earlier pipeline;
their layouts and labels must not be used for current accuracy, ranking, or
model-comparison claims.

Corpus v3 uses schema `pcb-planar-active-legs.v3` and one geometry contract in
`code/core/geometry_contract.py`. Its non-negotiable checks are:

- `layer` is the stackup identity and physical z is derived from the stackup;
- every trace has a stable ID, positive dimensions, and a board-contained box;
- conductor volumes are unique and non-overlapping;
- conductors on one layer meet the declared edge-clearance rule;
- graph construction, FastHenry, and FEM consume the same boxes and centers;
- labels are finite, positive where required, and satisfy
  `|M| <= sqrt(Lp * Ls)` within the declared numerical tolerance.

The generator emits only geometry. The 30-task SLURM array and independent
finalizer completed for all 1,500 layouts. This frozen source-v3 corpus contains
1,500 unique geometry hashes, inherited FastHenry inductance observations and
archival FEM capacitance observations, passive inductance matrices, one clean
source identity, and a closed artifact-hash manifest. Those inherited
capacitance observations are not the planned `FEM-R3P16`/`FEM-R4P16`
multi-fidelity corpus.

Capacitance now follows an explicit multi-fidelity contract:

| Fidelity | Numerical setting | Current role |
|---|---|---|
| `FEM-R1P8` | refine-1, pad 8 mm | Archival v3 observation |
| `FEM-R2P12` | refine-2, pad 12 mm | Legacy lower-cost observation; not validated truth |
| `FEM-R3P16` | refine-3, pad 16 mm | Planned fixed bulk numerical target |
| `FEM-R4P16` | refine-4, pad 16 mm | Planned higher-resolution validation subset |

On the frozen nine-layout study, the refine-3 12-to-16 mm domain comparison
passed (median 0.189658%, maximum 2.491566%), while the refine-3/refine-4 mesh
comparison failed (median 8.273879%, maximum 13.886399%). Therefore
`FEM-R3P16` is not described as mesh-converged and neither fidelity is described
as physical ground truth.

The multi-fidelity outputs must preserve each observation in long form with its
geometry hash, fidelity ID, solver settings, residual, resource record, source
identity, environment, and artifact hash. Missing higher-fidelity observations
remain missing; loaders may not silently substitute a lower fidelity. See the
canonical [corpus and target contract](../wiki/datasets/Corpus-and-Target-Contract.md).

The scope remains deliberately narrow: co-directed, series-connected active
legs of planar windings. Return conductors, vias, terminals, core windows, and
complete routed loops are excluded and must not be inferred from the data.

Execution identifiers and immutable corpus hashes are recorded separately in
the [evidence ledger](../wiki/evidence/Evidence-Ledger.md).
