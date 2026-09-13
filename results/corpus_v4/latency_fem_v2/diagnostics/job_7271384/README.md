# Failed analysis attempt: diagnostic evidence only

Scheduler observation on 2026-09-13: job `7271384`, `FAILED`, exit `1:0`,
elapsed 18 s, zero restarts, node `a0104`.

The finalizer wrote its four analysis artifacts, then raised `ValueError` at
`print(output.relative_to(ROOT))`: the output path was relative while the root
was absolute. This was an analysis-script error, not a solver failure.

These files are byte-preserving copies from the original execution output
`results/corpus_v4/latency_fem_v2/final/job_7271384/`. The manifest deliberately
retains its original paths. This diagnostic directory is not an admitted
analysis package, and its summary must not be used as a scientific claim.

Original analysis-manifest SHA-256:
`e9214c58245988c043e511865832bf98fe4c64040f1969c74c91b33e073a3ddc`.
Original summary SHA-256:
`5e5d6c13eb0d5c1c9859c4f7ab6196f0a9ee420dad5f745a7f017050f8ec2759`.

Recovery must preserve the original task execution lock and the 306-task
round-00 accepted set. A separately pinned finalizer must complete with exit
`0:0`, followed by archive replay, before a result can be admitted.
