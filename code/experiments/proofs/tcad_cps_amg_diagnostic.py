"""Stdlib-only contracts for one predeclared AMG diagnostic candidate."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
from pathlib import Path

import tcad_cps_support_recovery as recovery
from archive_tcad_cps_support_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = recovery.ROOT
BASE = Path("results/tcad/cps_amg_diagnostic_v1")
PROTOCOL = Path("protocols/tcad_cps_amg_diagnostic_v1.json")
LOCK = Path("protocols/tcad_cps_amg_diagnostic_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_amg_diagnostic.sh"
SOURCES = ["code/experiments/proofs/archive_tcad_cps_support_v1.py",
           "code/experiments/proofs/tcad_cps_amg_diagnostic.py",
           "code/experiments/proofs/run_tcad_cps_amg_diagnostic.py",
           "code/solvers/tcad_cps_amg_worker.py", "tests/test_tcad_cps_amg_diagnostic.py", WRAPPER]
read_json = recovery.read_json
check_allocation = recovery.check_allocation
check_runtime = recovery.check_runtime


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / recovery.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("diagnostic parent/archive identity mismatch")
    p = copy.deepcopy(recovery.protocol())
    p["diagnostic"] = cfg
    p["schema"], p["protocol_name"], p["scope"] = cfg["schema"], cfg["protocol_name"], cfg["scope"]
    p["worker_limits"] = {"toy": p["resources"]["smoke"], "local0": p["resources"]["feasibility"]}
    limits = copy.deepcopy(p["resources"]["feasibility"])
    limits["time_limit"] = cfg["diagnostic_scheduler_time_limit"]
    p["resources"] = {"diagnostic": limits}
    return p


def mode_input(mode, p):
    if mode == "toy":
        return "smoke", p["smoke"]["layout"], p["smoke"]["arm"]
    if mode == "local0":
        row = recovery.target(p)
        return row["layout_id"], row["layout"], p["recovery"]["recovery_arms"][0]
    raise ValueError("unfrozen diagnostic mode")


def frozen_lock():
    recovery.check_source(execution=False)
    archive = check_archive()
    paths = set(recovery.frozen_lock()["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(recovery.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-amg-diagnostic-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("diagnostic source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT:
            raise ValueError("diagnostic execution-root mismatch")
        command = recovery.original.command
        if command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("diagnostic commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("diagnostic external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != "diagnostic" or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("diagnostic executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked diagnostic dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / recovery.PANEL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{recovery.original.job_number(job)}"
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise ValueError("symlink in diagnostic output path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def check_system(record, mode, p):
    expected = p["diagnostic"]["expected_systems"][mode]
    if any(record.get(k) != v for k, v in expected.items()):
        raise ValueError("diagnostic matrix/mesh differs from the recorded system")
    if not 0 < record["n_free"] <= p["diagnostic"]["direct_n_free_max"]:
        raise ValueError("direct-comparison dimension cap exceeded")


def candidate_kwargs(p):
    return copy.deepcopy(p["diagnostic"]["candidate"])


def assess_result(result, mode, p):
    try:
        check_system(result, mode, p)
        limits = p["worker_limits"][mode]
        scalar = lambda v: isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
        upper = lambda v, cap: scalar(v) and 0 <= v <= cap
        positive = lambda v: scalar(v) and v > 0
        other = result["comparison"]
        return bool(result["candidate"] == candidate_kwargs(p) and result["solver_info"] == 0
            and result["input_system_sha256"] == other["input_system_sha256"] == result["system_sha256"]
            and upper(result["operator_complexity"], limits["operator_complexity_max"])
            and result["operator_complexity"] >= 1
            and upper(result["iterations"], p["linear_solver"]["maxiter"])
            and upper(result["relative_residual"], p["gates"]["relative_residual_max"])
            and upper(other["relative_residual"], p["gates"]["relative_residual_max"])
            and positive(result["cps_pf"]) and positive(other["cps_pf"])
            and abs(result["cps_pf"]-other["cps_pf"])/abs(other["cps_pf"]) <= p["gates"]["smoke_backend_relative_max"]
            and upper(result["solution_relative_l2"], p["diagnostic"]["solution_relative_l2_max"])
            and upper(result["peak_rss_gib"], limits["rss_gib_max"])
            and upper(result["elapsed_s"], limits["worker_timeout_s"])
            and result["mesh_nodes"] <= limits["mesh_nodes_max"]
            and result["mesh_tetrahedra"] <= limits["mesh_tetrahedra_max"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace diagnostic lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
