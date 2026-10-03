"""Stdlib contracts for a mesh-only HXT probe; no prior source is modified."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import re
from pathlib import Path

import tcad_cps_amg_feasibility as parent
from archive_tcad_cps_amg_feasibility_v1 import MANIFEST as ARCHIVE, check_archive
from geometry_contract import geometry_sha256, trace_box
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
BASE = Path("results/tcad/cps_mesh_probe_v1")
PROTOCOL = Path("protocols/tcad_cps_mesh_probe_v1.json")
LOCK = Path("protocols/tcad_cps_mesh_probe_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_mesh_probe.sh"
SOURCES = ["code/experiments/proofs/archive_tcad_cps_amg_feasibility_v1.py",
           "tests/test_tcad_cps_amg_feasibility_archive.py",
           "code/experiments/proofs/tcad_cps_mesh_probe.py",
           "code/experiments/proofs/run_tcad_cps_mesh_probe.py",
           "code/solvers/tcad_cps_mesh_probe_worker.py", "tests/test_tcad_cps_mesh_probe.py", WRAPPER]
STAGES = ["geometry_validated", "occ_fragmented", "mesh_generate_started", "mesh_generated",
          "mesh_extracted", "gmsh_finalized", "skfem_mesh_created", "mesh_fingerprinted"]
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("mesh-probe parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"], mesh_probe=cfg)
    p["mesh"]["gmsh_options"].update(cfg["candidate_mesh_options"])
    p["worker_limits"] = {"toy": copy.deepcopy(p["resources"]["smoke"]),
                          "local1": copy.deepcopy(p["resources"]["feasibility"]),
                          "repeat1": copy.deepcopy(p["resources"]["feasibility"])}
    allocation = copy.deepcopy(p["resources"]["feasibility"])
    allocation["time_limit"] = cfg["scheduler_time_limit"]
    p["resources"] = {"mesh_probe": allocation}
    return p


def mode_input(mode, p):
    if mode not in p["mesh_probe"]["modes"]:
        raise ValueError("unfrozen mesh-probe mode")
    phase, name = ("smoke", "smoke") if mode == "toy" else ("feasibility", "local1")
    return parent.inputs(phase, name, p)


def expected_policy(mode, p):
    _, layout, arm = mode_input(mode, p)
    policy = parent.arm_protocol(p, arm)["mesh"]
    near = policy["near_sizes_mm"][arm["level"]]
    options = {**policy["gmsh_options"], "Mesh.MeshSizeMin": near, "Mesh.MeshSizeMax": arm["far_size_mm"],
               "General.NumThreads": 1, "Mesh.MaxNumThreads1D": 1, "Mesh.MaxNumThreads2D": 1, "Mesh.MaxNumThreads3D": 1}
    boxes = []
    for trace in layout["traces"]:
        box = trace_box(layout, trace)
        settings = dict(zip(("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"),
                            [v + (-1 if i % 2 == 0 else 1)*policy["box_expansion_mm"] for i, v in enumerate(box)]))
        settings.update(VIn=near, VOut=arm["far_size_mm"], Thickness=policy["transition_thickness_mm"])
        boxes.append(settings)
    return {"options": options, "boxes": boxes, "near_size_mm": near, "far_size_mm": arm["far_size_mm"], "pad_mm": arm["pad_mm"]}


def bounded(value, cap):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= cap


def assess_result(result, mode, p):
    try:
        layout_id, layout, arm = mode_input(mode, p)
        limits = p["worker_limits"][mode]
        integer = lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0
        counts = result["region_tetrahedra"]
        return bool(result["mode"] == mode and result["layout_id"] == layout_id and result["arm"] == arm
                    and result["geometry_sha256"] == geometry_sha256(layout)
                    and result["mesh_policy"] == expected_policy(mode, p)
                    and result["mesh_policy_sha256"] == sha256_json(result["mesh_policy"])
                    and result["native_log_options"] == p["mesh_probe"]["native_log_options"]
                    and p["mesh_probe"]["required_build_feature"] in result["gmsh_build_options"].lower().split()
                    and result["stages"] == STAGES and result["field_solver_executed"] is False
                    and not any(k in result for k in ("cps_pf", "system_sha256", "n_free", "relative_residual"))
                    and result["mesh_fingerprint_schema"] == p["mesh_probe"]["mesh_fingerprint_schema"]
                    and bool(re.fullmatch(r"[a-f0-9]{64}", result["mesh_sha256"]))
                    and integer(result["mesh_nodes"]) and result["mesh_nodes"] <= limits["mesh_nodes_max"]
                    and integer(result["mesh_tetrahedra"]) and result["mesh_tetrahedra"] <= limits["mesh_tetrahedra_max"]
                    and set(counts) == {"dielectric", "primary", "secondary"} and all(integer(v) for v in counts.values())
                    and sum(counts.values()) == result["mesh_tetrahedra"]
                    and bounded(result["elapsed_s"], limits["worker_timeout_s"])
                    and bounded(result["peak_rss_gib"], limits["rss_gib_max"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def assessment(record, p):
    modes = p["mesh_probe"]["modes"]
    observed = record.get("modes", {})
    complete = (record.get("failure") is None and set(observed) == set(modes)
                and all(observed[m].get("passed") is True and assess_result(observed[m].get("result", {}), m, p) for m in modes))
    repeat = False
    if complete:
        a, b = (observed[m]["result"] for m in ("local1", "repeat1"))
        repeat = all(a[k] == b[k] for k in ("mesh_sha256", "mesh_nodes", "mesh_tetrahedra", "region_tetrahedra", "mesh_policy_sha256"))
    return {"complete": bool(complete), "repeatability_passed": bool(repeat), "mesh_feasible": bool(complete and repeat),
            "field_solver_executed": False, "reference_qualified": False, "training_may_start": False,
            "claim_eligible": False, "automatic_expansion": False, "terminal_admission_pending": True}


def frozen_lock():
    parent.check_source(execution=False)
    archive = check_archive()
    paths = set(parent.frozen_lock()["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-mesh-probe-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("mesh-probe source/input lock mismatch")
    if execution:
        command = parent.support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("mesh-probe execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("mesh-probe external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != "mesh_probe" or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("mesh-probe executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked mesh-probe dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / parent.PANEL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{parent.support.original.job_number(job)}"
    for ancestor in [path, *path.parents]:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ValueError("symlink in mesh-probe attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace mesh-probe source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
