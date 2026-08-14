#!/usr/bin/env python3
"""High-resolution AMG-CG FEM convergence preflight for corpus-v4 Cps labels."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from runtime_paths import fem_cps_diagnostic_worker_path  # noqa: E402
from v3_dataset import load_final_corpus  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-task.v2"
SETTINGS = ((2, 12.0), (2, 16.0), (3, 12.0), (3, 16.0))
LINEAR_SOLVER = "amg_cg"
SOLVER_RTOL = 1e-10
RESIDUAL_TOLERANCE = 1e-9
DIAGNOSTIC_SUMMARY_SCHEMA = "pcb-gnn.corpus-v4-fem-native-diagnostic-summary.v1"
EXPECTED_DIAGNOSTIC_ARRAY_JOB_ID = "6832704"
EXPECTED_DIAGNOSTIC_SUMMARY_SHA256 = (
    "f0b5510cf76325f5aefd8ad599f393cacacfc745d5413b351a5fe4c553513b89"
)
EXPECTED_CORPUS_SHA256 = {
    "layouts.jsonl": "17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b",
    "labels.jsonl": "48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327",
}


def selected_indices(samples: list[dict[str, Any]]) -> list[int]:
    """Cross trace-count terciles with low/median/high Cps order statistics."""
    order = np.argsort([len(sample["layout"]["traces"]) for sample in samples])
    selected: list[int] = []
    for group_indices in np.array_split(order, 3):
        group = sorted(
            (int(index) for index in group_indices),
            key=lambda index: float(samples[index]["y"][0]),
        )
        selected.extend((group[0], group[len(group) // 2], group[-1]))
    if len(selected) != 9 or len(set(selected)) != 9:
        raise ValueError("convergence selection is not nine unique layouts")
    return selected


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def setting_result_passes(result: dict[str, Any] | None) -> bool:
    """Fail closed unless an AMG-CG result satisfies every numerical contract."""
    if not isinstance(result, dict):
        return False
    residual = result.get("relative_residual")
    fingerprint = result.get("input_system_sha256")
    return bool(
        result.get("linear_solver") == "pyamg_smoothed_aggregation_cg"
        and isinstance(residual, (int, float))
        and np.isfinite(residual)
        and residual <= RESIDUAL_TOLERANCE
        and isinstance(fingerprint, str)
        and len(fingerprint) == 64
    )


def checkpoint_setting(
    path: Path, payload: dict[str, Any], setting: dict[str, Any]
) -> None:
    """Persist a setting atomically before propagating a failed gate."""
    payload["settings"].append(setting)
    atomic_write(path, payload)
    if not setting["success"]:
        raise RuntimeError("FEM convergence setting failed; inspect task artifact")


def validate_diagnostic_summary(path: Path, worker: Path) -> dict[str, Any]:
    """Bind production AMG runs to the successful backend proof artifact."""
    summary = json.loads(path.read_text())
    if summary.get("schema") != DIAGNOSTIC_SUMMARY_SCHEMA or not summary.get("pass"):
        raise ValueError("native FEM diagnostic summary did not pass")
    summary_sha256 = file_sha256(path)
    if summary_sha256 != EXPECTED_DIAGNOSTIC_SUMMARY_SHA256:
        raise ValueError("native FEM diagnostic summary hash is not the trusted artifact")
    if str(summary.get("array_job_id")) != EXPECTED_DIAGNOSTIC_ARRAY_JOB_ID:
        raise ValueError("native FEM diagnostic summary is from an untrusted array job")
    gates = summary.get("task_gates", {})
    cps_difference = float(
        gates.get("0", {}).get("cps_relative_difference", float("inf"))
    )
    refine3_residual = float(
        gates.get("1", {}).get("relative_residual", float("inf"))
    )
    if (
        not gates.get("0", {}).get("pass")
        or not gates["0"].get("identical_system")
        or not np.isfinite(cps_difference)
        or cps_difference < 0.0
        or cps_difference > 1e-7
        or not gates.get("1", {}).get("pass")
        or not np.isfinite(refine3_residual)
        or refine3_residual < 0.0
        or refine3_residual > 1e-9
    ):
        raise ValueError("native FEM diagnostic scientific gates are incomplete")
    proven_sources = summary.get("common_provenance", {}).get("file_sha256", {})
    required = {
        "requirements-proof.txt": ROOT / "requirements-proof.txt",
        "code/solvers/fem_capacitance_3d.py": CODE / "solvers/fem_capacitance_3d.py",
        "code/solvers/fem_cps_diagnostic_worker.py": worker,
    }
    for name, current_path in required.items():
        if proven_sources.get(name) != file_sha256(current_path):
            raise ValueError(f"native FEM diagnostic source mismatch for {name}")
    return {
        "path": str(path),
        "sha256": summary_sha256,
        "array_job_id": str(summary["array_job_id"]),
        "task_artifacts_sha256": summary["task_artifacts_sha256"],
    }


def parse_prefixed(
    lines: list[str], prefix: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.startswith(prefix):
            continue
        try:
            value = json.loads(line.removeprefix(prefix))
            if not isinstance(value, dict):
                raise TypeError("telemetry payload is not a JSON object")
            parsed.append(value)
        except (json.JSONDecodeError, TypeError) as error:
            errors.append(
                {"line_number": line_number, "raw_line": line, "error": str(error)}
            )
    return parsed, errors


def solve(
    layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int
) -> dict[str, Any]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        layout_path = Path(handle.name)
    command = [
        sys.executable,
        str(worker),
        str(layout_path),
        str(refine),
        str(pad_mm),
        LINEAR_SOLVER,
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=worker.parent,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env={**os.environ, "PYTHONFAULTHANDLER": "1"},
        )
        stdout, stderr = completed.stdout, completed.stderr
        returncode: int | None = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
        returncode = None
        timed_out = True
    finally:
        layout_path.unlink(missing_ok=True)
    wall_ms = (time.perf_counter() - started) * 1000.0
    stdout_lines = stdout.splitlines()
    stages, stage_errors = parse_prefixed(stdout_lines, "STAGE=")
    results, result_errors = parse_prefixed(stdout_lines, "RESULT=")
    signal_name = None
    if returncode is not None and returncode < 0:
        try:
            signal_name = signal.Signals(-returncode).name
        except ValueError:
            signal_name = f"SIGNAL_{-returncode}"
    result = results[0] if len(results) == 1 else None
    success = bool(
        not timed_out
        and returncode == 0
        and result is not None
        and not stage_errors
        and not result_errors
        and setting_result_passes(result)
    )
    return {
        "refine": int(refine),
        "pad_mm": float(pad_mm),
        "requested_linear_solver": LINEAR_SOLVER,
        "solver_rtol": SOLVER_RTOL,
        "residual_tolerance": RESIDUAL_TOLERANCE,
        "success": success,
        "timed_out": timed_out,
        "returncode": returncode,
        "signal": signal_name,
        "wall_ms": wall_ms,
        "last_stage": stages[-1].get("stage") if stages else None,
        "stages": stages,
        "telemetry_parse_errors": stage_errors + result_errors,
        "stdout_tail": stdout_lines[-20:],
        "stderr_tail": stderr.splitlines()[-80:],
        **(result or {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--timeout-s", type=int, default=18000)
    parser.add_argument("--diagnostic-summary", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "validation-ok",
                    "n_tasks": 9,
                    "settings": SETTINGS,
                    "linear_solver": LINEAR_SOLVER,
                    "solver_rtol": SOLVER_RTOL,
                    "residual_tolerance": RESIDUAL_TOLERANCE,
                }
            )
        )
        return
    if not os.environ.get("SLURM_ARRAY_JOB_ID") or not os.environ.get("SLURM_ARRAY_TASK_ID"):
        raise SystemExit("Submit corpus-v4 convergence preflight as a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    if args.diagnostic_summary is None:
        raise SystemExit("--diagnostic-summary is required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if task_id not in range(9):
        raise SystemExit("canonical convergence preflight has tasks 0..8")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing convergence preflight from a dirty tracked worktree")
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if untracked_code:
        raise SystemExit("Refusing convergence preflight with untracked code")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    executed_batch_script = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not executed_batch_script.is_file():
        raise SystemExit("exact executed SLURM batch script is unavailable")
    initial_batch_sha256 = file_sha256(executed_batch_script)
    samples, corpus_summary = load_final_corpus(args.corpus)
    if corpus_summary["artifacts_sha256"] != EXPECTED_CORPUS_SHA256:
        raise SystemExit("source corpus hashes do not match the convergence protocol")
    sample = samples[selected_indices(samples)[task_id]]
    worker = fem_cps_diagnostic_worker_path()
    sources = [
        Path(__file__),
        ROOT / "requirements-proof.txt",
        CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py",
        CODE / "core/planar_to_graph.py",
        CODE / "solvers/fem_capacitance_3d.py",
        worker,
        CODE / "jobs/submit_corpus_v4_convergence_preflight.sh",
        CODE / "experiments/proofs/finalize_corpus_v4_convergence_preflight.py",
        CODE / "jobs/submit_finalize_corpus_v4_convergence_preflight.sh",
    ]
    initial_source_hashes = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sources
    }
    tracked_batch_sha256 = initial_source_hashes[
        "code/jobs/submit_corpus_v4_convergence_preflight.sh"
    ]
    if initial_batch_sha256 != tracked_batch_sha256:
        raise SystemExit("executed SLURM script differs from the tracked protocol")
    diagnostic_evidence = validate_diagnostic_summary(args.diagnostic_summary, worker)
    output = ROOT / "results/corpus_v4/convergence_preflight/jobs" / (
        f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "package_versions": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "scipy", "scikit-fem", "gmsh", "meshio", "pyamg")
            },
            "thread_environment": {
                name: os.environ.get(name)
                for name in (
                    "OMP_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "PCB_GNN_GMSH_THREADS",
                )
            },
            "git_head": head,
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": initial_source_hashes,
            "executed_batch_script": {
                "path": str(executed_batch_script),
                "sha256": initial_batch_sha256,
            },
            "setting_timeout_s": args.timeout_s,
            "native_solver_diagnostic": diagnostic_evidence,
        },
        "selection": {
            "rule": "trace-count terciles crossed with low/median/high coarse-reference Cps",
            "selection_position": task_id,
            "layout_id": sample["layout_id"],
            "geometry_sha256": sample["geometry_sha256"],
            "n_traces": len(sample["layout"]["traces"]),
        },
        "settings": [],
        "task_pass": False,
    }
    atomic_write(path, payload)
    for refine, pad_mm in SETTINGS:
        setting = solve(sample["layout"], refine, pad_mm, args.timeout_s)
        print(
            f"layout={sample['layout_id']:04d} refine={refine} pad={pad_mm:g} "
            f"success={setting['success']} last_stage={setting['last_stage']} "
            f"wall={setting['wall_ms'] / 1000:.1f}s",
            flush=True,
        )
        checkpoint_setting(path, payload, setting)
    final_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    final_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    final_untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    final_source_hashes = {
        source.relative_to(ROOT).as_posix(): file_sha256(source) for source in sources
    }
    source_stable = bool(
        final_head == head
        and final_dirty == dirty
        and not final_untracked_code
        and final_source_hashes == initial_source_hashes
        and file_sha256(executed_batch_script) == initial_batch_sha256
        and initial_batch_sha256 == tracked_batch_sha256
    )
    payload["provenance"].update(
        {
            "final_git_head": final_head,
            "final_git_dirty_paths": final_dirty,
            "final_untracked_code": final_untracked_code,
            "final_file_sha256": final_source_hashes,
            "source_stable": source_stable,
        }
    )
    payload["task_pass"] = source_stable and all(
        setting["success"] for setting in payload["settings"]
    )
    atomic_write(path, payload)
    if not payload["task_pass"]:
        raise RuntimeError("convergence task source/provenance gate failed")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
