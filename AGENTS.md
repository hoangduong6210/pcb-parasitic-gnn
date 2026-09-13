# Project execution rules

## Mandatory wiki synchronization

Every project task must update the canonical wiki before handoff. This includes
code changes, experiments, monitoring, reviews, commits, pushes, failures and
recoveries. Read `wiki/CONTRIBUTING.md` and `wiki/status/Live-Execution.md` before
acting. Record a dated observation even when a status check finds no change.

Update the semantic owner, link new pages from `wiki/INDEX.md`, and keep
`wiki/status/Live-Execution.md` accurate about completed work, blockers and the
next action. Distinguish local commits from publication verified on GitHub.
Never report a push as complete before checking the remote branch hash.

Wiki updates are part of the deliverable, not deferred cleanup. Run the wiki
contract tests and deterministic research-prose audit before committing.
Never place credentials or internal AI-detector reports in the wiki or repo.
The prose audit checks style and disclosure boundaries, not authorship.

## Scientific and operational boundaries

- Submit heavy computation through SLURM; never solve or train on login nodes.
- Preserve immutable execution commits, locks, accepted and rejected evidence.
- Keep claims scoped to their dataset, solver fidelity and timing boundary.
- The wiki is the scientific source; export papers only when a snapshot is requested.
- Keep work and generated files inside the user-authorized project workspace.
