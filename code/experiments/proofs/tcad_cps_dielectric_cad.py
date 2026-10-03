"""Frozen CAD-only precursor to dielectric-domain meshing; stdlib contracts."""
from __future__ import annotations
import argparse
import copy
import json
import os
import sys
from pathlib import Path

import tcad_cps_hxt_postopt as parent
from archive_tcad_cps_hxt_postopt_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
sys.path.insert(0, str(ROOT / "code/solvers"))
from tcad_cps_dielectric_cad_metadata import review_report

PHASE = "dielectric_cad"
BASE = Path("results/tcad/cps_dielectric_cad_v1")
PROTOCOL = Path("protocols/tcad_cps_dielectric_cad_v1.json")
LOCK = Path("protocols/tcad_cps_dielectric_cad_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_dielectric_cad.sh"
WORKER = "code/solvers/tcad_cps_dielectric_cad_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_dielectric_cad.py",
    "code/experiments/proofs/run_tcad_cps_dielectric_cad.py",
    "code/experiments/proofs/archive_tcad_cps_hxt_postopt_v1.py",
    "code/solvers/tcad_cps_dielectric_topology.py",
    "code/solvers/tcad_cps_dielectric_cad_metadata.py",
    "code/solvers/tcad_cps_dielectric_cad_builder.py",
    "tests/test_tcad_cps_dielectric_topology.py",
    "tests/test_tcad_cps_dielectric_cad.py", "tests/test_tcad_cps_hxt_postopt_archive.py",
    WORKER, WRAPPER]
STAGES = ["geometry_validated", "occ_fragmented", "cad_before_verified",
          "metal_volumes_removed", "orphan_entities_removed", "cad_after_verified", "gmsh_finalized"]
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
mode_input = parent.mode_input
bounded = parent.bounded


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("dielectric CAD parent/archive identity mismatch")
    checks = cfg["geometry_checks"]
    if checks["outer_planes"] != 6 or checks["require_plane_surfaces"] is not True or checks["require_line_curves"] is not True:
        raise ValueError("CAD adapter requires the axis-aligned box contract")
    p = copy.deepcopy(parent.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"], dielectric_cad=cfg)
    p["resources"] = {PHASE: cfg["allocation"]}
    p["worker_limits"] = {mode: copy.deepcopy(cfg["worker_limits"]) for mode in cfg["modes"]}
    return p


def assess_result(result, mode, p):
    try:
        layout_id, layout, arm = mode_input(mode, p)
        cfg = p[PHASE]
        summary = review_report(result["cad_report"], layout, arm["pad_mm"], cfg["geometry_checks"], cfg["cad_options"])
        return bool(result["mode"] == mode and result["layout_id"] == layout_id and result["arm"] == arm
            and sha256_json(result["cad_summary"]) == sha256_json(summary) and result["cad_contract_passed"] is True
            and result["cad_report_sha256"] == sha256_json(result["cad_report"])
            and result["stages"] == STAGES
            and all(result[key] is False for key in ("mesh_generated", "mesh_feasible", "field_solver_executed",
                "reference_qualified", "training_may_start", "claim_eligible"))
            and not any(key in result for key in ("cps_pf", "mesh_sha256", "system_sha256", "n_free", "relative_residual"))
            and bounded(result["elapsed_s"], p["worker_limits"][mode]["worker_timeout_s"])
            and bounded(result["peak_rss_gib"], p["worker_limits"][mode]["rss_gib_max"]))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return False


def assessment(record, p):
    modes = p[PHASE]["modes"]
    observed = record.get("modes", {})
    complete = record.get("failure") is None and set(observed) == set(modes) and all(
        observed[m].get("passed") is True and assess_result(observed[m].get("result", {}), m, p) for m in modes)
    repeat = bool(complete and observed["local1"]["result"]["cad_report_sha256"] == observed["repeat1"]["result"]["cad_report_sha256"])
    return {"complete": bool(complete), "repeatability_passed": repeat,
        "diagnostic_passed": bool(complete and repeat), "mesh_generated": False, "mesh_feasible": False,
        "field_solver_executed": False, "reference_qualified": False, "training_may_start": False,
        "claim_eligible": False, "automatic_expansion": False, "terminal_admission_pending": True}


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-dielectric-cad-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("dielectric CAD source/input lock mismatch")
    if execution:
        command = parent.parent.parent.support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("dielectric CAD execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("dielectric CAD external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("dielectric CAD executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked dielectric CAD dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / parent.parent.parent.PANEL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{parent.parent.parent.support.original.job_number(job)}"
    for ancestor in [path, *path.parents]:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ValueError("symlink in dielectric CAD attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace dielectric CAD source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
