---
title: TCAD Submission Readiness
status: PROPOSED; editorial assessment
last_updated: 2026-10-02
paper_source: false
---

# TCAD Submission Readiness

## Assessment

IEEE Transactions on Computer-Aided Design of Integrated Circuits and Systems
is a plausible target for an extraction method that improves an electronic
design workflow. The current journal snapshot is a useful starting point, but
this review recommends additional scientific development before submission.
This is an editorial assessment, not a new admitted claim or a prediction of
acceptance. No solver or training run was started for this review.

The [official scope](https://ieee-ceda.org/publications/tcad) includes algorithms,
modeling, simulation and tools for circuit and system design. The paper should
therefore explain the methodological contribution and its effect on a design
decision. Open-source packaging and evidence traceability support that argument
but do not by themselves establish methodological novelty.

## Existing strengths

The [current journal package](../../Paper/Paper_Journal_Snapshot_1/) preserves
the geometry contract, family-held-out evaluation, admitted numerical results,
negative coordinate-update result, and a defined runtime boundary. Its frozen
manifest records eleven pages, nine figures and sixty references. The
[accuracy result](../results/Corpus-V4-FEM-v2-Accuracy.md),
[baseline result](../results/Corpus-V4-FEM-v2-Baselines.md), and
[paired latency result](../results/Corpus-V4-FEM-v2-Latency.md) provide the
version-scoped evidence for claims `C-ACC-FEMV2-001`, `C-BASE-FEMV2-001`, and
`C-LAT-FEMV2-001`. The released manuscript and evidence remain unchanged.

## Scientific priorities before submission

1. State a precise methodological contribution relative to existing learned
   parasitic extraction. The present manuscript describes an integrated
   evaluation workflow; a stronger TCAD case would identify what new algorithm,
   representation, or numerical treatment enables a better design outcome.
2. Strengthen comparisons. The existing pooled-feature baselines are post-hoc,
   use fixed settings, and do not isolate connectivity. Consider tuned tabular
   models, a pooled neural model, a controlled message-passing ablation, and
   relevant published extraction methods where their problem assumptions match.
   Freeze tuning and evaluation rules before new experiments.
3. Resolve or quantitatively bound reference error. The existing
   [mesh-sensitivity study](../results/FEM-R3-R4-Convergence.md) rejected the
   R3/R4 mesh gate, and the higher-resolution observation is not established
   ground truth. Use a converged or adaptively checked panel and, where feasible,
   an independent extraction method to distinguish model error from label error.
4. Demonstrate transfer and design utility. The active-leg abstraction excludes
   routed returns, vias, terminals and other full-board structures. A realistic
   routed example, held-out geometry or stackup transfer, and a screening or
   optimization task would strengthen practical relevance. Measurements would
   add physical validation; they are not stated here as a universal TCAD rule.
5. Retain the declared timing boundary and account for practical deployment.
   The existing ratio compares a specific sequential solver workflow with a
   warm-loaded model. Include model loading, data preparation, reference fidelity,
   and training cost when making a broader deployment claim.

The [limitations page](../LIMITATIONS.md) owns the existing scope boundaries.
These suggestions do not admit new results. The owner resumed TCAD planning
on 2026-10-02; the [continuation plan](TCAD-Research-Plan.md) recommends the
first new study and defines the gates before computational execution.

## Submission-format checks

The [official submission instructions](https://ieee-ceda.org/publications/tcad/tcad-paper-submissions),
consulted on 2026-10-02, specify IEEE two-column format, a minimum 10-point font,
a fourteen-page maximum for regular papers, a 100-to-250-word abstract, and four
to eight keywords. Space for author biographies must fit within that page limit.
The current eleven-page IEEE journal snapshot is within the page limit; its
frozen package verifier checks abstract length and document metadata.

The released snapshot has no generative-AI disclosure. The author supplied the
writing-assistance scope on 2026-10-02, and the
[TCAD working draft](../../Paper/Paper_TCAD/) now includes the
[Codex statement](AI-Disclosure.md) in Acknowledgment before References.
The released snapshot is unchanged. Authors must keep the submission disclosure
consistent with the actual assistance used during preparation.

If an earlier conference version was accepted or published, identify and cite
it, explain the substantive extension in the manuscript and cover letter, and
check the stated thirty-percent new-content requirement. The presence of an
archived submitted PDF alone does not establish acceptance or publication.
The cover letter must also disclose relevant prior peer review as instructed
by the journal. Author ORCIDs and actual publication history remain to be checked
when preparing the submission.

## Working location and next step

The checkout is named `GNN parasitic`; manuscript packages are under `Paper/`.
The editable submission source is
[`Paper/Paper_TCAD/main.tex`](../../Paper/Paper_TCAD/main.tex). It inherits the
released scientific content and adds the requested disclosure. New research
requires a frozen evaluation protocol and claim admission through the wiki.
Existing release tags and evidence identities remain the restart anchors.
