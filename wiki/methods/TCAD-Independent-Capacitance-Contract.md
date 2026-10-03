---
title: TCAD Independent Capacitance Comparison Contract
status: PROPOSED; legacy adapters not qualified for the current geometry
last_updated: 2026-10-03
paper_source: false
---

# TCAD Independent Capacitance Comparison Contract

## Source inspection finding

The planned independent extractor check must not directly reuse
[`fastcap_ref.py`](../../code/solvers/fastcap_ref.py) or
[`fastercap_ref.py`](../../code/solvers/fastercap_ref.py) as current-geometry
references. Their `_box_panels` helpers read `z_mm` as the lower face, or use
the legacy fallback `(layer + 0.5) * 0.2`. They do not consume the explicit
layout stackup or validate the canonical geometry. In contrast,
[`geometry_contract.py`](../../code/core/geometry_contract.py) derives the
conductor centre from the explicit stackup and places faces half a thickness
on either side.

A metadata-only check of the frozen TCAD smoke input on 2026-10-03 gives:

| Convention | Primary z interval (mm) | Secondary z interval (mm) | Gap (mm) |
|---|---|---|---|
| Canonical stackup | 0.065–0.135 | 0.245–0.315 | 0.11 |
| Legacy adapter without per-trace z override | 0.100–0.170 | 0.300–0.370 | 0.13 |

This is an input mismatch, not a measured solver error. Both historical
adapters are retained unchanged. No FastCap/FasterCap mesh or solve was run.
Their legacy timings and comments do not qualify a current reference.

## Match the electrical quantity, not only its unit

The frozen [TCAD FEM protocol](../../protocols/tcad_cps_reference_v1.json)
uses a uniform relative permittivity of 4.2, primary/secondary potentials of
1/0 V and a finite outer boundary with homogeneous natural Neumann conditions.
Its scalar is twice field energy at unit voltage. The legacy BEM wrappers
instead return the magnitude of a Maxwell-matrix off-diagonal entry and expose
no matching uniform-dielectric or finite-Neumann-boundary specification.

The [original FastCap publication, author-hosted indexed text](https://www.rle.mit.edu/cpg/publications/pub19.pdf)
defines the conductor charge–potential matrix and a free-space surface-panel
problem. Direct PDF retrieval timed out in this session. It does not establish
equivalence with the project's finite insulated outer boundary.

For a symmetric two-conductor Maxwell matrix, the following distinction is
derived from `Q = C V`, not asserted as an experimental result:

- With voltages fixed to `(1, 0)` relative to infinity, twice the energy is
  `C11`, not generally `-C12`.
- With total charge constrained to zero, define `d = (1, -1)`. The isolated
  two-terminal capacitance is `1 / (d^T C^{-1} d)`, or
  `(C11*C22 - C12*C12) / (C11 + C22 + 2*C12)` when the inverse exists.
- A finite insulated FEM boundary enforces zero total normal flux, but still
  changes the field domain. Even the charge-neutral free-space BEM quantity
  is not an exact finite-domain match without a separate domain-limit study.

These equations are a comparator-design constraint. They do not relabel
existing admitted FEM targets or prove their physical accuracy. Do not select
whichever scalar happens to agree best after observing numerical results.

## Required new implementation and qualification

1. Use canonical validated conductor boxes, identities and net grouping;
   record geometry hashes, face bounds, units and panel orientation. Test the
   exporter on deliberately non-default stackups and unequal thicknesses.
2. Declare the dielectric, infinity/outer-boundary convention and terminal
   constraint before solving. Preserve the full Maxwell matrix and raw logs,
   not only an absolute off-diagonal value. Check units, symmetry, passivity
   and charge/energy consistency independently of FEM agreement.
3. Freeze a finite panel-refinement ladder, resource caps and a small geometry
   subset. Run exporter smoke, meshing and all solver calls through guarded
   SLURM entry points. Historical unguarded main blocks are not runbooks.
4. Separate same-domain backend checks from asymptotic domain comparisons.
   Choose the electrical estimand in advance; qualify mesh and domain effects
   on each side before interpreting discrepancy as a solver disagreement.
5. Preserve failure and nonagreement. No independent-extractor or hardware
   validation claim is available merely because both outputs are in pF.

This review implements the matching requirement in the
[research plan](../manuscript/TCAD-Research-Plan.md); it does not authorize a
different physical target or bypass the active FEM feasibility gates.
