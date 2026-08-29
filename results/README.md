# Evidence status

All result directories that depend on v0 through v2 geometry are historical evidence.
They remain tracked to make earlier calculations auditable, but they are
quarantined from current scientific claims. In particular, old accuracy,
ranking, predictive strict-symmetry comparisons, and latency ratios must not be
presented as results on geometry-valid PCB layouts. The separately proven
encoded-graph E(3) property is an implementation claim, not a v2 accuracy claim.

Current evidence is admitted only in this order:

1. a job-backed legacy integrity audit;
2. a complete 1,500-layout v3 field-label array — complete;
3. a final corpus summary whose geometry, passivity, source, and hash gates pass
   — complete;
4. a frozen FEM backend and sensitivity protocol — complete, with domain pass
   and mesh rejection;
5. immutable geometry-family and split registries — complete;
6. a fidelity-explicit Cps corpus: 1,500 R3 and 198 R4 observations jointly finalized;
7. a family-aware descriptive R3/R4 discrepancy audit on the frozen 198-layout
   registry — complete;
8. declared multi-split/multi-initialization accuracy runs on the archived
   25-thread target package — complete and admitted for that version only;
9. a closed FEM-v2 accuracy-v2 diagnostic execution whose checkpoint workload
   completed but whose process-level held-out byte boundary was not enforced;
10. a separately frozen accuracy-v3 protocol with split-scoped training inputs
   and a compute-node filesystem sandbox;
11. baseline, ranking, symmetry, and paired end-to-end timing jobs on the same
   corpus and split registry;
12. figures and manuscript tables generated only from accepted wiki content.

Each current number must resolve to a job-scoped result, raw record, immutable
input hash, source commit, source-file hash map, executable hash, arguments, and
environment record. Current admitted numerical evidence includes the finalized
geometry corpus, native AMG-CG diagnostic, refine-4 feasibility checks, the
frozen refine-3/refine-4 negative convergence result, and the finalized
fidelity-explicit Cps package. The selected-registry discrepancy audit is also
admitted as a descriptive result: all 198 R3 observations exceeded their paired
R4 observations, with a median relative discrepancy of 8.479% and an observed
range of 2.754% to 17.517%. The deterministic registry is not a probability
sample, and R4 is not treated as truth. The domain comparison
passed at 0.189658% median and 2.491566% maximum; the mesh comparison was
rejected at 8.273879% median and 13.886399% maximum.

The archived 25-thread GNN accuracy result is accepted under its frozen
family-held-out protocol. The deterministic one-thread FEM-v2 accuracy-v2
checkpoint grid is diagnostic only and is closed without held-out inference.
Protocol v3 is the active successor; its sandbox preflight is the next gate, and
current-corpus paired speed remains blocked. The archived
numerical result and its scope are maintained in
[`Corpus V4 Family-Held-Out Accuracy`](../wiki/results/Corpus-V4-Accuracy.md).
Canonical lifecycle status and scientific interpretation live in
[`wiki/`](../wiki/README.md); raw jobs, commits, artifact paths, and SHA-256
values live in the [evidence ledger](../wiki/evidence/Evidence-Ledger.md).

The current accuracy artifact layout and checkpoint-before-test lifecycle are
indexed in [`corpus_v4/accuracy/README.md`](corpus_v4/accuracy/README.md).
The closed diagnostic revision is indexed in
[`corpus_v4/accuracy_v2/README.md`](corpus_v4/accuracy_v2/README.md). The active
split-scoped revision is indexed in
[`corpus_v4/accuracy_v3/README.md`](corpus_v4/accuracy_v3/README.md).
