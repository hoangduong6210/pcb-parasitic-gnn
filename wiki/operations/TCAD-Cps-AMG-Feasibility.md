---
title: TCAD AMG Feasibility Runbook
status: VALIDATED; source frozen; publication pending
last_updated: 2026-10-03
paper_source: false
---

# TCAD AMG Feasibility Runbook

Follow the [method](../methods/TCAD-Cps-AMG-Feasibility.md); record every outcome
in [evidence](../evidence/TCAD-Cps-AMG-Feasibility.md). All meshing, solving,
smoke and numerical finalization must run on verified SLURM compute nodes.

1. Collect the completed diagnostic with
   `code/experiments/proofs/archive_tcad_cps_amg_diagnostic_v1.py`. Its `--check`
   mode verifies metadata and raw-log reconstruction only, without solving.
2. Validate the additive code and wiki, then freeze the new source closure with
   `code/experiments/proofs/tcad_cps_amg_feasibility.py --freeze-lock`.
   The lock must include all inherited source and archived evidence; never
   overwrite a prior lock. Commit and verify publication before execution.
3. Create a clean detached worktree at the exact published source commit.
   Export `PCB_TCAD_EXECUTION_ROOT`, `PCB_TCAD_SOURCE_COMMIT` and
   `PCB_TCAD_LOCK_SHA256`. Quote paths, unset authentication tokens and submit
   from this worktree with its `logs/` directory present.

| Phase | Wrapper under code/jobs/ | Request |
|---|---|---|
| Smoke | submit_tcad_cps_amg_smoke.sh | 1 CPU, 8 GiB, 15 min |
| Feasibility | submit_tcad_cps_amg_feasibility.sh | 1 CPU, 160 GiB, 3 h |
| Finalizer | submit_tcad_cps_amg_finalize.sh | 1 CPU, 8 GiB, 15 min |

Use account `pgs0407`, partition `nextgen`, one node/task, no requeue and one
scientific thread. Site policy may allocate more CPUs for memory. Smoke worker
caps remain 600 seconds, 6 GiB RSS, 300,000 nodes and 1,500,000 tetrahedra.
Each feasibility worker remains capped at 1,200 seconds, 120 GiB RSS,
3,000,000 nodes and 20,000,000 tetrahedra. AMG operator complexity remains
capped at 1.25. Seven sequential workers allow at most 8,400 worker seconds
inside the three-hour envelope. These are ceilings, not runtime predictions.

Submit feasibility only after the new smoke passes raw-log/source/geometry
checks and terminal `COMPLETED/0:0`, zero restarts. Export its ID through
`PCB_TCAD_SMOKE_JOB_ID`. Submit the finalizer with
`--dependency=afterany:FEASIBILITY_JOB_ID` and export
`PCB_TCAD_FEASIBILITY_JOB_ID`; both phases recheck the admitted smoke.

Parent and workers verify the actual compute host, active allocation, runtime,
source and executed batch wrapper before numerical imports. Attempts use
exclusive directories under `results/tcad/cps_amg_feasibility_v1/`; symlinks
and overwrites are rejected. Timeout/RSS overflow terminates the worker process
group. Finalization verifies identities, exact coverage, raw-log hashes and
terminal accounting before scalar sensitivity assessment on compute.
Retain every failure. No further job is submitted automatically.
