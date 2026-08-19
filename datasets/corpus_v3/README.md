# Corpus v3 geometry root

This directory is the canonical tracked input used by the finalized Corpus v4
capacitance package. It contains 1,500 unique geometry-valid active-leg layouts,
their inherited full-precision field-solver records, and the job-backed closure
summary. The inherited capacitance field in `labels.jsonl` is archival; current
capacitance work uses the explicit R3/R4 observations under
[`results/corpus_v4/cps_multifidelity/`](../../results/corpus_v4/cps_multifidelity/README.md).

| File | SHA-256 |
|---|---|
| `layouts.jsonl` | `17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b` |
| `labels.jsonl` | `48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327` |
| `summary.json` | `05f83c708bc287bcc51b04f74bb1ec72332b57bbe18107d491caa242af03d12b` |

The closure summary records finalizer job `6818436`, source array `6818133`,
1,500 layouts, 1,500 unique geometry hashes, and passing geometry, passivity,
source-identity, and artifact gates. These identifiers are internal evidence;
paper snapshots use reviewed scientific wording from the wiki.

Verify the tracked bytes from the repository root:

```bash
sha256sum -c <<'CHECKSUMS'
17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b  datasets/corpus_v3/layouts.jsonl
48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327  datasets/corpus_v3/labels.jsonl
05f83c708bc287bcc51b04f74bb1ec72332b57bbe18107d491caa242af03d12b  datasets/corpus_v3/summary.json
CHECKSUMS
```

The supported geometry, target, and exclusion semantics are defined in the
[Corpus and Target Contract](../../wiki/datasets/Corpus-and-Target-Contract.md).
