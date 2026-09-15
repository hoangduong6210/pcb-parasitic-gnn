---
title: Live Execution Snapshot
status: active operational snapshot
last_updated: 2026-09-15
paper_source: false
---

# Live Execution Snapshot

Implementation review closed on 2026-09-15: the additive FEM-v2 coordinate-
update predictive pipeline, execution protocol, task-private training wrapper,
and admission/finalization/archive wrapper passed final contract review. The
design is 25 split--initialization tasks with three
sequential arms and exactly 75 safe numeric checkpoints. Held-out inputs remain
unavailable to training, and finalization is gated on complete terminal
admission. A broad relevant suite passed 324 tests and the focused E3 suite
passed 83 tests; the only warning is the existing PyTorch `index_reduce` beta
notice. Static compilation, shell syntax, diff hygiene and deterministic prose
checks passed. No predictive task or solver ran during this implementation
step. The next action is to select and publish the clean source commit, build
its immutable execution lock, and run a singleton no-fit SLURM probe before any
training array is authorized. Section 16D of the
[submission playbook](../operations/SLURM-Submission-Playbook.md) records the
exact operator sequence and the no-subset-retry rule.

Project-owner decision on 2026-09-13: the scoped baseline wording is approved.
`C-BASE-FEMV2-001` is now ADMITTED for requested paper snapshots, without
modifying existing manuscripts or immutable experiment receipts. Work has
moved to design and integration review for a separate FEM-v2 strict-E(3)
predictive ablation. No strict-E(3) training has been submitted in this stage.

Implementation update at 2026-09-13 12:27 UTC: owner-approved baseline
admission commit `dbcd319a02fa65c8bf90d520463f1bd17431be7e` was pushed and
verified. The new solver-free coordinate-update model and draft three-arm
design are implemented. Independent review identified and addressed seeded
initialization order, explicit shared-state pairing, the prediction-dead final
coordinate branch, and symmetry-preserving normalization. The next bounded
job qualifies initialized synthetic models only. Predictive training remains
disabled until its full isolated execution and archive pipeline is ready.
See the [new design](../methods/Corpus-V4-FEM-v2-Coordinate-Ablation.md) and
submission playbook section 16C. No old source or numerical evidence changed.

Qualification completed on 2026-09-13: job `7275182` finished `COMPLETED/0:0`
in 21 s with zero restarts, after briefly waiting for priority. Frozen source is
`9a1733ca4e64762f92578f4d158f71c9a8b41f13`; qualification protocol SHA-256 is
`a7fc5cdf3ee08e0bc431060719659c2d156ff827265c59766f35253b3a711f64`.
The focused suite passed 131 tests, with only the existing PyTorch
`index_reduce` beta warning. Prose audit and shell syntax checks passed.
Independent receipt review confirmed all 15 seed/arm rows and 600 transformed
arm evaluations passed. Maximum normalized scalar and coordinate residuals
were `5.960464477539063e-08` and `1.6362917025841673e-07`, respectively, below
`2e-5`. No fitting or corpus access occurred. Evidence is indexed by
`E-C4-E3-FEMV2-QUAL-01`. The draft 75-checkpoint predictive study remains
disabled. Next: implement its arm-specific training sandbox, safe checkpoints,
terminal admission, held-out finalizer and archive replay, then freeze that
execution source separately. No qualification job remains active.

Commit-scope review on 2026-09-13 confirmed the five baseline commits through
`5af4a78`, whose push was verified in the preceding execution session. They
add the baseline pipeline, frozen protocol, evidence, tests and wiki updates;
they do not modify the papers, original datasets or root README. This review
made no new scheduler submission or remote mutation. This local review note
is not included in those five published commits.

Last scheduler-backed observation: 2026-09-13 07:40 UTC. Baseline array
`7273435` completed all 25 tasks with exit `0:0` and zero restarts, in 26 to
40 s per task. Admission `7273449` completed `0:0` in 43 s and accepted all
25 tasks. Held-out finalizer `7273521` completed `0:0` in 79 s. Archive replay
`7273643` completed `0:0` in 101 s with exact numerical reconstruction.
Clean-tracked replay `7273758` completed `0:0` in 87 s with zero restarts.
All computational gates are closed. No task failed. Independent
receipt review confirmed held-out isolation and exact task coverage.

Publication was verified on GitHub at `5af4a78fde5fadb51c49662243521f94c390f472`
on `protocol/corpus-v4-accuracy-v3`, including all checkpoints and reconstructed
analysis. This final status update records the subsequent tracked replay.
The final focused suite passed 133 tests. Prose and table reviews passed;
the deterministic prose audit is not an authorship detector.

Previously completed chain: FEM-v2 latency preflight array
`7259818` finished all three tasks `COMPLETED/0:0` with no restarts. Admission
replay passed at SHA-256
`0cd724afb3b80be4e4b424da511009a0d931dce88b3ab1ba200766ffba47c5cf`.
The independent full array `7260429` completed all 306 tasks with exit `0:0`.
The round-00 accepted set contains all 306 tasks. Finalizer `7271384` wrote
analysis files but exited `1:0` when printing a relative output path against
an absolute repository root. Those files remain diagnostic evidence. Recovery
finalizer `7271440` completed `0:0` in 22 s. Archive reconstruction `7271461`
and clean-tracked replay `7271469` completed `0:0` in 10 and 17 s, respectively.
The reviewed result is admitted under `C-LAT-FEMV2-001`; no solver was repeated.

| Stage | State | Coverage | Active work | Anomalies |
|---|---|---:|---|---|
| Archived 25-thread FEM-R3P16 | `VALIDATED` | 1,500 of 1,500 accepted | None | Four missing final-array elements recovered as hash-pinned singletons |
| Archived 25-thread FEM-R4P16 | `VALIDATED` | 198 of 198 accepted | None | One scheduler-preflight miss recovered as a hash-pinned singleton |
| Archived 25-thread joint finalizer | `FINALIZED` | 1,698 long-form observations | None | First submission used a wrong helper path; corrected submission completed |
| R3/R4 discrepancy audit | `COMPLETED` | 198 of 198 pairs across 66 families | None | First job failed closed when site policy allocated 3 CPUs for a 2-CPU request; the corrected gate distinguished requested and allocated resources |
| Pre-FEM-v2 Corpus V4 accuracy | `FINALIZED AND ADMITTED` | 25 of 25 checkpoints accepted; 25 prediction tables; 7,350 full-test rows | None | Version-scoped to the archived 25-thread capacitance package; does not transfer to FEM-v2 |
| FEM mesh repeatability | `POSTTERMINAL NEGATIVE` | Corrected source Job `6916045`: 15 of 15 elements `COMPLETED/0:0`; Finalizer Job `6916047`: `COMPLETED/0:0`; 30 arm records and terminal admission preserved | None; its one-thread successor dataset is finalized | Existing 25-thread arm failed all three mesh/repeatability gates; one-thread diagnostic arm passed all three; the 25-thread paired-latency chain remains closed |
| One-thread FEM qualification | `ALL STAGES ADMITTED` | Gate A: 45 of 45 source tasks completed; Gate B: 9 of 9 completed; Gate C: 21 of 21 completed; one postterminal stage admission per gate | None | Gate C passed three-sentinel R4 repeatability but returned a negative finite-panel mesh-sensitivity observation; both fidelities remain explicit |
| One-thread FEM-v2 production | `FINALIZED AND POSTTERMINAL ADMITTED` | 1,500 of 1,500 R3; 198 of 198 R4; 1,698 long-form observations; no pending or terminal-negative task | None; downstream accuracy protocol v3 is frozen separately | Infrastructure cancellations were recovered only through hash-pinned pending sets; final admission SHA-256 `b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed` |
| FEM-v2 accuracy v2 | `DIAGNOSTIC EXECUTION CLOSED` | 25 of 25 fixed-epoch checkpoint tasks completed under array `7085613`; no held-out inference | None; preserve compact diagnostic closure only | Full joined R3/R4 bytes were materialized before training, so process-level held-out isolation was not enforced and no model result is eligible |
| FEM-v2 accuracy v3 | `FINALIZED; ARCHIVE VALIDATED` | Array `7087054` completed 25 of 25 tasks; round 01 accepted all 25 candidates; finalizer `7102842` completed `0:0`; clean-tracked archive replay passed | Freeze the next study from the admitted designated checkpoint | Round 00 preserved a transient scheduler-accounting access failure. No checkpoint was rerun. `C-ACC-FEMV2-001` is admitted; latency has its own separate evidence chain. |
| FEM-v2 paired latency | `FINALIZED; ARCHIVE VALIDATED; CLAIM ADMITTED` | Array `7260429`: 306/306; finalizer `7271440`, archive reconstruction `7271461`, tracked replay `7271469`: all `COMPLETED/0:0` | Preserve source roots and reviewed workflow scope | Failed finalizer `7271384` remains diagnostic; its replacement used unchanged timing observations |

Two versioned capacitance packages now exist. The archived 25-thread package
owns `C-ACC-001` and the admitted selected-registry discrepancy. The new
one-thread FEM-v2 finalizer `7084776` closed 1,500 R3 observations and 198 R4
observations over the unchanged 1,500 geometries. Its postterminal receipt sets
`dataset_generation_admitted=true` and
`accuracy_protocol_may_be_frozen=true`, but retains
`training_may_start=false`, `claim_eligible=false`, and
`speed_claim_eligible=false`. Neither fidelity is ground truth, mesh-converged,
or physically validated.

## Why the archived R4 run took longer

For the matched layout 717, R3 used 2,062,878 nodes, 12,477,301 tetrahedra,
18.565 GiB peak memory, and 528.949 s. R4 used 9,241,959 nodes, 56,742,824
tetrahedra, 83.240 GiB, and 3,460.433 s. On this layout, R4 increased the mesh
by about 4.5-fold and wall time by about 6.5-fold. This pair illustrates cost;
it is not reported as a corpus median.

The source artifacts are indexed under `E-C4-RUN-02`; complete execution and
finalization closure are indexed under `E-C4-RUN-01` and `E-C4-FINAL-01` in the
[Evidence Ledger](../evidence/Evidence-Ledger.md).

## Next transition

Status review at 2026-09-13 07:01 UTC: the recorded accuracy and latency
admissions are unchanged. Remote verification confirmed governance commit
`1d03a0941d47cd07af1e363227f43f8dcdd07926` on
`protocol/corpus-v4-accuracy-v3`. This review did not submit a computation or
perform a new scheduler query.

The user authorized implementation of the baseline-comparison stage on
2026-09-13. The active state is **baseline ADMITTED; strict-E(3) design review**,
not another corpus solve. The existing accuracy study evaluates the designated
GNN across splits and initializations; the next question is whether its graph
representation adds predictive value over simpler reference models on the
same FEM-v2 targets. Model choices, features, split reuse, tuning budget,
training-only preprocessing, metrics and admission gates must be frozen before
execution. The [baseline protocol](../methods/Corpus-V4-FEM-v2-Baseline-Protocol.md)
records fixed models, train-only transformations, matched metrics and known
benchmark exposure. A combined regression run passed 223 tests, and the final
baseline suite contains 52 passing tests using synthetic fixtures only. The
research-prose audit passed. The execution lock authenticates the unchanged
upstream inputs; a singleton SLURM filesystem preflight is required before
the 25-task training array. Source `23ca6d0` was pushed and verified; static
hash/runtime validation passed in its clean execution checkout. Singleton
preflight `7273416_0` completed `0:0` in 18 s without fitting or opening held-out
bytes. Its receipt confirms task-private output isolation. The independent
25-task training array `7273435` completed, with five concurrent tasks and
eight scientific threads per task. Admission job `7273449` started after
`afterok:7273435` and validated exact coverage and safe numeric bundles.
The accepted-set SHA-256 is
`3779355148fd79ecc919d99fde0bb086be540f9e7ee55c4ce7470736ab2dd475`.
Finalizer `7273521` bound that accepted set for held-out inference and completed.
Its analysis-manifest SHA-256 is
`f750b4257160b623eb5554f380601ce5a7a20e9342d90bec7e2ddbdd592edd28`.
The [baseline result page](../results/Corpus-V4-FEM-v2-Baselines.md) records
the validated matched comparison. Replay job `7273643` passed exact
reconstruction and job `7273758` repeated it against the clean, Git-tracked
artifact closure at `a6a6a18`. The immutable machine receipts retain
`claim_eligible=false`; they do not make an editorial admission decision.
The preflight receipt is indexed in
`E-C4-BASE-FEMV2-PLAN-01` in the [Evidence Ledger](../evidence/Evidence-Ledger.md).
The project owner subsequently approved the scoped baseline claim.
No additional computation is needed to close this baseline comparison.

After that comparison, separately freeze the strict-E(3) predictive ablation
and ranking study. The admitted encoded-graph symmetry property does not
already establish an accuracy benefit. Heavy work must be submitted through
SLURM. A paper export remains conditional on a requested snapshot.

Dataset generation is closed. Accuracy protocol v2 remains diagnostic evidence
and is not eligible for an accepted set or finalizer. Protocol v3 completed its
checkpoint, accepted-set, held-out finalizer, and clean-tracked archive gates.
`C-ACC-FEMV2-001` owns the resulting one-thread FEM-v2 accuracy statement. The
existing `C-ACC-001` remains immutable evidence for the archived 25-thread
package and must not be relabelled as an FEM-v2 result.

The completed production chain used R3 sources/finalizers
`6963561/6963562`, `7004761/7004762`, `7022705/7022706`, and
`7057802/7057803`, followed by the exact 55-task hash-pinned retry
`7064645/7064646`. The final R3 admission closed 1,500 accepted, zero pending,
and zero terminal-negative tasks. R4 source/finalizer `6963559/6963560`
closed 198 accepted, zero pending, and zero terminal-negative tasks. Dataset
finalizer `7084776` then completed `0:0`; the solver-free admission replayed the
full closure.

The frozen adjacent-mesh result remains negative, so the new package is still
multi-fidelity rather than mesh-converged. A new paired-latency protocol now
binds the admitted accuracy-v3 task-12 checkpoint and the one-thread FEM-v2
dataset. `C-LAT-FEMV2-001` now admits the version-scoped
[paired runtime result](../results/Corpus-V4-FEM-v2-Latency.md).
Baseline, strict E(3), and ranking results still require their own FEM-v2
protocols and jobs.

Check full array `7260429` with `squeue -j 7260429` and
`sacct -X -n -P -j 7260429 --format=JobID,JobIDRaw,Account,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES,MaxRSS,Restarts,Partition,Timelimit,NodeList`.
The completed job wrote only to the detached execution checkout. Its accepted
set is preserved at `results/corpus_v4/latency_fem_v2/resume/round_00/`.
Failed finalizer evidence is preserved under
`results/corpus_v4/latency_fem_v2/diagnostics/job_7271384/`.
A failed finalizer does not authorize publication of its written summary.

The measurement source remains `186ba2c`; recovery source is `b2f2ac6`.
The initial push failed authentication on 2026-09-13. A subsequent authenticated
push published all four evidence and wiki commits to
`protocol/corpus-v4-accuracy-v3`. Remote verification confirmed
`82e788317c408c29cc05ca2af134261200803b9a`; the authentication blocker is resolved.
No archived paper was changed. Existing execution and evidence commit hashes
were preserved; the configured email for future commits was updated separately.

Governance observation, 2026-09-13: wiki synchronization is mandatory for every
project task, including status checks and publication updates. The rule is
enforced in repository `AGENTS.md` and defined in
[Contributing](../CONTRIBUTING.md). No new scientific computation is needed for
this correction. Baseline, strict E(3), and ranking studies remain separate
future stages requiring their own frozen FEM-v2 protocols.
