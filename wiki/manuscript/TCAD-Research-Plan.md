---
title: TCAD Research Continuation Plan
status: RUNNING; continuing Q1 goal authorized; scientific gates retained
last_updated: 2026-10-03
paper_source: false
---

# TCAD Research Continuation Plan

## Continuing goal authorized on 2026-10-03

The owner requested autonomous continuation toward a Q1 journal, prioritizing
TCAD. The [goal record](../status/Q1-Journal-Goal.md) defines the standing scope
and completion evidence. Subsequent ordinary implementation steps no longer
need a separate chat approval, but later studies still require their declared
scientific prerequisites and new frozen protocols. Earlier dated statements
about stage-specific approval retain their historical meaning. No gate in an
already frozen experiment is changed by this instruction.

The [related-work audit](../references/TCAD-Related-Work-Audit.md) now identifies
direct prior art in multi-fidelity EM optimization and newer graph/fidelity
surrogates. Generic multi-fidelity graph learning is not the novelty claim.
Original-method review and compatible statistical multi-fidelity controls are
required before any later acquisition study.

The [original-method review](../references/TCAD-Multi-Fidelity-Method-Review.md)
adds distinct latent-conditioning and simple fine-tuning controls, and separates
geometry-only inference from charged low-fidelity solver-assisted screening.
Prior graph methods already compare matched data-generation cost, so that
evaluation practice is not itself the new contribution. These requirements
inform a later frozen learning protocol; they do not bypass reference gates.

## Current checkpoint: both global tensor-grid candidates rejected

The [latest planning evidence](../evidence/TCAD-Layer-Grid-Planning.md) rejects
the projected-support tensor candidate on capacity/conditioning preflight.
The diagnosis and exact repeat are archived; no mesh or field was generated.
The separate [canonical-plane midpoint/face-band study](../evidence/TCAD-Layer-Grid-Dyadic.md)
has also completed and is archived: its condition screen passes, but sentinel
capacity still fails. Do not instantiate or tune either rejected grid. Next:
separately specify a conforming planar-footprint/column feasibility probe that
avoids the full x/y coordinate product. This is a design hypothesis, not a
validated mesh. Geometry, original caps and prior failed gates remain preserved.
The [exact column contract](../evidence/TCAD-Column-Feasibility.md) is now
implemented with synthetic checks of ownership, counts, shared facets and a
new element-map condition certificate. Native 2D integration and its frozen
feasibility protocol remain next; no actual column mesh has been tested.
The sequence below records the earlier CAD, mesh and arithmetic observations.

## Preserved decision after explicit-optimizer timeout: 2026-10-03

The [explicit-optimizer study](../evidence/TCAD-HXT-Explicit-Optimization.md)
is now terminal and archived: toy diagnostic passed, sentinel timed out and
repeat was unrun. Keep the failed source, all-region gates and original caps.
No final sentinel mesh or reference was obtained. The native tail does not
independently map its volume tag to a material, so conductor removal is not a
proven solution to the observed timeout.

Proceed with the separate [dielectric-only formulation contract](../methods/TCAD-Dielectric-Only-Formulation.md)
and metadata-only topology checks. Preserve canonical geometry, terminal and outer-boundary
physics. Real geometry/mesh work remains gated on new guarded source, tests,
frozen protocol and SLURM execution. This is a reference-engineering step,
not a new GNN contribution. The prior optimizer design below is historical.

The [guarded CAD-only implementation](../evidence/TCAD-Dielectric-CAD-Diagnostic.md)
now captures/replays native provenance and complete pre/post entity topology.
Its bounded native job has since passed the declared CAD gates and exact fresh
repeat, with a checked terminal archive. This geometry prerequisite is separate
from mesh feasibility. Next: boundary-aware meshing that binds the validated
CAD reports, verifies surface-to-tetrahedron boundary coverage and disjoint net
nodes, and retains strict signed-quality gates. Field equivalence and later
sensitivity studies still require separate protocols; no learning gate opens.

The [boundary-mesh audit implementation](../methods/TCAD-Dielectric-Boundary-Mesh.md)
now covers native packet reading, complete surface/facet correspondence,
signed determinants and terminal-anchored components using synthetic fixtures.
The [guarded integration](../evidence/TCAD-Dielectric-Boundary-Mesh.md) now
implements the live-session builder, bounded worker/parent and raw/final array
preservation, with a new source/protocol freeze. Complete post-freeze validation
and publish before running through SLURM. No real dielectric-only mesh has yet
been generated or qualified at this implementation checkpoint.

The subsequent [native mesh diagnostic](../evidence/TCAD-Dielectric-Boundary-Mesh.md)
is now terminal at toy's Jacobian-agreement gate. Raw/final packets are archived;
sentinel modes were unrun. Next: a separately frozen SLURM replay locating the
mismatches and testing arithmetic on identical stored coordinates, without
relaxing the gate, regenerating a mesh or opening field/training stages. Native
positive signed metrics alone have not qualified this mesh or its capacitance.

The [exact-arithmetic replay](../evidence/TCAD-Jacobian-Arithmetic.md) has now
completed and is archived. It localized errors on near-coplanar elements and
showed that native/vector agreement can miss errors against exact stored
coordinates. No inversion was found, but positive signs do not establish usable
conditioning. Next: assess a canonical-box-conforming layer-aligned mesh
candidate, checking plane separation and prospective cell count before a new
frozen quality/boundary protocol. No coordinate snapping or selective element
removal is implicitly authorized. Do not retry the rejected HXT source or
relax its gate. This remains reference engineering, not learning novelty.

The first [tensor-grid preflight](../evidence/TCAD-Layer-Grid-Planning.md) is
now terminal and archived. Its global projected-support grid failed frozen
capacity/conditioning checks before 3D generation. The evidence separates
canonical geometry from near-coincident optional support planes and records
the excessive prospective cell count. Next: separately specify and test
canonical-interval midpoint refinement near face bands, preserving geometry,
count caps and quality thresholds. Neither diagnosis completion nor a later
passing plan substitutes for mesh, field and sensitivity qualification.

## Preserved implementation after the toy quality rejection: 2026-10-03

The [unoptimized HXT diagnostic](../evidence/TCAD-HXT-Optimization-Isolation.md)
is terminal at its toy quality gate. It does not establish sentinel feasibility
or usable finite elements. Keep the signed-positive gate and retain the failed
source and archive; do not rerun it with a tolerance or absolute-value change.

Inspection of the [official Gmsh 4.15.2 source](https://gmsh.info/src/gmsh-4.15.2-source.tgz),
`src/mesh/Generator.cpp`, on 2026-10-03 found:

- Lines 1522–1532 exclude HXT from automatic post-generation Gmsh/Netgen
  optimization. Setting `Mesh.OptimizeNetgen` alone therefore does not schedule
  that stage for the HXT path in this version.
- Lines 873–910 dispatch the explicit default optimizer through
  `optimizeMeshGRegion` for each region, then orient volumes positively. This
  is separate from HXT's internal optimization branch. It does not guarantee
  removal of small or ill-conditioned elements.
- The default branch does not use `niter` as its internal work bound. One API
  call is not evidence of one bounded internal iteration; the parent watchdog
  must still enforce the full worker ceiling.

The [pinned API documentation](https://gmsh.info/doc/texinfo/#gmsh_002fmodel_002fmesh_002foptimize)
exposes this path as `gmsh.model.mesh.optimize` with an empty method name.
This motivates one new candidate, not a mesh-quality or performance claim.
No source was compiled, installed or numerically executed during this review.

Prepare a separate mesh-only protocol: unchanged HXT generation with
`Mesh.Optimize=0`, followed by exactly one explicit default-optimizer call,
`method="", force=False, niter=1, dimTags=[]`. Pin and read back its effective
quality-threshold option in the new protocol rather than rely on a mutable
runtime default. Keep geometry, Box fields, sizes, padding, seed and threads
unchanged. Record pre-optimization and post-optimization signed-condition and
Jacobian summaries, region counts, array identities and stage times. Invalid
pre-optimization metrics are retained as observations, not converted to a
passing mesh; post-optimization finite/strict-positive gates remain mandatory.
Check structural validity and resource caps at both stages. No fallback method,
optimizer search, iteration escalation or automatic retry is included.

Implementation needs a separate builder because the existing frozen builder
reads node coordinates **before** its `mesh_generated` callback. Optimizing
inside that callback could pair stale coordinates with changed connectivity.
The new path must optimize before coordinate extraction, then fetch fresh node
tags, coordinates and tetrahedra. Test this order with a fake optimizer that
changes both coordinates and connectivity; never patch the old builder or use
a global API monkeypatch in production. Bind final quality-region counts to
the exact extracted mesh and retain the old source unchanged.

Keep toy/local1/fresh-repeat order, 600/1,200/1,200-second ceilings, existing
RSS/mesh caps and a single 160 GiB/55-minute SLURM allocation. Generation,
optimization, both quality observations and extraction share those same
ceilings. Stop on the first failure. Freeze and publish new source/lock before
submission. Even a complete positive repeatable result remains diagnostic:
field solving, conditioning, sensitivity, reference qualification, learning and
new manuscript claims stay closed. A later field qualification is a separate
decision. The [separate implementation](../methods/TCAD-HXT-Explicit-Optimization.md)
now includes a guarded fresh-extraction builder and fake-native integration
tests. Its [evidence page](../evidence/TCAD-HXT-Explicit-Optimization.md) owns
source freeze and scheduler receipts. Its later terminal failure does not
admit numerical quality, reference accuracy or a mesh-sensitivity conclusion.

### Source-only follow-up question while the fixed diagnostic runs

The [initial sentinel observation](../evidence/TCAD-HXT-Explicit-Optimization.md)
contains more conductor-interior tetrahedra than dielectric tetrahedra. Source
inspection of `code/solvers/fem_capacitance_3d.py` lines 353–395 confirms that
every node touched by conductor tetrahedra is fixed to its net's constant
potential, although all volume elements are assembled before condensation.
In exact arithmetic, a P1 element with all nodal potentials equal has zero
gradient/energy and no free row in the condensed field equations. Floating-point
energy cancellation on a nearly singular element is not guaranteed by that
mathematical statement. No new field calculation was run during this review.

After the current fixed diagnostic is terminal and archived, investigate a
separate dielectric-only formulation with explicitly tagged conductor surfaces.
Retain the canonical conductor boxes, uniform permittivity, 1/0-V potentials
and finite natural-Neumann outer boundary. Removing unused conductor interiors
could reduce meshing/optimization work, but this has not been measured and is
not an algorithmic novelty claim. It must not mean simply ignoring the failed
conductor quality metrics in the running study.

Such a change needs a new builder/target contract: prove interface coverage and
net tags, compare full-volume and dielectric-only formulations on controlled
geometries, preserve all-region gates for every old artifact, and separately
qualify algebraic accuracy, charge/energy consistency and mesh/domain sensitivity.
Regenerated meshes need not have equal matrix hashes, so the comparison must
state its discretization boundary rather than claim same-system equivalence.
Do not implement or submit this alternative as an adaptive fallback inside
the optimizer job. Its now-archived terminal outcome permits a separate
source-only formulation investigation, not an automatic field solve.

## Preserved decisions after the meshing timeout: 2026-10-03

The initial HXT probe has since closed incomplete; the following new decision
supersedes its execution instruction while preserving the original design below.

### Follow-up after the HXT improvement timeout

The [checked HXT archive](../evidence/TCAD-Cps-Mesh-Probe.md) locates the new
timeout after completed 1D/2D meshing and during 3D improvement. Inspection of
the [official Gmsh 4.15.2 source archive](https://gmsh.info/src/gmsh-4.15.2-source.tgz)
on 2026-10-03 found `src/mesh/meshGRegionHxt.cpp` passing `Mesh.Optimize` into
HXT's optimization flag. In `contrib/hxt/tetMesh/src/hxt_tetMesh.c`, that flag
controls a separate optimization branch after boundary recovery and size-field
refinement. Source was streamed for reading, not compiled or installed. This
supports a targeted diagnostic, not a conclusion that optimization is optional
for accurate field solving.

Prepare one separately versioned mesh-only candidate with `Mesh.Optimize=0`,
leaving HXT, geometry, size fields, seed, threads and caps unchanged. Keep toy,
local1 and its fresh repeat, the 600/1,200/1,200-second worker ceilings and a
single 160 GiB/55-minute allocation. Add predeclared finite-element quality
and region diagnostics, including invalid/degenerate-element checks, before
interpreting a completed mesh. Freeze the exact quality measure and gates from
the pinned API before execution. Preserve logs, times, arrays' fingerprints and
all failures; do not reuse the incomplete predecessor's counts or hashes.

This intentionally unoptimized diagnostic isolates a costly stage. Completion
and repeatability do not prove usable conditioning or discretization accuracy.
Any later algebraic, charge/energy or sensitivity study requires separate
source-bound qualification. Do not substitute an unoptimized mesh for the
reference, reduce quality requirements after results, or raise worker caps.
The [separate implementation](../methods/TCAD-HXT-Optimization-Isolation.md)
now specifies signed condition and Jacobian observations and validity gates.
Its [evidence record](../evidence/TCAD-HXT-Optimization-Isolation.md) owns the
source freeze and subsequent scheduler state; implementation is not execution.

### Preserved initial HXT specification

The seven-arm AMG study closed incomplete at local1's mesh-generation time
limit; its [terminal archive](../evidence/TCAD-Cps-AMG-Feasibility.md) is checked.
This result separates the immediate resource bottleneck from the successful
coarse AMG check, but does not identify Gmsh's slow internal substep. A new
mesh-only diagnostic is the next work package; no failed job is resubmitted.

Test one alternative: Gmsh `Mesh.Algorithm3D=10` (HXT), retaining geometry,
Box fields, local sizes, padding, random seed and one-thread settings. The
[pinned-version Gmsh manual](https://gmsh.info/doc/texinfo/#Choosing-the-right-unstructured-algorithm)
describes HXT as a Delaunay reimplementation supporting general size fields;
the [option definition](https://gmsh.info/doc/texinfo/#Mesh-options) identifies
algorithm 10. This motivates a bounded test, not a prediction that HXT will
fix this geometry or meet the caps. Enable native meshing logs to distinguish
1D, 2D and 3D progress if a worker times out again.

The planned sequence is a mesh-only toy smoke, fresh layout-597 local1 and a
fresh identical local1 repeat. Inherit toy limits of 600 seconds, 6 GiB RSS,
300,000 nodes and 1,500,000 tetrahedra; inherit sentinel limits of 1,200 seconds,
120 GiB RSS, 3,000,000 nodes and 20,000,000 tetrahedra per worker. The aggregate
worker ceiling is 3,000 seconds; a single 160 GiB, 55-minute SLURM allocation
can contain this bounded sequence. No matrix assembly, AMG/CG or field solve
belongs in this probe. Record native logs, stage times, geometry/runtime,
effective mesh options, region/mesh counts and ordered mesh fingerprints.

Freeze code, protocol, exact file closure, repeatability rule and source before
submission. Require complete bounded mesh generation and identical fresh-repeat
fingerprints to consider a later solver study. A changed mesher generates a new
discretization: old matrix hashes and capacitances cannot be reused as results
for it. A pass would authorize preparation of new source-bound backend and
sensitivity checks, not qualify a reference or open training. Failure stops
the probe and is archived without another unrecorded candidate or wider cap.
The [mesh-only implementation](../methods/TCAD-Cps-Mesh-Probe.md) now follows
this specification. Its [evidence record](../evidence/TCAD-Cps-Mesh-Probe.md)
owns validation, source freeze, publication and subsequent scheduler receipts;
implementation alone is not a numerical outcome.

## Research question

Can a graph surrogate that distinguishes numerical fidelities reduce the cost
of selecting useful PCB winding designs at a fixed reference-error budget?

The proposed direction combines learning across solver fidelities with a
design-screening evaluation. It is a research hypothesis, not an admitted
result or a claim of novelty. The current draft retains its existing title and
scientific content until the new contribution is supported by evidence.

The initial literature check includes
[ParaGraph](https://research.nvidia.com/publication/2020-07_paragraph-layout-parasitics-and-device-parameter-prediction-using-graph-neural),
which already uses graph learning for parasitic prediction, and
[parasitic-aware circuit sizing](https://research.nvidia.com/publication/2021-02_parasitic-aware-analog-circuit-sizing-graph-neural-networks-and-bayesian),
which already combines parasitic graph representations, uncertainty and design
optimization. Consequently, adding a GNN or uncertainty alone cannot establish
the proposed contribution. A broader literature comparison remains necessary
before claiming a new method; IC netlist tasks and PCB conductor-geometry tasks
also need their different assumptions stated explicitly.

## Next decision after the AMG diagnostic: 2026-10-02

Implementation was subsequently approved. The
[separately versioned seven-arm method](../methods/TCAD-Cps-AMG-Feasibility.md)
and its [evidence record](../evidence/TCAD-Cps-AMG-Feasibility.md) now own that
bounded execution. Later stages remain conditional. The dated recommendation
below records the decision before implementation; it is not authorization for
automatic panel expansion or training.

The owner requested the next research direction, not a new job submission.
The [AMG evidence](../evidence/TCAD-Cps-AMG-Diagnostic.md) establishes successful
toy and local0 same-matrix backend checks within the existing caps. It does
not establish compact-support accuracy or finer-level feasibility. The
recommended immediate work package remains reference qualification.

1. Collect the completed diagnostic's terminal artifacts without overwrite.
   Freeze a separately versioned single-sentinel protocol using the tested
   AMG candidate. Keep physical geometry, compact/wide mesh policies, tolerances
   and all per-worker caps unchanged; do not edit either rejected protocol.
   Run a new source-bound smoke before seven fresh arms on layout 597:
   local0, local1, local2, repeat2, pad20, far2 and support1. Do not substitute
   the earlier local0 result for an arm in this new study. The new implementation
   needs its own source lock, tests, verified publication and SLURM runbook.
2. Require complete successful coverage, residual/resource checks and the
   existing single-layout sensitivity gates: at most 5% separately for adjacent
   fine-mesh, padding, far-mesh and intermediate support comparisons; identical
   repeat mesh/system hashes and relative repeat difference at most 1e-4.
   Retain the original comparison denominators. A single layout cannot satisfy
   a three-layout median gate. Stop on a failed worker; retain numerical gate
   failures and do not widen caps or drop the failed geometry.
3. If the largest sentinel passes, consider a separately frozen three-sentinel
   study, then the twelve-layout development panel. Require fresh, comparable
   observations under the new policy, not the two completed old-policy tasks.
   Keep the original 2% median and 5% maximum mesh/domain criteria. The level-1
   support check is not a finest-level error bound; broader reference
   qualification must address this limitation and a matched independent
   extractor on a small subset. Finite-panel stability is not physical truth.
4. If a resource or sensitivity gate fails, separate mesh-generation cost,
   algebraic error and discretization sensitivity before proposing another
   version. Preserve the fixed-fidelity interpretation and do not start a new
   label corpus or training grid on a purported qualified reference.

## Contribution and evaluation priorities

The recommended paper hypothesis is cost-aware multi-fidelity graph learning
for PCB design screening: at matched measured solver cost, does learning
between explicitly named fidelities improve both prediction and design
selection? The AMG change is an implementation prerequisite, not the proposed
paper novelty. Start with low-only, high-only and residual multi-fidelity
controls, plus tuned pooled and graph baselines. Introduce adaptive query
selection only after a controlled fidelity-learning benefit is established;
compare it against random and geometry-diversity selection under the same
candidate pool and budget. Include failed queries in the cost accounting.

Freeze a new evaluation geometry set and family-grouped splits before producing
its labels. The inspected development panel is not a blind test. Keep reference
discrepancy separate from model uncertainty. For the CAD outcome, evaluate a
locked capacitance-screening task with inductance/coupling constraints and
reference-verified finalists, reporting selection regret, constraint violations
and end-to-end cost. A routed geometry/stackup transfer study remains separate
from the present active-leg abstraction.

The [official TCAD instructions](https://ieee-ceda.org/publications/tcad/tcad-paper-submissions),
rechecked on 2026-10-02, require original contributions and identify inadequate
related work or state-of-the-art comparison as desk-rejection grounds. The
literature comparison above must therefore be expanded before asserting
novelty; this roadmap is a proposed testable contribution, not an acceptance
prediction. No manuscript claim, execution protocol or new submission was
created by this planning review. All heavy work remains SLURM-only and paper
content remains an export of an identified, admitted wiki snapshot.

## Ordered work packages (conditional roadmap)

| Stage | Question | Deliverable and decision gate |
|---|---|---|
| 1. Reference qualification | What numerical accuracy is attainable within the resource budget? | A frozen, geometry-selected development panel; bounded refinement, padding and repeatability evidence; a named qualified reference or an explicit negative result |
| 2. Controlled fidelity learning | Does learning the discrepancy between fidelities help at a matched label budget? | Low-only, high-only and multi-fidelity comparisons with matched splits and train-only fitting; tuned pooled and graph controls |
| 3. Solver-query allocation | Does adaptive selection beat simpler selection at equal measured solver cost? | Random, geometry-diversity and proposed selectors on identical candidate pools; learning curves in solver time as well as label count |
| 4. Design evaluation | Does the surrogate select better feasible designs within a fixed budget? | A locked screening task with reference-verified finalists, selection regret, constraint violations and total cost; then a separate routed-geometry transfer study |

Only Stage 1 is the recommended immediate research track. Later stages are a
conditional roadmap. The prior coordinate-update result is closed and provides
no reason by itself to run a larger EGNN training grid.

## First study: capacitance reference qualification

Protocol identity: `tcad-cps-reference-qualification-v1`. The owner approved
Stage 1 implementation on 2026-10-02. The
[method specification](../methods/TCAD-Cps-Reference-Qualification.md) now owns
the exact machine protocol, panel and gates; the
[evidence record](../evidence/TCAD-Cps-Reference-Pilot.md) owns freeze and
submission status. The recommendations below explain the original design.

Use the existing one-thread FEM-v2 artifacts as development evidence. The
[negative mesh result](../results/FEM-R3-R4-Convergence.md) and
[reference method](../methods/FEM-Cps-Reference.md) remain unchanged. Historical
results may inform this study, so this panel must not later be described as a
new blind test of model accuracy.

Prepare a deterministic twelve-layout panel using geometry alone: three
conductor-count strata crossed with two gap strata and two overlap strata.
Freeze bin edges, representatives, stable-hash tie breaking, empty-cell rules
and geometry hashes before any new solve. Select three complexity sentinels
from the panel for an initial feasibility pilot. These counts are proposed
study design, not completed coverage.

The first implementation should examine local refinement around conductor
edges and narrow gaps, with an independently specified outer-domain mesh.
This is a candidate discretization policy, not an existing validated adaptive
error estimator. Uniform R5 must not be launched over the full corpus as a
default next step. Pilot cost and numerical behavior determine whether a
bounded local-refinement ladder is feasible.

The frozen protocol should specify:

1. Identical conductor volumes, dielectric assumptions, terminal potentials,
   capacitance definition and outer boundary treatment for every comparison.
2. A finite refinement ladder, a separate padding expansion at the finest
   feasible level, and fresh-mesh repeats on the three sentinels. Numerical
   thread counts must remain fixed. Resource exhaustion is retained as a
   feasibility outcome and cannot trigger an unrecorded wider retry.
3. The relative-difference denominator and panel aggregation. Proposed
   development gates are median at most 2% and maximum at most 5% for the final
   adjacent refinement comparison and for domain expansion separately,
   consistent with the previous target tolerances. A single passing pair is
   finite-panel stability evidence, not proof of continuum convergence.
4. Residual checks and diagnostics for algebraic error, mesh identity, element
   counts, charge/energy consistency where available, wall time and peak memory.
   These diagnostics address different error sources and must not be pooled.
5. A matched independent extractor on a small subset where material, boundary
   and terminal definitions can be aligned. Numerical disagreement must be
   investigated before assigning a reference label; agreement alone is not
   fabricated-board validation. The
   [independent capacitance contract](../methods/TCAD-Independent-Capacitance-Contract.md)
   records concrete legacy geometry and electrical-quantity mismatches that
   a new adapter must resolve before any comparison.
6. An explicit stop decision. If refinement or resource gates fail, retain the
   fixed-fidelity interpretation, investigate the discretization, and do not
   start a new corpus or predictive claim on an unqualified reference.

## Candidate model and evaluation after reference qualification

Start with a residual multi-fidelity capacitance predictor: a graph encoder
learns the lower-fidelity response and a separate correction predicts the
higher-fidelity discrepancy. Evaluate direct high-fidelity learning as a control
at every high-fidelity budget. Keep model uncertainty and numerical-reference
discrepancy as separate reported quantities; an ensemble spread is not itself
a bound on FEM error. A calibrated query rule is a candidate extension whose
benefit must be measured against random and geometry-diversity selection.

Compare the current GNN, a pooled MLP and tuned tree/boosting models with the
same target versions, train/validation splits, tuning-trial caps and test panel.
Add controlled removals of connectivity and fidelity correction. Record tuning
compute separately from labeling cost. The old fixed-baseline result remains
valid only within its original scope.

The existing benchmark and higher-fidelity panel have already been inspected.
Use them for development; freeze a new evaluation geometry set and group splits
before producing its labels. Exclude geometry duplicates, keep all related
family members together, and prevent test labels from entering acquisition,
calibration, normalization, tuning or checkpoint selection. Held-out evaluation
opens only after the accepted model and query rules are frozen.

For the first screening task, consider minimizing inter-winding capacitance
subject to specified inductance and coupling constraints within a fixed winding
family. Freeze the objective, constraints, candidate pool, query budget, tie
rules and regret denominator before evaluation. Score the chosen designs with
the qualified reference. Report top-candidate recall, constraint violations,
selection regret and total wall time, including solver queries and model/data
overhead. A complete routed example requires its own terminal, return-path,
via and solver-geometry contract. Measurements are a further validation track.

## Execution boundaries

All meshing, field solving, model fitting, tuning, substantial inference replay
and scientific finalization must run through submitted SLURM jobs. Login-node
work is limited to editing, small no-solver tests, validation, submission,
monitoring and artifact indexing. Follow the
[submission playbook](../operations/SLURM-Submission-Playbook.md).

The [resource record](../operations/SLURM-Resource-Plan.md) lists prior one-thread
R4 tasks with 160 GiB allocations and three-hour scheduler caps. Those are
historical limits, not a qualified budget for a finer mesh. Before submission,
recheck the account, partition and current limits; freeze the pilot's thread,
memory, timeout and retry settings. Begin at concurrency one. Do not transfer
the older 25-thread meshing setting into the deterministic FEM-v2 study.

Submission requires a reviewed protocol, input manifest, clean execution
commit, source and environment hashes, solver-entry allocation checks, and
paths that remain quoted with the space in `GNN parasitic`. Every attempt needs
a separate evidence directory. Finalization must account for failures before
admission; a dependency completing is not scientific acceptance.

## Manuscript outline for the eventual TCAD version

1. Design problem and a precise contribution relative to learned extraction.
2. Geometry, target definitions and qualified numerical references.
3. Fidelity-learning method and, if supported, solver-query selection.
4. Split, budget, baseline and calibration protocols.
5. Reference, prediction, ablation, cost and design-selection results.
6. Transfer limits, reproducibility, conclusion and author-confirmed disclosure.

The [working manuscript](../../Paper/Paper_TCAD/) currently adds only the
[Codex writing disclosure](AI-Disclosure.md). Proposed experiments and outcomes
are not inserted as scientific results. Stage 1 implementation was approved
on 2026-10-02. No later learning or paper-claim stage is automatically enabled.
