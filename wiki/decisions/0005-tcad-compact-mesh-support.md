---
title: Bounded Compact-Support Feasibility After the TCAD Pilot
status: REJECTED; bounded trial incomplete; original decision preserved
last_updated: 2026-10-02
paper_source: false
---

# Bounded Compact-Support Feasibility After the TCAD Pilot

The bounded trial is now closed at the local0 AMG operator-complexity cap,
before CG or a capacitance result. Its [evidence](../evidence/TCAD-Cps-Support-Recovery.md)
is retained; this does not establish compact-support accuracy or infeasibility
under every solver policy. The decision below records the original trial.

The owner requested the next step after the original three-sentinel pilot
stopped at the mesh-node cap. Preserve that rejected pilot, its frozen source
and all outcomes. The [archive](../evidence/TCAD-Cps-Reference-Pilot.md) and
geometry/cost receipt separate an execution-budget limit from numerical accuracy.

The largest sentinel used most of its local2 worker time generating a mesh
that was rejected before matrix assembly. Memory was not the limiting gate.
The chosen next step is a new, single-sentinel feasibility study that changes
the spatial extent of the fine-size field, not its three near-size values,
physical geometry, solver tolerance or resource caps.

Use a 0.055 mm conductor-box expansion and 0.5 mm transition thickness. The
expansion is half the 0.11 mm nearest projected interlayer gap in the selected
geometry, so the opposing expanded boxes still cover that nearest gap. It does
not imply that every larger gap or fringing-field region has the same fine
size. The sum of expanded-box volumes is a geometric cost proxy, not a union
volume, mesh-count estimate or error bound. Its reduction motivates the trial
but cannot establish that the new mesh will fit or remain accurate.

Start only with layout 597, the failed sentinel. Run the compact refinement,
repeat, padding and far-size arms anew, plus a fresh wider-support control at
the intermediate level. This control checks sensitivity to both support
changes together; it cannot separate their individual effects or substitute
for a finest-level support test. No old value is substituted for a new arm.

The [method](../methods/TCAD-Cps-Compact-Support-Recovery.md) freezes exact
comparisons and limits. A single-layout pass is only evidence for considering
a new full-pilot protocol. It does not repair the rejected original study,
qualify a reference, reopen training or enter a paper. An outcome requiring
larger caps or different controls needs another explicit version and decision.
