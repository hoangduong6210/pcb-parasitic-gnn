---
title: TCAD Research Continuation Plan
status: RUNNING; Stage 1 implementation approved; later stages conditional
last_updated: 2026-10-03
paper_source: false
---

# TCAD Research Continuation Plan

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
   fabricated-board validation.
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
