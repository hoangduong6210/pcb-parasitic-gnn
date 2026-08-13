#!/usr/bin/env python3
"""SLURM-array worker for geometry-valid v3 FastHenry/FEM labels."""
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
for _directory in (
    CODE / "core", CODE / "data", CODE / "solvers", CODE / "experiments/proofs",
):
    sys.path.insert(0, str(_directory))

from fasthenry_ref import FASTHENRY, fasthenry_totals
from gen_corpus_v3 import make_layout_v3
from geometry_contract import geometry_sha256, validate_layout, validate_passive_labels
from runtime_paths import fem_cps_worker_path


SCHEMA = "pcb-gnn.corpus-v3-field-label-chunk.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-total", type=int, default=1500)
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--seed-start", type=int, default=42000)
    parser.add_argument("--fem-refine", type=int, default=1)
    parser.add_argument("--fem-timeout-s", type=int, default=180)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def timed(callable_: Any) -> tuple[Any, float]:
    started = time.perf_counter()
    result = callable_()
    return result, (time.perf_counter() - started) * 1000.0


def safe_fem(layout: dict[str, Any], refine: int, timeout_s: int) -> tuple[float | None, float]:
    worker = fem_cps_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        path = Path(handle.name)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), str(path), str(refine)],
            cwd=worker.parent, env=os.environ.copy(), capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
        for line in completed.stdout.splitlines():
            if line.startswith("CPS="):
                return float(line.removeprefix("CPS=")), (time.perf_counter() - started) * 1000.0
        return None, (time.perf_counter() - started) * 1000.0
    except subprocess.TimeoutExpired:
        return None, (time.perf_counter() - started) * 1000.0
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()
    if args.validate_only:
        if args.n_total != 1500 or args.chunk_size != 50 or args.seed_start != 42000:
            raise SystemExit("Canonical v3 protocol requires n=1500, chunk=50, seed_start=42000")
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "n_tasks": 30}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing field solves outside a SLURM array job")
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty_paths = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty_paths:
        raise SystemExit("Refusing field solves from a dirty tracked worktree")
    fasthenry = Path(FASTHENRY).resolve()
    if not fasthenry.is_file() or not os.access(fasthenry, os.X_OK):
        raise FileNotFoundError(f"FASTHENRY_BIN is not executable: {fasthenry}")

    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    start = task_id * args.chunk_size
    stop = min(args.n_total, start + args.chunk_size)
    if start >= args.n_total:
        raise ValueError(f"array task {task_id} starts beyond corpus")
    job_dir = ROOT / "results/corpus_v3/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    job_dir.mkdir(parents=True, exist_ok=True)
    records_path = job_dir / f"task_{task_id:02d}_records.jsonl"
    meta_path = job_dir / f"task_{task_id:02d}_meta.json"

    valid_count = 0
    with records_path.open("w") as handle:
        for layout_id in range(start, stop):
            layout = make_layout_v3(args.seed_start + layout_id)
            geometry_audit = validate_layout(layout)
            digest = geometry_sha256(layout)
            fh, fh_ms = timed(lambda layout=layout: fasthenry_totals(layout, 1e5))
            cps, fem_ms = safe_fem(layout, args.fem_refine, args.fem_timeout_s)
            label = None
            passivity = None
            error = None
            if fh is not None and cps is not None and cps > 0:
                candidate = {
                    "Cps_pF": float(cps), "L_pri_nH": float(fh["L_pri_nH"]),
                    "L_sec_nH": float(fh["L_sec_nH"]), "L_mut_nH": float(fh["L_mut_nH"]),
                }
                try:
                    passivity = validate_passive_labels(candidate)
                    label = candidate
                    valid_count += 1
                except Exception as exc:
                    error = f"passivity: {type(exc).__name__}: {exc}"
            else:
                error = "solver_failure"
            record = {
                "layout_id": layout_id, "seed": args.seed_start + layout_id,
                "geometry_sha256": digest, "geometry_audit": geometry_audit,
                "layout": layout, "label": label, "passivity": passivity,
                "valid": label is not None, "error": error,
                "timing_ms": {"fasthenry": fh_ms, "fem": fem_ms, "paired": fh_ms + fem_ms},
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            print(
                f"task={task_id:02d} layout={layout_id:04d} traces={geometry_audit['n_traces']} "
                f"FH={fh_ms:.1f}ms FEM={fem_ms:.1f}ms valid={record['valid']}", flush=True,
            )

    sources = [
        Path(__file__), ROOT / "code/data/gen_corpus_v3.py",
        ROOT / "code/core/geometry_contract.py", ROOT / "code/solvers/fasthenry_ref.py",
        ROOT / "code/solvers/fem_capacitance_3d.py", fem_cps_worker_path(), fasthenry,
    ]
    meta = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id,
            "hostname": socket.gethostname(), "platform": platform.platform(),
            "python": platform.python_version(),
            "packages": {name: package_version(name) for name in ("numpy", "scipy", "scikit-fem", "gmsh", "meshio")},
            "git_head": git_head,
            "git_dirty_paths": dirty_paths,
            "arguments": vars(args),
            "file_sha256": {
                (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else "external/" + path.name): sha256(path)
                for path in sources
            },
        },
        "range": {"start_inclusive": start, "stop_exclusive": stop},
        "n_attempted": stop - start, "n_valid": valid_count,
        "records_sha256": sha256(records_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    if valid_count != stop - start:
        raise RuntimeError(f"task {task_id}: only {valid_count}/{stop-start} labels passed")


if __name__ == "__main__":
    main()
