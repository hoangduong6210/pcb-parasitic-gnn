---
title: Evidence Ledger
status: canonical execution ledger
last_updated: 2026-08-19
paper_source: false
---

# Evidence Ledger

Every entry names the claims it can support. An execution record marked
operational or pending archival is not publication evidence.

## E-C3-GEOM-01 — Geometry-valid corpus root

| Field | Value |
|---|---|
| Finalizer job | `6818436` |
| Source array | `6818133` |
| Layout count | 1,500 |
| Unique geometry count | 1,500 |
| Source commit | `df8a113f7c78c31da578268877da7f5a493d2031` |
| Summary SHA-256 | `05f83c708bc287bcc51b04f74bb1ec72332b57bbe18107d491caa242af03d12b` |
| Layout SHA-256 | `17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b` |
| Label SHA-256 | `48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327` |
| Supported claim | `C-GEOM-001` |
| Clean-clone availability | [Canonical source corpus](../../datasets/corpus_v3/README.md) is tracked with layouts, labels, summary, and file hashes |

## E-C4-FEM-01 — Native backend diagnostic

| Field | Value |
|---|---|
| Array | `6832704` |
| Finalizer | `6832706` |
| Tracked artifact | [Native diagnostic summary](../../results/corpus_v4/fem_native_diagnostic/jobs/job_6832704/summary.json) |
| Summary SHA-256 | `f0b5510cf76325f5aefd8ad599f393cacacfc745d5413b351a5fe4c553513b89` |
| Direct/AMG relative Cps difference | `2.1663128521249161e-16` |
| Refine-3 AMG residual | `6.218617941378876e-11` |
| Supported claim | `C-FEM-001` |

## E-C4-CONV-00 — Refine-2/refine-3 rejection

| Field | Value |
|---|---|
| Array | `6833715` |
| Finalizer | `6833716` |
| Tracked artifact | [Convergence preflight summary](../../results/corpus_v4/convergence_preflight/final/job_6833716/results_corpus_v4_convergence_preflight.json) |
| Final artifact SHA-256 | `d38b0f1f3b22d3dd2580a334f34e001aedae72707e1b298f1600d8cb68d4785b` |
| Decision | Refine-2/pad-16 rejected |

## E-C4-FEAS-01 — Refine-4 feasibility

| Layout | Job | Tracked artifact | Artifact SHA-256 | Scheduler MaxRSS | Decision |
|---:|---:|---|---|---:|---|
| 149 | `6834616` | [Layout 149 artifact](../../results/corpus_v4/refine4_feasibility/jobs/job_6834616/layout_0149.json) | `6115d234071dfd8884f5d88c575c4baf695fc911abb9980f8ba5f965360fd32b` | 86.13 GiB | Pass |
| 407 | `6837051` | [Layout 407 artifact](../../results/corpus_v4/refine4_feasibility/jobs/job_6837051/layout_0407.json) | `397074e8690bbff4b4b29ef7f3567b90493f45910dc438dee1c1e34290ec80e3` | 83.29 GiB | Pass |

## E-C4-CONV-01 — Frozen refine-3/refine-4 study

| Field | Value |
|---|---|
| Array | `6843340` |
| Finalizer | `6843343` |
| Scientific source commit | `53c56a8aea57727be2b62364428bf95cc49745bc` |
| Evidence commit | `1c6de1af6933827680ef6901fbd15459a9ee998f` |
| Tracked artifact | [Refine-3/refine-4 final result](../../results/corpus_v4/refine34_convergence/final/job_6843343/results_corpus_v4_refine34_convergence.json) |
| Final artifact SHA-256 | `78ee69aac46fbce3f914617b6d9cbc4ac51cc56b82f7944f34d2bd9c4172daa1` |
| Domain median / maximum | 0.189658% / 2.491566% |
| Mesh median / maximum | 8.273879% / 13.886399% |
| Scientific decision | Refine-3 rejected as mesh-converged |
| Supported claims | `C-FEM-002`, `C-FEM-003` |

The finalizer exited nonzero only after atomically writing the rejection
artifact. All nine source tasks completed with clean, stable source and passing
solver/resource gates.

## E-C4-PLAN-01 — Multi-fidelity geometry and split plan

| Field | Value |
|---|---|
| Protocol SHA-256 | `36bbda0935c3bbc7c3f61de3ac67c603430e05df65551823ad6eabed37051c4b` |
| Plan SHA-256 | `419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a` |
| Execution lock SHA-256 | `697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb` |
| Family registry SHA-256 | `adb015939c5dcc29f63e5068e843c65bacde046591f30619612a15ebd3c6589d` |
| HF selection registry SHA-256 | `675f46e1777c2f07d4774853d0fa78f89851e3abc78acd184771832ec0973da9` |
| Split registry SHA-256 | `c30e06e33a58f03336c02d04fc9081d58ac7663338afe355610cfc0fdc7aa641` |
| R3 / R4 task counts | 1,500 / 198 |
| HF families / mandatory anchors | 66 / 9 |

## E-C4-SUBMIT-00 — Rejected scheduler preflight

| Field | Value |
|---|---|
| R4 array | `6845922` |
| Source commit | `00eb8ea68ab6fd588bcf160b0229516a67fb9eaf` |
| Outcome | Ten tasks failed at the scheduler contract gate in 0–1 s; remainder canceled |
| Solver execution | None |
| Requested resources | 25 CPU, 160 GiB |
| Allocated resources | 41 CPU, 160 GiB |
| Root cause | Validator conflated requested CPU count with memory-inflated allocation |
| Scientific use | None; operational regression evidence only |

Two earlier submission attempts created no job. One omitted the required
`pgs0407` account; the other requested the invalid R3 array index range
`0-1499` on a cluster with `MaxArraySize=1001`. The corrected procedure is
maintained in the [SLURM Submission Playbook](../operations/SLURM-Submission-Playbook.md).

## E-C4-SUBMIT-01 — QOS and remote-submit preflight failures

| Field | Value |
|---|---|
| Source commit | `d6162b1c4c502cca2a880a32fce2b1d894ff808b` |
| QOS limit | `MaxSubmitJobsPU=1000` |
| Rejected request | R3 array with 1,001 elements, `--test-only`; no job created |
| Canceled arrays | R3 `6846270`, dependent R3 `6846287`, R4 `6846304` |
| Outcome | Initial tasks exited in 1–3 s; remaining elements canceled |
| Root cause | `--chdir` did not change `SLURM_SUBMIT_DIR`; the absolute `PCB_GNN_JOB_ENV` was not exported |
| Solver execution | None; failure occurred before the runner and FEM worker |
| Scientific use | None; operational regression evidence only |

## E-C4-RUN-01 — Completed multi-fidelity production execution

| Field | Value |
|---|---|
| Lifecycle | `FINALIZED` |
| Source commit | `d6162b1c4c502cca2a880a32fce2b1d894ff808b` |
| Execution lock SHA-256 | `697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb` |
| R3 dispatch summary SHA-256 | `7362284e217f50a3d94393e4e59627e13d0fde5b75a6ebdf55b1f6bb1f0ae887` |
| R3 shard A | Job `6846403`, canonical tasks 0–399, task-set SHA-256 `03571b414be015d33210f527032d34a04c4f303e3eb16bc4b042021ab2df9889` |
| R3 shard B | Job `6846415`, canonical tasks 400–799, dependency `afterany:6846403`, task-set SHA-256 `7748d81227bdca1edf6b2c76bdeb26bde8bd7e7537c410463549a2813d47c719` |
| R3 shard C | Job `6852522`, canonical tasks 800–1199, dependency `afterany:6846415`, task-set SHA-256 `0981c92ac2e4bd4b8cdd931cadadbaa6b1cc1f80b16f9163663a38fc7b906398` |
| R3 shard D | Job `6852689`, canonical tasks 1200–1499, dependency `afterany:6852522`, task-set SHA-256 `08b669fc5969641fd940a4180e7ab8fff8eb062e915a5d05c696b066e35288ad` |
| R4 array | Job `6846412`, 198 tasks, concurrency 2 |
| Initial scheduler check | R3 requested/allocated 25 CPU and 48 GiB; R4 requested 25 CPU/160 GiB and allocated 41 CPU/160 GiB |
| Initial execution check | Eight R3 and two R4 started artifacts existed; no failure signature at admission time |
| First completed solver proof | R3 job `6846403`, canonical task 1, `task_pass=true`, artifact SHA-256 `e1be5cea98621c3bfd1c93590d83294316ac6f4c0724b5d25f7dd142d494ddc2` |
| First completed numerical/resource record | 1,697,083 mesh nodes; 10,243,932 tetrahedra; relative residual `8.504706647340125e-11`; 25 iterations; 415.605 s worker wall; 15.322 GiB worker peak RSS |
| Initial R3 candidate index | 1,496 entries; SHA-256 `c563e55d334099bfe8d3fcd65c1208b6f8eaa92197960ec8850d7335c7c714d5` |
| Initial R3 resume | 1,496 accepted, 4 pending, 0 rejected; accepted-set SHA-256 `4e7bd9b89282c6d5b6060127e0a32ede7342397222edab3a93355febdfa08078`; pending-set SHA-256 `57b320f3b824e74ebdec6d4c0fd18e5e70b0a47a6b843a42e166b09de5faab4c` |
| R3 retry dispatch | Four singleton shards; summary SHA-256 `f7557555b4e967891818a0cfe1b02c5cd7076f186586c02545e7dec77d352495` |
| R3 retry task 399 | Job `6860601`, artifact SHA-256 `695d53c5a1489729a04e955e90e5c7e962f87dc1a259b9b22626ead72b4c7b77` |
| R3 retry task 799 | Job `6860602`, dependency `afterany:6860601`, artifact SHA-256 `912ec6cbbf07eba339959ef5c3438b1e453c7ab1b2a9d4414dd35f1ead4de9e5` |
| R3 retry task 1199 | Job `6860603`, dependency `afterany:6860602`, artifact SHA-256 `a7348cafb2b585d349ba5944bcd14e4258276e18f465a0dc30b9b62b3b3d3455` |
| R3 retry task 1499 | Job `6860604`, dependency `afterany:6860603`, artifact SHA-256 `e7cbb84c34de02bf5991623734952feada6e4ce1316fe9dc6d7705d55b0c6eb0` |
| Cumulative R3 candidate index | 1,500 entries; SHA-256 `2a478a85a98df0183c7c2739b16167e65ec27b938ca39761cb9c3902f9dda490` |
| Final R3 resume | 1,500 accepted, 0 pending, 0 rejected; accepted-set SHA-256 `dd2f5fe7bc57366eddeead3a4761c58818c4186314c57cb13b9277b452f2db0f`; empty pending-set SHA-256 `f9d49ef2059d68d379740706173fe85e02fd6b52971755e32ff4a4b18a083fda` |
| Initial R4 candidate index | 197 entries; SHA-256 `2dda52951eb2ad65c807ce4075e679ff06694bd84263f26f10b05d0f0fd7cb26` |
| Initial R4 resume | 197 accepted, 1 pending, 0 rejected; accepted-set SHA-256 `21ed20219e7713589e13f9378cec1059be880f41b9f88d6562669bfa3b9f5d83`; pending-set SHA-256 `f88f38273c7827198744c207849e8af2a136264a178cdfe6b59a49fb11aaf7e7` |
| R4 retry | Job `6891382`, canonical task 197, layout 1497, `COMPLETED 0:0`, `task_pass=true`; artifact SHA-256 `c4ee6ada11fd5c91986ac82287762fed76d304a993ff0a1b788d9dbfc4ac42a6` |
| R4 retry numerical/resource record | 9,246,989 mesh nodes; 56,776,659 tetrahedra; relative residual `6.94e-11`; 28 iterations; 3,443.215 s worker wall; 81.198 GiB worker peak RSS |
| Cumulative R4 candidate index | 198 entries; SHA-256 `d1d06e5f1c4ebbb8009f14f94e9416f27d63d27df314df28fd6fd4a276bf1301` |
| Final R4 resume | 198 accepted, 0 pending, 0 rejected; accepted-set SHA-256 `4ed4bd5652688457e803f9fd377ba38fec83f5fee08a44698d374b9764cc82b1`; empty pending-set SHA-256 `f80e0becb50a6fc0f38547a9f1b8c6c998b928745ec3328c2acb5ee291ddc238` |
| Lifecycle claim IDs | `C-CPS-R3-001`, `C-CPS-R4-001`, `C-CPS-FINAL-001` |
| Scientific use | Exact execution and artifact-coverage evidence; not predictive accuracy or physical validation |

## E-C4-FINAL-01 — Joint explicit-fidelity package

| Field | Value |
|---|---|
| Finalizer job | `6893754`, `COMPLETED 0:0`, 13 s on `nextgen` |
| Scheduler resources | Requested 2 CPU/16 GiB; allocated 5 CPU/16 GiB; batch peak RSS about 200 MiB |
| Source commit | `d6162b1c4c502cca2a880a32fce2b1d894ff808b`, clean and stable at both finalizer gates |
| Archive-manifest SHA-256 | `567c1187ca74e0148691b9ac464a51f5fd014862e2c120d03963b2eacc681505` |
| Artifact | [Final summary](../../results/corpus_v4/cps_multifidelity/final/job_6893754/summary.json) |
| Observation table | [Long-form explicit-fidelity records](../../results/corpus_v4/cps_multifidelity/final/job_6893754/label_observations.jsonl) |
| Coverage | 1,500 geometries; 1,500 R3 observations; 198 R4 observations; 1,698 long-form rows |
| Summary SHA-256 | `5f3a9158eac1cab5289ceddafba0037b37daecafc88d8eed01179b8dfdd457c6` |
| Observation-table SHA-256 | `c17f71187e31fd10152ac0b459694a022be0d41b132ed7c5992d94d96219795b` |
| Accepted-set SHA-256 | R3 `dd2f5fe7bc57366eddeead3a4761c58818c4186314c57cb13b9277b452f2db0f`; R4 `4ed4bd5652688457e803f9fd377ba38fec83f5fee08a44698d374b9764cc82b1` |
| Frozen identities | Plan `419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a`; protocol `36bbda0935c3bbc7c3f61de3ac67c603430e05df65551823ad6eabed37051c4b`; execution lock `697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb` |
| Manifest SHA-256 | R3 `3eb7931837bcc813523905386a9e9898ee135ababc482e124b927df52f59c7d2`; R4 `88c15d2489ee069e0b76a1e62074725796c847df5eeaaa0c88a6e0bb10e1df1d` |
| Semantics | Explicitly forbids `ground_truth`, `mesh_converged_r3`, and `validated_physical_accuracy`; records R3-to-R4 and R4-continuum convergence as false |
| Supported lifecycle claims | `C-CPS-R3-001`, `C-CPS-R4-001`, `C-CPS-FINAL-001` |
| Scientific use | Finalized numerical-observation package; downstream discrepancy and predictive studies remain separate gates |

## E-C4-OPS-02 — Final-array-element scheduler parser incident

| Field | Value |
|---|---|
| Affected production element | R3 shard A canonical task 399 |
| Accepted neighboring coverage | Canonical tasks 0–398 produced 399 passing artifacts |
| Failure stage | Scheduler-contract preflight; FEM worker did not start for task 399 |
| Root cause | The final array element reused the base array job ID. A base-ID `scontrol` query returned multiple records, which the runner incorrectly flattened into one dictionary. |
| Future-run regression fix | Lock v2 queries the exact `array-job-id_array-task-id` component and requires exactly one matching record |
| Singleton probe | Job `6852528`, `COMPLETED 0:0` |
| Probe script SHA-256 | `bf64f402c9474bc9b87a321496a12eb2afc2e11da21d05d8c7ef12dcbc4d05dd` |
| Probe result | A one-element array retained `ArrayTaskThrottle=8`, returned one scheduler record for job/base/exact-component queries, and exposed count/min/max `1/0/0` |
| Active-corpus recovery decision | After resume validation, use the unchanged lock-v1 runner and retry only missing canonical indices as hash-pinned singleton arrays; the singleton avoids the multi-record condition |
| Scientific use | None; operational recovery evidence only |

An attempted R3-D submission was rejected before job creation by
`QOSMaxSubmitJobPerUserLimit`. The incorrect preliminary count used compressed
array rows; the required gate uses expanded `squeue -r` elements. No runner or
solver executed and no scientific artifact was created.

Execution lock v2 has SHA-256
`111ff2347f74afd4a280cc21b8a337387f982341367e6b73550794b13089f081`
and pins runner SHA-256
`e8f2d2bf39937c380d0396535fa95229bb8295cd6c2a0f3c1e2d5b238973cffb`.
It is reserved for future complete runs and is not admissible in the active
lock-v1 artifact set.

## E-C4-OPS-03 — Finalizer submit-path incident

| Field | Value |
|---|---|
| Failed finalizer | Job `6891705`, `FAILED 1:0` after 27 s |
| Failure stage | Batch bootstrap before Python finalization |
| Root cause | `PCB_GNN_JOB_ENV` resolved from the remote login directory instead of the immutable execution worktree |
| Scientific computation | None; no final output directory was created |
| Corrective action | Resubmitted with `--chdir` and every input/helper path exported as an absolute path |
| Successful closure | Job `6893754`, `COMPLETED 0:0`; see `E-C4-FINAL-01` |
| Scientific use | None; operational regression evidence only |

This incident repeats the remote-submit lesson in `E-C4-SUBMIT-01`: `--chdir`
does not rewrite `SLURM_SUBMIT_DIR`, so the helper path must be absolute.

## E-C4-DISC-01 — Family-aware production R3/R4 discrepancy

| Field | Value |
|---|---|
| Lifecycle | `ADMITTED DESCRIPTIVE RESULT` |
| Successful audit job | `6894098`, `COMPLETED 0:0`, 7 s on `nextgen` |
| Requested and allocated resources | 2 CPU and 8 GiB requested; 3 CPU and 8 GiB allocated; batch peak RSS 97,956 KiB |
| Source commit | `f0f60cdf67daf3df6973185d353836677163c02e` |
| Analysis manifest | [Derived archive manifest](../../results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1/ANALYSIS_MANIFEST.json), SHA-256 `ae3859cc6004f5edf01053813f8237ca0b98e68d6cb634a8f200aeed74e03d40` |
| Summary | [Job-backed discrepancy summary](../../results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1/job_6894098/summary.json), SHA-256 `1a545715e05d4758778b78580e8c27d249a265c880212740c8dcedd6804c1c08` |
| Protocol SHA-256 | `9c6e6483c0c86b4f737f48772b72349b9e8dcad0975d6ed60a5aaeafa6bf65e3` |
| Implementation SHA-256 | `ed5ee726e107cc8f742b98b312ed1c980271abce24c06b863e7d9f286487c16c` |
| Executed batch-script SHA-256 | `7a77dc888b27209fc5780d5b5c0aec49f06186a28de241c027accd96763f2ba6` |
| Upstream archive-manifest SHA-256 | `567c1187ca74e0148691b9ac464a51f5fd014862e2c120d03963b2eacc681505` |
| Coverage | 198 matched layouts; 66 families; three layouts per family; 9 mandatory anchors and 189 non-anchor selections |
| Direction | FEM-R3P16 greater than FEM-R4P16 in 198 of 198 pairs |
| Absolute discrepancy | Median 8.479391982%; mean 8.848992052%; range 2.753572171% to 17.516912883%; 90th percentile 11.567606379%; 95th percentile 12.532540049% |
| Family summary | Median of the 66 family medians 8.467535812% |
| Failed-closed predecessor | Job `6894034`, no scientific artifact; the first gate rejected an allocated count of 3 CPUs even though the request remained 2 CPUs under the site memory-per-CPU policy |
| Supported claim | `C-CPS-DISC-001` |

The deterministic selected registry is not a probability sample. Nine anchors
were inherited from an earlier selection that used capacitance order
statistics; the remaining 189 entries were selected from geometry descriptors.
No new R3/R4 discrepancy was used for selection. The analysis supplies no
confidence interval, population estimate, global correction, continuum claim,
or physical-accuracy claim. Its five overlapping split-test panels are
sensitivity views rather than independent replicates.

## E-V2-PROOF-01: Historical accuracy and paired timing proof

| Field | Value |
|---|---|
| Job | `51174495` |
| Artifact | [Historical claim proof](../../results/proof_updates/jobs/claim_proof/job_51174495/results_claim_proof.json) |
| Artifact SHA-256 | `940a59358d5c6a2660bf4ca0da2c6f02862ae23c3a5066bf87f21581d0e78202` |
| Accuracy fields | `held_out_accuracy` |
| Solver timing fields | `solver_timing_ms` |
| GNN timing fields | `gnn_timing` |
| Paired-ratio fields | `derived_claims.paired_speedup_solver_vs_end_to_end_gnn` |
| Historical claim IDs | `H-ACC-001`, `H-LAT-002`, `H-LAT-003`, `H-SPD-002`, `H-SPD-003` |
| Scientific status | Quarantined v2 geometry; archival interpretation only |

The 95% interval for the 670.160891-fold statistic resamples the 67 evaluated
designs. It does not include hardware, system load, software environment, or
model-retraining variation.

## E-V2-E3-01: Strict E3 implementation and historical ablation

| Field | Value |
|---|---|
| Job | `51174496` |
| Artifact | [Strict E3 proof and ablation](../../results/proof_updates/jobs/strict_e3/job_51174496/results_strict_egnn_ablation.json) |
| Artifact SHA-256 | `d4a80929e39b8135ba64e40a415a1b72f7a9ec5171a4753ffa54bb589be416a1` |
| Source commit | `181dc79556989908000b9ce857ca216b87a60cf7` |
| Proof script SHA-256 | `6807e9b7b452c72b1cfea6118b548bef89a74fcedbd840f4ade48da1af9f5d4f` |
| EGNN implementation SHA-256 | `855d3d5c8dd6b0b7936a725d05cb88bbf72c279250aa8a888abae4755d8e4c74` |
| Graph implementation SHA-256 | `3d67f533a86eed78802a5fa1f930a1be6bcc03a8a616270b841195c5ec105bb5` |
| Symmetry summary | `results/proof_updates/results.json`, `strict_e3` |
| Predictive fields | `paired_analysis`, `sample_efficiency`, and `verdict` |
| Supported current claim | `C-E3-001`, implementation property only |
| Historical claim | `H-E3-001`, predictive effect unresolved |

The graph encoding and stored scalar metadata are outside the transformation
check. The numerical proof therefore supports E(3) behavior on encoded graphs,
not an unrestricted raw-layout E(n) statement.

## E-V2-LAT-01: Historical throughput reproduction

| Field | Value |
|---|---|
| Original timing job | `5676466` |
| Reproduction job | `51174497` |
| Artifact | [Legacy throughput reproduction](../../results/proof_updates/jobs/legacy_latency/job_51174497/results_legacy_latency_reproduction.json) |
| Artifact SHA-256 | `51a8922b760e9eea766ea8b8c3c4bd9d8c98b0ba04fce0243745e5da1a006b9a` |
| Original value | 1.16845 ms per design |
| Reproduced median | 0.674565245 ms per design |
| Historical claim IDs | `H-LAT-001`, `H-SPD-001`, `H-SPD-004` |
| Boundary | Pre-collated 400-design batch throughput |

The differing clock values are expected across hardware and runtime
environments. This record reproduces the timing protocol rather than asserting
bitwise or clock-time equality.

## E-C4-RUN-02: Matched R3/R4 resource example

| Field | R3 | R4 |
|---|---:|---:|
| Layout | 717 | 717 |
| Job and task artifact | `6846415/task_0717.json` | `6846412/task_0100.json` |
| Artifact SHA-256 | `2449a6c4adc911a12eeb7a2f49ceb3782e5eecea7058c19088f110109f18e42d` | `b150bfecb9ad1cd44fd050344e1f47735b466e99979a49917992a8225b2db335` |
| Nodes | 2,062,878 | 9,241,959 |
| Tetrahedra | 12,477,301 | 56,742,824 |
| Worker wall | 528.948702 s | 3,460.433289 s |
| Peak RSS | 18.565044 GiB | 83.240124 GiB |
| Relative residual | `6.8885e-11` | `8.3918e-11` |
| Scientific use | None; single-layout operational cost example | None; single-layout operational cost example |

These accepted task artifacts are tracked at their finalized repository-relative
paths. The pair explains resource cost but is not a corpus runtime statistic.

## E-C4-ACC-PREFLIGHT-01: Family-crossed accuracy freeze

| Field | Value |
|---|---|
| Lifecycle | `PREFLIGHT FROZEN; NUMERICAL EXECUTION PENDING` |
| Protocol | [`corpus_v4_accuracy_v1.json`](../../protocols/corpus_v4_accuracy_v1.json), SHA-256 `f707eb45e44042bc7231a4393caa1b998a283658ce2c3d4093e7c6c7a3eaf3bf` |
| Plan | [`plan.json`](../../results/corpus_v4/accuracy/plan/v1/plan.json), SHA-256 `e67509a6a742bb6a936287a79e9622f087a14ba08219a7c9521f05288b704206` |
| Task rows | [`task_manifest.jsonl`](../../results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl), SHA-256 `2c7079fdd844d9e54a76d32a3bee6e623735303d7d59185ee97e3daf40000f20` |
| Evaluation table | [`evaluation_dataset.jsonl`](../../results/corpus_v4/accuracy/plan/v1/evaluation_dataset.jsonl), SHA-256 `c7f6128f6d189b82dbec036ff8f448fa468980bbf518abcb1358c0a143a1b02c` |
| Execution lock | [`corpus_v4_accuracy_execution_lock_v1.json`](../../protocols/corpus_v4_accuracy_execution_lock_v1.json), SHA-256 `7d88d016dc9af19b40de36756a8c35c70d3895cb0784a90585d8cf31822c3a60` |
| Source closure | 23 execution files are byte-pinned; the clean execution commit is an external trust root recorded by each submitted task |
| Grid | Five family-held-out splits crossed with five initialization seeds; 25 row-major tasks |
| Held-out boundary | Training tasks emit checkpoints and validation diagnostics only; the accepted-set gate precedes the SLURM finalizer's first test/R4 inference |
| Review gates | 314 repository tests, 121 focused accuracy tests, research-prose audit, Python compile, shell syntax, deterministic planner replay, and execution-lock validation passed on the login-safe review path |
| Scientific use | Defines an execution contract only. It supports no accuracy or runtime number until the final archive is job-backed, hash-closed, committed, and entered separately in this ledger. |

## E-C4-ACC-SUBMIT-00: Accuracy resource-contract preflight failure

| Field | Value |
|---|---|
| Array | `6902623` |
| Source commit | `4327cd05b6d7a85afecc5ba7f058f32fc740c03e` |
| Outcome | Fifteen elements failed at the scheduler-resource gate; the remaining elements were canceled |
| Scientific computation | None; every started element exited before graph construction or training, and no checkpoint was created |
| Requested resources | 8 CPU and 48 GiB per task |
| Observed allocation | 13 CPU and 48 GiB per started task under the site memory-per-CPU policy |
| Root cause | `ReqTRES` and `TresPerTask` retained the eight-CPU request, while `SLURM_CPUS_PER_TASK`, `CPUs/Task`, `NumCPUs`, and `AllocTRES` consistently reported the 13-CPU allocation; the first accuracy gate incorrectly expected the requested value in the former two allocation fields |
| Corrective action | Preserve the request in `ReqTRES` and `TresPerTask`; require all environment and allocation fields to agree on the actual allocation; keep scientific thread variables fixed at eight |
| Superseded execution-lock SHA-256 | `b1d36a9f2c01a31a41d42b7f9a3a87c5d63a6cd69c4df155dd78425d12c96b4a` |
| Corrected execution-lock SHA-256 | `7d88d016dc9af19b40de36756a8c35c70d3895cb0784a90585d8cf31822c3a60` |
| Scientific use | None; operational regression evidence only |

## E-V2-GEOM-PENDING: Legacy geometry audit closure

`code/data/audit_legacy_v2_geometry.py` implements the legacy integrity audit,
but no finalized, tracked job artifact currently closes the exact defect counts
quoted in earlier internal reviews. Until that artifact is submitted, finalized,
hashed, and committed, the wiki records only the qualitative quarantine reason.
No exact audit count is paper eligible.
