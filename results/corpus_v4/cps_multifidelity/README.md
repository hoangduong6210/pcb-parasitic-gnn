# Corpus v4 multi-fidelity closure

This directory contains the tracked scientific closure for the explicit-
fidelity capacitance package. The accepted task records stay at their original
repository-relative paths because the accepted sets bind each path and byte
hash. Moving or rewriting those records would break the finalized provenance
chain.

## Contents

- `plan/v1/`: frozen geometry families, higher-fidelity selection, split
  registry, and dense R3/R4 manifests;
- `index/*_retry_01_candidates.json`: cumulative candidate indexes admitted by
  the final resume pass;
- `resume/*_retry_01/accepted_artifact_set.json`: dense accepted sets with
  1,500 R3 and 198 R4 task records;
- `r3/attempts/` and `r4/attempts/`: exactly the 1,698 accepted task JSON files;
- `final/job_6893754/`: the 1,698-row observation table and final summary.

Operational start snapshots, bulk scheduler logs, dispatch copies, failed
attempt outputs, initial sparse indexes, and pending sets are intentionally not
part of this scientific package. Their incident identities and hashes remain in
the [Evidence Ledger](../../../wiki/evidence/Evidence-Ledger.md).

## Closure identity

| Item | Value |
|---|---|
| Archive-manifest SHA-256 | `567c1187ca74e0148691b9ac464a51f5fd014862e2c120d03963b2eacc681505` |
| Source commit | `d6162b1c4c502cca2a880a32fce2b1d894ff808b` |
| Plan SHA-256 | `419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a` |
| Protocol SHA-256 | `36bbda0935c3bbc7c3f61de3ac67c603430e05df65551823ad6eabed37051c4b` |
| Execution-lock SHA-256 | `697dd97a20fc93c8e512e9546f520b3e6ecf04b556b0ac10d0ea1f3dcf9397bb` |
| Final R3 accepted-set SHA-256 | `dd2f5fe7bc57366eddeead3a4761c58818c4186314c57cb13b9277b452f2db0f` |
| Final R4 accepted-set SHA-256 | `4ed4bd5652688457e803f9fd377ba38fec83f5fee08a44698d374b9764cc82b1` |
| Final summary SHA-256 | `5f3a9158eac1cab5289ceddafba0037b37daecafc88d8eed01179b8dfdd457c6` |
| Observation-table SHA-256 | `c17f71187e31fd10152ac0b459694a022be0d41b132ed7c5992d94d96219795b` |

## Clean-clone audit

The canonical read-only gate checks source Git blobs, frozen plan descendants,
every accepted task byte and identity, final rows, and exact coverage without
running a field solver:

```bash
python3 code/quality/verify_corpus_v4_archive.py --require-git-tracked
```

The lower-level byte-only equivalent is:

```bash
(
  jq -r '.entries[] | "\(.artifact_sha256)  \(.path)"' \
    results/corpus_v4/cps_multifidelity/resume/r3_retry_01/accepted_artifact_set.json
  jq -r '.entries[] | "\(.artifact_sha256)  \(.path)"' \
    results/corpus_v4/cps_multifidelity/resume/r4_retry_01/accepted_artifact_set.json
) | sha256sum -c --quiet

sha256sum \
  results/corpus_v4/cps_multifidelity/final/job_6893754/summary.json \
  results/corpus_v4/cps_multifidelity/final/job_6893754/label_observations.jsonl
```

The exact finalizer replay remains SLURM-only because its source enforces a
scheduler allocation. Use `datasets/corpus_v3` as the corpus input and follow
the [SLURM Submission Playbook](../../../wiki/operations/SLURM-Submission-Playbook.md).

## Public provenance boundary

Accepted task JSONs retain the scheduler account, host, node, job identifiers,
and absolute execution paths captured by the frozen run. These fields are not
credentials; they are immutable machine provenance needed to preserve the
accepted-set hashes. They are public evidence under `results/`, but are excluded
from manuscript packages and from every wiki page marked `paper_source: true`.

R4 is a higher-resolution observation, not continuum or physical ground truth.
The package finalizes data provenance; it does not by itself admit an accuracy,
generalization, or speed claim.
