# Summary manuscript package

> **ARCHIVAL SNAPSHOT — SUPERSEDED FOR CURRENT CLAIMS.** This package preserves
> the submitted manuscript exactly. Its legacy timing and equivariance language
> must not be used as the current project result. Use
> [`Paper_Full/`](../Paper_Full/) for the authoritative manuscript.

This directory preserves the four-page conference-format manuscript as a
versioned snapshot. The manuscript text and its reported values are not updated
when later experiments change the current conclusions. For current claims and
protocols, use [`Paper_Full/`](../Paper_Full/) and the repository-level
[`README.md`](../README.md).

## Snapshot identity

| Artifact | SHA-256 | Role |
|---|---|---|
| [`main.tex`](main.tex) | `5caa894fb44b7370085497906a3f09cb60a90daa8d398cbb3e5e8432286a25ae` | LaTeX source of this snapshot |
| [`Conference_Submission_ARCHIVE.pdf`](Conference_Submission_ARCHIVE.pdf) | `abf291ea3df4dacdbb6228885e17528f9fcfd18d44aa56998b79097d9dabba54` | Immutable rendered submission; superseded for current claims |

The hashes above identify this exact manuscript version. They deliberately do
not identify the evolving evidence files linked below.

## Claim ledger for this version

The JSON path column names the exact field whenever a released result contains
the number. “Derived” means the manuscript rounded or combined released values;
the arithmetic is shown explicitly. “Snapshot only” identifies wording whose
underlying scalar was not retained as a separate machine-readable field in this
public release.

| Manuscript claim | Exact released source | JSON path or derivation | Status |
|---|---|---|---|
| 2,000-layout analytical-label corpus; 1,600/400 split; mean 25.172 nodes and 662.715 edges | [`run_v1/results.json`](../results/run_v1/results.json) | `n_samples`, `n_train`, `n_test`, `avg_nodes`, `avg_edges` | Direct |
| Dense GNN has 275,339 parameters; three-seed analytical-teacher accuracy and RMSE in Table I | [`run_v2/results_v2.json`](../results/run_v2/results_v2.json) | `dense_gnn_multiseed` | Direct |
| Pooled MLP, no-relative-geometry, two-layer, and sparse-GNN ablations in Table I | [`run_v2/results_v2.json`](../results/run_v2/results_v2.json) | `baseline_pooled_mlp`, `ablation_no_geometry`, `ablation_shallow_2layer`, `knn_gnn` | Direct |
| Tree metrics, 332/67 split, rank and size-generalization columns in Table II | [`run_trees/results_trees.json`](../results/run_trees/results_trees.json) | `meta`, `pointwise`, `ranking`, `size_generalization` | Direct |
| k-NN sweep, mean edge counts, and 150-epoch budget in Table III | [`run_v3/results_v3.json`](../results/run_v3/results_v3.json) | `meta`, `knn_k_sweep` | Direct |
| 32k-parameter capacity result | [`run_v3/results_v3.json`](../results/run_v3/results_v3.json) | `capacity_sweep[0]` | Direct |
| Size split at 32–42 nodes and random-split reference | [`run_v4/results_v4.json`](../results/run_v4/results_v4.json) | `generalization_size_split`, `random_split_reference` | Direct |
| Measured 51–70-node test range, minimum R² = 0.9885 | [`run_v5/results_v5.json`](../results/run_v5/results_v5.json) | `large_N_measured` | Direct |
| Total-capacitance teacher/GNN discrepancy of 23.83/24.16% on 12 layouts | [`run_v2/fem_total_validation.json`](../results/run_v2/fem_total_validation.json) | `peec_vs_fem_median_pct`, `gnn_vs_fem_median_pct` | Direct |
| Mutual-inductance teacher/GNN discrepancy of 62.62/62.91% on 12 layouts | [`run_v4/results_v4.json`](../results/run_v4/results_v4.json) | `inductance_fem_validation` | Direct |
| Filament reference vs FastHenry: 1.63%; Grover vs FastHenry: 55.98%, 24 layouts | [`run_fh/results_fh.json`](../results/run_fh/results_fh.json) | `filament_vs_fasthenry_median_pct`, `grover_vs_fasthenry_median_pct`, `n` | Direct |
| GNN mutual inductance vs FastHenry: 2.21% median and 2.31% mean | [`run_t1b/results_t1b.json`](../results/run_t1b/results_t1b.json) | `gnn_vs_fasthenry_median_pct`, `gnn_vs_fasthenry_mean_pct` | Direct |
| Analytical Lp/Ls/M errors: 51.5/53.6/58.6% | [`run_selfL/results_selfL.json`](../results/run_selfL/results_selfL.json) | `L_pri_nH.median_rel_err_pct`, `L_sec_nH.median_rel_err_pct`, `L_mut_nH.median_rel_err_pct` | Direct |
| Summary-version field accuracy: Cps 3.22% (R² 0.9527), Lp/Ls/M 2.83/3.81/2.56% | [`run_femcps/results_femcps.json`](../results/run_femcps/results_femcps.json) | `Cps_pF`, `L_pri_nH`, `L_sec_nH`, `L_mut_nH` | Direct |
| Analytical Cps error of 266.6% | [`run_femcps/results_femcps.json`](../results/run_femcps/results_femcps.json) | `analytical_Cps_vs_fastcap_median_pct` | Direct |
| Independent Neumann comparison over 346/70 total/test layouts | [`run_xsolver/results_xsolver.json`](../results/run_xsolver/results_xsolver.json) | `n_samples`, `n_test`, and the six `*_vs_Neumann_*` objects | Direct |
| EER40 solver check of 5.69/4.09/5.41% at 0.05/0.1/0.2 mm gaps | [`run_pfc/results_pfc.json`](../results/run_pfc/results_pfc.json) | `rows[0:3].fem_vs_analytical_pct` | Direct |
| Core magnetizing term is 37.6–72.9× the winding mutual term | [`run_coremfem/results_coremfem.json`](../results/run_coremfem/results_coremfem.json) | `rows[*].core_over_air_mut_ratio` | Direct |
| Frequency extension: 136 boards, 27 test, 17 points, 0.37% median, R² 0.995 | [`run_t3/results_t3.json`](../results/run_t3/results_t3.json) | `n_samples`, `n_test`, `n_freq_points`, `curve_median_relerr_pct`, `curve_r2` | Direct |
| Exploratory E(n) comparison and 0.3262% rotation drift | [`run_t2/results_t2.json`](../results/run_t2/results_t2.json) | `full_data`, `sample_efficiency`, `equivariance_check` | Direct; historical exploratory protocol, not the later strict-E(3) proof |
| Pairwise rank ρ = 0.929 median; pointwise ρ = 0.27 | [`run_rank/results_rank.json`](../results/run_rank/results_rank.json) | `spearman_median`, `baseline_regression_rho` | Direct |
| Lateral-registration GNN ρ = 0.95 and analytical blind fraction = 1.0 | [`run_ranklat2/results_ranklat2.json`](../results/run_ranklat2/results_ranklat2.json) | `XY_registration` | Direct |
| Lateral pick regret 1176.1% analytical, 1126.2% random, 3.5% GNN | [`run_declat/results_declat.json`](../results/run_declat/results_declat.json) | `XY_decision` | Direct |
| “~340× lower regret” | [`run_declat/results_declat.json`](../results/run_declat/results_declat.json) | `1176.1 / 3.5 = 336.0`, rounded to two significant figures | Derived |
| Analytical PEEC 0.783 ms/design and GNN 1.16845 ms/design | [`run_v1/results.json`](../results/run_v1/results.json) | `ref_allpairs_ms_per_sample`, `gnn_infer_ms_per_sample` | Direct; pre-collated throughput boundary |
| “~4300× faster” | [`run_v1/results.json`](../results/run_v1/results.json), later timing reproduction [`job_51174497`](../results/proof_updates/jobs/legacy_latency/job_51174497/results_legacy_latency_reproduction.json) | `5000 ms / 1.16845 ms = 4279.2×`, rounded to `~4300×`; the later job reproduces the same GNN protocol at 0.675 ms and records its hardware dependence | Derived historical throughput comparison |
| 1,000 candidates in ~1.2 s versus ~1.4 h | [`run_v1/results.json`](../results/run_v1/results.json) | `1000 × 1.16845 ms = 1.168 s`; `1000 × 5 s = 5000 s = 1.389 h` | Derived |
| Sparse k-NN crossover near N = 80 and ~80× at N = 1280 | [`scaling_v1/scaling.json`](../results/scaling_v1/scaling.json) | `knn_beats_ref_at_N`, `max_knn_speedup_x`, `rows` | Direct timing study |

### Snapshot-only scalars

The following illustrative values occur in this manuscript but do not have a
dedicated scalar field in the released JSON set: the stacked/offset example
`92.9/0.38/44.3 pF`, the Figure 3 lateral example `550 pF` and `67%`, and the
FastCap panel-density range `6–40×`. They remain traceable to
[`main.tex`](main.tex), but should not be promoted as independently reproducible
claims without restoring their raw solver records. The current Full Paper does
not rely on these values.

## Figures

| Figure | Released asset | Regeneration source |
|---|---|---|
| Pipeline | [`fig1_pipeline.pdf`](../figures/fig1_pipeline.pdf) | [`make_figures.py`](../code/figures/make_figures.py) |
| Speed/accuracy illustration | [`fig_pareto.pdf`](../figures/fig_pareto.pdf) | Retained publication asset; no standalone generator is present in this release |
| Lateral-registration illustration | [`fig_lateral.pdf`](../figures/fig_lateral.pdf) | Retained publication asset; no standalone generator is present in this release |

## Build

From the repository root:

```bash
bash Paper_Summary/build.sh
```

The compatibility wrapper patches only the figure search path in a generated
build copy. It does not edit `main.tex`, and it fixes the PDF timestamp for
deterministic rebuilds within one TeX toolchain. The rebuilt output is named
`Conference_Submission_ARCHIVE.pdf`. The archived PDF was produced
by `pdfTeX-1.40.27`; its exact byte hash therefore also depends on using that
font/toolchain version. Other TeX Live versions should reproduce the four-page
content and layout but are not claimed to produce the same PDF bytes.
