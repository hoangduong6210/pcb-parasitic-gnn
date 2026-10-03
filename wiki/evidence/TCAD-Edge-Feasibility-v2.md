---
title: TCAD Edge-Local Feasibility v2 Evidence
status: VALIDATED; planar and prospective column gates only
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Feasibility v2 Evidence

## Preparation on 2026-10-03

Local HEAD and GitHub main were reverified at
`4c4fa0a690e0404dc01e592f78edd9736eb4ec52`; no scientific job was active.
The [new integration](../methods/TCAD-Edge-Feasibility-v2.md) retains all
edge-v1 scientific/resource gates and uses the separately qualified adapter.
Its parent is the native API terminal archive, SHA-256
`b4d339befd6993abfd9a36316fb155cfe11afd90b5d4142230aab8e645eb17bd`.
The real-layout baseline protocol SHA-256 is
`16472fe0dc5f6ca880df1e7766330b3a884276ae5c4d1fdce5ba61b4e5027cea`.
Both earlier execution sources and terminal evidence remain unchanged.

Initial fake-native integration passed **79 tests with one expected pre-lock
skip** in 16.35 seconds. The fixture explicitly separates original CAD/empty
mesh, temporary model-backed point elements, and the generated planar packet.
Tests reject plugin, numeric, cleanup and original-state failures before mesh
generation, retain partial raw records, and reject rehashed metadata tampering.
Terminal tests forbid native imports, layout probe reconstruction and actual
mesh planning. These synthetic tests are not native qualification results.

Expanded regression, source freeze/publication and one bounded SLURM submission
are next. No v2 native attempt has run. The full TCAD goal remains active and
incomplete; no new paper claim is admitted or snapshot exported.

Expanded pre-freeze regression passed **563 tests with one expected lock skip**
in 149.55 seconds. A separate tightened protocol-type check passed 80 tests
with the same expected pre-lock skip. The prose audit and wrapper syntax check
passed. Five inspected completed fixture roots were removed without touching
scientific data or execution worktrees. Freeze and rerun the final source suite
before publication and the one SLURM attempt.

## Frozen source identities

- Protocol: `protocols/tcad_cps_edge_feasibility_v2.json`, SHA-256
  `5ce71ce4b556deedada58591051faf429117e70e74e052e3538fdf875ab1bed6`.
- Lock: `protocols/tcad_cps_edge_feasibility_v2.lock.json`, SHA-256
  `6dd9567573dff42854a79a9df16e8c65c97e899aa61fd2c8b365c5ad5fe12d41`.
- Source/input dependencies: 530, including the qualified adapter, unchanged
  real-layout baseline and complete parent terminal archive.

Final frozen regression passed **565 tests, zero skips**, in 160.27 seconds.
No actual layout probe or native mesh has run in v2; source publication remains
pending. Publish this frozen source, verify a fresh sparse worktree, then
submit the single bounded toy/sentinel/repeat attempt.

## Source publication

Source `5a6eb0d7d48114a9d96e15e968ffa54727127c97` was verified against
GitHub main at 16:21:00 UTC. Final checks passed the 7,358-file manifest,
prose audit and 55 wiki/prose tests. Agent guidance remains untracked.
Prepare and preflight the fresh sparse checkout before the single submission.
Source is published; current operational receipts remain local.

The 533-file sparse checkout passed source/wrapper/runtime metadata preflight.
One submission at 16:21:45 UTC returned **job 7655921**; at 16:21:59 UTC it
was running on `a0113`. The receipt is
`results/tcad/cps_edge_feasibility_v2/submission.json`. Monitor this exact
attempt and retain all partial outputs; no automatic retry is permitted.

At 16:22:52 UTC the parent receipt accepted toy; sentinel `local1` had reached
preserved sizing fields after its CAD audit. Toy has an audited 201-node,
378-triangle, 74-line planar mesh; prospective columns have 3,216 nodes and
16,074 tetrahedra and pass all declared planning gates. These are toy-only
results while the attempt remains active; no sentinel result or full-repeat
conclusion is available. The additive collector passed 24 synthetic tests with
one expected pre-collection skip.

At 16:25:43 UTC the parent had accepted sentinel `local1`, including 1,461
native distance/size probes, unchanged observed original state, planar audit
and all four prospective column gates. Its planning stage completed at
116.51 seconds in the worker-stage timing boundary. Fresh repeat remains
pending; no complete-study or electrical-accuracy conclusion is available.

## Terminal result and preservation

At 16:27:32 UTC SLURM confirmed **7655921** as `COMPLETED/0:0`, zero
restarts, 316 seconds on `a0113`; it was absent from the queue. All three
workers passed. The archive collector preserved and checked **101 members**:
`results/tcad/cps_edge_feasibility_v2/archive/job_7655921/manifest.json`, SHA-256
`da56f24bbca687c54fa202c9270dc0fcb85bcf899164bf74f9929e072b8dd381`.
Collection validates bytes and recorded scalar/state closures, without native
initialization or actual-layout geometric/mesh replay on login.

| Mode | Probe points | Audited planar nodes | Triangles | Lines | z points | Prospective node upper bound | Prospective tetrahedra |
|---|---:|---:|---:|---:|---:|---:|---:|
| Toy | 60 | 201 | 378 | 74 | 16 | 3,216 | 16,074 |
| Sentinel 597 | 1,461 | 33,941 | 67,798 | 26,992 | 43 | 1,459,463 | 8,287,554 |
| Fresh sentinel repeat | 1,461 | 33,941 | 67,798 | 26,992 | 43 | 1,459,463 | 8,287,554 |

Each passed native distance/size probes, observed original-state restoration,
planar ownership/topology/leakage audit, and prospective node, tetrahedron,
Jacobian-condition and volume gates. All 67,798 sentinel triangles and 203,394
prism templates were covered by the condition summary, with zero failures at
the unchanged 10,000 bound. This is a geometric upper-bound certificate, not
the condition number of an assembled field system or an accuracy result.

The sentinel and repeat report files are byte-identical, SHA-256
`fe45d84dd9314454ddb969c5d48f07f4223e963a4cb729d3d83ccd9623f5ea7c`.
Each binds all 17 preserved JSON payload members. Their raw bundle manifests
are identical, SHA-256
`426ad63b4d94ded7c28bb327f345e77c63fb10aac596e85b907c71dc9477d3df`,
covering 5,204,832 payload bytes; packet identity is
`39b2ec718d11507ac01d37024c8eb24797e4abf2ec3e6c45b056a9bc08174751`.
Sentinel before/after original-state files and the repeat snapshots have SHA-256
`feb4237ccadf110bdef56e1f7396624c77d3e20227549426382c2dba909c8503`.
These observations do not certify hidden native caches.

Parent-monitored worker wall times were 20.5312, 129.6623 and 130.1635 seconds;
observed peak RSS was approximately 0.0633, 0.1906 and 0.1916 GiB for toy,
sentinel and repeat. These are bounded-study telemetry, not comparative timing
claims. Native planar mesh generation and audits ran only in the verified
SLURM allocation. No volume connectivity, full 3D boundary audit, field solve,
reference qualification, training or publication claim was produced.

## Next scientific action

After terminal regression/publication, specify a separately versioned bounded
3D column-connectivity and boundary qualification using these immutable planar
packets and canonical vertical planes. Preserve original geometry and all
count/conditioning/volume tolerances; audit complete volume and terminal/outer
boundary coverage before any PDE assembly. Plan chunked storage and bounded
memory explicitly for the prospective tetrahedron count. A later field study
must include analytic-box, same-mesh restriction, charge/energy/residual,
mesh/domain-sensitivity and fresh-repeat checks. This pass does not open a
learning run, a three-sentinel expansion or a paper claim. The full TCAD goal
remains active and incomplete; terminal publication is pending.

Terminal regression passed **260 tests, zero skips**, in 82.42 seconds,
including exact terminal archive inspection. The prose audit passed. Four
more completed test roots were inspected and removed; all regular files were
reproducible prose fixtures or synthetic log/watchdog receipts matching their
test source. Scientific artifacts, source worktrees and recovery archives are
unchanged. Final manifest/member checks and publication are next.
