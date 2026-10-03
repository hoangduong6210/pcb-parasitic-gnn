"""Additive support-recovery contracts; the original pilot closure is immutable."""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_reference as original
from archive_tcad_cps_pilot_v1 import MANIFEST as ARCHIVE
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = original.ROOT
BASE = Path("results/tcad/cps_support_recovery_v1")
PROTOCOL = Path("protocols/tcad_cps_support_recovery_v1.json")
LOCK = Path("protocols/tcad_cps_support_recovery_v1.lock.json")
PANEL = original.PANEL
WRAPPERS = {p: f"code/jobs/submit_tcad_cps_support_{p}.sh" for p in ("smoke", "feasibility", "finalize")}
SOURCES = ["code/experiments/proofs/archive_tcad_cps_pilot_v1.py",
           "code/experiments/proofs/tcad_cps_support_recovery.py",
           "code/experiments/proofs/run_tcad_cps_support_recovery.py",
           "code/solvers/tcad_cps_support_worker.py", "tests/test_tcad_cps_support_recovery.py",
           *WRAPPERS.values()]
read_json = original.read_json
check_allocation = original.check_allocation
check_runtime = original.check_runtime
assess_result = original.assess_result


def protocol() -> dict:
    cfg = read_json(ROOT / PROTOCOL)
    for path, expected in ((original.PROTOCOL, cfg["parent_protocol_sha256"]),
                           (PANEL, cfg["panel_sha256"]), (ARCHIVE, cfg["archive_sha256"])):
        if sha256_file(ROOT / path) != expected:
            raise ValueError("recovery parent/panel/archive identity mismatch")
    p = copy.deepcopy(read_json(ROOT / original.PROTOCOL))
    p["schema"], p["protocol_name"] = cfg["schema"], cfg["protocol_name"]
    p["scope"] = cfg["scope"]
    p["mesh"].update(cfg["compact_support"])
    p["resources"]["feasibility"] = p["resources"].pop("pilot")
    for key in ("array_count", "array_throttle"):
        p["resources"]["feasibility"].pop(key)
    p["recovery"] = cfg
    p.pop("pilot_arms")
    p["smoke"]["arm"]["support"] = "compact"
    return p


def arm_protocol(p: dict, arm: dict) -> dict:
    out = copy.deepcopy(p)
    if arm["support"] not in ("compact", "wide"):
        raise ValueError("unknown support policy")
    out["mesh"].update(p["recovery"][arm["support"] + "_support"])
    return out


def target(p: dict) -> dict:
    rows = read_json(ROOT / PANEL)["rows"]
    matches = [r for r in rows if r["layout_id"] == p["recovery"]["layout_id"]
               and r["geometry_sha256"] == p["recovery"]["geometry_sha256"]]
    if len(matches) != 1:
        raise ValueError("recovery target missing or ambiguous")
    return matches[0]


def frozen_lock() -> dict:
    original.check_source(execution=False)
    p = protocol()
    archive = read_json(ROOT / ARCHIVE)
    paths = set(original.frozen_lock()["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(original.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.tcad-cps-support-recovery-lock.v1", "effective_protocol_sha256": sha256_json(p),
            "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("recovery source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT:
            raise ValueError("recovery execution-root mismatch")
        if original.command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("recovery commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("recovery external lock mismatch")
        wrapper = WRAPPERS[os.environ["PCB_TCAD_BATCH_PHASE"]]
        if sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / wrapper):
            raise ValueError("recovery batch wrapper mismatch")
        original.command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(original.command(["git", "ls-files"]).splitlines())
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(tracked):
            raise ValueError("untracked recovery execution dependency")
    return lock


def identity() -> dict:
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"],
            "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL), "panel_sha256": sha256_file(ROOT / PANEL)}


def attempt_directory(phase: str, job_id: str, *, create=False) -> Path:
    if phase not in WRAPPERS:
        raise ValueError("unknown recovery phase")
    path = ROOT / BASE / phase / f"job_{original.job_number(job_id)}"
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise ValueError("symlink in recovery attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assess_feasibility(record: dict, p: dict) -> dict:
    expected = {a["name"]: a for a in p["recovery"]["recovery_arms"]}
    complete = record.get("passed") is True and record.get("layout_id") == p["recovery"]["layout_id"]
    complete = complete and set(record.get("arms", {})) == set(expected)
    if complete:
        complete = all(a["passed"] is True and a["arm"] == expected[name]
                       and assess_result(a["result"], p, "feasibility") for name, a in record["arms"].items())
    out = {"complete": bool(complete), "feasibility_passed": False, "comparisons": {},
           "three_sentinel_qualification": False, "claim_eligible": False,
           "training_may_start": False, "automatic_expansion": False,
           "continuum_convergence_established": False}
    if not complete:
        return out
    arms = {n: a["result"] for n, a in record["arms"].items()}
    for name, candidate, reference in (("mesh", "local1", "local2"), ("padding", "pad20", "local2"),
                                      ("far_field", "far2", "local2"), ("support_at_level1", "support1", "local1")):
        difference = 100 * abs(arms[candidate]["cps_pf"] - arms[reference]["cps_pf"]) / abs(arms[reference]["cps_pf"])
        out["comparisons"][name] = {"relative_difference_pct": difference,
                                     "passed": difference <= p["recovery"]["feasibility_sensitivity_pct_max"]}
    a, b = arms["local2"], arms["repeat2"]
    out["repeatability_passed"] = (all(a[k] == b[k] for k in ("system_sha256", "mesh_nodes", "mesh_tetrahedra"))
                                    and abs(a["cps_pf"] - b["cps_pf"]) / abs(a["cps_pf"]) <= p["gates"]["repeatability_relative_max"])
    out["feasibility_passed"] = out["repeatability_passed"] and all(c["passed"] for c in out["comparisons"].values())
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace recovery lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
