"""Source-bound explicit Gmsh post-optimization diagnostic; stdlib only."""
from __future__ import annotations
import argparse
import copy
import json
import math
import os
import re
from pathlib import Path

import tcad_cps_mesh_probe as parent
import tcad_cps_hxt_isolation as predecessor
from archive_tcad_cps_hxt_isolation_v1 import MANIFEST as ARCHIVE, check_archive
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
BASE = Path("results/tcad/cps_hxt_postopt_v1")
PROTOCOL = Path("protocols/tcad_cps_hxt_postopt_v1.json")
LOCK = Path("protocols/tcad_cps_hxt_postopt_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_hxt_postopt.sh"
SOURCES = ["code/experiments/proofs/archive_tcad_cps_hxt_isolation_v1.py",
           "tests/test_tcad_cps_hxt_isolation_archive.py",
           "code/experiments/proofs/tcad_cps_hxt_postopt.py",
           "code/experiments/proofs/run_tcad_cps_hxt_postopt.py",
           "code/solvers/tcad_cps_hxt_postopt_worker.py",
           "code/solvers/tcad_cps_hxt_postopt_mesh.py",
           "tests/test_tcad_cps_hxt_postopt.py", WRAPPER]
STAGES = parent.STAGES[:3] + ["raw_mesh_generated", "mesh_optimize_started", "mesh_optimize_finished"] + parent.STAGES[3:]
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
mode_input = parent.mode_input
expected_policy = parent.expected_policy
bounded = parent.bounded
assess_quality = predecessor.assess_quality


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / predecessor.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("HXT-postopt parent/archive identity mismatch")
    p = copy.deepcopy(predecessor.protocol())
    p.update(schema=cfg["schema"], protocol_name=cfg["protocol_name"], scope=cfg["scope"], hxt_postopt=cfg)
    p["mesh"]["gmsh_options"].update(cfg["candidate_mesh_options"])
    p["resources"]["hxt_postopt"] = p["resources"].pop("hxt_isolation")
    return p


def quality_counts(q):
    return {"mesh_tetrahedra": q["element_count"],
            "region_tetrahedra": {k: v["count"] for k, v in q["regions"].items()}}


def valid_observation(q, p, limits):
    """Validate pre-optimization structure, not signed positivity or accuracy."""
    try:
        cfg = p["hxt_isolation"]["quality"]
        for key in ("schema", "metrics", "metric_units", "quantile_probabilities", "quantile_method"):
            if q[key] != cfg[key]:
                return False
        if not re.fullmatch(r"[a-f0-9]{64}", q["arrays_sha256"]):
            return False
        if type(q["element_count"]) is not int or not 0 < q["element_count"] <= limits["mesh_tetrahedra_max"]:
            return False
        if set(q["regions"]) != {"dielectric", "primary", "secondary"}:
            return False
        if sum(v["count"] for v in q["regions"].values()) != q["element_count"]:
            return False
        for region in q["regions"].values():
            count = region["count"]
            if type(count) is not int or count <= 0:
                return False
            for metric in cfg["metrics"]:
                stats = region[metric]
                if any(type(stats[k]) is not int or not 0 <= stats[k] <= count for k in ("finite_count", "nonpositive_count")):
                    return False
                values = stats["quantiles"]
                if len(values) != len(cfg["quantile_probabilities"]):
                    return False
                if not stats["finite_count"]:
                    if any(v is not None for v in values):
                        return False
                elif any(type(v) not in (float, int) or not math.isfinite(v) for v in values) or values != sorted(values):
                    return False
            bins = region["sicn_below_threshold"]
            if set(bins) != {str(t) for t in cfg["sicn_diagnostic_thresholds"]}:
                return False
            counts = [bins[str(t)] for t in cfg["sicn_diagnostic_thresholds"]]
            if any(type(v) is not int or not 0 <= v <= count for v in counts) or counts != sorted(counts):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def assess_result(result, mode, p):
    try:
        # The inherited checker owns unchanged geometry/policy/resource fields.
        inherited = {**result, "stages": parent.STAGES}
        pre = result["quality_before"]
        limits = p["worker_limits"][mode]
        return bool(parent.assess_result(inherited, mode, p)
            and result["stages"] == STAGES and result["numerical_quality_qualified"] is False
            and valid_observation(pre, p, limits)
            and type(result["nodes_before"]) is int and 0 < result["nodes_before"] <= limits["mesh_nodes_max"]
            and result["quality_before_passed"] is assess_quality(pre, quality_counts(pre), p)
            and assess_quality(result["mesh_quality"], result, p)
            and sha256_json(result["optimizer"]) == sha256_json(p["hxt_postopt"]["optimizer"])
            and type(result["optimizer_calls"]) is int and result["optimizer_calls"] == p["hxt_postopt"]["optimizer_calls"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def assessment(record, p):
    modes = p["hxt_postopt"]["modes"]
    observed = record.get("modes", {})
    complete = (record.get("failure") is None and set(observed) == set(modes)
                and all(observed[m].get("passed") is True and assess_result(observed[m].get("result", {}), m, p) for m in modes))
    repeat = False
    if complete:
        a, b = (observed[m]["result"] for m in ("local1", "repeat1"))
        repeat = all(sha256_json(a[k]) == sha256_json(b[k]) for k in (
            "mesh_sha256", "mesh_nodes", "mesh_tetrahedra", "region_tetrahedra", "mesh_policy_sha256",
            "quality_before", "nodes_before", "quality_before_passed", "mesh_quality", "optimizer", "optimizer_calls"))
    return {"complete": bool(complete), "repeatability_passed": bool(repeat), "diagnostic_passed": bool(complete and repeat),
            "mesh_feasible": False, "numerical_quality_qualified": False, "field_solver_executed": False,
            "reference_qualified": False, "training_may_start": False, "claim_eligible": False,
            "automatic_expansion": False, "terminal_admission_pending": True}


def frozen_lock():
    # The archive checker invokes the immutable predecessor source/receipt validator.
    archive = check_archive()
    paths = set(read_json(ROOT / predecessor.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(predecessor.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-hxt-postopt-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("HXT-postopt source/input lock mismatch")
    if execution:
        command = parent.parent.support.original.command
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("HXT-postopt execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("HXT-postopt external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != "hxt_postopt" or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("HXT-postopt executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked HXT-postopt dependency")
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
            raise ValueError("symlink in HXT-postopt attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace HXT-postopt source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
