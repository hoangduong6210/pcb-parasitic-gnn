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
7. declared multi-split/multi-initialization accuracy runs on that frozen corpus;
8. baseline, ranking, symmetry, and paired end-to-end timing jobs on the same
   corpus and split registry;
9. figures and manuscript tables generated only from accepted wiki content.

Each current number must resolve to a job-scoped result, raw record, immutable
input hash, source commit, source-file hash map, executable hash, arguments, and
environment record. Current admitted numerical evidence includes the finalized
geometry corpus, native AMG-CG diagnostic, refine-4 feasibility checks, the
frozen refine-3/refine-4 negative convergence result, and the finalized
fidelity-explicit Cps package. The domain comparison
passed at 0.189658% median and 2.491566% maximum; the mesh comparison was
rejected at 8.273879% median and 13.886399% maximum.

There is no accepted current-corpus GNN accuracy or speed headline yet. The
canonical status and scientific interpretation live in
[`wiki/`](../wiki/README.md); raw jobs, commits, artifact paths, and SHA-256
values live in the [evidence ledger](../wiki/evidence/Evidence-Ledger.md).
