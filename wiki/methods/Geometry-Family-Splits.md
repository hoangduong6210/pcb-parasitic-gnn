---
title: Geometry Family Splits
status: finalized frozen protocol
last_updated: 2026-08-15
paper_source: true
prose_reviewed: true
claim_ids: none
---

# Geometry Family Splits

The earlier family key treated primary and secondary turn counts as an ordered
pair. This permits a reversed pair to appear in training while its near-symmetric
counterpart appears in testing. The active protocol closes that leakage route by
using

```text
family_key = (min(n_primary, n_secondary), max(n_primary, n_secondary))
family_id  = turns-{min}-{max}
```

The 1,500-layout corpus contains 66 such swap-closed families. For each of five
split seeds, the sorted family registry is shuffled and divided into 46 training
families, 7 validation families, and 13 test families. Every fidelity belonging
to one geometry and both ordered forms of a turn-count family remain in the same
partition.

Five initialization and training-order seeds are crossed with the five split
seeds. Normalization is fitted only on the active training partition. Model
selection may inspect validation families; test observations remain unavailable
until independent evaluation.

Primary uncertainty estimates use family-cluster resampling within a run and
crossed resampling of split and initialization axes across runs. These intervals
describe the evaluated finite corpus and software/hardware protocol; they do not
represent fabrication variability.
