---
title: TCAD Compact-Support Recovery Method
status: REJECTED; frozen protocol retained after incomplete execution
last_updated: 2026-10-02
paper_source: false
---

# TCAD Compact-Support Recovery Method

Execution closed at the local0 AMG cap before a capacitance result; see the
[terminal evidence](../evidence/TCAD-Cps-Support-Recovery.md). The contract
below is preserved unchanged, not amended to admit that failure.

## Question and unchanged contract

Can a more compact fine-mesh region complete the largest sentinel within the
original resource caps while satisfying the declared single-layout diagnostic
checks? The [decision](../decisions/0005-tcad-compact-mesh-support.md) records
why this follows the rejected original pilot. The machine protocol is
[`tcad_cps_support_recovery_v1.json`](../../protocols/tcad_cps_support_recovery_v1.json).
It inherits a SHA-256-pinned original protocol and keeps its canonical conductor
volumes, uniform dielectric, terminal potentials, natural outer boundary,
energy definition, AMG-CG solver, near-size ladder, numerical threads and caps.

Only layout 597 is authorized. Its geometry hash is pinned to the original
twelve-layout panel, and it is already development evidence, not a blind test.
No comparison across two different support policies is labelled an unchanged
fidelity result. Successful old arms are retained, not reused as new results.

## Compact and wider support

The compact policy uses a 0.055 mm expansion of every conductor box and a
0.5 mm outer transition. The original wider policy uses 0.11 mm and 1.5 mm.
Gmsh's Box field assigns the near size inside the expanded box and interpolates
toward the far size through the specified outer transition; the Min field
combines conductor fields. See the
[Gmsh field reference](https://gmsh.info/doc/texinfo/#Specifying-mesh-element-sizes).
This changes the size-field region, not the conductor volume or dielectric.

The near sizes remain 0.12, 0.08 and 0.05333333333333334 mm. The nominal far
size remains 4 mm, with an independent 2 mm check. Padding is 16 mm, with a
20 mm check. The original options disabling point sizing, curvature sizing and
boundary extension remain unchanged. This is prescribed mesh sizing, not an
adaptive error estimator.

| Order | Arm | Near level | Support | Padding | Far size |
|---:|---|---:|---|---:|---:|
| 1 | local0 | 0 | Compact | 16 mm | 4 mm |
| 2 | local1 | 1 | Compact | 16 mm | 4 mm |
| 3 | local2 | 2 | Compact | 16 mm | 4 mm |
| 4 | repeat2 | 2 | Compact | 16 mm | 4 mm |
| 5 | pad20 | 2 | Compact | 20 mm | 4 mm |
| 6 | far2 | 2 | Compact | 16 mm | 2 mm |
| 7 | support1 | 1 | Original wider support | 16 mm | 4 mm |

All arms are fresh processes. Stop at the first failed arm, retain it, and do
not skip ahead. A preceding compact-support toy smoke compares AMG and direct
solutions on the same matrix under the inherited smoke gates.

## Feasibility checks and interpretation

Every completed arm must pass the inherited positive finite capacitance,
residual, mesh size, operator complexity, memory and timeout checks. Require
all seven arms and terminal success with zero restarts before numerical
assessment. Compare local1/local2, pad20/local2 and far2/local2 using
`100*abs(candidate-reference)/abs(reference)`. Compare support1/local1 with
the compact local1 as denominator. Each must be at most 5%, the original
per-layout maximum gate. Repeat2/local2 must meet the inherited relative
repeatability limit of 1e-4 and identical system hash and mesh counts.

No three-layout median is computed in this single-layout study. The original
2% median and 5% maximum criteria remain requirements of a future full-panel
protocol; this diagnostic does not lower or replace them. The intermediate
wider-support check is not a finest-level error bound. Even complete success
does not prove continuum convergence or physical accuracy. Outputs explicitly
keep three-sentinel qualification, automatic expansion, training and claim
eligibility false. A complete negative numerical outcome is valid evidence;
incomplete execution remains incomplete.
