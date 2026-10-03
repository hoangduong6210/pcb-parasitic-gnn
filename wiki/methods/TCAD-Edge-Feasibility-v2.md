---
title: TCAD Edge-Local Planar Feasibility v2
status: PROPOSED; model-backed probe integration
last_updated: 2026-10-03
paper_source: false
---

# TCAD Edge-Local Planar Feasibility v2

## Change boundary

Integrate the separately [qualified native adapter](TCAD-Native-Field-Probe.md)
into a new version of the [edge-local study](TCAD-Edge-Feasibility.md). Preserve
the original failed implementation and archive. Change only the probe API and
its observed-state/raw-data preservation. The sizing definition, original
geometry, conductor identities, transition, near/far sizes, mesh options,
capacity caps, quality thresholds and toy/sentinel/repeat coverage are unchanged.
Inherit real-layout resources from edge v1, not the smaller synthetic API study.

Each fresh worker audits the fragmented planar CAD, applies the original
finite-segment distance/linear Threshold field, and preserves native field,
option, CAD and empty-mesh snapshots. In an isolated model-backed point view,
sample both distance and final size at the existing deterministic layout probes.
Preserve every request, scaffold, initial/output view and cleanup record. Compute
the exact projection oracle only inside the guarded SLURM worker. Preserve the
comparison before its numeric gate; preserve the final original-model snapshot
even when a probe fails. Meshing requires both numeric agreement and unchanged
observed original state. These checks do not certify hidden native caches.

## Unchanged downstream checks

Generate only the native 2D mesh, preserve its raw bundle, then perform the
existing planar ownership, topology and leakage audit and prospective vertical
column capacity, conditioning and volume checks. Do not generate volume
connectivity, solve a field, train a model or admit a paper claim. Repeat must
match the full report and raw bundle; the report binds all probe raw/state files.
Any native/probe/planar audit failure stops the mode sequence without retry.
Prospective capacity failures remain reportable diagnostic outcomes.

Terminal inspection is byte/scalar metadata closure only: bind recorded points,
tags, raw values, field definitions and before/after state. Do not reconstruct
layout probe geometry or replay real-mesh numerical audits on login. Retain the
600-second, 6-GiB worker bounds, one-CPU/8-GiB/35-minute request, and existing
payload caps. Freeze and publish the new source before one SLURM attempt.

## Preparation

On 2026-10-03 the prior published checkpoint was reverified locally with a clean
worktree and no active owner jobs. Implementation and synthetic negative tests
are in progress; no v2 native attempt has run. The full TCAD goal remains active
and incomplete. New results will be recorded in an indexed evidence owner.
