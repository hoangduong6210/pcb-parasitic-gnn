---
title: TCAD Dielectric Boundary-Mesh Diagnostic Evidence
status: REJECTED; toy Jacobian-agreement gate failed; terminal archive checked
last_updated: 2026-10-03
paper_source: false
---

# TCAD Dielectric Boundary-Mesh Diagnostic Evidence

## Terminal observation and archive on 2026-10-03

At 09:46:48 UTC, exact accounting reported job `7652212` terminal
`FAILED/2:0`, zero restarts, 23 elapsed seconds, 41 allocated CPUs and 160 GiB
on `a0116`. It was absent from the queue. Toy was the only attempted mode;
local1 and its repeat were correctly unrun. No job in this chain remains active.

Toy reproduced the frozen CAD report identity before generation. HXT produced
a raw dielectric mesh and the single explicit optimizer returned. Both complete
packets were preserved. The subsequent independent audit stopped with
`native and independently reconstructed Jacobians disagree`. Its comparison
uses the frozen relative tolerance `1e-8` and zero absolute tolerance; no
threshold was changed after observing the result. Later volume-sum/facet/terminal
checks and the final post-mesh CAD snapshot were not reached. This is not a
passed boundary audit, usable reference or field observation.

| Observation | Raw packet | Post-optimizer packet |
|---|---:|---:|
| Nodes | 1,253 | 1,253 |
| Dielectric tetrahedra | 3,643 | 3,541 |
| Native surface triangles | 2,430 | 2,430 |
| Minimum native signed condition | -2.295723906874384e-16 | 6.398856084358075e-15 |
| Nonpositive native signed-condition count | 1 | 0 |
| Minimum native Jacobian (mm cubed) | 1.0842021724855044e-18 | 4.445228907190568e-18 |
| Nonpositive native Jacobian count | 0 | 0 |
| Canonical array bytes | 370,448 | 363,920 |

Parent-observed worker time was 9.515884320950136 seconds and peak RSS was
0.06568145751953125 GiB. Worker stages recorded raw preservation at
4.706128001911566 seconds, optimizer start at 4.706176914041862, optimizer
finish at 5.132067027967423 and final preservation at 5.158548515988514.
These timing boundaries are not field-extraction latency or a speedup claim.

- Raw canonical packet SHA-256: `7338595872a287e39b1ad7f978fcaab13c20cc4a30021ed5e768b1f05cb64807`.
- Final canonical packet SHA-256: `7a2b4c8a768bd2feb369e3be2c39531cf3a7c90ee7508cf6155bfc6a49e9b4f1`.
- Attempt SHA-256: `d5c047d81db5fd77a07af0666d143ba977294fb3ca03807e3d2db9fd2d27877e`.
- [Terminal archive manifest](../../results/tcad/cps_dielectric_mesh_v1/archive/job_7652212/manifest.json)
  SHA-256: `787aafe6f1d37cdde5abbe4fecc5836f0f4d4aa1abcaeb473a0b3a55eecc0369`.

The additive collector passed 24 synthetic tests before collecting all
31 terminal members: attempt/mode receipts, native stdout/stderr, CAD report,
both array manifests and every chunk, scheduler logs, accounting and submission.
Byte/hash/source/receipt checks passed without native work or numerical array
replay on login. Archive regression now also checks the actual packets by
streaming byte hashes; no numerical loading is performed. Publication and the
final combined regression are pending at this checkpoint. Execution source
remains the separately frozen commit below.

The final combined regression subsequently passed all 655 tests with no skips,
including 25 collector/actual-archive cases, the frozen mesh source and all
selected predecessors. Wiki/prose recheck passed 55 tests; the deterministic
prose audit passed. At 09:57:41 UTC, accounting still reported the same terminal
state; the short-lived queue record had expired, not restarted. Publication
of this terminal checkpoint follows these checks.

At 10:01:36 UTC the complete terminal checkpoint was published and remote-hash
verified as `b426b0afaa1b3d6dd51b3412d3345ee30cfd1910`. Every archive member
is Git-tracked and the 7,085-file manifest passed. Raw native bytes were not
reformatted. Execution source remains `3187f810557957aa6c2188db2174c295d5a6c21a`;
publication does not convert the rejected diagnostic into a qualified mesh.

The raw/post signed minima alone do not identify the mismatching tetrahedra
or prove whether the discrepancy is rounding, conditioning, an API convention
or an implementation defect. Native positivity is not independent accuracy.
Next: freeze a bounded SLURM-only replay of these same packets, locate every
Jacobian mismatch and compare against exact arithmetic on the stored binary64
coordinates. Preserve packet identities and original failed thresholds; do not
regenerate a different mesh, retry the rejected candidate or silently relax the
gate. Field/reference/training/claim flags remain false.

The subsequent [same-packet exact-arithmetic study](TCAD-Jacobian-Arithmetic.md)
has now completed through SLURM and localized floating-evaluation errors on
near-coplanar elements. It found positive exact stored-coordinate determinants
but did not admit this mesh. Its evidence page owns the complete diagnosis and
next prospective mesh-policy decision; the rejection and archive above remain
unchanged. The earlier diagnosis-pending statement is historical.

## Published source and submission on 2026-10-03

Source `3187f810557957aa6c2188db2174c295d5a6c21a` was published and
remote-hash verified. The 7,051-file manifest and final wiki/prose checks passed.
The sparse detached execution checkout materializes 255 tracked files,
including all 252 locked dependencies; 6,797 tracked paths are excluded.
Clean execution-root/commit/wrapper/lock checks and the pinned runtime passed
before [submission](../../results/tcad/cps_dielectric_mesh_v1/submission.json).
No native operation was used for login-node preflight.

The single sbatch invocation was accepted at 09:44:45 UTC as job `7652212`.
At 09:45:25 UTC, both queue and accounting reported RUNNING on `a0116`,
zero restarts and 18 elapsed seconds. Memory policy allocated 41 CPUs for
160 GiB; one CPU was requested and scientific thread settings remain one.
This is an observation of an active allocation, not terminal mesh success.
Next: follow this same job, retain attempted raw/final/partial packets, and
archive exact terminal accounting. Field/reference/training/claim gates stay
closed. Earlier no-submission statements below are historical.

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
