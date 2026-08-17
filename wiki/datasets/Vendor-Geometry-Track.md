---
title: Vendor Geometry Track
status: proposed external validation track
last_updated: 2026-08-17
paper_source: false
---

# Vendor Geometry Track

The local research workspace contains a manufacturer datasheet, mechanical STEP
assembly, and LTspice package for Würth Elektronik part 750341134. These files
are not redistributed until their license and redistribution terms are checked.
Their presence does not make the current corpus hardware-validated.

## What the three files contribute

| Asset | Useful information | Missing information |
|---|---|---|
| Datasheet | Product dimensions, turns ratio, test conditions, inductance and leakage bounds | Full field geometry, material curves, and de-embedded parasitics |
| STEP assembly | Commercial package surfaces and component placement | Reliable electromagnetic materials, winding net assignment, terminal conditions, and manufacturing tolerances |
| LTspice model | Vendor circuit-level behavior and lumped elements | A unique mapping from each circuit element to this project's air-core targets |

A STEP file is a mechanical description, not a solver-ready electromagnetic
model. Copper, dielectric, ferrite, gap, connectivity, excitation, and boundary
conditions must be assigned and recorded independently.

## What a commercial geometry can demonstrate

A correctly segmented and parameterized model can test whether the meshing and
solver pipeline accepts a commercial package, whether a synthetic-trained model
transfers outside its generator, and whether sensitivity rankings remain useful
under commercial geometry constraints. Comparison with a datasheet limit is a
product-level sanity check. It is not equivalent to de-embedded measurement of
the four project targets.

One part cannot establish population-level generalization. A measured component
with documented fixtures and de-embedding would provide stronger validation.

## Geometry-preserving perturbations

One nominal STEP may yield a controlled family rather than one sample. Candidate
variables include lateral winding registration, inter-layer spacing, insulation
thickness, copper thickness, winding offset, core-to-winding alignment, and a
documented core-gap variation for core-inclusive studies. Mesh level is a
numerical sensitivity variable, not a new physical sample.

Every variant retains the base part ID, geometry family ID, perturbation vector,
material and terminal assignments, source hashes, and solver protocol. Splits
are grouped by base part and perturbation family or reserve a declared region of
the perturbation space for testing.

## Admission gates

1. Verify the vendor files against a local manifest and record their source.
2. Resolve redistribution and derivative-model licensing before committing an
   asset or exported mesh.
3. Segment solids and document all material and net assignments.
4. Pass geometry, mesh, residual, domain, and passivity checks.
5. Compare quantities only when the vendor test condition and project target
   have matching definitions.
6. Keep commercial-anchor results separate from fabricated-board measurements.
