# Evidence status

All result directories that depend on v0--v2 geometry are historical evidence.
They remain tracked to make earlier calculations auditable, but they are
quarantined from current scientific claims. In particular, old accuracy,
ranking, strict-symmetry, and latency ratios must not be presented as results on
geometry-valid PCB layouts.

Current evidence will be admitted only in this order:

1. a job-backed legacy integrity audit;
2. a complete 1,500-layout v3 field-label array;
3. a final corpus summary whose geometry, passivity, source, and hash gates pass;
4. declared multi-split/multi-initialization accuracy runs on that frozen corpus;
5. baseline, ranking, symmetry, and paired end-to-end timing jobs on the same
   corpus and split registry;
6. figures and manuscript tables generated only from the accepted summaries.

Each current number must resolve to a job-scoped result, raw record, immutable
input hash, source commit, source-file hash map, executable hash, arguments, and
environment record. This directory contains no accepted v3 headline result yet.
