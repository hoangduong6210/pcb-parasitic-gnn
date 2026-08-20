"""Fail-closed FastHenry execution for the paired Corpus V4 latency study.

The public artifact records the executable digest, never its private path.  The
timer covers deck construction, temporary-workspace setup, solver execution,
matrix parsing, target reduction, and temporary-workspace cleanup.
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from fasthenry_ref import _parse_zc, layout_to_inp


def _tail(text: str, lines: int = 40) -> list[str]:
    return text.splitlines()[-lines:]


def _net_totals(
    matrix_nh: np.ndarray, ports: list[tuple[int, str, str, str]]
) -> dict[str, float]:
    primary = [index for index, port in enumerate(ports) if port[3] == "pri"]
    secondary = [index for index, port in enumerate(ports) if port[3] == "sec"]
    if not primary or not secondary:
        raise RuntimeError("FastHenry deck does not contain both winding nets")

    def self_and_mutual(indices: list[int]) -> float:
        total = 0.0
        for offset, left in enumerate(indices):
            total += float(matrix_nh[left, left])
            for right in indices[offset + 1 :]:
                total += 2.0 * float(matrix_nh[left, right])
        return total

    values = {
        "L_pri_nH": self_and_mutual(primary),
        "L_sec_nH": self_and_mutual(secondary),
        "L_mut_nH": float(
            sum(matrix_nh[left, right] for left in primary for right in secondary)
        ),
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise RuntimeError("FastHenry produced non-finite inductance totals")
    return values


def run_fasthenry_timed(
    raw_layout: bytes,
    *,
    parse_layout: Any,
    binary: Path,
    frequency_hz: float,
    timeout_s: int,
) -> dict[str, Any]:
    """Execute one complete FastHenry workflow from resident raw JSON bytes."""
    if binary.is_symlink() or not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError("verified FastHenry executable is unavailable")
    if not math.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise ValueError("FastHenry frequency must be positive and finite")
    if type(timeout_s) is not int or timeout_s <= 0:
        raise ValueError("FastHenry timeout must be a positive integer")

    start_ns = time.perf_counter_ns()
    completed: subprocess.CompletedProcess[str] | None = None
    targets: dict[str, float] | None = None
    try:
        layout = parse_layout(raw_layout)
        deck, ports = layout_to_inp(layout, (frequency_hz,), nhinc=1, nwinc=1)
        with tempfile.TemporaryDirectory(prefix="pcb-gnn-fh-") as directory:
            workspace = Path(directory)
            input_path = workspace / "in.inp"
            input_path.write_text(deck, encoding="utf-8")
            completed = subprocess.run(
                [str(binary), input_path.name],
                cwd=workspace,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout_s,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"FastHenry returned nonzero status {completed.returncode}"
                )
            matrix_path = workspace / "Zc.mat"
            if matrix_path.is_symlink() or not matrix_path.is_file():
                raise RuntimeError("FastHenry did not produce Zc.mat")
            blocks = _parse_zc(matrix_path)
            matches = [
                matrix for observed_hz, matrix in blocks
                if math.isclose(observed_hz, frequency_hz, rel_tol=1e-12, abs_tol=0.0)
            ]
            if len(matches) != 1:
                raise RuntimeError("FastHenry frequency block is missing or ambiguous")
            impedance = matches[0]
            expected_shape = (len(ports), len(ports))
            if impedance.shape != expected_shape or not np.isfinite(impedance).all():
                raise RuntimeError("FastHenry impedance matrix violates its contract")
            inductance_nh = impedance.imag / (2.0 * np.pi * frequency_hz) * 1e9
            targets = _net_totals(inductance_nh, ports)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("FastHenry execution timed out") from exc
    finally:
        stop_ns = time.perf_counter_ns()

    if targets is None or completed is None or stop_ns <= start_ns:
        raise RuntimeError("FastHenry timing did not complete monotonically")
    return {
        "elapsed_ms": (stop_ns - start_ns) / 1e6,
        "returncode": completed.returncode,
        "stderr_tail": _tail(completed.stderr),
        "stdout_tail": _tail(completed.stdout),
        "stop_ns": stop_ns,
        "start_ns": start_ns,
        "targets": targets,
    }

