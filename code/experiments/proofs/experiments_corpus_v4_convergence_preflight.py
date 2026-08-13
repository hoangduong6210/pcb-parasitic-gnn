#!/usr/bin/env python3
"""High-resolution FEM convergence preflight for corpus-v4 Cps labels."""
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

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers"):
    sys.path.insert(0, str(directory))

from runtime_paths import fem_cps_diagnostic_worker_path  # noqa: E402
from v3_dataset import load_final_corpus, sha256  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-convergence-preflight-task.v1"
SETTINGS = ((2, 12.0), (2, 16.0), (3, 12.0), (3, 16.0))


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


def solve(layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int) -> dict[str, Any]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        layout_path = Path(handle.name)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), str(layout_path), str(refine), str(pad_mm)],
            cwd=worker.parent,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"FEM timeout at refine={refine}, pad={pad_mm:g}") from error
    finally:
        layout_path.unlink(missing_ok=True)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    lines = [line for line in completed.stdout.splitlines() if line.startswith("RESULT=")]
    if completed.returncode != 0 or len(lines) != 1:
        raise RuntimeError(
            f"FEM failed at refine={refine}, pad={pad_mm:g}; return={completed.returncode}"
        )
    return {"wall_ms": elapsed_ms, **json.loads(lines[0].removeprefix("RESULT="))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--timeout-s", type=int, default=7200)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({
            "schema": SCHEMA,
            "status": "validation-ok",
            "n_tasks": 9,
            "settings": SETTINGS,
        }))
        return
    if not os.environ.get("SLURM_ARRAY_JOB_ID") or not os.environ.get("SLURM_ARRAY_TASK_ID"):
        raise SystemExit("Submit corpus-v4 convergence preflight as a SLURM array")
    if args.corpus is None:
        raise SystemExit("--corpus is required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if task_id not in range(9):
        raise SystemExit("canonical convergence preflight has tasks 0..8")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing convergence preflight from a dirty tracked worktree")
    samples, corpus_summary = load_final_corpus(args.corpus)
    sample = samples[selected_indices(samples)[task_id]]
    settings = []
    for refine, pad_mm in SETTINGS:
        result = solve(sample["layout"], refine, pad_mm, args.timeout_s)
        settings.append(result)
        print(
            f"layout={sample['layout_id']:04d} refine={refine} pad={pad_mm:g} "
            f"Cps={result['cps_pf']:.6f}pF nodes={result['mesh_nodes']} "
            f"wall={result['wall_ms'] / 1000:.1f}s",
            flush=True,
        )
    worker = fem_cps_diagnostic_worker_path()
    sources = [
        Path(__file__), ROOT / "requirements-proof.txt", CODE / "data/v3_dataset.py",
        CODE / "core/geometry_contract.py", CODE / "core/planar_to_graph.py",
        CODE / "solvers/fem_capacitance_3d.py", worker,
    ]
    output = ROOT / "results/corpus_v4/convergence_preflight/jobs" / (
        f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    )
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
                for name in ("numpy", "scipy", "scikit-fem", "gmsh", "meshio")
            },
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "file_sha256": {
                path.relative_to(ROOT).as_posix(): file_sha256(path) for path in sources
            },
        },
        "selection": {
            "rule": "trace-count terciles crossed with low/median/high coarse-reference Cps",
            "selection_position": task_id,
            "layout_id": sample["layout_id"],
            "geometry_sha256": sample["geometry_sha256"],
            "n_traces": len(sample["layout"]["traces"]),
        },
        "settings": settings,
    }
    path = output / f"task_{task_id:02d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
