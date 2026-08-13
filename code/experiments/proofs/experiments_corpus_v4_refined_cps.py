#!/usr/bin/env python3
"""SLURM-array refinement of all v3 Cps labels at FEM refine=2, pad=12 mm."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
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


SCHEMA = "pcb-gnn.corpus-v4-refined-cps-task.v1"
FEM_REFINE = 2
DOMAIN_PAD_MM = 12.0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solve(layout: dict[str, Any], timeout_s: int) -> tuple[dict[str, Any], float]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        path = Path(handle.name)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(worker),
                str(path),
                str(FEM_REFINE),
                str(DOMAIN_PAD_MM),
            ],
            cwd=worker.parent, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("refined Cps solve timed out") from error
    finally:
        path.unlink(missing_ok=True)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    lines = [line for line in completed.stdout.splitlines() if line.startswith("RESULT=")]
    if completed.returncode != 0 or len(lines) != 1:
        raise RuntimeError(f"refined Cps solve failed with return code {completed.returncode}")
    return json.loads(lines[0].removeprefix("RESULT=")), elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--n-total", type=int, default=1500)
    parser.add_argument("--timeout-s", type=int, default=3600)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 150}))
        return
    required = ("SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Submit refined Cps generation as a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    expected_tasks = (args.n_total + args.chunk_size - 1) // args.chunk_size
    if task_id not in range(expected_tasks):
        raise SystemExit(f"canonical refined-Cps array has tasks 0..{expected_tasks - 1}")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing refined-Cps generation from a dirty tracked worktree")
    samples, corpus_summary = load_final_corpus(args.corpus)
    if len(samples) != args.n_total:
        raise ValueError(f"expected {args.n_total} layouts, found {len(samples)}")
    start = task_id * args.chunk_size
    stop = min(start + args.chunk_size, args.n_total)
    records = []
    for sample in samples[start:stop]:
        diagnostics, wall_ms = solve(sample["layout"], args.timeout_s)
        old_cps = float(sample["y"][0])
        new_cps = float(diagnostics["cps_pf"])
        record = {
            "layout_id": sample["layout_id"],
            "geometry_sha256": sample["geometry_sha256"],
            "Cps_pF": new_cps,
            "coarse_Cps_pF": old_cps,
            "coarse_to_refined_relative_difference_pct": abs(new_cps - old_cps) / abs(new_cps) * 100.0,
            "solver_ms": wall_ms,
            "diagnostics": diagnostics,
        }
        records.append(record)
        print(
            f"layout={sample['layout_id']:04d} refined={new_cps:.6f}pF "
            f"delta={record['coarse_to_refined_relative_difference_pct']:.3f}% "
            f"wall={wall_ms / 1000:.1f}s",
            flush=True,
        )
    sources = [
        Path(__file__),
        ROOT / "requirements-proof.txt",
        CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py",
        CODE / "core/planar_to_graph.py",
        CODE / "solvers/fem_capacitance_3d.py",
        fem_cps_diagnostic_worker_path(),
    ]
    output = ROOT / "results/corpus_v4/refined_cps/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    result = {
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
                for name in ("numpy", "scipy", "scikit-fem")
            },
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                text=True, check=True,
            ).stdout.strip(),
            "git_dirty_paths": dirty,
            "source_corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sources},
        },
        "protocol": {
            "fem_refine": FEM_REFINE,
            "pad_mm": DOMAIN_PAD_MM,
            "timeout_s": args.timeout_s,
            "range": [start, stop],
        },
        "records": records,
    }
    path = output / f"task_{task_id:03d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
