"""Stdlib-only source/input and SLURM contracts for saved-packet arithmetic."""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_dielectric_mesh as parent
from archive_tcad_cps_dielectric_mesh_v1 import MANIFEST as ARCHIVE, DIRECTORY as INPUT_DIRECTORY, check_archive
from tcad_cps_reference import command, job_number
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "jacobian_arithmetic"
BASE = Path("results/tcad/cps_jacobian_arithmetic_v1")
PROTOCOL = Path("protocols/tcad_cps_jacobian_arithmetic_v1.json")
LOCK = Path("protocols/tcad_cps_jacobian_arithmetic_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_jacobian_arithmetic.sh"
WORKER = "code/solvers/tcad_cps_jacobian_arithmetic_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_jacobian_arithmetic.py",
    "code/experiments/proofs/run_tcad_cps_jacobian_arithmetic.py",
    "code/experiments/proofs/archive_tcad_cps_dielectric_mesh_v1.py",
    "code/solvers/tcad_cps_jacobian_exact.py", "tests/test_tcad_cps_jacobian_arithmetic.py", WORKER, WRAPPER]
CLOSED = ("boundary_contract_passed", *parent.CLOSED)
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
bounded = parent.bounded


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("arithmetic parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    if cfg["jacobian_rtol"] != p[parent.PHASE]["mesh_checks"]["jacobian_rtol"] or cfg["jacobian_atol"] != 0:
        raise ValueError("original Jacobian tolerance changed")
    p[PHASE] = cfg
    p["resources"] = {PHASE: cfg["resources"]}
    p["worker_limits"] = {m: cfg["worker_limits"] for m in cfg["modes"]}
    return p


def input_kind(mode, p):
    if mode not in p[PHASE]["modes"]:
        raise ValueError("unfrozen arithmetic mode")
    return "final" if mode == "repeat_final" else mode


def input_path(mode, p):
    return ROOT / INPUT_DIRECTORY / "toy.payload" / input_kind(mode, p)


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.jacobian-arithmetic-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
        "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("arithmetic source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("arithmetic execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("arithmetic external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("arithmetic executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked arithmetic dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
        "protocol_sha256": sha256_file(ROOT / PROTOCOL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{job_number(job)}"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in arithmetic attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assessment(record, p):
    modes = record.get("modes", {})
    complete = record.get("failure") is None and set(modes) == set(p[PHASE]["modes"]) and all(v.get("passed") is True for v in modes.values())
    repeat = bool(complete and modes["final"]["result"]["report_sha256"] == modes["repeat_final"]["result"]["report_sha256"])
    return {"complete": bool(complete), "repeatability_passed": repeat, "diagnostic_passed": bool(complete and repeat), **{k: False for k in CLOSED}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace arithmetic lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
