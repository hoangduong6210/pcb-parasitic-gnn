"""Frozen contracts for an unoptimized HXT mesh/quality isolation diagnostic."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import re
from pathlib import Path

import tcad_cps_mesh_probe as parent
from archive_tcad_cps_mesh_probe_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
BASE = Path("results/tcad/cps_hxt_isolation_v1")
PROTOCOL = Path("protocols/tcad_cps_hxt_isolation_v1.json")
LOCK = Path("protocols/tcad_cps_hxt_isolation_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_hxt_isolation.sh"
SOURCES = ["code/experiments/proofs/archive_tcad_cps_mesh_probe_v1.py",
           "tests/test_tcad_cps_mesh_probe_archive.py",
           "code/experiments/proofs/tcad_cps_hxt_isolation.py",
           "code/experiments/proofs/run_tcad_cps_hxt_isolation.py",
           "code/solvers/tcad_cps_hxt_isolation_worker.py",
           "tests/test_tcad_cps_hxt_isolation.py", WRAPPER]
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
mode_input = parent.mode_input
expected_policy = parent.expected_policy
bounded = parent.bounded


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("HXT-isolation parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"], hxt_isolation=cfg)
    p["mesh"]["gmsh_options"].update(cfg["candidate_mesh_options"])
    allocation = p["resources"].pop("mesh_probe")
    p["resources"]["hxt_isolation"] = allocation
    return p


def assess_quality(quality, result, p):
    try:
        cfg = p["hxt_isolation"]["quality"]
        if quality["schema"] != cfg["schema"] or quality["metrics"] != cfg["metrics"] or quality["metric_units"] != cfg["metric_units"]:
            return False
        if quality["quantile_probabilities"] != cfg["quantile_probabilities"] or quality["quantile_method"] != cfg["quantile_method"]:
            return False
        if not re.fullmatch(r"[a-f0-9]{64}", quality["arrays_sha256"]) or set(quality["regions"]) != set(result["region_tetrahedra"]):
            return False
        if quality["element_count"] != result["mesh_tetrahedra"] or type(quality["element_count"]) is not int:
            return False
        for region, count in result["region_tetrahedra"].items():
            values = quality["regions"][region]
            if type(values["count"]) is not int or values["count"] != count or count <= 0:
                return False
            for metric in cfg["metrics"]:
                stats = values[metric]
                if any(type(stats[k]) is not int for k in ("finite_count", "nonpositive_count")) or stats["finite_count"] != count or stats["nonpositive_count"] != 0:
                    return False
                quantiles = stats["quantiles"]
                if len(quantiles) != len(cfg["quantile_probabilities"]) or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in quantiles):
                    return False
                if quantiles != sorted(quantiles) or (metric == "minSICN" and quantiles[-1] > cfg["sicn_max"]):
                    return False
            bins = values["sicn_below_threshold"]
            if set(bins) != {str(t) for t in cfg["sicn_diagnostic_thresholds"]}:
                return False
            counts = [bins[str(t)] for t in cfg["sicn_diagnostic_thresholds"]]
            if any(type(v) is not int or not 0 <= v <= count for v in counts) or counts != sorted(counts):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def assess_result(result, mode, p):
    return (parent.assess_result(result, mode, p) and result.get("numerical_quality_qualified") is False
            and assess_quality(result.get("mesh_quality", {}), result, p))


def assessment(record, p):
    previous = parent.assessment(record, p)
    complete = previous["complete"] and all(assess_result(r.get("result", {}), mode, p) for mode, r in record["modes"].items())
    repeat = False
    if complete:
        a, b = (record["modes"][m]["result"]["mesh_quality"] for m in ("local1", "repeat1"))
        repeat = previous["repeatability_passed"] and sha256_json(a) == sha256_json(b)
    return {"complete": bool(complete), "repeatability_passed": bool(repeat), "diagnostic_passed": bool(complete and repeat),
            "mesh_feasible": False, "numerical_quality_qualified": False, "field_solver_executed": False,
            "reference_qualified": False, "training_may_start": False, "claim_eligible": False,
            "automatic_expansion": False, "terminal_admission_pending": True}


def frozen_lock():
    parent.check_source(execution=False)
    archive = check_archive()
    paths = set(parent.frozen_lock()["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-hxt-isolation-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("HXT-isolation source/input lock mismatch")
    if execution:
        command = parent.parent.support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("HXT-isolation execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("HXT-isolation external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != "hxt_isolation" or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("HXT-isolation executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked HXT-isolation dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / parent.parent.PANEL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{parent.parent.support.original.job_number(job)}"
    for ancestor in [path, *path.parents]:
        if ancestor == ROOT:
            break
        if ancestor.is_symlink():
            raise ValueError("symlink in HXT-isolation attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace HXT-isolation source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
