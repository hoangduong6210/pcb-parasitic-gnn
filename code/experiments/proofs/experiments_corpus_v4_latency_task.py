#!/usr/bin/env python3
"""One-design SLURM-array task for paired corpus-v4 latency measurement."""
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
for directory in (CODE / "core", CODE / "data", CODE / "solvers", CODE / "inference"):
    sys.path.insert(0, str(directory))

from fasthenry_ref import FASTHENRY, fasthenry_totals  # noqa: E402
from geometry_contract import validate_passive_labels  # noqa: E402
from predict_safe_bundle import load_bundle, predict_layout  # noqa: E402
from runtime_paths import fem_cps_diagnostic_worker_path  # noqa: E402
from v3_dataset import load_final_corpus, sha256  # noqa: E402


SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v1"
FEM_REFINE = 2
DOMAIN_PAD_MM = 12.0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solve_fem(layout: dict[str, Any], timeout_s: int) -> tuple[dict[str, Any], float]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        layout_path = Path(handle.name)
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(worker),
                str(layout_path),
                str(FEM_REFINE),
                str(DOMAIN_PAD_MM),
            ],
            cwd=worker.parent,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("corpus-v4 latency FEM solve timed out") from error
    finally:
        layout_path.unlink(missing_ok=True)
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    lines = [line for line in completed.stdout.splitlines() if line.startswith("RESULT=")]
    if completed.returncode != 0 or len(lines) != 1:
        raise RuntimeError(f"FEM worker failed with return code {completed.returncode}")
    return json.loads(lines[0].removeprefix("RESULT=")), elapsed_ms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--n-designs", type=int, default=100)
    parser.add_argument("--inference-repetitions", type=int, default=30)
    parser.add_argument("--fem-timeout-s", type=int, default=3600)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 100}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Submit paired corpus-v4 latency as a SLURM array")
    if args.corpus is None or args.bundle is None:
        raise SystemExit("--corpus and --bundle are required")
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if args.n_designs != 100 or task_id not in range(args.n_designs):
        raise SystemExit("canonical paired-latency array has exactly tasks 0..99")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing latency measurement from a dirty tracked worktree")
    binary = Path(FASTHENRY).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(binary)
    samples, corpus_summary = load_final_corpus(args.corpus)
    model_started = time.perf_counter_ns()
    model, norm, metadata = load_bundle(args.bundle)
    model_load_ms = (time.perf_counter_ns() - model_started) / 1e6
    if metadata.get("schema") != "pcb-gnn.safe-inference-bundle.v2":
        raise ValueError("unexpected safe inference bundle schema")
    eligible = np.asarray(metadata["test_layout_ids"], dtype=int)
    if args.n_designs > len(eligible):
        raise ValueError("n-designs exceeds the held-out split")
    rng = np.random.default_rng(20260813)
    selected = sorted(rng.choice(eligible, size=args.n_designs, replace=False).tolist())
    by_id = {sample["layout_id"]: sample for sample in samples}
    layout_id = int(selected[task_id])
    sample = by_id[layout_id]
    layout = sample["layout"]

    fh_started = time.perf_counter_ns()
    inductance = fasthenry_totals(layout, 1e5)
    fh_ms = (time.perf_counter_ns() - fh_started) / 1e6
    if inductance is None:
        raise RuntimeError(f"FastHenry failed for layout {layout_id}")
    fem, fem_ms = solve_fem(layout, args.fem_timeout_s)
    rerun_label = {"Cps_pF": float(fem["cps_pf"]), **inductance}
    passivity = validate_passive_labels(rerun_label)

    predict_layout(model, norm, layout)
    repetitions = []
    prediction = None
    for _ in range(args.inference_repetitions):
        infer_started = time.perf_counter_ns()
        prediction = predict_layout(model, norm, layout)
        repetitions.append((time.perf_counter_ns() - infer_started) / 1e6)
    inference_ms = float(np.median(repetitions))
    reference = sample["y"].astype(np.float64)
    rerun = np.asarray([
        rerun_label["Cps_pF"], rerun_label["L_pri_nH"],
        rerun_label["L_sec_nH"], rerun_label["L_mut_nH"],
    ])
    drift = np.abs(rerun - reference) / np.maximum(np.abs(reference), 1e-9)
    if float(np.max(drift)) > 1e-4:
        raise RuntimeError(f"solver-label drift exceeds tolerance: {drift}")
    paired_ms = fh_ms + fem_ms
    record = {
        "layout_id": layout_id,
        "geometry_sha256": sample["geometry_sha256"],
        "solver_ms": {"fasthenry": fh_ms, "fem": fem_ms, "paired": paired_ms},
        "inference_raw_layout_ms": {"median": inference_ms, "repetitions": repetitions},
        "speedup_paired_four_target_x": paired_ms / inference_ms,
        "solver_label_max_relative_drift": float(np.max(drift)),
        "coupling_coefficient": passivity["coupling_coefficient"],
        "prediction": prediction.tolist(),
        "reference": reference.tolist(),
        "fem_diagnostics": fem,
    }
    sources = [
        Path(__file__), ROOT / "requirements-proof.txt", CODE / "data/v3_dataset.py",
        CODE / "inference/predict_safe_bundle.py", CODE / "core/geometry_contract.py",
        CODE / "core/planar_to_graph.py", CODE / "solvers/fasthenry_ref.py",
        CODE / "solvers/fem_capacitance_3d.py", fem_cps_diagnostic_worker_path(), binary,
    ]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "package_versions": {
                name: importlib.metadata.version(name)
                for name in ("numpy", "scipy", "scikit-fem", "torch")
            },
            "git_head": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "git_dirty_paths": dirty,
            "corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
            "bundle_sha256": {
                path.name: sha256(path) for path in args.bundle.iterdir() if path.is_file()
            },
            "file_sha256": {
                (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT)
                 else f"external/{path.name}"): file_sha256(path)
                for path in sources
            },
        },
        "protocol": {
            "n_designs": args.n_designs,
            "selection_seed": 20260813,
            "selected_layout_ids_sha256": hashlib.sha256(
                json.dumps(selected).encode("utf-8")
            ).hexdigest(),
            "fem_refine": FEM_REFINE,
            "pad_mm": DOMAIN_PAD_MM,
            "fem_timeout_s": args.fem_timeout_s,
            "inference_repetitions": args.inference_repetitions,
            "model_load_excluded_from_per_design_inference": True,
            "model_load_ms": model_load_ms,
        },
        "record": record,
    }
    output = ROOT / "results/corpus_v4/latency/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"task_{task_id:03d}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"layout={layout_id} solver={paired_ms:.3f}ms gnn={inference_ms:.6f}ms "
        f"speedup={paired_ms / inference_ms:.2f}x artifact={path.relative_to(ROOT)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
