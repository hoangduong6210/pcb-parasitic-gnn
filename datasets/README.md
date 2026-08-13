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

The generator emits only geometry. A 30-task SLURM array computes paired
FastHenry/FEM labels for 1,500 layouts, and a separate SLURM finalizer refuses
partial, dirty, mixed-source, duplicate, or non-passive output. Until the
finalizer emits a summary with all gates true, there is no current corpus.

The scope remains deliberately narrow: co-directed, series-connected active
legs of planar windings. Return conductors, vias, terminals, core windows, and
complete routed loops are excluded and must not be inferred from the data.
