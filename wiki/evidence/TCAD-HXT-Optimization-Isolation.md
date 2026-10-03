---
title: TCAD HXT Optimization-Isolation Evidence
status: PROPOSED; source frozen and validated; no numerical observation yet
last_updated: 2026-10-03
paper_source: false
---

# TCAD HXT Optimization-Isolation Evidence

## Preparation: 2026-10-03

The [method](../methods/TCAD-HXT-Optimization-Isolation.md) and
[runbook](../operations/TCAD-HXT-Optimization-Isolation.md) implement the single
optimization-stage diagnostic recorded after the previous HXT timeout. The
predecessor's 11-file archive remains byte-identical, manifest SHA-256
`76713195d6b46b1197392693408d9ddc268070fb8a137fe3f2cd79a4570eb25c`.
Its terminal/research checkpoint is now published and remotely verified at
`02e1b3b12599feb2f31858c929e6460ee2475554`.

The new implementation has separate protocol, parent, worker and wrapper files.
It adds signed-condition/Jacobian observations before mesh extraction and
checks quality-region counts against the inherited mesh representation.
Initial tests found shared mutable configuration metadata in the new quality
receipt; the metadata is now copied so editing a receipt cannot change its
expected units. The corrected suite passed 48 tests, with the source-closure
check deferred until freeze. Tests use tiny arrays, fake Gmsh and synthetic
receipts; no mesher or solver runs on login.

Freeze, full regression, source publication and scheduler submission remain
pending at this checkpoint. No old source, lock, cap, dataset or paper is
changed. Field computation, reference/training eligibility and new claims
remain closed even if the diagnostic later completes.

## Source freeze

After additional fake-builder integration tests, all 52 new tests passed with
the frozen source. The earlier combined source/archive/wiki/prose suite passed
182 tests with one pre-freeze skip. No previous source was changed.

- Protocol SHA-256: `3ae43c358d362e9aeeb1485f15cb1144eeb114854e544e8d918090b509936dc6`.
- Lock SHA-256: `28c9b79e24703ab916bee4ec81f5d04395efc1767bb7fbc97d721b7c6a594a3c`.
- Source closure: 179 files, excluding the new lock itself.

The closure includes the preceding failed attempt, source validator and archive
checker. This freeze does not validate an actual mesh. Publication and the
single bounded SLURM submission remain pending at this checkpoint.

The combined post-freeze regression then passed all 186 selected tests with no
skips. Prose audit, wrapper syntax and source/documentation diff checks passed.
