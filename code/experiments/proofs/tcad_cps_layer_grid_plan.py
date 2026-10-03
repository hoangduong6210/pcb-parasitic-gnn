"""Source-bound exact-plane planning and allocation contracts; stdlib only."""
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_jacobian_arithmetic as parent
import tcad_cps_dielectric_cad as cad
from archive_tcad_cps_jacobian_arithmetic_v1 import MANIFEST as ARCHIVE, check_archive
from tcad_cps_reference import command, job_number
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "layer_grid_plan"
BASE = Path("results/tcad/cps_layer_grid_plan_v1")
PROTOCOL = Path("protocols/tcad_cps_layer_grid_plan_v1.json")
LOCK = Path("protocols/tcad_cps_layer_grid_plan_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_layer_grid_plan.sh"
WORKER = "code/solvers/tcad_cps_layer_grid_plan_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_layer_grid_plan.py", "code/experiments/proofs/run_tcad_cps_layer_grid_plan.py",
    "code/experiments/proofs/archive_tcad_cps_jacobian_arithmetic_v1.py", "code/solvers/tcad_cps_layer_grid_axes.py",
    "tests/test_tcad_cps_layer_grid_plan.py", WORKER, WRAPPER]
CLOSED = ("coordinates_snapped", "mesh_generated", *parent.CLOSED)
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
bounded = parent.bounded
mode_input = cad.mode_input


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("grid planning parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    p[PHASE] = cfg
    p["resources"] = {PHASE: cfg["resources"]}
    original = parent.parent.protocol()["worker_limits"]
    p["worker_limits"] = {m: {**original[m], "worker_timeout_s": cfg["worker_timeout_s"], "rss_gib_max": cfg["rss_gib_max"]} for m in cfg["modes"]}
    return p


def policy(mode, p):
    _, _, arm = mode_input(mode, p)
    return {"near_size_mm": p["mesh"]["near_sizes_mm"][arm["level"]], "far_size_mm": arm["far_size_mm"],
        "support_expansion_mm": p[PHASE]["support_expansion_mm"], "pad_mm": arm["pad_mm"]}


def cad_report(mode, p):
    if mode not in p[PHASE]["modes"]:
        raise ValueError("unfrozen grid planning mode")
    report = read_json(ROOT / cad.BASE / "job_7651941" / f"{mode}.json")["result"]["cad_report"]
    if sha256_json(report) != p["dielectric_mesh"]["cad_report_sha256"][mode]:
        raise ValueError("grid planning CAD identity mismatch")
    return report


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.layer-grid-plan-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
        "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("grid planning source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("grid planning execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("grid planning external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("grid planning executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked grid planning dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
        "protocol_sha256": sha256_file(ROOT / PROTOCOL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{job_number(job)}"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in grid planning attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assessment(record, p):
    modes = record.get("modes", {})
    complete = record.get("failure") is None and set(modes) == set(p[PHASE]["modes"]) and all(v.get("passed") is True for v in modes.values())
    repeat = bool(complete and modes["local1"]["result"]["report_sha256"] == modes["repeat1"]["result"]["report_sha256"])
    feasible = bool(complete and repeat and all(v["result"]["summary"]["planning_feasible"] is True for v in modes.values()))
    return {"complete": bool(complete), "repeatability_passed": repeat, "diagnostic_passed": bool(complete and repeat),
        "planning_feasible": feasible, **{k: False for k in CLOSED}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace grid planning lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
