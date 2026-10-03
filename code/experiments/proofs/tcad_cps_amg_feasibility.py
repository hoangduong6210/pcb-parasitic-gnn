"""Frozen single-sentinel contracts; unchanged mesh/caps, tested AMG candidate."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
from pathlib import Path

import tcad_cps_amg_diagnostic as diagnostic
import tcad_cps_support_recovery as support
from archive_tcad_cps_amg_diagnostic_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = support.ROOT
BASE = Path("results/tcad/cps_amg_feasibility_v1")
PROTOCOL = Path("protocols/tcad_cps_amg_feasibility_v1.json")
LOCK = Path("protocols/tcad_cps_amg_feasibility_v1.lock.json")
PANEL = support.PANEL
WRAPPERS = {phase: f"code/jobs/submit_tcad_cps_amg_{phase}.sh" for phase in ("smoke", "feasibility", "finalize")}
SOURCES = ["code/experiments/proofs/archive_tcad_cps_amg_diagnostic_v1.py",
           "code/experiments/proofs/tcad_cps_amg_feasibility.py",
           "code/experiments/proofs/run_tcad_cps_amg_feasibility.py",
           "code/solvers/tcad_cps_amg_feasibility_worker.py",
           "tests/test_tcad_cps_amg_feasibility.py", *WRAPPERS.values()]
read_json = support.read_json
check_allocation = support.check_allocation
check_runtime = support.check_runtime
target = support.target
arm_protocol = support.arm_protocol


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    for path, key in ((support.PROTOCOL, "parent_support_protocol_sha256"),
                      (diagnostic.PROTOCOL, "amg_diagnostic_protocol_sha256"),
                      (ARCHIVE, "diagnostic_archive_sha256")):
        if sha256_file(ROOT / path) != cfg[key]:
            raise ValueError("AMG feasibility parent/archive identity mismatch")
    p = copy.deepcopy(support.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"])
    p["amg_feasibility"] = cfg
    # Shared, immutable numeric helpers consume this candidate configuration.
    p["diagnostic"] = copy.deepcopy(diagnostic.protocol()["diagnostic"])
    return p


def arms_for(phase, p):
    if phase == "smoke":
        return [p["smoke"]["arm"]]
    if phase == "feasibility":
        return p["recovery"]["recovery_arms"]
    raise ValueError("unknown AMG worker phase")


def inputs(phase, name, p):
    arms = [a for a in arms_for(phase, p) if a["name"] == name]
    if len(arms) != 1:
        raise ValueError("unfrozen AMG feasibility arm")
    if phase == "smoke":
        return "smoke", p["smoke"]["layout"], arms[0]
    row = target(p)
    return row["layout_id"], row["layout"], arms[0]


def check_anchor(result, phase, arm, p):
    mode = "toy" if phase == "smoke" else "local0" if arm["name"] == "local0" else None
    if mode is not None and any(result.get(k) != v for k, v in p["diagnostic"]["expected_systems"][mode].items()):
        raise ValueError("AMG feasibility anchor matrix/mesh mismatch")
    if phase == "smoke" and not 0 < result["n_free"] <= p["diagnostic"]["direct_n_free_max"]:
        raise ValueError("smoke direct-comparison dimension cap exceeded")


def assess_result(result, p, phase):
    try:
        if phase not in ("smoke", "feasibility") or not support.assess_result(result, p, phase):
            return False
        check_anchor(result, phase, result["arm"], p)
        finite = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        upper = lambda x, cap: finite(x) and 0 <= x <= cap
        integer = lambda x: isinstance(x, int) and not isinstance(x, bool)
        valid = (result["candidate"] == diagnostic.candidate_kwargs(p)
                 and integer(result["solver_info"]) and result["solver_info"] == 0
                 and integer(result["iterations"]) and upper(result["iterations"], p["linear_solver"]["maxiter"])
                 and result["input_system_sha256"] == result["system_sha256"]
                 and result["operator_complexity"] >= 1
                 and upper(result["elapsed_s"], p["resources"][phase]["worker_timeout_s"])
                 and all(integer(result[k]) and result[k] > 0 for k in ("mesh_nodes", "mesh_tetrahedra", "n_free", "nnz")))
        if phase == "smoke":
            other = result["comparison"]
            valid = valid and other["input_system_sha256"] == result["system_sha256"]
            valid = valid and upper(other["relative_residual"], p["gates"]["relative_residual_max"])
            valid = valid and upper(result["solution_relative_l2"], p["diagnostic"]["solution_relative_l2_max"])
        return bool(valid)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False


def assess_feasibility(record, p):
    # The inherited scalar comparison function and denominators are unchanged.
    if not all(assess_result(arm.get("result", {}), p, "feasibility") for arm in record.get("arms", {}).values()):
        record = {}
    out = support.assess_feasibility(record, p)
    out["reference_qualified"] = False
    return out


def frozen_lock():
    diagnostic.check_source(execution=False)
    archive = check_archive()
    paths = set(diagnostic.frozen_lock()["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(diagnostic.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-amg-feasibility-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("AMG feasibility source/input lock mismatch")
    if execution:
        command = support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT:
            raise ValueError("AMG feasibility execution-root mismatch")
        if command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("AMG feasibility commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("AMG feasibility external lock mismatch")
        wrapper = WRAPPERS[os.environ["PCB_TCAD_BATCH_PHASE"]]
        if sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / wrapper):
            raise ValueError("AMG feasibility batch wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked AMG feasibility dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / PANEL)}


def attempt_directory(phase, job, *, create=False):
    if phase not in WRAPPERS:
        raise ValueError("unknown AMG feasibility phase")
    path = ROOT / BASE / phase / f"job_{support.original.job_number(job)}"
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise ValueError("symlink in AMG feasibility attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace AMG feasibility lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
