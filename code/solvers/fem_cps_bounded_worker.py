#!/usr/bin/env python3
"""Fail-fast FEM worker for the bounded refine-4 feasibility probe."""
from __future__ import annotations

import faulthandler
import json
import os
import resource
import sys

from fem_capacitance_3d import fem_cps_3d_diagnostics
from fem_cps_diagnostic_worker import _json_default


def optional_limit(name: str) -> float | None:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else None


def enforce_resource_limits(payload: dict, max_rss_kb: int) -> None:
    """Abort at the earliest observable stage when a configured limit is crossed."""
    checks = (
        ("n_nodes", "PCB_GNN_MAX_MESH_NODES", float(payload.get("n_nodes", 0))),
        (
            "n_tetrahedra",
            "PCB_GNN_MAX_MESH_TETRAHEDRA",
            float(payload.get("n_tetrahedra", 0)),
        ),
        (
            "operator_complexity",
            "PCB_GNN_MAX_OPERATOR_COMPLEXITY",
            float(payload.get("operator_complexity", 0)),
        ),
        ("max_rss_kb", "PCB_GNN_MAX_RSS_KB", float(max_rss_kb)),
    )
    for metric, environment_name, observed in checks:
        limit = optional_limit(environment_name)
        if limit is not None and observed > limit:
            raise RuntimeError(
                f"configured resource limit exceeded: {metric}={observed:g} > {limit:g}"
            )


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
        raise RuntimeError("bounded FEM worker returned no positive capacitance")
    print(
        "RESULT=" + json.dumps(result, default=_json_default, sort_keys=True),
        flush=True,
    )
