# Recovery validation record

Observed on 2026-09-13. The original 306 timing tasks were not repeated.

| Job | Purpose | State | Exit | Elapsed seconds | Restarts | Node |
|---|---|---|---|---:|---:|---|
| 7271384 | Original analysis, retained as diagnostic | FAILED | 1:0 | 18 | 0 | a0104 |
| 7271440 | Separately locked recovery finalizer | COMPLETED | 0:0 | 22 | 0 | a0104 |
| 7271461 | Archive reconstruction | COMPLETED | 0:0 | 10 | 0 | a0104 |
| 7271469 | Committed-evidence replay | COMPLETED | 0:0 | 17 | 0 | a0104 |

All four accounting rows report account `pgs0407`, partition `nextgen`,
and time limit `00:20:00`. Scheduler logs are preserved under `logs/` and the
failed attempt under `diagnostics/`. Successful archive commands reported
`Corpus V4 latency archive: PASS (3 analysis files)`.

The finalizer source is `b2f2ac66ee61cbcd9149b80dfbf68269fcae3c08`.
The archive replay wrapper source is `2ff0c4f96fa791151a71780e6071cd2a7eab861a`.
The tracked replay evaluated evidence committed at
`bb2e4306e9d4cac9b22388817a3b18000b3855fb`.

Targeted recovery, original latency, numerical wiki binding, wiki contract and
prose regression tests: 139 passed. The deterministic research-prose audit
passed. No paper snapshot was rebuilt or changed. These checks do not classify
authorship or establish physical accuracy.

```bash
rtk pytest -q tests/test_corpus_v4_latency_finalizer_recovery.py \
  tests/test_corpus_v4_latency_v2_pipeline.py \
  tests/test_corpus_v4_latency_wiki_result.py \
  tests/test_wiki_contract.py tests/test_research_prose_audit.py
rtk proxy /usr/bin/python3 code/quality/audit_research_prose.py
```

The [result page](../../../wiki/results/Corpus-V4-FEM-v2-Latency.md) and
[evidence ledger](../../../wiki/evidence/Evidence-Ledger.md) define the admitted
claim and distinguish the original timing source from the recovery source.
