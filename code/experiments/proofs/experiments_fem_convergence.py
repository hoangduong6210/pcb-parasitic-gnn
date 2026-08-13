#!/usr/bin/env python3
"""Mesh/domain sensitivity study for the electrostatic C_ps reference.

Nine field-corpus layouts span trace-count terciles and low/middle/high C_ps
within each tercile.  Each layout is solved for the Cartesian product of three
mesh refinements and three outer-domain paddings.  Solves are subprocess-isolated
and this heavy protocol refuses to run outside SLURM.
"""
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
for _directory in (CODE / "core", CODE / "solvers", CODE / "data"):
    sys.path.insert(0, str(_directory))

from gen_corpus_fh import big_layout
from runtime_paths import fem_cps_diagnostic_worker_path


SCHEMA = "pcb-gnn.fem-cps-convergence.v1"
DEFAULT_TARGETS = ROOT / "results/proof_updates/jobs/strict_e3/job_51174496/field_grade_targets.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--refinements", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--pads-mm", type=float, nargs="+", default=[6.0, 8.0, 12.0])
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()


def select_layouts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for position, record in enumerate(records):
        layout = big_layout(42 + int(record["layout_id"]), 36)
        enriched.append({
            "position": position, "layout_id": int(record["layout_id"]),
            "layout": layout, "n_traces": len(layout["traces"]),
            "baseline_cps_pf": float(record["target"][0]),
        })
    selected = []
    for trace_stratum, indices in enumerate(np.array_split(
        np.argsort([item["n_traces"] for item in enriched]), 3
    )):
        group = sorted((enriched[int(index)] for index in indices), key=lambda item: item["baseline_cps_pf"])
        picks = [0, len(group) // 2, len(group) - 1]
        for cps_stratum, pick in enumerate(picks):
            item = dict(group[pick])
            item["trace_stratum"] = trace_stratum
            item["cps_stratum"] = cps_stratum
            selected.append(item)
    return selected


def solve(layout: dict[str, Any], refine: int, pad_mm: float, timeout_s: int) -> tuple[dict[str, Any] | None, float]:
    worker = fem_cps_diagnostic_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        path = Path(handle.name)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, str(worker), str(path), str(refine), str(pad_mm)],
            cwd=worker.parent, env=os.environ.copy(), capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
        for line in completed.stdout.splitlines():
            if line.startswith("RESULT="):
                return json.loads(line.removeprefix("RESULT=")), (time.perf_counter() - started) * 1000
        return None, (time.perf_counter() - started) * 1000
    except subprocess.TimeoutExpired:
        return None, (time.perf_counter() - started) * 1000
    finally:
        path.unlink(missing_ok=True)


def delta(rows: list[dict[str, Any]], left: tuple[int, float], right: tuple[int, float]) -> dict[str, Any]:
    by_layout_setting = {
        (row["layout_id"], row["refine"], row["pad_mm"]): row for row in rows if row["valid"]
    }


def original_baseline_delta(rows: list[dict[str, Any]]) -> dict[str, Any]:
    details = []
    for row in rows:
        if row["valid"] and row["refine"] == 1 and row["pad_mm"] == 8.0:
            relative = abs(row["cps_pf"] - row["original_reference_cps_pf"]) / abs(
                row["original_reference_cps_pf"]
            ) * 100.0
            details.append({"layout_id": row["layout_id"], "relative_difference_pct": relative})
    values = np.asarray([item["relative_difference_pct"] for item in details], dtype=np.float64)
    return {
        "n_paired": len(details),
        "median_relative_difference_pct": float(np.median(values)) if len(values) else None,
        "max_relative_difference_pct": float(np.max(values)) if len(values) else None,
        "per_layout": details,
    }
    values = []
    details = []
    for layout_id in sorted({row["layout_id"] for row in rows}):
        a = by_layout_setting.get((layout_id, left[0], left[1]))
        b = by_layout_setting.get((layout_id, right[0], right[1]))
        if a is None or b is None:
            continue
        relative = abs(a["cps_pf"] - b["cps_pf"]) / abs(b["cps_pf"]) * 100.0
        values.append(relative)
        details.append({"layout_id": layout_id, "relative_difference_pct": relative})
    array = np.asarray(values, dtype=np.float64)
    return {
        "left": {"refine": left[0], "pad_mm": left[1]},
        "right_reference": {"refine": right[0], "pad_mm": right[1]},
        "n_paired": len(values),
        "median_relative_difference_pct": float(np.median(array)) if len(array) else None,
        "max_relative_difference_pct": float(np.max(array)) if len(array) else None,
        "per_layout": details,
    }


def main() -> None:
    args = parse_args()
    args.targets = args.targets.resolve()
    if args.validate_only:
        if set(args.refinements) != {0, 1, 2} or set(args.pads_mm) != {6.0, 8.0, 12.0}:
            raise SystemExit("Canonical protocol requires refinements 0/1/2 and pads 6/8/12 mm")
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "n_solves": 81}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Refusing FEM solves outside SLURM; submit submit_fem_convergence.sh")

    attempted = [json.loads(line) for line in args.targets.read_text().splitlines() if line.strip()]
    records = [record for record in attempted if record.get("valid") and record.get("target") is not None]
    if len(records) != 332:
        raise ValueError(
            f"Expected 332 valid field-grade records, found {len(records)} "
            f"among {len(attempted)} attempted records"
        )
    selections = select_layouts(records)
    output_dir = ROOT / "results/proof_updates/jobs/fem_convergence" / f"job_{os.environ['SLURM_JOB_ID']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in selections:
        for refine in args.refinements:
            for pad_mm in args.pads_mm:
                result, wall_ms = solve(item["layout"], refine, pad_mm, args.timeout_s)
                row = {
                    "layout_id": item["layout_id"], "n_traces": item["n_traces"],
                    "trace_stratum": item["trace_stratum"], "cps_stratum": item["cps_stratum"],
                    "original_reference_cps_pf": item["baseline_cps_pf"],
                    "refine": refine, "pad_mm": pad_mm, "wall_ms": wall_ms,
                    "valid": result is not None,
                }
                if result:
                    row.update(result)
                rows.append(row)
                print(
                    f"layout={item['layout_id']} refine={refine} pad={pad_mm:g} "
                    f"valid={row['valid']} wall={wall_ms/1000:.1f}s", flush=True,
                )

    summaries = {
        "recomputed_vs_original_published_setting": original_baseline_delta(rows),
        "published_baseline_vs_highest_setting": delta(rows, (1, 8.0), (2, 12.0)),
        "mesh_refinement_at_published_domain": delta(rows, (1, 8.0), (2, 8.0)),
        "domain_padding_at_highest_refinement": delta(rows, (2, 8.0), (2, 12.0)),
        "coarse_vs_published_baseline": delta(rows, (0, 8.0), (1, 8.0)),
    }
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
            "hostname": socket.gethostname(), "platform": platform.platform(),
            "python": platform.python_version(), "numpy": np.__version__,
            "gmsh": importlib.metadata.version("gmsh"),
            "scikit_fem": importlib.metadata.version("scikit-fem"),
            "git_head": git_output("rev-parse", "HEAD"),
            "git_dirty_paths": git_output("status", "--short", "--untracked-files=no").splitlines(),
            "arguments": {**vars(args), "targets": args.targets.relative_to(ROOT).as_posix()},
            "inputs": {args.targets.relative_to(ROOT).as_posix(): sha256(args.targets)},
            "source_sha256": sha256(Path(__file__)),
            "solver_sha256": sha256(ROOT / "code/solvers/fem_capacitance_3d.py"),
            "worker_sha256": sha256(fem_cps_diagnostic_worker_path()),
        },
        "selection": {
            "rule": "trace-count terciles crossed with low/middle/high Cps order statistics",
            "layouts": [{key: value for key, value in item.items() if key != "layout"} for item in selections],
        },
        "summaries": summaries,
        "raw_results": rows,
        "status": "complete" if all(row["valid"] for row in rows) else "incomplete",
    }
    result_path = output_dir / "results_fem_convergence.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(result_path.relative_to(ROOT), flush=True)
    if result["status"] != "complete":
        failed = sum(not row["valid"] for row in rows)
        raise RuntimeError(f"Convergence protocol incomplete: {failed} of {len(rows)} solves failed")


if __name__ == "__main__":
    main()
