---
title: Limitations
status: canonical
last_updated: 2026-08-19
paper_source: true
prose_reviewed: true
claim_ids: C-GEOM-001, C-FEM-003, C-CPS-DISC-001, C-ACC-001, C-LAT-001
---

# Limitations

1. The active layouts are synthetic active-leg abstractions rather than complete
   routed windings. Returns, vias, terminals, planes, and core windows are absent.
2. The capacitance model uses an effective uniform dielectric and one
   electrostatic volume-FEM implementation.
3. FEM-R3P16 failed the mesh-sensitivity gate. FEM-R4P16 is more resolved but has
   not been compared with refine-5 or an adaptive error estimator.
4. Numerical solver agreement does not establish agreement with a fabricated
   board. Connector fixtures, solder, copper roughness, anisotropy, and
   manufacturing variability are not modeled.
5. FastHenry supplies free-space winding inductances. The GNN does not model the
   nonlinear ferrite magnetic circuit or frequency-dependent permeability.
6. The current family-crossed accuracy study is complete, but paired
   current-corpus latency is not. Historical v2 values cannot be promoted to
   current claims.
7. The crossed-axis ranges are descriptive sensitivity intervals for the
   evaluated split and initialization grid. They are not population confidence
   intervals and do not cover cross-machine, protocol, or fabrication
   uncertainty.
8. The 198-layout R3/R4 registry is deterministic rather than probability
   sampled. Nine anchors were inherited from a convergence selection that used
   capacitance order statistics, while 189 entries were selected from geometry
   descriptors. Its discrepancy summaries describe that panel and do not
   support population coverage or a global correction.
