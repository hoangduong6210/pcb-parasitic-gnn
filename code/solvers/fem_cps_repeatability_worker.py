#!/usr/bin/env python3
"""Isolated R3P16 FEM worker with mandatory Gmsh-thread telemetry.

This worker preserves the bounded production FEM solve and resource checks but
adds one pre-solve observation of the Gmsh thread environment.  Keeping the
instrumentation here avoids changing the byte-frozen production worker used by
historical Corpus V4 artifacts.
"""
from __future__ import annotations

import faulthandler
import json
import os
import resource
import sys

from fem_capacitance_3d import fem_cps_3d_diagnostics
from fem_cps_bounded_worker import enforce_resource_limits
from fem_cps_diagnostic_worker import _json_default


TELEMETRY_SCHEMA = "pcb-gnn.gmsh-thread-observation.v1"


if __name__ == "__main__":
    faulthandler.enable(all_threads=True)
    layout = json.load(open(sys.argv[1]))
    refine = int(sys.argv[2])
    pad_mm = float(sys.argv[3])

    def progress(stage: str, payload: dict) -> None:
        max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(
            "STAGE="
            + json.dumps(
                {"stage": stage, "max_rss_kb": max_rss_kb, **payload},
                default=_json_default,
                sort_keys=True,
            ),
            flush=True,
        )
        enforce_resource_limits(payload, max_rss_kb)

    raw_gmsh_threads = os.environ.get("PCB_GNN_GMSH_THREADS")
    try:
        observed_gmsh_threads = int(raw_gmsh_threads or "")
    except ValueError as exc:
        raise RuntimeError(
            "repeatability Gmsh thread environment is missing or malformed"
        ) from exc
    if observed_gmsh_threads <= 0:
        raise RuntimeError("repeatability Gmsh thread count must be positive")
    progress(
        "repeatability_environment",
        {
            "gmsh_threads": observed_gmsh_threads,
            "telemetry_contract": TELEMETRY_SCHEMA,
        },
    )

    result = fem_cps_3d_diagnostics(
        layout,
        eps_r=4.2,
        refine=refine,
        pad_mm=pad_mm,
        linear_solver="amg_cg",
        solver_rtol=1e-10,
        solver_maxiter=500,
        progress=progress,
        strict=True,
    )
    if result is None or result["cps_pf"] <= 0:
        raise RuntimeError("repeatability FEM worker returned no positive capacitance")
    print(
        "RESULT=" + json.dumps(result, default=_json_default, sort_keys=True),
        flush=True,
    )
