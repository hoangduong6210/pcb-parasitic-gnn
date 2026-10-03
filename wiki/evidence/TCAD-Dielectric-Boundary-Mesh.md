---
title: TCAD Dielectric Boundary-Mesh Diagnostic Evidence
status: PROPOSED; guarded implementation under validation; no native execution
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric Boundary-Mesh Diagnostic Evidence

## Implementation checkpoint on 2026-10-03

The previous goal turn made progress by publishing the extraction/boundary
audit and tests. At the start of this continuation, remote main was reverified
as `3ef9401053198e2bab1e5f11fd3013e168722372`, the worktree was clean and the
owner's queue was empty. The full journal goal remains active and incomplete.

The separate [protocol](../../protocols/tcad_cps_dielectric_mesh_v1.json)
now has a guarded live-session builder, worker, externally bounded parent,
SLURM wrapper and deterministic chunked-array storage. It binds the validated
CAD reports from the [CAD-only study](TCAD-Dielectric-CAD-Diagnostic.md).
The construction/removal statements are checked against the immutable CAD
builder by AST comparison; the new path also requires the exact native CAD
hash before generation and unchanged CAD metadata after optimization.

The [method page](../methods/TCAD-Dielectric-Boundary-Mesh.md) owns the
array/facet contract. The live-session integration adds one inherited explicit
optimizer call, raw/final packet preservation and fresh final extraction.
Raw packets are written before optimization, so a later timeout does not erase
the mesh available at that stage. Final packets are written before the strict
audit, preserving a mesh that subsequently fails quality or boundary checks.
Unsupported/nonfinite extraction may still stop before a complete packet;
raw logs and any partial files are retained, never repaired or overwritten.

Binary chunks are at most 32 MiB. A combined raw/final array-payload cap of
2 GiB per mode is new and does not widen any old time/RSS/mesh ceiling. The
metadata-only checker reconstructs the canonical packet hash from labelled
array headers and chunk bytes without importing numerical libraries. Numerical
loading and replay of actual mesh arrays remain compute-only. Exact membership,
shapes, byte sizes, chunk offsets, hashes and absence of symlinks are checked.

Initial integration/storage tests passed 31 cases with one pre-freeze lock
skip. Expanded integration, semantic-failure and array-audit tests then passed
158 cases with that same skip. A small Cartesian fixture fitting the canonical
toy boxes exercises full CAD replay, native-reader adaptation, raw preservation,
post-optimizer coordinate replacement and the actual boundary audit through a
fake API. It is not a native mesh, field result or physical accuracy observation.
The prior 96-node fixture remains a separate array-audit test.

No real CAD, mesh, field solve, training or array replay ran in this preparation
step. No new SLURM job is submitted yet. Source freeze, full regression,
publication and sparse execution-source validation remain prerequisites.
Source, lock, submission, terminal and archive identities will be recorded here
as observed; this preparation record must not be read as execution evidence.

## Source freeze on 2026-10-03

The source lock now binds 252 dependencies, including unchanged predecessor
locks, raw CAD archive members, new code/tests and the wrapper. The pre-freeze
combined new/wiki/prose suite passed 216 tests with one lock skip; the wrapper
syntax and prose audit passed. Post-freeze full regression is running before
publication or submission.

- Protocol SHA-256: `1b415ce95aee2d4cf0766b5e8de4d7f1befe39651f409c68c2f58cd8fa4a5648`.
- Lock SHA-256: `8cf23148f56da0b36580c286c20880b23891c305abd4f43656dfd99e8c13fcc1`.

These identities freeze the new candidate without rewriting an old execution
source. They do not establish native success or authorize an automatic retry.

Post-freeze regression passed all 630 selected tests with no skips, including
the new source closure, full fake-native builder/worker integration, chunk
verification, previous source locks/archives and wiki/prose checks. Protocol
anchors were checked against the actual archived CAD reports. No native
geometry/mesh execution occurred during these tests. Next: source publication
and sparse-checkout validation before one SLURM submission.

## Interpretation gates

Run toy, selected sentinel and fresh repeat under one-thread scientific
execution, stop at the first failure and preserve every attempted mode. Exact
repeat requires matching CAD, raw/final packet, audit and effective-policy
identities. These tests do not qualify the continuum target or a mesh-converged
reference. Field, reference, training and claim flags remain false even if the
mesh diagnostic passes. No old rejected source, tolerance, geometry or cap is
changed, and no automatic fallback, retry or expansion is included.
