---
title: Historical Claim Ledger
status: canonical archival registry
last_updated: 2026-08-17
paper_source: false
---

# Historical Claim Ledger

The submitted summary and superseded extended paper remain auditable snapshots.
Their numbers are retained here with their original meaning, but none is a
current geometry-valid headline unless the current registry separately admits
it.

Several early release files predate the job-backed evidence contract. A path to
an aggregate JSON preserves snapshot provenance but does not satisfy the current
requirement for a job-scoped artifact, environment, protocol hash, and exact raw
records. Such a claim remains archival until it is rerun under the current
contract.

## Accuracy and symmetry

| Claim ID | Historical result | Provenance | Current interpretation |
|---|---|---|---|
| `H-ACC-001` | On one fixed seed-42 265/67 split of the 332-layout solver corpus, median errors were 2.630866% for \(C_{ps}\), 2.446639% for \(L_p\), 3.313963% for \(L_s\), and 1.746952% for \(M\). | `results/proof_updates/jobs/claim_proof/job_51174495/results_claim_proof.json`, `held_out_accuracy` | Quarantined v2 geometry and one initialization. Do not write “consistently.” |
| `H-ACC-002` | The submitted summary reported 3.22%, 2.83%, 3.81%, and 2.56% median errors for the same four targets under its earlier protocol. | `results/run_femcps/results_femcps.json` | Archival submitted-version result on quarantined geometry. |
| `H-E3-001` | The strict model was 6.27% worse on the primary full-data metric, with a 95% interval from 4.44% better to 17.68% worse. | `results/proof_updates/jobs/strict_e3/job_51174496/results_strict_egnn_ablation.json`, `paired_analysis.full` and `verdict` | Predictive effect unresolved; v2 accuracy comparison remains historical. |
| `H-E3-002` | The earlier exploratory model showed 0.3262% median prediction drift under rotation. | `results/run_t2/results_t2.json`, `equivariance_check` | Exploratory architecture, not the later strict E(3) proof. |

## Latency and speed

| Claim ID | Historical result | Derivation or boundary | Current interpretation |
|---|---|---|---|
| `H-LAT-001` | 1.16845 ms per design. | `results/run_v1/results.json`, `gnn_infer_ms_per_sample`; pre-collated 400-design batch throughput. | Reproduced at 0.674565 ms on another node by job 51174497. The protocol is reproducible; the clock value is hardware-dependent. |
| `H-LAT-002` | Approximately 5 s per design for the reference solve. | Rounded planning language. Job 51174495 later measured the paired four-target workflow at 3.659 s median, 3.750 s mean, and 4.656 s 95th percentile. | “About 5 s” describes the upper part of that distribution, not an exact median. |
| `H-SPD-001` | Approximately 4,300-fold faster. | (5000/1.16845=4279.2), rounded to two significant figures. | Historical combination of a rounded solver time and pre-collated throughput. It is not a paired end-to-end benchmark. |
| `H-LAT-003` | 0.331 ms pre-collated, 2.285 ms prepared single forward, and 5.617 ms raw-layout end to end. | `results/proof_updates/jobs/claim_proof/job_51174495/results_claim_proof.json`, `gnn_timing` | Three different timer boundaries on quarantined v2 geometry. Only the raw-layout value is end to end. |
| `H-SPD-002` | 670.160891-fold median paired speedup, with a 95% design-bootstrap interval from 640.779346 to 710.369083. | Same job, median of 67 per-design ratios: paired FastHenry plus electrostatic FEM for all four targets divided by raw-layout GNN time. | Historical v2 workflow only. The interval covers evaluated-design resampling on one node, not node, load, environment, or retraining uncertainty. |
| `H-SPD-003` | Inductance-only and capacitance-only ratios are about 15.8-fold and 635-fold at the reported medians. | (88.480567/5.617149) and (3565.41025/5.617149). | Derived boundary examples. They show why the four-target 670-fold claim cannot be generalized to every solver request. |
| `H-SPD-004` | One thousand candidates in about 1.2 s versus about 1.4 h. | \(1000\times1.16845\) ms and \(1000\times5\) s. | Historical throughput projection, not observed end-to-end bank latency. |

## Other submitted-version results

| Claim ID | Historical result | Source field or derivation | Status |
|---|---|---|---|
| `H-DATA-001` | The analytical corpus contained 2,000 layouts with a 1,600/400 split, 25.172 mean nodes, and 662.715 mean edges. | `results/run_v1/results.json`: `n_samples`, `n_train`, `n_test`, `avg_nodes`, `avg_edges` | Archival analytical-label corpus |
| `H-MODEL-001` | The dense GNN had 275,339 parameters; its three-seed analytical-teacher metrics and RMSE were reported in the submitted Table I. | `results/run_v2/results_v2.json`: `dense_gnn_multiseed` | Archival analytical-teacher study |
| `H-MODEL-002` | Pooled MLP, no-relative-geometry, two-layer, and sparse-GNN ablations were reported in the submitted Table I. | Same artifact: `baseline_pooled_mlp`, `ablation_no_geometry`, `ablation_shallow_2layer`, `knn_gnn` | Archival analytical-teacher study |
| `H-TREE-001` | Tree metrics, a 332/67 split, ranking, and size-generalization columns were reported in the submitted Table II. | `results/run_trees/results_trees.json`: `meta`, `pointwise`, `ranking`, `size_generalization` | Archival v2 geometry |
| `H-SPARSE-001` | The k-nearest-neighbor sweep, mean edge counts, and 150-epoch budget were reported in the submitted Table III. | `results/run_v3/results_v3.json`: `meta`, `knn_k_sweep` | Archival v2 geometry |
| `H-CAPACITY-001` | A roughly 32,000-parameter capacity result was reported. | Same artifact: `capacity_sweep[0]` | Archival v2 geometry |
| `H-SIZE-001` | The early size split used 32 to 42 node training and included a random-split reference. | `results/run_v4/results_v4.json`: `generalization_size_split`, `random_split_reference` | Archival; not family-disjoint generalization |
| `H-SIZE-002` | The later large-layout test covered 51 to 70 nodes and reported minimum R-squared of 0.9885. | `results/run_v5/results_v5.json`: `large_N_measured` | Archival v2 geometry |
| `H-TARGET-001` | On 12 layouts, the analytical teacher and GNN differed from the total-capacitance FEM value by 23.83% and 24.16%. | `results/run_v2/fem_total_validation.json`: `peec_vs_fem_median_pct`, `gnn_vs_fem_median_pct` | Historical target-mismatch evidence |
| `H-TARGET-002` | On 12 layouts, the analytical teacher and GNN differed from the inductance FEM value by 62.62% and 62.91%. | `results/run_v4/results_v4.json`: `inductance_fem_validation` | Historical target-mismatch evidence |
| `H-FH-001` | Over 24 layouts, the filament reference differed from FastHenry by 1.63% and Grover differed by 55.98%. | `results/run_fh/results_fh.json`: `filament_vs_fasthenry_median_pct`, `grover_vs_fasthenry_median_pct`, `n` | Historical numerical cross-check |
| `H-FH-002` | Historical GNN mutual-inductance error against FastHenry was 2.21% median and 2.31% mean. | `results/run_t1b/results_t1b.json`: `gnn_vs_fasthenry_median_pct`, `gnn_vs_fasthenry_mean_pct` | Quarantined v2 predictive result |
| `H-ANALYTICAL-001` | Analytical errors for Lp, Ls, and M were 51.5%, 53.6%, and 58.6%. | `results/run_selfL/results_selfL.json`: target `median_rel_err_pct` fields | Historical convention-mismatch evidence |
| `H-CPS-001` | The submitted analysis reported 266.6% analytical capacitance error against its numerical reference. | `results/run_femcps/results_femcps.json`: `analytical_Cps_vs_fastcap_median_pct` | Historical label-quality evidence |
| `H-NEUMANN-001` | The independent Neumann comparison covered 346 total and 70 test layouts. | `results/run_xsolver/results_xsolver.json`: `n_samples`, `n_test`, and target comparison objects | Historical cross-solver evidence |
| `H-CORE-001` | The EER40 solver check differed by 5.69%, 4.09%, and 5.41% at 0.05, 0.1, and 0.2 mm gaps. | `results/run_pfc/results_pfc.json`: `rows[0:3].fem_vs_analytical_pct` | Solver anchor, not a GNN or hardware validation |
| `H-CORE-002` | The reported core magnetizing term was 37.6 to 72.9 times the winding mutual term. | `results/run_coremfem/results_coremfem.json`: `rows[*].core_over_air_mut_ratio` | Core-versus-air numerical comparison |
| `H-FREQ-001` | The frequency extension used 136 boards, 27 test boards, and 17 frequency points; it reported 0.37% median curve error and R-squared of 0.995. | `results/run_t3/results_t3.json`: corpus and curve metric fields | Archival v2 geometry |
| `H-RANK-001` | Pairwise ranking reported median Spearman rho of 0.929 versus 0.27 for pointwise regression. | `results/run_rank/results_rank.json`: `spearman_median`, `baseline_regression_rho` | Archival v2 geometry |
| `H-RANK-002` | The lateral-registration study reported GNN rho of 0.95 and analytical blind fraction 1.0. | `results/run_ranklat2/results_ranklat2.json`: `XY_registration` | Archival v2 geometry |
| `H-DECISION-001` | Lateral-selection regret was 1,176.1% for analytical selection, 1,126.2% for random selection, and 3.5% for GNN selection. | `results/run_declat/results_declat.json`: `XY_decision` | Archival v2 decision protocol |
| `H-DECISION-002` | The submitted “about 340-fold lower regret” phrase came from 1176.1 divided by 3.5, which is 336.0. | Same artifact and displayed derivation | Historical rounded ratio |
| `H-SCALE-001` | The historical sparse-graph crossover was near 80 nodes and the maximum reported k-nearest-neighbor speed ratio was about 80-fold at 1,280 nodes. | `results/scaling_v1/scaling.json`: `knn_beats_ref_at_N`, `max_knn_speedup_x`, `rows` | Historical computational scaling study |

## Snapshot-only values

The submitted text also contains an illustrative stacked/offset example of
92.9, 0.38, and 44.3 pF; a lateral example of 550 pF and 67%; and a FastCap
panel-density range of 6 to 40-fold. These values have no dedicated scalar field
or restored raw record in the released evidence. They remain snapshot text and
are not independently reproducible claims.

The four-page snapshot retains a more detailed field-by-field ledger in
`Paper_Summary/README.md`. That ledger identifies the submitted text. This page
owns the current interpretation and supersession status.
