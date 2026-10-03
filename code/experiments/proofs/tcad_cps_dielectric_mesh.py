"""Source-bound boundary-aware dielectric mesh diagnostic; stdlib contracts."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import re
from pathlib import Path

import tcad_cps_dielectric_cad as parent
from archive_tcad_cps_dielectric_cad_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "dielectric_mesh"
BASE = Path("results/tcad/cps_dielectric_mesh_v1")
PROTOCOL = Path("protocols/tcad_cps_dielectric_mesh_v1.json")
LOCK = Path("protocols/tcad_cps_dielectric_mesh_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_dielectric_mesh.sh"
WORKER = "code/solvers/tcad_cps_dielectric_mesh_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_dielectric_mesh.py",
    "code/experiments/proofs/run_tcad_cps_dielectric_mesh.py",
    "code/experiments/proofs/archive_tcad_cps_dielectric_cad_v1.py",
    "code/solvers/tcad_cps_dielectric_mesh_builder.py", "code/solvers/tcad_cps_dielectric_mesh_audit.py",
    "code/solvers/tcad_cps_dielectric_mesh_bundle.py", "tests/test_tcad_cps_dielectric_mesh.py",
    "tests/test_tcad_cps_dielectric_mesh_audit.py", "tests/test_tcad_cps_dielectric_mesh_bundle.py",
    "tests/test_tcad_cps_dielectric_cad_archive.py", WORKER, WRAPPER]
STAGES = parent.STAGES[:-1] + ["cad_identity_verified", "mesh_generate_started", "raw_mesh_preserved",
    "mesh_optimize_started", "mesh_optimize_finished", "final_mesh_preserved", "boundary_audit_passed",
    "cad_unchanged_after_mesh", "gmsh_finalized"]
CLOSED = ("field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible")
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
mode_input = parent.mode_input
bounded = parent.bounded
expected_policy = parent.parent.expected_policy


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("dielectric mesh parent/archive mismatch")
    p = copy.deepcopy(parent.parent.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"], dielectric_mesh=cfg)
    p["dielectric_cad"] = parent.protocol()[parent.PHASE]
    p["resources"] = {PHASE: p["resources"]["hxt_postopt"]}
    for limits in p["worker_limits"].values():
        limits["mesh_triangles_max"] = cfg["triangle_cap_per_tetrahedron_cap"]*limits["mesh_tetrahedra_max"]
    if cfg["optimizer"] != p["hxt_postopt"]["optimizer"] or cfg["modes"] != p["mesh_probe"]["modes"]:
        raise ValueError("unfrozen mode/optimizer change")
    if any(cfg["mesh_checks"][k] != p["dielectric_cad"]["geometry_checks"][k] for k in ("coordinate_atol_mm", "measure_rtol", "measure_atol_native")):
        raise ValueError("CAD/mesh geometric tolerances differ")
    return p


def assess_result(result, mode, p):
    try:
        layout_id, layout, arm = mode_input(mode, p)
        cfg, cad = p[PHASE], p["dielectric_cad"]
        summary = parent.review_report(result["cad_report"], layout, arm["pad_mm"], cad["geometry_checks"], cad["cad_options"])
        audit = result["mesh_audit"]
        limits = p["worker_limits"][mode]
        if (result["mode"] != mode or result["layout_id"] != layout_id or result["arm"] != arm
                or result["cad_report_sha256"] != cfg["cad_report_sha256"][mode]
                or sha256_json(result["cad_report"]) != result["cad_report_sha256"]
                or sha256_json(result["cad_summary"]) != sha256_json(summary) or result["stages"] != STAGES
                or result["mesh_policy"] != expected_policy(mode, p)
                or result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"])
                or result["optimizer"] != cfg["optimizer"] or type(result["optimizer_calls"]) is not int or result["optimizer_calls"] != 1
                or not all(result[k] is False for k in CLOSED)
                or not all(audit[k] is False for k in (*CLOSED, "numerical_accuracy_qualified"))
                or audit["boundary_contract_passed"] is not True
                or audit["schema"] != "pcb-gnn.dielectric-boundary-mesh.v1"
                or result["mesh_audit_sha256"] != sha256_json(audit)
                or not bounded(result["elapsed_s"], limits["worker_timeout_s"])
                or not bounded(result["peak_rss_gib"], limits["rss_gib_max"])):
            return False
        if any(key in result for key in ("cps_pf", "system_sha256", "relative_residual")):
            return False
        for kind in ("nodes", "tetrahedra", "triangles"):
            value = audit["mesh_" + kind]
            if type(value) is not int or not 0 < value <= limits["mesh_" + kind + "_max"]:
                return False
        if "hxt" not in result["gmsh_build_options"].lower().split():
            return False
        raw = result["quality_before"]
        for kind in ("nodes", "tetrahedra", "triangles"):
            if type(raw[kind]) is not int or not 0 < raw[kind] <= limits["mesh_" + kind + "_max"]:
                return False
        if set(raw["metrics"]) != {"min_sicn", "min_det_jac_mm3"}:
            return False
        for observation in raw["metrics"].values():
            if (type(observation["nonpositive_count"]) is not int
                    or not 0 <= observation["nonpositive_count"] <= raw["tetrahedra"]
                    or any(type(observation[k]) not in (float, int) or not math.isfinite(observation[k]) for k in ("minimum", "maximum"))
                    or observation["minimum"] > observation["maximum"]):
                return False
        for metric in ("minimum_sicn", "minimum_native_det_jac_mm3", "minimum_independent_det_jac_mm3"):
            value = audit[metric]
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                return False
        if audit["minimum_sicn"] > cfg["mesh_checks"]["sicn_max"]:
            return False
        if type(audit["tetrahedral_components"]) is not int or audit["tetrahedral_components"] != 1:
            return False  # Both frozen native CAD identities have one connected domain.
        groups = audit["boundary_groups"]
        if set(groups) != {"primary", "secondary", "outer", "internal_dielectric"}:
            return False
        for name, group in groups.items():
            if group["faces"] != summary[name + "_faces"]:
                return False
            for key in ("nodes", "triangles"):
                if type(group[key]) is not int or group[key] < (0 if name == "internal_dielectric" else 1):
                    return False
        if (sum(g["triangles"] for g in groups.values()) != audit["mesh_triangles"]
                or audit["cross_volume_facets"] != groups["internal_dielectric"]["triangles"]
                or audit["exterior_facets"] != audit["mesh_triangles"]-audit["cross_volume_facets"]
                or 2*audit["interior_facets"] + audit["exterior_facets"] != 4*audit["mesh_tetrahedra"]):
            return False
        for stage in ("raw", "final"):
            b = result["bundles"][stage]
            if not re.fullmatch("[a-f0-9]{64}", b["manifest_sha256"]) or not re.fullmatch("[a-f0-9]{64}", b["packet_sha256"]):
                return False
            if type(b["payload_bytes"]) is not int or b["payload_bytes"] <= 0:
                return False
        return bool(set(result["bundles"]) == {"raw", "final"}
            and sum(v["payload_bytes"] for v in result["bundles"].values()) <= cfg["payload"]["per_mode_bytes_max"]
            and audit["packet_sha256"] == result["bundles"]["final"]["packet_sha256"])
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return False


def assessment(record, p):
    modes, observed = p[PHASE]["modes"], record.get("modes", {})
    complete = record.get("failure") is None and set(observed) == set(modes) and all(
        observed[m].get("passed") is True and assess_result(observed[m].get("result", {}), m, p) for m in modes)
    repeat = False
    if complete:
        a, b = (observed[m]["result"] for m in ("local1", "repeat1"))
        repeat = all(a[k] == b[k] for k in ("cad_report_sha256", "mesh_policy_sha256", "mesh_audit_sha256", "bundles"))
    return {"complete": bool(complete), "repeatability_passed": bool(repeat), "diagnostic_passed": bool(complete and repeat),
        "mesh_feasible": False, **{k: False for k in CLOSED}, "automatic_expansion": False, "terminal_admission_pending": True}


def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-dielectric-mesh-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("dielectric mesh source/input lock mismatch")
    if execution:
        command = parent.parent.parent.parent.support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("dielectric mesh execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("dielectric mesh external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("dielectric mesh executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked dielectric mesh dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / parent.parent.parent.parent.PANEL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{parent.parent.parent.parent.support.original.job_number(job)}"
    for ancestor in [path, *path.parents]:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ValueError("symlink in dielectric mesh attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace dielectric mesh source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
