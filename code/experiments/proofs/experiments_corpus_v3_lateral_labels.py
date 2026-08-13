#!/usr/bin/env python3
"""SLURM-array paired field labels for 70 controlled v3 lateral families."""
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
for directory in (CODE / "core", CODE / "data", CODE / "solvers", CODE / "experiments/proofs"):
    sys.path.insert(0, str(directory))

from fasthenry_ref import FASTHENRY, fasthenry_totals
from geometry_contract import validate_passive_labels
from runtime_paths import fem_cps_worker_path
from v3_dataset import sha256
from v3_lateral_families import make_family

SCHEMA = "pcb-gnn.corpus-v3-lateral-label-task.v1"


def safe_fem(layout: dict, timeout_s: int = 180) -> tuple[float, float]:
    worker = fem_cps_worker_path()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(layout, handle)
        path = Path(handle.name)
    started = time.perf_counter_ns()
    try:
        completed = subprocess.run([sys.executable, str(worker), str(path), "1"], cwd=worker.parent,
                                   capture_output=True, text=True, timeout=timeout_s, check=False)
        for line in completed.stdout.splitlines():
            if line.startswith("CPS="):
                return float(line[4:]), (time.perf_counter_ns() - started) / 1e6
        raise RuntimeError(f"FEM failure: {completed.stderr[-500:]}")
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok", "array_tasks": 14}))
        return
    required = ("SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID")
    if any(not os.environ.get(name) for name in required):
        raise SystemExit("Refusing lateral field solves outside a SLURM array")
    dirty = subprocess.run(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing lateral solves from a dirty tracked worktree")
    binary = Path(FASTHENRY).resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise FileNotFoundError(binary)
    task_id = int(os.environ["SLURM_ARRAY_TASK_ID"])
    if not 0 <= task_id < 14:
        raise SystemExit("canonical lateral array has tasks 0..13")
    output = ROOT / "results/corpus_v3/lateral/jobs" / f"job_{os.environ['SLURM_ARRAY_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / f"task_{task_id:02d}_records.jsonl"
    records = []
    for family_id in range(task_id * 5, task_id * 5 + 5):
        for variant in make_family(family_id):
            started = time.perf_counter_ns()
            inductance = fasthenry_totals(variant["layout"], 1e5)
            fh_ms = (time.perf_counter_ns() - started) / 1e6
            if inductance is None:
                raise RuntimeError(f"FastHenry failed for family {family_id}")
            cps, fem_ms = safe_fem(variant["layout"])
            label = {"Cps_pF": cps, **inductance}
            passivity = validate_passive_labels(label)
            record = {**variant, "label": label, "passivity": passivity,
                      "timing_ms": {"fasthenry": fh_ms, "fem": fem_ms, "paired": fh_ms + fem_ms}}
            records.append(record)
            print(f"family={family_id:02d} variant={variant['variant_id']} valid=True", flush=True)
    records_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))
    sources = [Path(__file__), CODE / "data/v3_lateral_families.py", CODE / "data/gen_corpus_v3.py",
               CODE / "core/geometry_contract.py", CODE / "solvers/fasthenry_ref.py",
               CODE / "solvers/fem_capacitance_3d.py", fem_cps_worker_path(), binary]
    meta = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "slurm_array_job_id": os.environ["SLURM_ARRAY_JOB_ID"],
            "slurm_array_task_id": task_id, "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
            "git_dirty_paths": dirty,
            "file_sha256": {
                (path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else f"external/{path.name}"): sha256(path)
                for path in sources
            },
        },
        "family_range": [task_id * 5, task_id * 5 + 5],
        "n_records": len(records), "records_sha256": sha256(records_path),
    }
    (output / f"task_{task_id:02d}_meta.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
