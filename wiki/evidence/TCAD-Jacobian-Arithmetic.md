---
title: TCAD Saved-Packet Jacobian Arithmetic Evidence
status: VALIDATED; arithmetic diagnosis only; terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD Saved-Packet Jacobian Arithmetic Evidence

## Terminal diagnosis on 2026-10-03

At **10:29:33 UTC**, exact accounting showed job `7652241` terminal
`COMPLETED/0:0`, zero restarts, 48 elapsed seconds, three allocated CPUs and
8 GiB on `a0113`. The queue was empty. One CPU was requested; all scientific
thread settings remained one. No geometry generation, optimization, field
assembly or solve occurred. All three fresh workers completed, and the
independent rational algorithms agreed for every element.

| Archived diagnostic | Raw | Final | Repeat final |
|---|---:|---:|---:|
| Tetrahedra examined | 3,643 | 3,541 | 3,541 |
| Exact positive determinants | 3,643 | 3,541 | 3,541 |
| Exact zero or negative determinants | 0 | 0 | 0 |
| Original native/NumPy gate mismatches | 6 | 2 | 2 |
| Native errors outside tolerance against exact stored coordinates | 15 | 4 | 4 |
| NumPy-vector errors outside tolerance against exact stored coordinates | 14 | 4 | 4 |
| Scalar-float errors outside tolerance against exact stored coordinates | 14 | 4 | 4 |
| Nonpositive saved native SICN | 1 | 0 | 0 |
| Complete report bytes | 4,443,554 | 4,330,298 | 4,330,298 |

The diagnostic error denominator is the absolute exact stored-coordinate
determinant, whereas the original gate uses native magnitude through NumPy
`isclose`. These are separately labelled comparisons, not substituted gates.
All original relative/absolute tolerances remain unchanged.

Final tetrahedra **3160 and 4964** fail the original gate. Four final elements
have errors exceeding tolerance against exact arithmetic: **3160, 4964, 5523,
5635**. The last two pass native/NumPy agreement while both estimates are wrong
at that tolerance. Agreement alone therefore missed their arithmetic error.
All four have native SICN on the order of `1e-14`. Saved hexadecimal coordinates
of the two gate failures show near-vertical node pairs differing by one binary64
step in a horizontal coordinate, consistent with nearly coplanar slivers and
cancellation. The diagnosis establishes floating-evaluation error on these
stored coordinates; it does not establish a Gmsh implementation defect,
continuum geometric accuracy or a safe FEM conditioning bound.

No stored-coordinate inversion or exact degeneracy was found. Strictly positive
exact determinants do **not** make these elements usable. The original mesh
remains rejected; its downstream facet, volume and terminal checks were not
completed. No reference/training/claim gate opens.

Parent-observed worker times were 9.517149785999209, 9.015219527995214 and
9.015281026950106 seconds for raw/final/repeat-final. The worker-reported times
were 4.9919007930438966, 4.760602083057165 and 4.730881784111261 seconds;
those include loading/reporting/post-source checks, not pure determinant time.
Peak worker RSS was below 0.058 GiB. These are diagnostic costs, not field
extraction latency or a performance contribution.

## Checked terminal preservation

The additive collector passed 24 synthetic cases before collection. It copied
all **17 terminal members**, including every complete per-element report,
receipts, stdout/stderr, scheduler logs, accounting and submission. Source,
byte/hash, coverage and repeat checks passed on login without numerical replay.

- [Archive manifest](../../results/tcad/cps_jacobian_arithmetic_v1/archive/job_7652241/manifest.json)
  SHA-256: `9cad8aa54f37f7f356a08c890878bab4a449d31a75842a119facec1eee5bef31`.
- Attempt SHA-256: `5f9ec83c09f9d8952d08a48d822554f035f367accd2478cc1768ff2013f6e38f`.
- Raw report SHA-256: `550700a66b188bdf47d120bd70a0589d188c73ae07fd95bcfa388808ea4d3a1a`.
- Final and repeat-final report SHA-256:
  `6cebb86dc2c60d7c3696bef71357b4a6f40820bb2e1fcb82ce1d5e1f20f1683c`.

The execution source/lock below remains immutable; this collector was added
after execution-source freeze. Terminal regression and publication of this
checkpoint follow. Earlier pending statements below describe historical stages.

The terminal regression subsequently passed **182 tests with zero skips** in
45.30 seconds, including the actual arithmetic archive, byte-only rejected-mesh
archive, new guards/exact algorithms and wiki/prose checks. The frozen execution
regression had already passed 443 tests. The collector is
`code/experiments/proofs/archive_tcad_cps_jacobian_arithmetic_v1.py`; `--check`
only verifies source, report metadata and bytes, never recomputes determinants.
Two completed synthetic collector/wiki fixture directories were removed;
all source worktrees and scientific evidence remain preserved. Publication
follows the final wiki/prose and tracked-manifest checks.

## Research decision

Keep the old rejection and its failed tolerance. Do not rerun the optimizer,
accept absolute determinants, remove selected elements or patch only the two
mismatch IDs. The exact-arithmetic result shows why a prospective mesh policy
must address near-coplanar slivers and conditioning rather than merely make two
floating calculations agree.

Next, assess a geometry-conforming, layer-aligned structured candidate for the
axis-aligned canonical boxes. First inspect coordinate-plane separation and
prospective cell count; no snapping, geometric change or cell omission is
implicitly allowed. If suitable, freeze a separate bounded mesh-only protocol
with signed/conditioning and complete boundary gates before SLURM execution.
It must preserve the finite-domain physics and rejected baseline. This is
reference engineering, not the TCAD learning contribution. Field restriction,
analytic-box checks and mesh/domain sensitivity remain later gated stages.

## Preparation on 2026-10-03

The [method](../methods/TCAD-Jacobian-Arithmetic.md) is a read-only diagnosis of
the complete raw/final toy packets from rejected job `7652212`. Parent archive
SHA-256 is `787aafe6f1d37cdde5abbe4fecc5836f0f4d4aa1abcaeb473a0b3a55eecc0369`.
Input identities and exact row counts are fixed in the new protocol. Old
source `3187f810557957aa6c2188db2174c295d5a6c21a`, rejected evidence, tolerances,
optimizer policy and unrun sentinel remain unchanged.

New implementation covers exact all-element arithmetic, finite floating
reconstruction, deterministic full reports, independent algorithm agreement,
guarded fresh workers and byte-only receipt checking. Synthetic software tests
are being run. No real packet arithmetic, new native mesh or field solve has
run during this preparation; no new job is submitted. Source freeze and
publication precede any SLURM submission. No scientific result is claimed.

## Source freeze

The new immutable source lock includes 293 dependencies. Protocol SHA-256 is
`dc271f0eb498ae78ac63078f821aa9dca811f347f304ada8a4c89ea9306dda01`; lock
SHA-256 is `1bce5b7db75abf05ae4a954044e43880ba173a76791727f80c4a8914aae18278`.
The expanded pre-freeze suite passed 129 tests with one expected lock skip.
An earlier synthetic unknown-node test exposed shared test-array storage; its
fixture was corrected to use separate connectivity storage, and the case now
passes. This was a test-fixture issue, not a real-mesh observation.

The first full-suite command named a nonexistent historical test file, so
collection stopped without running tests. The corrected frozen regression is
running; neither event triggered scientific execution. Two completed temporary
fixture directories were removed to recover file quota; scientific evidence
and source checkouts were retained. No job has yet been submitted.

The corrected frozen regression completed: **443 tests passed, zero skips** in
152.18 seconds. It includes exact-arithmetic/guard/receipt tests, dielectric
mesh and CAD regressions, existing archive/source checks, original allocation
guards and wiki/prose contracts. No native generation or real numerical packet
replay ran. Publication and one SLURM submission follow; the frozen source
has not been revised after testing. The completed regression fixture directory
and the empty directory from the collection-only failure were also removed;
all scientific artifacts remain intact.

## Publication and submission

At 10:27:42 UTC GitHub main and local HEAD were verified as source commit
`8168208a1248befcaf72a56ed139bf17d230ca56`. The 7,095-file manifest passed;
the final 55 wiki/prose tests passed. Internal agent instructions remain
ignored/untracked. A clean detached sparse worktree materialized exactly 296
tracked files (293 dependencies, lock, ignore rules and repository manifest).
Source/wrapper/runtime checks passed without numerical execution on login.

One `sbatch` invocation at **10:28:33 UTC** returned job **`7652241`** under
the frozen 8-GiB/15-minute profile. Receipt:
`results/tcad/cps_jacobian_arithmetic_v1/submission.json`. No retry, new mesh,
field solve or claim admission is part of this submission. Its outcome is
pending terminal observation and archive verification.
