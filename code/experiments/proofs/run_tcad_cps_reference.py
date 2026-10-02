#!/usr/bin/env python3
"""Guarded smoke, bounded three-sentinel pilot and terminal evidence finalizer."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tcad_cps_reference import (ROOT, PANEL, PROTOCOL, assess_result, attempt_directory,
    check_allocation, check_runtime, check_source, command, identity, job_number,
    read_json, sensitivity_summary)
from scientific_artifact import atomic_write_json, sha256_file


def rss_gib(pid: int) -> float:
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
        return max((int(line.split()[1]) / 1024**2 for line in lines
                    if line.startswith(("VmRSS:", "VmHWM:"))), default=0.0)
    except FileNotFoundError:
        return 0.0


def result_from_log(path: Path) -> dict:
    lines = [line[7:] for line in path.read_text().splitlines() if line.startswith("RESULT=")]
    if len(lines) != 1:
        raise ValueError("expected exactly one terminal worker result")
    def invalid(value):
        raise ValueError(f"nonfinite worker JSON: {value}")
    return json.loads(lines[0], parse_constant=invalid)


def bounded_arm(directory: Path, phase: str, arm: dict, protocol: dict) -> dict:
    limits = protocol["resources"][phase]
    out, err = directory / f'{arm["name"]}.stdout', directory / f'{arm["name"]}.stderr'
    started, peak, failure = time.monotonic(), 0.0, None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, str(ROOT / "code/solvers/tcad_cps_reference_worker.py"),
                                    "--phase", phase, "--arm", arm["name"]],
                                   cwd=directory, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while process.poll() is None:
                peak = max(peak, rss_gib(process.pid))
                if time.monotonic() - started > limits["worker_timeout_s"]:
                    failure = "worker wall-time cap exceeded"
                    break
                if peak > limits["rss_gib_max"]:
                    failure = "worker RSS cap exceeded"
                    break
                time.sleep(0.5)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    record = {"arm": arm, "returncode": process.returncode, "elapsed_s": time.monotonic() - started,
              "observed_peak_rss_gib": peak, "failure": failure, "passed": False,
              "files_sha256": {p.name: sha256_file(p) for p in (out, err)}}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            if result["arm"] != arm or any(result.get(k) != v for k, v in identity().items()):
                raise ValueError("worker provenance/arm mismatch")
            record["result"] = result
            record["passed"] = assess_result(result, protocol, phase)
            if not record["passed"]:
                record["failure"] = "worker result rejected"
        except (KeyError, ValueError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr"
    atomic_write_json(directory / f'{arm["name"]}.json', record)
    return record


def accounting(job_id: str) -> tuple[str, list[dict]]:
    columns = ["JobID", "State", "ExitCode", "Restarts", "ElapsedRaw", "AllocCPUS", "ReqMem", "NodeList"]
    raw = command(["sacct", "-X", "-n", "-P", "-j", job_number(job_id), "--format=" + ",".join(columns)])
    rows = [dict(zip(columns, line.split("|"))) for line in raw.splitlines() if line.strip()]
    return raw, rows


def terminal_success(rows: list[dict], identifier: str) -> bool:
    matches = [r for r in rows if r["JobID"] == identifier]
    return len(matches) == 1 and all(matches[0][key] == val for key, val in
                                    (("State", "COMPLETED"), ("ExitCode", "0:0"), ("Restarts", "0")))


def validate_attempt(directory: Path, phase: str, protocol: dict) -> dict:
    record = read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in identity().items()) or record["phase"] != phase:
        raise ValueError("attempt source/phase binding mismatch")
    for name, arm in record["arms"].items():
        if arm != read_json(directory / f"{name}.json"):
            raise ValueError("arm receipt mismatch")
        if set(arm["files_sha256"]) != {f"{name}.stdout", f"{name}.stderr"}:
            raise ValueError("unexpected arm log closure")
        for filename, digest in arm["files_sha256"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("worker-log hash mismatch")
        if arm["passed"] and (result_from_log(directory / f"{name}.stdout") != arm["result"]
                              or not assess_result(arm["result"], protocol, phase)):
            raise ValueError("worker result does not reconstruct from log")
    return record


def accepted_smoke(protocol: dict) -> dict:
    job_id = job_number(os.environ["PCB_TCAD_SMOKE_JOB_ID"])
    directory = attempt_directory("smoke", job_id)
    record = validate_attempt(directory, "smoke", protocol)
    _, rows = accounting(job_id)
    if not terminal_success(rows, job_id) or not record["passed"] or set(record["arms"]) != {"smoke"}:
        raise ValueError("a terminal validated smoke job is required")
    return {"job_id": job_id, "attempt_sha256": sha256_file(directory / "attempt.json"), "accounting": rows}


def run_phase(phase: str, protocol: dict, scheduler: dict, runtime: dict) -> bool:
    pilot = phase == "pilot"
    task = os.environ["SLURM_ARRAY_TASK_ID"] if pilot else None
    job_id = os.environ["SLURM_ARRAY_JOB_ID" if pilot else "SLURM_JOB_ID"]
    directory = attempt_directory(phase, job_id, task, create=True)
    record = {**identity(), "phase": phase, "scheduler": scheduler, "runtime": runtime,
              "arms": {}, "passed": False, "all_attempts_retained": True}
    if pilot:
        record["smoke"] = accepted_smoke(protocol)
        panel = read_json(ROOT / PANEL)
        record["layout_id"] = panel["pilot_layout_ids"][int(task)]
        arms = protocol["pilot_arms"]
    else:
        arms = [protocol["smoke"]["arm"]]
    atomic_write_json(directory / "attempt.json", record)
    for arm in arms:
        check_source()
        record["arms"][arm["name"]] = bounded_arm(directory, phase, arm, protocol)
        atomic_write_json(directory / "attempt.json", record)
        if not record["arms"][arm["name"]]["passed"]:
            break
    check_source()
    record["passed"] = len(record["arms"]) == len(arms) and all(a["passed"] for a in record["arms"].values())
    atomic_write_json(directory / "attempt.json", record)
    print(json.dumps({"attempt": str(directory.relative_to(ROOT)), "passed": record["passed"]}))
    return record["passed"]


def finalize(protocol: dict, scheduler: dict, runtime: dict) -> bool:
    directory = attempt_directory("finalize", os.environ["SLURM_JOB_ID"], create=True)
    array_id = job_number(os.environ["PCB_TCAD_PILOT_ARRAY_ID"])
    raw, rows = accounting(array_id)
    (directory / "sacct.txt").write_text(raw + "\n")
    tasks, errors, bindings = [], [], []
    panel = read_json(ROOT / PANEL)
    smoke = accepted_smoke(protocol)
    for i, layout_id in enumerate(panel["pilot_layout_ids"]):
        path = attempt_directory("pilot", array_id, str(i))
        try:
            record = validate_attempt(path, "pilot", protocol)
            if record["layout_id"] != layout_id or record["scheduler"]["ArrayTaskId"] != str(i) or record["scheduler"]["ArrayJobId"] != array_id:
                raise ValueError("task/geometry coverage mismatch")
            if record["smoke"]["attempt_sha256"] != smoke["attempt_sha256"]:
                raise ValueError("smoke prerequisite binding mismatch")
            if not terminal_success(rows, f"{array_id}_{i}"):
                raise ValueError("task did not complete with zero exit and restarts")
            expected = next(r for r in panel["rows"] if r["layout_id"] == layout_id)
            for name, arm in record["arms"].items():
                if arm["arm"] != next(a for a in protocol["pilot_arms"] if a["name"] == name):
                    raise ValueError("unfrozen arm in pilot result")
                if arm["passed"] and (arm["result"]["layout_id"] != layout_id or arm["result"]["geometry_sha256"] != expected["geometry_sha256"]):
                    raise ValueError("worker geometry binding mismatch")
            tasks.append(record)
            bindings.append({"task": i, "attempt_sha256": sha256_file(path / "attempt.json")})
        except (OSError, KeyError, ValueError, StopIteration) as exc:
            errors.append({"task": i, "error": str(exc)})
    summary = {**identity(), **sensitivity_summary(tasks, protocol), "scheduler": scheduler,
               "runtime": runtime, "pilot_array_id": array_id, "smoke": smoke,
               "attempt_bindings": bindings, "errors": errors, "accounting": rows,
               "accounting_sha256": sha256_file(directory / "sacct.txt")}
    check_source()
    atomic_write_json(directory / "summary.json", summary)
    print(json.dumps({"summary": str(directory.relative_to(ROOT) / "summary.json"),
                      "complete": summary["complete"], "pilot_passed": summary["pilot_passed"]}))
    # A complete negative numerical result is a valid finalized experiment.
    return summary["complete"] and not errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "pilot", "finalize"), required=True)
    args = parser.parse_args()
    protocol = read_json(ROOT / PROTOCOL)
    scheduler = check_allocation(args.phase, protocol)
    check_source()
    runtime = check_runtime(protocol)
    passed = finalize(protocol, scheduler, runtime) if args.phase == "finalize" else run_phase(args.phase, protocol, scheduler, runtime)
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
