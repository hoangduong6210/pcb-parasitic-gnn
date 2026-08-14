#!/usr/bin/env python3
"""SLURM-only direct-versus-AMG diagnostic for the corpus-v4 FEM failure."""
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


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from runtime_paths import fem_cps_diagnostic_worker_path  # noqa: E402
from v3_dataset import load_final_corpus  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-fem-native-diagnostic-task.v2"
PROTOCOL_REVISION = 2
RETRY_OF_ARRAY_JOB_ID = "6832495"
EXPECTED_GEOMETRY_SHA256 = "b1d837fc6357a278ef823510dd7c5e162fa5b686c8e4827ec383d2d14fe2c590"
EXPECTED_CORPUS_SHA256 = {
    "layouts.jsonl": "17ed51025830e5be125412e922269179fce55c4662786fb34ed82db13c39511b",
    "labels.jsonl": "48fa10572883fd2f36baa3b02189cb778fc1bbd65986c9fcc3b7024a4fd50327",
}
ARMS = {
    0: (
        {
            "name": "direct_vs_amg_refine2",
            "refine": 2,
            "pad_mm": 12.0,
            "solver": "direct",
            "comparison_solver": "amg_cg",
        },
    ),
    1: (
        {"name": "amg_refine3", "refine": 3, "pad_mm": 12.0, "solver": "amg_cg"},
    ),
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def selected_layout(samples: list[dict[str, Any]]) -> dict[str, Any]:
    for sample in samples:
        if int(sample["layout_id"]) == 1055:
            return sample
    raise ValueError("canonical diagnostic layout 1055 is absent")


def parse_prefixed(
    lines: list[str], prefix: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse worker telemetry without hiding a native failure behind invalid JSON."""
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


def run_arm(
    layout: dict[str, Any], arm: dict[str, Any], timeout_s: int
) -> dict[str, Any]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        layout_path = Path(handle.name)
    command = [
        sys.executable,
        str(worker),
        str(layout_path),
        str(arm["refine"]),
        str(arm["pad_mm"]),
        str(arm["solver"]),
    ]
    if arm.get("comparison_solver"):
        command.append(str(arm["comparison_solver"]))
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
        timed_out = False
    except subprocess.TimeoutExpired as error:
        completed = None
        timed_out = True
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
    finally:
        layout_path.unlink(missing_ok=True)
    wall_ms = (time.perf_counter() - started) * 1000.0
    if completed is not None:
        stdout, stderr = completed.stdout, completed.stderr
        returncode = completed.returncode
    else:
        returncode = None
    stdout_lines = stdout.splitlines()
    stages, stage_parse_errors = parse_prefixed(stdout_lines, "STAGE=")
    results, result_parse_errors = parse_prefixed(stdout_lines, "RESULT=")
    signal_name = None
    if returncode is not None and returncode < 0:
        try:
            signal_name = signal.Signals(-returncode).name
        except ValueError:
            signal_name = f"SIGNAL_{-returncode}"
    success = bool(
        not timed_out
        and returncode == 0
        and len(results) == 1
        and not stage_parse_errors
        and not result_parse_errors
    )
    return {
        **arm,
        "success": success,
        "timed_out": timed_out,
        "returncode": returncode,
        "signal": signal_name,
        "wall_ms": wall_ms,
        "last_stage": stages[-1]["stage"] if stages else None,
        "stages": stages,
        "telemetry_parse_errors": stage_parse_errors + result_parse_errors,
        "result": results[0] if len(results) == 1 else None,
        "stdout_tail": stdout_lines[-20:],
        "stderr_tail": stderr.splitlines()[-80:],
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--timeout-s", type=int, default=18000)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "validation-ok",
                    "protocol_revision": PROTOCOL_REVISION,
                    "arms": ARMS,
                }
            )
        )
        return
    if not os.environ.get("SLURM_ARRAY_JOB_ID") or not os.environ.get("SLURM_ARRAY_TASK_ID"):
        raise SystemExit("Submit the native FEM diagnostic as a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if task_id not in ARMS:
        raise SystemExit("canonical diagnostic tasks are 0 and 1")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing native FEM diagnostic from a dirty tracked worktree")
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if untracked_code:
        raise SystemExit("Refusing native FEM diagnostic with untracked files under code/")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    executed_batch_script = Path(
        os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", "")
    )
    if not executed_batch_script.is_file():
        raise SystemExit("exact executed SLURM batch script is unavailable")
    initial_batch_script_sha256 = file_sha256(executed_batch_script)
    samples, corpus_summary = load_final_corpus(args.corpus)
    if corpus_summary["artifacts_sha256"] != EXPECTED_CORPUS_SHA256:
        raise SystemExit("source corpus hashes do not match the diagnostic protocol")
    sample = selected_layout(samples)
    if sample["geometry_sha256"] != EXPECTED_GEOMETRY_SHA256:
        raise SystemExit("canonical layout 1055 geometry hash does not match the protocol")
    worker = fem_cps_diagnostic_worker_path()
    sources = [
        Path(__file__),
        ROOT / "requirements-proof.txt",
        CODE / "core/runtime_paths.py",
        CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py",
        CODE / "core/planar_to_graph.py",
        CODE / "solvers/fem_capacitance_3d.py",
        worker,
        CODE / "jobs/submit_corpus_v4_fem_native_diagnostic.sh",
        CODE / "jobs/slurm_job_env.sh",
        CODE / "experiments/proofs/finalize_corpus_v4_fem_native_diagnostic.py",
        CODE / "jobs/submit_corpus_v4_fem_native_diagnostic_finalizer.sh",
    ]
    initial_source_hashes = {
        source.relative_to(ROOT).as_posix(): file_sha256(source) for source in sources
    }
    output = ROOT / "results/corpus_v4/fem_native_diagnostic/jobs" / (
        f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:02d}.json"
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "protocol_revision": PROTOCOL_REVISION,
        "retry": {
            "array_job_id": RETRY_OF_ARRAY_JOB_ID,
            "reason": "telemetry JSON serialization rejected numpy.int32 before assembly",
        },
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
            "slurm_resources": {
                name: os.environ.get(name)
                for name in (
                    "SLURM_CPUS_PER_TASK",
                    "SLURM_MEM_PER_NODE",
                    "SLURM_TIMELIMIT",
                    "SLURM_JOB_PARTITION",
                )
            },
            "arm_timeout_s": args.timeout_s,
            "executed_batch_script": {
                "path": str(executed_batch_script),
                "sha256": initial_batch_script_sha256,
            },
            "git_head": head,
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": initial_source_hashes,
        },
        "selection": {
            "layout_id": sample["layout_id"],
            "geometry_sha256": sample["geometry_sha256"],
        },
        "task_id": task_id,
        "arms": [],
        "gates": {},
    }
    atomic_write(path, payload)
    for arm in ARMS[task_id]:
        record = run_arm(sample["layout"], arm, args.timeout_s)
        payload["arms"].append(record)
        atomic_write(path, payload)
        print(
            f"arm={arm['name']} success={record['success']} "
            f"last_stage={record['last_stage']} wall={record['wall_ms'] / 1000:.1f}s",
            flush=True,
        )
    final_source_hashes = {
        source.relative_to(ROOT).as_posix(): file_sha256(source) for source in sources
    }
    final_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    final_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    final_untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    final_batch_script_sha256 = file_sha256(executed_batch_script)
    source_stable = bool(
        final_source_hashes == initial_source_hashes
        and final_dirty == dirty
        and final_head == head
        and not final_untracked_code
        and final_batch_script_sha256 == initial_batch_script_sha256
    )
    payload["provenance"]["final_file_sha256"] = final_source_hashes
    payload["provenance"]["final_git_dirty_paths"] = final_dirty
    payload["provenance"]["final_git_head"] = final_head
    payload["provenance"]["final_untracked_code"] = final_untracked_code
    payload["provenance"]["final_executed_batch_script_sha256"] = (
        final_batch_script_sha256
    )
    payload["provenance"]["source_stable"] = source_stable
    if task_id == 0:
        record = payload["arms"][0]
        direct = record["result"]
        iterative = direct.get("comparison") if direct is not None else None
        relative_difference = None
        same_system = False
        if direct is not None and iterative is not None:
            relative_difference = abs(direct["cps_pf"] - iterative["cps_pf"]) / abs(direct["cps_pf"])
            same_system = direct["system_sha256"] == iterative["system_sha256"]
        all_arms_success = all(record["success"] for record in payload["arms"])
        payload["gates"] = {
            "all_arms_success": all_arms_success,
            "source_stable": source_stable,
            "identical_system": same_system,
            "cps_relative_difference": relative_difference,
            "cps_equivalence_tolerance": 1e-7,
            "pass": bool(
                all_arms_success
                and source_stable
                and same_system
                and relative_difference is not None
                and relative_difference <= 1e-7
            ),
        }
    else:
        record = payload["arms"][0]
        result = record["result"]
        payload["gates"] = {
            "all_arms_success": record["success"],
            "source_stable": source_stable,
            "relative_residual": result.get("relative_residual") if result else None,
            "residual_tolerance": 1e-9,
            "pass": bool(
                record["success"]
                and source_stable
                and result is not None
                and result["relative_residual"] <= 1e-9
            ),
        }
    atomic_write(path, payload)
    if not payload["gates"]["pass"]:
        raise RuntimeError("native FEM diagnostic gate failed; inspect the task artifact")


if __name__ == "__main__":
    main()
