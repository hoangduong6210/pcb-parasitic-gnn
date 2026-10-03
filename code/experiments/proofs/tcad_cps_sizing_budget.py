"""Frozen archived-sizing diagnostic contracts; byte/scalar metadata only."""
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_column_feasibility as parent
from archive_tcad_cps_column_feasibility_v1 import MANIFEST as ARCHIVE, DIRECTORY as INPUTS, check_archive
from tcad_cps_reference import command, job_number
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "sizing_budget"
BASE = Path("results/tcad/cps_sizing_budget_v1")
PROTOCOL = Path("protocols/tcad_cps_sizing_budget_v1.json")
LOCK = Path("protocols/tcad_cps_sizing_budget_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_sizing_budget.sh"
WORKER = "code/solvers/tcad_cps_sizing_budget_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_sizing_budget.py",
    "code/experiments/proofs/run_tcad_cps_sizing_budget.py",
    "code/experiments/proofs/archive_tcad_cps_column_feasibility_v1.py", WORKER, WRAPPER,
    "code/solvers/tcad_cps_sizing_budget_math.py", "tests/test_tcad_cps_sizing_budget_math.py",
    "tests/test_tcad_cps_sizing_budget.py"]
CLOSED = ("mesh_generated", "planar_mesh_generated", "volume_mesh_generated", "boundary_contract_passed",
          "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible")
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
bounded = parent.bounded
mode_input = parent.mode_input
cad_report = parent.cad_report
policy = parent.policy


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("sizing budget parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    if (cfg["modes"] != p[parent.PHASE]["modes"]
            or cfg["archived_input_modes"] != {"toy": "toy", "local1": "local1", "repeat1": "local1"}
            or cfg["axis_points_max"] != 4096 or cfg["subdivision_depth_max"] != 64
            or cfg["rectangle_cap"] != 128 or cfg["reference_cells_max"] != 100000
            or cfg["automatic_retries"] != 0 or cfg["automatic_expansion"] is not False
            or cfg["coordinates_snapped"] is not False or cfg["candidate_selected"] is not False
            or any(cfg[k] is not False for k in CLOSED)):
        raise ValueError("sizing budget protocol changes fixed diagnostic scope")
    p[PHASE] = cfg
    p["resources"] = {PHASE: cfg["resources"]}
    p["worker_limits"] = {m: {**p["worker_limits"][m], "worker_timeout_s": cfg["worker_timeout_s"],
        "rss_gib_max": cfg["rss_gib_max"]} for m in cfg["modes"]}
    return p


def archived_inputs(mode, p):
    """Return only fixed, byte-bound archived inputs; do not reconstruct geometry."""
    source = p[PHASE]["archived_input_modes"][mode]
    paths = {"planar_cad": INPUTS / f"{source}.payload/cad.json",
        "sizing": INPUTS / f"{source}.payload/sizing.json", "native_stdout": INPUTS / f"{source}.stdout"}
    manifest = read_json(ROOT / ARCHIVE)
    for path in paths.values():
        full = ROOT / path
        if (any(q.is_symlink() for q in [full, *full.parents]) or not full.is_file()
                or sha256_file(full) != manifest["files_sha256"][str(path)]):
            raise ValueError("archived sizing diagnostic input changed")
    return paths, {key: {"path": str(path), "sha256": manifest["files_sha256"][str(path)]} for key,path in paths.items()}


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.sizing-budget-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
        "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("sizing budget source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("sizing budget execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("sizing budget external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("sizing budget executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked sizing budget dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
        "protocol_sha256": sha256_file(ROOT / PROTOCOL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{job_number(job)}"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in sizing budget attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assessment(record, p):
    modes = record.get("modes", {})
    complete = record.get("failure") is None and set(modes) == set(p[PHASE]["modes"]) and all(v.get("passed") is True for v in modes.values())
    repeat = bool(complete and modes["local1"]["result"]["report_sha256"] == modes["repeat1"]["result"]["report_sha256"])
    return {"complete": bool(complete), "repeatability_passed": repeat, "diagnostic_passed": bool(complete and repeat),
        "native_mesh_repeatability_tested": False, "candidate_selected": False, **{k: False for k in CLOSED}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace sizing budget source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
