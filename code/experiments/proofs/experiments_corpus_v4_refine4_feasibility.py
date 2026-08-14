#!/usr/bin/env python3
"""Bounded SLURM feasibility probe for refine-4/pad-16 FEM solves."""
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

from experiments_corpus_v4_convergence_preflight import parse_prefixed  # noqa: E402
from v3_dataset import load_final_corpus  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-refine4-feasibility.v1"
PRIOR_FINAL_SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-final.v2"
PRIOR_ARRAY_JOB_ID = "6833715"
PRIOR_FINAL_SHA256 = "d38b0f1f3b22d3dd2580a334f34e001aedae72707e1b298f1600d8cb68d4785b"
LAYOUTS = {
    149: {
        "task_id": 3,
        "geometry_sha256": "0e2aef8a6ec688d3b271569091cd9a3d8ad786a1bc5f54bb3456ec292eda96b4",
        "role": "largest measured refine-3/pad-16 memory footprint",
    },
    407: {
        "task_id": 1,
        "geometry_sha256": "5cc53be678ba4bb99fb0ea35a8cf5ef32c94bb5a44b4210a595f7ed46e0a3d4f",
        "role": "largest refine-2-to-refine-3 Cps delta",
    },
}
PRIOR_TASK_SHA256 = {
    149: "e82a1f0a7df7b4728cec9dbe7e3d06003779f32969db7fa87fcfdb64cdee0cfa",
    407: "bee1419fbab9899157e6c1468de41decf4f35129e5edd822668ca3ecf5e8cba9",
}
LIMITS = {
    "mesh_nodes_max": 10_000_000,
    "mesh_tetrahedra_max": 65_000_000,
    "worker_peak_rss_gib_max": 120.0,
    "operator_complexity_max": 1.25,
    "iterations_max": 100,
    "relative_residual_max": 1e-9,
    "wall_s_max": 7200.0,
}


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


def solve_bounded(
    layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int
) -> dict[str, Any]:
    worker = CODE / "solvers/fem_cps_bounded_worker.py"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        layout_path = Path(handle.name)
    command = [sys.executable, str(worker), str(layout_path), str(refine), str(pad_mm)]
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
        and result.get("linear_solver") == "pyamg_smoothed_aggregation_cg"
        and int(result.get("maxiter", -1)) == 500
        and float(result.get("rtol", float("inf"))) == 1e-10
    )
    return {
        "refine": int(refine),
        "pad_mm": float(pad_mm),
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


def validate_stage_a(
    path: Path,
    expected_sha256: str,
    current_source_hashes: dict[str, str],
    current_packages: dict[str, str],
    current_threads: dict[str, str | None],
    current_python: str,
    current_head: str,
) -> dict[str, Any]:
    if file_sha256(path) != expected_sha256:
        raise ValueError("layout-149 stage-A artifact hash mismatch")
    stage_a = json.loads(path.read_text())
    setting = stage_a.get("refine4_pad16", {})
    recomputed_gate = evaluate_gates(setting)
    provenance = stage_a.get("provenance", {})
    if (
        stage_a.get("schema") != SCHEMA
        or int(stage_a.get("selection", {}).get("layout_id", -1)) != 149
        or stage_a.get("selection", {}).get("geometry_sha256")
        != LAYOUTS[149]["geometry_sha256"]
        or not stage_a.get("feasibility_pass")
        or stage_a.get("resource_gate") != recomputed_gate
        or not recomputed_gate["pass"]
        or stage_a.get("scientific_acceptance_evaluated") is not False
        or stage_a.get("contraction_is_non_gating") is not True
        or not provenance.get("source_stable")
        or provenance.get("git_dirty_paths")
        or provenance.get("final_git_dirty_paths")
        or provenance.get("final_untracked_code")
        or provenance.get("git_head") != current_head
        or provenance.get("final_git_head") != current_head
    ):
        raise ValueError("layout-149 stage-A feasibility artifact did not pass")
    if (
        provenance.get("file_sha256") != current_source_hashes
        or provenance.get("final_file_sha256") != current_source_hashes
        or provenance.get("executed_batch_script", {}).get("sha256")
        != current_source_hashes["code/jobs/submit_corpus_v4_refine4_feasibility.sh"]
        or provenance.get("prior_final", {}).get("sha256") != PRIOR_FINAL_SHA256
        or provenance.get("prior_task", {}).get("sha256") != PRIOR_TASK_SHA256[149]
        or provenance.get("python") != current_python
        or provenance.get("package_versions") != current_packages
        or provenance.get("thread_environment") != current_threads
    ):
        raise ValueError("layout-149 stage-A source differs from stage B")
    return {"path": str(path), "sha256": expected_sha256}


def validate_computational_context(
    prior_task: dict[str, Any],
    current_source_hashes: dict[str, str],
    current_packages: dict[str, str],
    current_threads: dict[str, str | None],
    current_python: str,
) -> None:
    comparable_source_names = (
        "requirements-proof.txt",
        "code/experiments/proofs/experiments_corpus_v4_convergence_preflight.py",
        "code/data/v3_dataset.py",
        "code/core/geometry_contract.py",
        "code/solvers/fem_capacitance_3d.py",
        "code/solvers/fem_cps_diagnostic_worker.py",
    )
    prior_source_hashes = prior_task["provenance"]["file_sha256"]
    for name in comparable_source_names:
        if current_source_hashes.get(name) != prior_source_hashes.get(name):
            raise ValueError(f"refine-4 computational source differs for {name}")
    if (
        current_python != prior_task["provenance"]["python"]
        or current_packages != prior_task["provenance"]["package_versions"]
        or current_threads != prior_task["provenance"]["thread_environment"]
    ):
        raise ValueError("refine-4 runtime environment differs from refine-3 evidence")


def validate_prior_evidence(
    final_path: Path, layout_id: int
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    if file_sha256(final_path) != PRIOR_FINAL_SHA256:
        raise ValueError("prior convergence final artifact hash mismatch")
    final = json.loads(final_path.read_text())
    if (
        final.get("schema") != PRIOR_FINAL_SCHEMA
        or final.get("gate_pass") is not False
        or str(final.get("provenance", {}).get("source_array_job_id"))
        != PRIOR_ARRAY_JOB_ID
    ):
        raise ValueError("prior convergence rejection artifact is not canonical")
    task_id = int(LAYOUTS[layout_id]["task_id"])
    task_name = f"task_{task_id:02d}.json"
    task_path = (
        ROOT
        / "results/corpus_v4/convergence_preflight/jobs"
        / f"job_{PRIOR_ARRAY_JOB_ID}"
        / task_name
    )
    expected_task_sha = final["provenance"]["task_artifacts_sha256"][task_name]
    if expected_task_sha != PRIOR_TASK_SHA256[layout_id]:
        raise ValueError("prior convergence task hash is not the pinned artifact")
    if file_sha256(task_path) != expected_task_sha:
        raise ValueError("prior convergence task artifact hash mismatch")
    task = json.loads(task_path.read_text())
    if (
        int(task["selection"]["layout_id"]) != layout_id
        or task["selection"]["geometry_sha256"]
        != LAYOUTS[layout_id]["geometry_sha256"]
        or not task.get("task_pass")
    ):
        raise ValueError("prior convergence task selection/provenance mismatch")
    return final, task, task_path


def evaluate_gates(setting: dict[str, Any]) -> dict[str, Any]:
    rss_values = [
        float(stage["max_rss_kb"])
        for stage in setting.get("stages", [])
        if stage.get("max_rss_kb") is not None
    ]
    peak_rss_gib = max(rss_values, default=float("inf")) / 1048576.0
    observed = {
        "mesh_nodes": int(setting.get("mesh_nodes", -1)),
        "mesh_tetrahedra": int(setting.get("mesh_tetrahedra", -1)),
        "worker_peak_rss_gib": peak_rss_gib,
        "operator_complexity": float(setting.get("operator_complexity", float("inf"))),
        "iterations": int(setting.get("iterations", -1)),
        "relative_residual": float(setting.get("relative_residual", float("inf"))),
        "wall_s": float(setting.get("wall_ms", float("inf"))) / 1000.0,
    }
    checks = {
        "solver_success": bool(setting.get("success")),
        "mesh_nodes": 0 < observed["mesh_nodes"] <= LIMITS["mesh_nodes_max"],
        "mesh_tetrahedra": (
            0 < observed["mesh_tetrahedra"] <= LIMITS["mesh_tetrahedra_max"]
        ),
        "worker_peak_rss": (
            np.isfinite(observed["worker_peak_rss_gib"])
            and observed["worker_peak_rss_gib"] <= LIMITS["worker_peak_rss_gib_max"]
        ),
        "operator_complexity": (
            np.isfinite(observed["operator_complexity"])
            and 0.0 < observed["operator_complexity"]
            <= LIMITS["operator_complexity_max"]
        ),
        "iterations": 0 < observed["iterations"] <= LIMITS["iterations_max"],
        "relative_residual": (
            np.isfinite(observed["relative_residual"])
            and 0.0 <= observed["relative_residual"]
            <= LIMITS["relative_residual_max"]
        ),
        "wall": np.isfinite(observed["wall_s"])
        and observed["wall_s"] <= LIMITS["wall_s_max"],
    }
    return {"limits": LIMITS, "observed": observed, "checks": checks, "pass": all(checks.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--prior-convergence-final", type=Path)
    parser.add_argument("--layout-id", type=int, choices=sorted(LAYOUTS))
    parser.add_argument("--prior-refine4-149", type=Path)
    parser.add_argument("--prior-refine4-149-sha256")
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "status": "validation-ok",
                    "layouts": LAYOUTS,
                    "setting": {"refine": 4, "pad_mm": 16.0, "solver": "amg_cg"},
                    "limits": LIMITS,
                }
            )
        )
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit refine-4 feasibility through SLURM")
    if args.corpus is None or args.prior_convergence_final is None or args.layout_id is None:
        raise SystemExit("--corpus, --prior-convergence-final and --layout-id are required")
    if args.layout_id == 407 and args.prior_refine4_149 is None:
        raise SystemExit("layout 407 requires a passing layout-149 stage-A artifact")
    if args.layout_id == 407 and not args.prior_refine4_149_sha256:
        raise SystemExit("layout 407 requires the pinned layout-149 artifact SHA256")
    if args.layout_id == 149 and args.prior_refine4_149 is not None:
        raise SystemExit("layout 149 is stage A and cannot consume a stage-A artifact")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing refine-4 feasibility from a dirty worktree")
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if untracked_code:
        raise SystemExit("Refusing refine-4 feasibility with untracked code")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    batch_script = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not batch_script.is_file():
        raise SystemExit("exact executed SLURM batch script is unavailable")
    final, prior_task, prior_task_path = validate_prior_evidence(
        args.prior_convergence_final, args.layout_id
    )
    samples, corpus_summary = load_final_corpus(args.corpus)
    if (
        corpus_summary["artifacts_sha256"]
        != prior_task["provenance"]["corpus_artifacts_sha256"]
    ):
        raise ValueError("source corpus differs from the pinned convergence evidence")
    sample = next(
        sample for sample in samples if int(sample["layout_id"]) == args.layout_id
    )
    if sample["geometry_sha256"] != LAYOUTS[args.layout_id]["geometry_sha256"]:
        raise ValueError("corpus geometry does not match the frozen feasibility protocol")
    worker = CODE / "solvers/fem_cps_bounded_worker.py"
    sources = [
        Path(__file__),
        ROOT / "requirements-proof.txt",
        CODE / "experiments/proofs/experiments_corpus_v4_convergence_preflight.py",
        CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py",
        CODE / "solvers/fem_capacitance_3d.py",
        CODE / "solvers/fem_cps_diagnostic_worker.py",
        worker,
        CODE / "jobs/submit_corpus_v4_refine4_feasibility.sh",
    ]
    source_hashes = {
        source.relative_to(ROOT).as_posix(): file_sha256(source) for source in sources
    }
    tracked_batch_sha = source_hashes[
        "code/jobs/submit_corpus_v4_refine4_feasibility.sh"
    ]
    if file_sha256(batch_script) != tracked_batch_sha:
        raise SystemExit("executed feasibility batch differs from tracked protocol")
    current_packages = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "scikit-fem", "gmsh", "meshio", "pyamg")
    }
    current_threads = {
        name: os.environ.get(name)
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "PCB_GNN_GMSH_THREADS",
        )
    }
    validate_computational_context(
        prior_task,
        source_hashes,
        current_packages,
        current_threads,
        platform.python_version(),
    )
    stage_a_evidence = None
    if args.layout_id == 407:
        stage_a_evidence = validate_stage_a(
            args.prior_refine4_149,
            args.prior_refine4_149_sha256,
            source_hashes,
            current_packages,
            current_threads,
            platform.python_version(),
            head,
        )
    prior_r3 = next(
        row
        for row in prior_task["settings"]
        if int(row["refine"]) == 3 and float(row["pad_mm"]) == 16.0
    )
    prior_delta23 = next(
        row["relative_difference_pct"]
        for row in final["comparisons"]["mesh_refine2_vs_refine3_at_16mm"]["per_layout"]
        if int(row["layout_id"]) == args.layout_id
    )
    setting = solve_bounded(sample["layout"], 4, 16.0, args.timeout_s)
    gates = evaluate_gates(setting)
    final_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
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
        and final_source_hashes == source_hashes
        and file_sha256(batch_script) == tracked_batch_sha
    )
    delta34 = None
    contraction = None
    if setting.get("success") and float(setting.get("cps_pf", 0.0)) > 0.0:
        delta34 = abs(float(prior_r3["cps_pf"]) - float(setting["cps_pf"])) / abs(
            float(setting["cps_pf"])
        ) * 100.0
        contraction = delta34 < float(prior_delta23)
    payload = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "hostname": socket.gethostname(),
            "git_head": head,
            "git_dirty_paths": dirty,
            "file_sha256": source_hashes,
            "final_file_sha256": final_source_hashes,
            "final_git_head": final_head,
            "final_git_dirty_paths": final_dirty,
            "final_untracked_code": final_untracked_code,
            "source_stable": source_stable,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "python": platform.python_version(),
            "package_versions": current_packages,
            "thread_environment": current_threads,
            "executed_batch_script": {
                "path": str(batch_script),
                "sha256": file_sha256(batch_script),
            },
            "prior_final": {
                "path": str(args.prior_convergence_final),
                "sha256": file_sha256(args.prior_convergence_final),
            },
            "prior_task": {
                "path": str(prior_task_path),
                "sha256": file_sha256(prior_task_path),
            },
            "stage_a_layout_149": stage_a_evidence,
        },
        "selection": {
            "layout_id": args.layout_id,
            "geometry_sha256": sample["geometry_sha256"],
            "role": LAYOUTS[args.layout_id]["role"],
        },
        "prior_refine3_pad16": {
            "cps_pf": prior_r3["cps_pf"],
            "mesh_nodes": prior_r3["mesh_nodes"],
            "mesh_tetrahedra": prior_r3["mesh_tetrahedra"],
        },
        "refine4_pad16": setting,
        "cps_delta_refine3_vs_refine4_pct": delta34,
        "prior_delta_refine2_vs_refine3_pct": prior_delta23,
        "delta_contracted": contraction,
        "scientific_acceptance_evaluated": False,
        "contraction_is_non_gating": True,
        "interpretation": "resource feasibility only; production acceptance requires the frozen nine-layout refine-3/refine-4 protocol",
        "resource_gate": gates,
        "feasibility_pass": bool(gates["pass"] and source_stable),
    }
    output = ROOT / "results/corpus_v4/refine4_feasibility/jobs" / (
        f"job_{os.environ['SLURM_JOB_ID']}"
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"layout_{args.layout_id:04d}.json"
    atomic_write(path, payload)
    print(path.relative_to(ROOT), flush=True)
    if not payload["feasibility_pass"]:
        raise RuntimeError("refine-4 feasibility resource gate failed")


if __name__ == "__main__":
    main()
