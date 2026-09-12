"""Timed one-thread FEM-v2 R3P16 wrapper for paired-latency evidence."""
from __future__ import annotations

import math
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from corpus_v4_fem_v2_production import validate_protocol as validate_fem_v2_protocol
from experiments_corpus_v4_fem_repeatability import (
    _arm_environment,
    gmsh_thread_gate,
    run_repeatability_worker,
)
from run_corpus_v4_cps_multifidelity_task import evaluate_result


FEM_V2_FIDELITY_ID = "cps_fem_r3_p16_t1_v2"


@contextmanager
def _bounded_worker_environment(limits: Mapping[str, Any]) -> Iterator[None]:
    """Install the same fail-fast bounds used by FEM-v2 production tasks."""
    updates = {
        "PCB_GNN_GMSH_THREADS": "1",
        "PCB_GNN_MAX_MESH_NODES": str(int(limits["mesh_nodes_max"])),
        "PCB_GNN_MAX_MESH_TETRAHEDRA": str(
            int(limits["mesh_tetrahedra_max"])
        ),
        "PCB_GNN_MAX_OPERATOR_COMPLEXITY": str(
            float(limits["operator_complexity_max"])
        ),
        "PCB_GNN_MAX_RSS_KB": str(
            int(float(limits["worker_peak_rss_gib_max"]) * 1_048_576)
        ),
    }
    previous = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_fem_v2_r3p16_timed(
    raw_layout: bytes,
    *,
    parse_layout: Any,
    fem_v2_protocol: Mapping[str, Any],
    timeout_s: int,
) -> dict[str, Any]:
    """Run the production-equivalent raw-record-to-Cps FEM-v2 boundary.

    The outer timer starts before strict raw-layout parsing and stops only after
    the float64 capacitance target and both numerical/resource gates have been
    materialized.  The heavy worker remains subprocess-isolated and must be
    called only from the latency SLURM task runner.
    """
    protocol = dict(fem_v2_protocol)
    validate_fem_v2_protocol(protocol)
    fidelity = protocol["fidelities"][FEM_V2_FIDELITY_ID]
    limits = protocol["resource_profiles"][FEM_V2_FIDELITY_ID]["fail_fast"]
    if (
        int(fidelity["refine"]) != 3
        or float(fidelity["pad_mm"]) != 16.0
        or protocol["linear_solver"].get("requested") != "amg_cg"
        or any(value != "1" for value in protocol["runtime"]["threads"].values())
    ):
        raise ValueError("supplied protocol is not FEM-v2 R3P16 one-thread")
    frozen_timeout = int(float(limits["wall_s_max"]))
    if type(timeout_s) is not int or timeout_s != frozen_timeout:
        raise ValueError("FEM timeout differs from the frozen FEM-v2 R3 gate")

    start_ns = time.perf_counter_ns()
    layout = parse_layout(raw_layout)
    with _bounded_worker_environment(limits), _arm_environment(1):
        execution = run_repeatability_worker(
            layout,
            int(fidelity["refine"]),
            float(fidelity["pad_mm"]),
            timeout_s,
        )
    numerical_gate = evaluate_result(execution, protocol, FEM_V2_FIDELITY_ID)
    thread_gate = gmsh_thread_gate(execution, 1)
    worker_result = execution.get("worker_result")
    if not isinstance(worker_result, dict):
        raise RuntimeError("FEM-v2 worker result is missing")
    cps_pf = numerical_gate.get("observed", {}).get("cps_pf")
    target = {
        "Cps_pF": float(cps_pf)
        if isinstance(cps_pf, (int, float)) and math.isfinite(float(cps_pf))
        else math.nan
    }
    stop_ns = time.perf_counter_ns()
    elapsed_ms = (stop_ns - start_ns) / 1e6

    if stop_ns <= start_ns or not math.isfinite(elapsed_ms) or elapsed_ms <= 0.0:
        raise RuntimeError("FEM-v2 timer did not complete monotonically")
    if numerical_gate.get("pass") is not True:
        failed = sorted(
            name
            for name, passed in numerical_gate.get("checks", {}).items()
            if passed is not True
        )
        raise RuntimeError(f"FEM-v2 R3P16 numerical/resource gate failed: {failed}")
    if thread_gate.get("pass") is not True:
        raise RuntimeError("FEM-v2 worker did not prove one-thread Gmsh execution")
    if not math.isfinite(target["Cps_pF"]):
        raise RuntimeError("FEM-v2 R3P16 did not produce finite Cps")
    mesh_identity = {
        "mesh_nodes": worker_result.get("mesh_nodes"),
        "mesh_tetrahedra": worker_result.get("mesh_tetrahedra"),
        "system_sha256": worker_result.get("system_sha256"),
    }
    if (
        type(mesh_identity["mesh_nodes"]) is not int
        or mesh_identity["mesh_nodes"] <= 0
        or type(mesh_identity["mesh_tetrahedra"]) is not int
        or mesh_identity["mesh_tetrahedra"] <= 0
        or not isinstance(mesh_identity["system_sha256"], str)
        or len(mesh_identity["system_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in mesh_identity["system_sha256"]
        )
    ):
        raise RuntimeError("FEM-v2 worker did not emit a valid mesh/system identity")
    return {
        "elapsed_ms": elapsed_ms,
        "execution": execution,
        "mesh_identity": mesh_identity,
        "numerical_gate": numerical_gate,
        "start_ns": start_ns,
        "stop_ns": stop_ns,
        "target": target,
        "thread_gate": thread_gate,
    }
