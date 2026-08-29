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
capacitance observations are not the active `FEM-R3P16`/`FEM-R4P16`
multi-fidelity corpus.

The archived 25-thread capacitance package follows this explicit multi-fidelity
contract:

| Fidelity | Numerical setting | Current role |
|---|---|---|
| `FEM-R1P8` | refine-1, pad 8 mm | Archival v3 observation |
| `FEM-R2P12` | refine-2, pad 12 mm | Legacy lower-cost observation; not validated truth |
| `FEM-R3P16` | refine-3, pad 16 mm | Fixed bulk target; 1,500 task artifacts validated |
| `FEM-R4P16` | refine-4, pad 16 mm | Higher-resolution 198-layout subset; validated and jointly finalized |

On the frozen nine-layout study, the refine-3 12-to-16 mm domain comparison
passed (median 0.189658%, maximum 2.491566%), while the refine-3/refine-4 mesh
comparison failed (median 8.273879%, maximum 13.886399%). Therefore
`FEM-R3P16` is not described as mesh-converged and neither fidelity is described
as physical ground truth.

The 198-layout R4 registry contains three entries from each of 66 swap-closed
turn-count families. It preserves nine mandatory anchors from the earlier
convergence design, whose selection used capacitance order statistics; the
other 189 entries were selected with geometry-only descriptors. No production
R3/R4 discrepancy was used to alter the registry. On this exact deterministic
panel, all 198 R3 values exceeded their paired R4 values. The median relative
discrepancy was 8.479%, with an observed range of 2.754% to 17.517%. These
descriptive values are not a probability-sampled full-corpus estimate or a
global correction.

The finalized multi-fidelity outputs preserve each observation in long form with its
geometry hash, fidelity ID, solver settings, residual, resource record, source
identity, environment, and artifact hash. Missing higher-fidelity observations
remain missing; loaders may not silently substitute a lower fidelity. See the
canonical [corpus and target contract](../wiki/datasets/Corpus-and-Target-Contract.md).

## Deterministic one-thread FEM-v2 dataset

`D-C4-FEM-D1-v2` is a separate numerical-target version on the unchanged
1,500-layout geometry root. It contains 1,500
`cps_fem_r3_p16_t1_v2` observations and the frozen 198-layout
`cps_fem_r4_p16_t1_v2` panel, for 1,698 long-form observations. Every source
task used one Gmsh thread. The joint finalizer and its solver-free
postterminal admission completed without pending or terminal-negative tasks.

The canonical closure is under
[`results/corpus_v4/cps_reference_v2/production/v1/`](../results/corpus_v4/cps_reference_v2/production/v1/README.md).
Its dataset source-set SHA-256 is
`f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b`.
The final admission has SHA-256
`b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed`;
the long-form observation table has SHA-256
`83a771bf318c0660731c6e5d1e5e91a6b15642e178b8172b2b46dedb656a1784`.
The tracked archive manifest has SHA-256
`89b2e235ff5d1aaa06ab589a95578f7a3ef129d60f2386494ea2d1686de6dbbc`.

This receipt admits dataset generation and sets
`accuracy_protocol_may_be_frozen=true`. It also retains
`training_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. The archived accuracy result above is not a model
evaluation of these one-thread observations. A new accuracy protocol, plan, and
execution lock must be frozen and admitted before training begins.

The scope remains deliberately narrow: co-directed, series-connected active
legs of planar windings. Return conductors, vias, terminals, core windows, and
complete routed loops are excluded and must not be inferred from the data.

Execution identifiers and immutable corpus hashes are recorded separately in
the [evidence ledger](../wiki/evidence/Evidence-Ledger.md).
The archived 25-thread closure package and its clean-clone verification commands are in
[`results/corpus_v4/cps_multifidelity/`](../results/corpus_v4/cps_multifidelity/README.md).
The deterministic one-thread production evidence is kept in the distinct
`cps_reference_v2/production/v1` namespace above.
The complete dataset version boundary, including the proposed vendor geometry
track, is maintained in the [Dataset Registry](../wiki/datasets/Dataset-Registry.md).
