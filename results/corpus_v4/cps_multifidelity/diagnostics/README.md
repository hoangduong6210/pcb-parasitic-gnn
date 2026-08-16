# Cps multi-fidelity operational diagnostics

This directory contains internal, job-backed scheduler diagnostics. It is not
manuscript source and must not be copied into `Paper_Full/` or
`Paper_Summary/`.

## Singleton-array probe

`slurm_singleton_probe.sh` records the array environment and compares three
read-only scheduler queries: job ID, exact array component, and base array ID.
SLURM job `6852528` ran the script as `0-0%8` and completed with exit code
`0:0`. The selected results and hashes of the raw stdout/stderr capture are in
`singleton_probe_6852528.json`.

The probe establishes only an operational fact: on the evaluated scheduler, a
one-element array exposes one record for each query and retains
`ArrayTaskThrottle=8`. It does not execute FEM, validate a scientific result,
or authorize mixing artifacts from different execution locks.

For the active lock-v1 corpus, the result supports hash-pinned singleton retry
of missing canonical tasks with the unchanged lock-v1 runner. Lock v2 contains
the exact-component query fix for future complete executions.
