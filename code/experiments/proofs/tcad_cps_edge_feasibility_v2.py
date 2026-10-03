"""Frozen planar/column study orchestration contracts; stdlib only."""
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_edge_feasibility as baseline
import tcad_cps_field_probe_api as parent
from archive_tcad_cps_field_probe_api_v1 import MANIFEST as ARCHIVE, check_archive
from tcad_cps_reference import command, job_number
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "edge_feasibility_v2"
BASE = Path("results/tcad/cps_edge_feasibility_v2")
PROTOCOL = Path("protocols/tcad_cps_edge_feasibility_v2.json")
LOCK = Path("protocols/tcad_cps_edge_feasibility_v2.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_edge_feasibility_v2.sh"
WORKER = "code/solvers/tcad_cps_edge_worker_v2.py"
SOURCES = ["code/experiments/proofs/tcad_cps_edge_feasibility_v2.py",
    "code/experiments/proofs/run_tcad_cps_edge_feasibility_v2.py",
    "code/experiments/proofs/archive_tcad_cps_field_probe_api_v1.py", WORKER, WRAPPER,
    "code/solvers/tcad_cps_edge_builder_v2.py", "code/solvers/tcad_cps_edge_sizing.py",
    "code/solvers/tcad_cps_edge_probe_metadata_v2.py", "tests/test_tcad_cps_edge_feasibility_v2.py"]
CLOSED = ("volume_mesh_generated", "boundary_contract_passed", "field_solver_executed",
          "reference_qualified", "training_may_start", "claim_eligible")
STAGES = ["canonical_geometry_verified", "planar_inputs_preserved", "planar_cad_preserved", "planar_cad_verified",
    "sizing_fields_preserved", "probe_state_before_preserved", "sizing_probe_preserved",
    "probe_state_after_preserved", "probe_state_restored", "sizing_probe_verified",
    "planar_mesh_generate_started", "planar_mesh_generate_finished", "planar_packet_preserved", "planar_cad_unchanged",
    "column_plan_preserved", "gmsh_finalized"]
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
bounded = parent.bounded
mode_input = baseline.mode_input
cad_report = baseline.cad_report


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("edge parent/archive identity mismatch")
    p = copy.deepcopy(baseline.protocol())
    expected = {**p[baseline.PHASE],
        "schema": "pcb-gnn.edge-feasibility.v2",
        "scope": "Unchanged edge-v1 planar/column gates with qualified isolated model-backed native probes",
        "parent_protocol_sha256": sha256_file(ROOT / parent.PROTOCOL),
        "terminal_archive_sha256": sha256_file(ROOT / ARCHIVE),
        "baseline_protocol_sha256": sha256_file(ROOT / baseline.PROTOCOL),
        "probe_adapter_policy": "Qualified isolated 0D NodeData adapter; preserve all raw stages and main CAD/fields/options/empty-mesh before/after; exact oracle only under compute guards"}
    if sha256_json(cfg) != sha256_json(expected):
        raise ValueError("edge v2 changes baseline science/resources or qualified probe contract")
    p[PHASE] = cfg
    p["resources"] = {PHASE: cfg["resources"]}
    p["worker_limits"] = {m: {**p["worker_limits"][m], **cfg["planar_limits"],
        "worker_timeout_s": cfg["worker_timeout_s"], "rss_gib_max": cfg["rss_gib_max"]} for m in cfg["modes"]}
    return p


def policy(mode, p):
    _, _, arm = mode_input(mode, p)
    return {"near_size_mm": p["mesh"]["near_sizes_mm"][arm["level"]], "far_size_mm": arm["far_size_mm"],
        "face_band_half_width_mm": p[PHASE]["face_band_half_width_mm"], "pad_mm": arm["pad_mm"]}


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.edge-feasibility-lock.v2", "effective_protocol_sha256": sha256_json(protocol()),
        "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("edge source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("edge execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("edge external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("edge executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked edge dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
        "protocol_sha256": sha256_file(ROOT / PROTOCOL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{job_number(job)}"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in edge attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assessment(record, p):
    modes = record.get("modes", {})
    complete = record.get("failure") is None and set(modes) == set(p[PHASE]["modes"]) and all(v.get("passed") is True for v in modes.values())
    repeat = bool(complete and all(modes["local1"]["result"][k] == modes["repeat1"]["result"][k]
        for k in ("report_sha256", "bundle")))
    feasible = bool(complete and repeat and all(v["result"]["planning_feasible"] is True for v in modes.values()))
    return {"complete": bool(complete), "repeatability_passed": repeat, "diagnostic_passed": bool(complete and repeat),
        "planning_feasible": feasible, **{k: False for k in CLOSED}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace edge source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
