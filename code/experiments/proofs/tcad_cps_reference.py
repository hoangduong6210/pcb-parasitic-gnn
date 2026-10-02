"""Stdlib-only contracts for the separately versioned TCAD reference pilot."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import re
import socket
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))
from scientific_artifact import atomic_write_json, sha256_file

BASE = Path("results/tcad/cps_reference_v1")
PROTOCOL = Path("protocols/tcad_cps_reference_v1.json")
PANEL = BASE / "plan/panel.json"
LOCK = Path("protocols/tcad_cps_reference_v1.lock.json")
SOURCES = [
    "code/core/geometry_contract.py", "code/core/scientific_artifact.py",
    "code/data/verified_geometry_corpus.py", "code/solvers/fem_capacitance_3d.py",
    "code/solvers/tcad_cps_reference_worker.py",
    "code/experiments/proofs/plan_tcad_cps_reference.py",
    "code/experiments/proofs/tcad_cps_reference.py",
    "code/experiments/proofs/run_tcad_cps_reference.py",
    "code/env.sh", "code/jobs/slurm_job_env.sh",
    "code/jobs/tcad_cps_reference_env.sh",
    "code/jobs/submit_tcad_cps_reference_smoke.sh",
    "code/jobs/submit_tcad_cps_reference_pilot.sh",
    "code/jobs/submit_finalize_tcad_cps_reference.sh",
    "tests/test_tcad_cps_reference.py",
]


def read_json(path: Path):
    def invalid(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    return json.loads(path.read_text(), parse_constant=invalid)


def command(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, timeout=30).strip()


def frozen_lock() -> dict:
    paths = SOURCES + [str(PROTOCOL), str(PANEL),
                       "datasets/corpus_v3/summary.json", "datasets/corpus_v3/layouts.jsonl"]
    return {"schema": "pcb-gnn.tcad-cps-reference-lock.v1",
            "files_sha256": {p: sha256_file(ROOT / p) for p in sorted(paths)}}


def check_source(*, execution: bool = True) -> dict:
    lock = read_json(ROOT / LOCK)
    if lock != frozen_lock():
        raise ValueError("source/input bytes differ from the frozen lock")
    if execution:
        if Path(os.environ["PCB_TCAD_EXECUTION_ROOT"]).resolve() != ROOT:
            raise ValueError("execution-root mismatch")
        if command(["git", "rev-parse", "HEAD"]) != os.environ["PCB_TCAD_SOURCE_COMMIT"]:
            raise ValueError("execution commit mismatch")
        if sha256_file(ROOT / LOCK) != os.environ["PCB_TCAD_LOCK_SHA256"]:
            raise ValueError("externally pinned lock mismatch")
        phase = os.environ["PCB_TCAD_BATCH_PHASE"]
        wrapper = "submit_finalize_tcad_cps_reference.sh" if phase == "finalize" else f"submit_tcad_cps_reference_{phase}.sh"
        if sha256_file(Path(os.environ["PCB_TCAD_EXECUTED_BATCH_SCRIPT"])) != sha256_file(ROOT / "code/jobs" / wrapper):
            raise ValueError("executed batch script differs from frozen wrapper")
        command(["git", "diff", "--exit-code", "HEAD", "--"])
        tracked = set(command(["git", "ls-files"]).splitlines())
        if not set(lock["files_sha256"]).union({str(LOCK)}).issubset(tracked):
            raise ValueError("untracked execution dependency")
    return lock


def check_runtime(protocol: dict) -> dict:
    expected = protocol["runtime"]
    packages = {name: importlib.metadata.version(name) for name in expected["packages"]}
    threads = {name: os.environ.get(name) for name in expected["thread_environment"]}
    if platform.python_version() != expected["python"] or packages != expected["packages"]:
        raise ValueError("runtime versions differ from protocol")
    if threads != expected["thread_environment"]:
        raise ValueError("numerical thread environment differs from protocol")
    return {"python": platform.python_version(), "packages": packages, "threads": threads}


def fields(output: str) -> list[dict]:
    return [dict(token.split("=", 1) for token in line.split() if "=" in token)
            for line in output.splitlines() if line.strip()]


def allocation_matches(record: dict, env: dict, hostname: str, phase: str, protocol: dict) -> bool:
    """Check actual host, scheduler identity and requested versus allocated CPUs."""
    profile = protocol["resources"][phase]
    tres = lambda name: dict(s.split("=", 1) for s in record.get(name, "").split(",") if "=" in s)
    try:
        allocated = int(env["SLURM_CPUS_PER_TASK"])
        host = hostname.split(".")[0]
        valid = (
            record["JobId"] == env["SLURM_JOB_ID"]
            and record["UserId"].endswith(f"({os.getuid()})")
            and record["JobState"] == "RUNNING"
            and record["Account"] == profile["account"]
            and record["Partition"] == profile["partition"]
            and record["TimeLimit"] == profile["time_limit"]
            and record["Requeue"] == "0" and record.get("Restarts", "0") == "0"
            and record["NumNodes"] == "1" and record["NumTasks"] == "1"
            and host == record["NodeList"] == record["BatchHost"] == env["SLURMD_NODENAME"]
            and allocated >= profile["cpus_per_task"]
            and int(record["NumCPUs"]) == int(record["CPUs/Task"]) == allocated
            and tres("ReqTRES").get("cpu") == str(profile["cpus_per_task"])
            and tres("TresPerTask").get("cpu") == str(profile["cpus_per_task"])
            and tres("AllocTRES").get("cpu") == str(allocated)
            and tres("ReqTRES").get("mem") == tres("AllocTRES").get("mem") == f'{profile["mem_gib"]}G'
            and record["MinMemoryNode"] == f'{profile["mem_gib"]}G'
            and int(env["SLURM_MEM_PER_NODE"]) == profile["mem_gib"] * 1024
        )
        if phase == "pilot":
            valid = valid and (
                record["ArrayJobId"] == env["SLURM_ARRAY_JOB_ID"]
                and record["ArrayTaskId"] == env["SLURM_ARRAY_TASK_ID"]
                and 0 <= int(record["ArrayTaskId"]) < profile["array_count"]
                and int(env["SLURM_ARRAY_TASK_COUNT"]) == profile["array_count"]
                and env["SLURM_ARRAY_TASK_MIN"] == "0"
                and int(env["SLURM_ARRAY_TASK_MAX"]) == profile["array_count"] - 1
            )
        else:
            valid = valid and not record.get("ArrayJobId")
        return bool(valid)
    except (KeyError, TypeError, ValueError):
        return False


def check_allocation(phase: str, protocol: dict) -> dict:
    if os.environ.get("PCB_TCAD_BATCH_PHASE") != phase:
        raise ValueError("phase differs from the submitted batch wrapper")
    job_id = os.environ.get("SLURM_JOB_ID", "")
    if not re.fullmatch(r"[0-9]+", job_id):
        raise ValueError("active SLURM allocation required; login-node execution prohibited")
    records = fields(command(["scontrol", "show", "job", "-o", job_id]))
    matching = [r for r in records if allocation_matches(r, os.environ, socket.gethostname(), phase, protocol)]
    if len(matching) != 1:
        raise ValueError("active compute-node SLURM contract missing or ambiguous")
    return matching[0]


def job_number(value: str) -> str:
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("invalid scheduler ID")
    return value


def attempt_directory(phase: str, job_id: str, task: str | None = None, *, create=False) -> Path:
    path = ROOT / BASE / phase / f"job_{job_number(job_id)}"
    if task is not None:
        path = path / f"task_{job_number(task)}"
    # Refuse symlinks, including a symlinked ancestor of the result directory.
    for parent in [path, *path.parents]:
        if parent == ROOT:
            break
        if parent.is_symlink():
            raise ValueError("symlink in attempt path")
    if create:
        path.mkdir(parents=True, exist_ok=False)
    return path


def identity() -> dict:
    return {"source_commit": os.environ["PCB_TCAD_SOURCE_COMMIT"],
            "lock_sha256": os.environ["PCB_TCAD_LOCK_SHA256"],
            "protocol_sha256": sha256_file(ROOT / PROTOCOL),
            "panel_sha256": sha256_file(ROOT / PANEL)}


def positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def assess_result(result: dict, protocol: dict, phase: str) -> bool:
    limits, gates = protocol["resources"][phase], protocol["gates"]
    residual = result.get("relative_residual")
    valid = (positive(result.get("cps_pf"))
             and isinstance(residual, (int, float)) and math.isfinite(residual)
             and 0 <= residual <= gates["relative_residual_max"]
             and bool(re.fullmatch(r"[a-f0-9]{64}", result.get("system_sha256", ""))))
    for key, maximum in (("mesh_nodes", "mesh_nodes_max"), ("mesh_tetrahedra", "mesh_tetrahedra_max"),
                         ("operator_complexity", "operator_complexity_max"), ("peak_rss_gib", "rss_gib_max")):
        valid = valid and positive(result.get(key)) and result[key] <= limits[maximum]
    if phase == "smoke":
        other = result.get("comparison", {})
        valid = valid and positive(other.get("cps_pf")) and other.get("system_sha256") == result.get("system_sha256")
        valid = valid and abs(result["cps_pf"] - other["cps_pf"]) / abs(other["cps_pf"]) <= gates["smoke_backend_relative_max"]
    return bool(valid)


def sensitivity_summary(tasks: list[dict], protocol: dict) -> dict:
    """Incomplete/failed coverage never becomes a numerical pass."""
    names = [a["name"] for a in protocol["pilot_arms"]]
    complete = len(tasks) == protocol["selection"]["pilot_size"] and all(
        t.get("passed") is True and set(t.get("arms", {})) == set(names)
        and all(assess_result(t["arms"][n]["result"], protocol, "pilot") for n in names)
        for t in tasks)
    output = {"complete": complete, "pilot_passed": False, "comparisons": {},
              "claim_eligible": False, "training_may_start": False,
              "continuum_convergence_established": False}
    if not complete:
        return output
    gates = protocol["gates"]
    for name, candidate, reference in (("mesh", "local1", "local2"), ("padding", "pad20", "local2"),
                                        ("far_field", "far2", "local2"), ("coarse_mesh_descriptive", "local0", "local1")):
        values = [100 * abs(t["arms"][candidate]["result"]["cps_pf"] - t["arms"][reference]["result"]["cps_pf"])
                  / abs(t["arms"][reference]["result"]["cps_pf"]) for t in tasks]
        output["comparisons"][name] = {"per_layout_pct": values, "median_pct": statistics.median(values),
                                        "max_pct": max(values), "passed": statistics.median(values) <= gates["sensitivity_median_pct_max"] and max(values) <= gates["sensitivity_max_pct_max"]}
    repeats = []
    for t in tasks:
        a, b = (t["arms"][n]["result"] for n in ("local2", "repeat2"))
        repeats.append(abs(a["cps_pf"] - b["cps_pf"]) / abs(a["cps_pf"]) <= gates["repeatability_relative_max"]
                       and all(a[k] == b[k] for k in ("system_sha256", "mesh_nodes", "mesh_tetrahedra")))
    output["repeatability_passed"] = all(repeats)
    output["pilot_passed"] = all(repeats) and all(output["comparisons"][n]["passed"] for n in ("mesh", "padding", "far_field"))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    args = parser.parse_args()
    if args.freeze_lock:
        if (ROOT / LOCK).exists():
            raise SystemExit("refusing to replace an execution lock")
        atomic_write_json(ROOT / LOCK, frozen_lock())
    else:
        check_source(execution=False)
    print(json.dumps({"lock_sha256": sha256_file(ROOT / LOCK), "execution": False}))
