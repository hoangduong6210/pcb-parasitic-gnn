---
title: TCAD Saved-Packet Jacobian Arithmetic Evidence
status: PROPOSED
last_updated: 2026-10-03
paper_source: false
---

# TCAD Saved-Packet Jacobian Arithmetic Evidence

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
