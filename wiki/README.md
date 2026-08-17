---
title: PCB Parasitic GNN Research Wiki
status: canonical home
last_updated: 2026-08-17
paper_source: false
---

# PCB Parasitic GNN Research Wiki

This wiki is the project's scientific source of truth. Methods, result
interpretation, claim status, limitations, decisions, and publication-ready
language are developed here. A paper is a dated snapshot exported from admitted
wiki content. It is not an independent source that silently acquires newer
claims.

Raw solver records remain under `results/`. Executable protocols remain under
`code/` and `protocols/`. The wiki explains what those artifacts establish,
where they apply, and whether a statement is eligible for publication.

## Choose an entry route

| Reader | Begin here | Then read |
|---|---|---|
| New contributor | [Start Here](START-HERE.md) | [Research System Map](architecture/Research-System-Map.md) and [Research Workflow](operations/Research-Workflow.md) |
| Research reader | [Claim Registry](claims/Current-Claim-Language.md) | [Dataset Registry](datasets/Dataset-Registry.md), methods, results, and [Limitations](LIMITATIONS.md) |
| HPC operator | [SLURM Submission Playbook](operations/SLURM-Submission-Playbook.md) | [Resource Plan](operations/SLURM-Resource-Plan.md) and [Live Execution](status/Live-Execution.md) |
| Paper editor | [Paper Export Contract](manuscript/Paper-Export-Contract.md) | [Paper Outline](manuscript/Paper-Outline.md), admitted claims, and [Prose Audit](operations/Prose-Audit.md) |

## Canonical index

The [Exhaustive Index](INDEX.md) lists every wiki page and the registries for
claim, evidence, dataset, decision, and publication identifiers. A page not
reachable from that index is not part of the maintained research record.

## Authority rules

1. `paper_source: true` marks scientific prose that may be considered for a
   future paper after its linked claims are admitted.
2. `paper_source: false` marks operational, historical, or editorial material.
   It may contain scheduler identifiers, hashes, paths, and rejected attempts.
3. A completed computation does not become a claim automatically. The claim
   registry records the permitted wording, scope, evidence, and publication
   eligibility.
4. A paper snapshot pins a wiki commit, claim set, figures, bibliography, and
   file hashes. Later wiki changes do not alter an archived snapshot.
5. Detailed AI-detector reports and internal editorial notes are not committed
   to paper packages. The public gate is the reproducible prose and provenance
   audit described in the wiki.

## Admission path

```text
research question
    -> frozen protocol and immutable inputs
    -> job-backed artifacts and numerical gates
    -> evidence record with hash closure
    -> scoped claim reviewed in the registry
    -> manuscript-source page
    -> versioned paper snapshot
```

Machine-generated summaries may refresh counts, timings, and numerical fields.
They cannot change a claim from pending or rejected to admitted.
