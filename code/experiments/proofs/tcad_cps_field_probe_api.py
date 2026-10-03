"""Frozen tiny synthetic native field-probe API contracts; stdlib only."""
import argparse
import copy
import json
import os
from pathlib import Path

import tcad_cps_edge_feasibility as parent
from archive_tcad_cps_edge_feasibility_v1 import MANIFEST as ARCHIVE, check_archive
from tcad_cps_reference import command, job_number
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = parent.ROOT
PHASE = "field_probe_api"
BASE = Path("results/tcad/cps_field_probe_api_v1")
PROTOCOL = Path("protocols/tcad_cps_field_probe_api_v1.json")
LOCK = Path("protocols/tcad_cps_field_probe_api_v1.lock.json")
WRAPPER = "code/jobs/submit_tcad_cps_field_probe_api.sh"
WORKER = "code/solvers/tcad_cps_field_probe_worker.py"
SOURCES = ["code/experiments/proofs/tcad_cps_field_probe_api.py",
    "code/experiments/proofs/run_tcad_cps_field_probe_api.py",
    "code/experiments/proofs/archive_tcad_cps_edge_feasibility_v1.py", WORKER, WRAPPER,
    "code/solvers/tcad_cps_model_field_probe.py",
    "tests/test_tcad_cps_model_field_probe.py", "tests/test_tcad_cps_field_probe_api.py"]
CLOSED = (*parent.CLOSED, "planar_mesh_generated", "native_mesh_generation_called")
read_json = parent.read_json
check_allocation = parent.check_allocation
check_runtime = parent.check_runtime
bounded = parent.bounded


def protocol():
    cfg = read_json(ROOT / PROTOCOL)
    if sha256_file(ROOT / parent.PROTOCOL) != cfg["parent_protocol_sha256"] or sha256_file(ROOT / ARCHIVE) != cfg["terminal_archive_sha256"]:
        raise ValueError("field probe API parent/archive identity mismatch")
    p = copy.deepcopy(parent.protocol())
    if (cfg["schema"] != "pcb-gnn.field-probe-api.v1" or cfg["report_bytes_max"] != 2097152 or cfg["fixture_points_max"] != 512
            or cfg["modes"] != ["probe","repeat"] or cfg["worker_timeout_s"] != 180 or cfg["rss_gib_max"] != 2
            or cfg["automatic_retries"] != 0 or cfg["automatic_expansion"] is not False
            or cfg["resources"] != {"account":"pgs0407","partition":"nextgen","cpus_per_task":1,"mem_gib":8,"time_limit":"00:10:00"}
            or cfg["synthetic_probe_elements_only"] is not True or any(cfg[k] is not False for k in CLOSED)
            or cfg["fixture"] != {"boxes_mm":[[1.,2.,1.,2.,1.,2.],[1.,2.,1.,2.,3.,4.],[1.0000000000000002,2.,1.,2.,4.5,5.]],
                "domain_mm":[0.,3.,0.,3.,0.,6.]}
            or cfg["policy"] != {"near_size_mm":.12,"far_size_mm":1.,"face_band_half_width_mm":.055,"pad_mm":2.}):
        raise ValueError("field probe API frozen synthetic definition differs")
    p[PHASE] = cfg
    p["resources"] = {PHASE:cfg["resources"]}
    p["worker_limits"] = {m:{"worker_timeout_s":cfg["worker_timeout_s"],"rss_gib_max":cfg["rss_gib_max"]} for m in cfg["modes"]}
    return p


def probe_config(p):
    return p[parent.PHASE]



def frozen_lock():
    archive = check_archive()
    paths = set(read_json(ROOT / parent.LOCK)["files_sha256"]) | set(archive["files_sha256"])
    paths.update(SOURCES + [str(parent.LOCK), str(PROTOCOL), str(ARCHIVE)])
    return {"schema": "pcb-gnn.field-probe-api-lock.v1", "effective_protocol_sha256": sha256_json(protocol()),
        "files_sha256": {path: sha256_file(ROOT / path) for path in sorted(paths)}}


def check_source(*, execution=True):
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("field probe source/input lock mismatch")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT or command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("field probe execution root/commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("field probe external lock mismatch")
        if os.environ.get("PCB_TCAD_BATCH_PHASE") != PHASE or sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / WRAPPER):
            raise ValueError("field probe executed wrapper mismatch")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        if not (set(lock["files_sha256"]) | {str(LOCK)}).issubset(set(command(["git", "ls-files"]).splitlines())):
            raise ValueError("untracked field probe dependency")
    return lock


def identity():
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"], "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
        "protocol_sha256": sha256_file(ROOT / PROTOCOL)}


def attempt_directory(job, *, create=False):
    path = ROOT / BASE / f"job_{job_number(job)}"
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in field probe attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def assessment(record, p):
    modes = record.get("modes", {})
    complete = record.get("failure") is None and set(modes) == set(p[PHASE]["modes"]) and all(v.get("passed") is True for v in modes.values())
    repeat = bool(complete and modes["probe"]["result"]["report_sha256"] == modes["repeat"]["result"]["report_sha256"])
    return {"complete":bool(complete),"repeatability_passed":repeat,"diagnostic_passed":bool(complete and repeat),
        "synthetic_probe_elements_only":True, **{k:False for k in CLOSED}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace field probe source lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
