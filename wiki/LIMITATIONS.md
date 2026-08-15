---
title: Limitations
status: canonical
last_updated: 2026-08-15
paper_source: true
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
6. Current geometry-valid multi-seed accuracy and paired latency results are not
   yet complete. Historical v2 values cannot be promoted to current claims.
7. Confidence intervals from design, family, split, and initialization
   resampling do not include cross-machine or fabrication uncertainty unless
   explicitly stated.
