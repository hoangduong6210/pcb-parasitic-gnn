"""Timed FEM-R3P16 wrapper using the admitted bounded-worker contract."""
from __future__ import annotations

import math
import time
from typing import Any, Mapping

from run_corpus_v4_cps_multifidelity_task import evaluate_result, run_worker


def run_fem_r3p16_timed(
    raw_layout: bytes,
    *,
    parse_layout: Any,
    cps_protocol: Mapping[str, Any],
    timeout_s: int,
) -> dict[str, Any]:
    """Run the complete resident raw-record-to-Cps reference workflow."""
    fidelity_id = "cps_fem_r3_p16"
    fidelity = cps_protocol["fidelities"][fidelity_id]
    if (
        int(fidelity.get("refine", -1)) != 3
        or float(fidelity.get("pad_mm", -1.0)) != 16.0
        or cps_protocol.get("linear_solver", {}).get("requested") != "amg_cg"
    ):
        raise ValueError("supplied Cps protocol is not the admitted FEM-R3P16 workflow")
    frozen_timeout = int(
        cps_protocol["resource_profiles"][fidelity_id]["fail_fast"]["wall_s_max"]
    )
    if type(timeout_s) is not int or timeout_s != frozen_timeout:
        raise ValueError("FEM timeout differs from the frozen R3 resource gate")

    start_ns = time.perf_counter_ns()
    layout = parse_layout(raw_layout)
    execution = run_worker(layout, 3, 16.0, timeout_s)
    gate = evaluate_result(execution, dict(cps_protocol), fidelity_id)
    stop_ns = time.perf_counter_ns()
    elapsed_ms = (stop_ns - start_ns) / 1e6
    if stop_ns <= start_ns or not math.isfinite(elapsed_ms) or elapsed_ms <= 0.0:
        raise RuntimeError("FEM timer did not complete monotonically")
    if gate.get("pass") is not True:
        failed = sorted(name for name, passed in gate.get("checks", {}).items() if not passed)
        raise RuntimeError(f"FEM-R3P16 numerical/resource gate failed: {failed}")
    cps_pf = gate.get("observed", {}).get("cps_pf")
    if not isinstance(cps_pf, (int, float)) or not math.isfinite(float(cps_pf)):
        raise RuntimeError("FEM-R3P16 did not produce finite Cps")
    return {
        "elapsed_ms": elapsed_ms,
        "execution": execution,
        "gate": gate,
        "start_ns": start_ns,
        "stop_ns": stop_ns,
        "target": {"Cps_pF": float(cps_pf)},
    }

