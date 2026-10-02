---
title: TCAD Capacitance Reference Qualification
status: PROPOSED; owner-approved bounded pilot; not a qualified reference
last_updated: 2026-10-02
paper_source: false
---

# TCAD Capacitance Reference Qualification

## Question and version boundary

Can local refinement around the canonical conductor volumes meet the existing
finite-panel sensitivity targets within a bounded one-thread resource budget?
The owner approved implementation of Stage 1 of the
[TCAD research plan](../manuscript/TCAD-Research-Plan.md). This new pilot does not
alter the old R3/R4 protocols, labels, negative convergence result, admitted
claims or released journal snapshots. A passing pilot would support considering
panel expansion, not a continuum-convergence claim or immediate GNN training.

The machine specification is
[`tcad_cps_reference_v1.json`](../../protocols/tcad_cps_reference_v1.json).
The [runbook](../operations/TCAD-Cps-Reference-Pilot.md) owns execution and
the [evidence record](../evidence/TCAD-Cps-Reference-Pilot.md) owns observations.

## Geometry-only development panel

The verified corpus-v3 geometry root has 1,500 distinct geometries. Labels are
not used for selection. Conductor-count intervals are 1–14, 15–21 and 22–28.
Within each interval, split by rank into two clearance groups, then split each
group by rank into two projected-overlap groups. The lower half has floor(n/2)
members. Empty groups fail rather than invoking a fallback. Numeric ties use
the SHA-256 of `tcad-cps-reference-v1:` followed by the geometry hash.
Each of the twelve cells contributes its lowest salted-hash member.

Clearance is the minimum xy box clearance among same-layer conductor pairs;
if no pair exists, use the board diagonal and mark that fallback explicitly.
It is not a varying interlayer dielectric thickness. Overlap is the sum of xy
intersection areas over unordered opposite-net pairs; overlapping projections
of different pairs remain separate contributions. Actual cell ranges and
population counts are recorded in the generated panel.

One sentinel per count interval is selected from the four representatives:
most conductors, then greatest overlap, then smallest clearance, then salted
hash. The selected identifiers and geometry hashes are frozen before solving.
The existing corpus has been inspected previously; this is a development panel,
not a new blind model-evaluation set.

## Physics and candidate mesh policy

Keep the original canonical conductor boxes, uniform relative permittivity
4.2, primary potential 1 V, secondary potential 0 V and natural homogeneous
Neumann outer boundary. Capacitance is twice the stored field energy at unit
voltage. The inherited model excludes returns, vias and cores. No hardware
measurement or heterogeneous-stackup accuracy is asserted.

The original FEM implementation is unchanged. Its callback immediately before
mesh generation installs the new background field. Each conductor box expands
by 0.11 mm in every direction and receives a Gmsh Box size field with a 1.5 mm
outer transition. A Min field combines these fields. The three near sizes are
0.12, 0.08 and 0.05333333333333334 mm; the default far size is 4 mm. Disable
point-derived sizing, curvature sizing and boundary-size extension; clamp the
size range to the specified near and far sizes. Use single-thread Delaunay
meshing with a fixed seed. These settings follow the background-field and Box
definitions in the [Gmsh reference manual](https://gmsh.info/doc/texinfo/).
This is a prescribed local-size policy, not an a posteriori adaptive estimator.

Each sentinel runs six fresh-process arms in this order:

| Arm | Near level | Padding | Far size | Purpose |
|---|---:|---:|---:|---|
| local0 | 0 | 16 mm | 4 mm | Coarse local mesh |
| local1 | 1 | 16 mm | 4 mm | Intermediate local mesh |
| local2 | 2 | 16 mm | 4 mm | Finest planned local mesh |
| repeat2 | 2 | 16 mm | 4 mm | Fresh-mesh repeatability |
| pad20 | 2 | 20 mm | 4 mm | Outer-domain sensitivity |
| far2 | 2 | 16 mm | 2 mm | Outer-mesh sensitivity |

The first failure stops that sentinel and retains its successful preceding
arms, failed logs and resource outcome. No automatic retry, outlier removal,
larger cap or full-corpus refinement is permitted by this protocol.

## Numerical and feasibility gates

AMG-preconditioned CG uses relative tolerance 1e-10 and at most 500 iterations.
Require positive finite capacitance and relative residual at most 1e-9.
A preceding small two-conductor smoke job compares AMG and direct solutions
on the same matrix: their system hashes must agree and relative capacitance
difference must be at most 1e-6. This checks implementation consistency, not
physical accuracy or mesh convergence.

For mesh sensitivity compare local1 with local2. For padding compare pad20
with local2; for outer-mesh sensitivity compare far2 with local2. In each case
the percentage is `100*abs(candidate-reference)/abs(reference)` with local2
as reference. Each comparison must have median at most 2% and maximum at most
5% over all three sentinels. local0 versus local1 is reported descriptively.
Fresh repeats require identical system hash and mesh counts plus relative
capacitance difference at most 1e-4, with local2 as denominator.

All expected arms, terminal scheduler records, source/input hashes and resource
gates must pass before assessing numerical stability. Failed or missing arms
cannot disappear from the denominator. Even three passing sentinels do not
qualify the twelve-member panel, prove continuum convergence, validate a real
PCB or authorize later learning stages. An independent extractor remains a
separate follow-up after feasibility is established.
