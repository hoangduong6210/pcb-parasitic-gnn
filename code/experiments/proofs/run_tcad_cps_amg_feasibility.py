#!/usr/bin/env python3
"""Bounded smoke, seven fresh AMG arms and failure-retaining finalization."""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
import time

from tcad_cps_amg_feasibility import (ROOT, arms_for, assess_feasibility, assess_result,
    attempt_directory, check_allocation, check_runtime, check_source, identity, inputs, protocol, read_json)
from tcad_cps_reference import job_number
from run_tcad_cps_reference import accounting, result_from_log, rss_gib, terminal_success
from geometry_contract import geometry_sha256
from scientific_artifact import atomic_write_json, sha256_file, sha256_json


def expected_runtime(p):
    return {"python": p["runtime"]["python"], "packages": dict(p["runtime"]["packages"]),
            "threads": dict(p["runtime"]["thread_environment"])}


def validate_result(result, phase, arm, p, job):
    if result["arm"] != arm or any(result.get(k) != v for k, v in identity().items()):
        raise ValueError("AMG feasibility worker arm/source mismatch")
    layout_id, layout, expected_arm = inputs(phase, arm["name"], p)
    if arm != expected_arm or result["layout_id"] != layout_id or result["geometry_sha256"] != geometry_sha256(layout):
        raise ValueError("AMG feasibility worker geometry mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p):
        raise ValueError("AMG feasibility worker job/runtime mismatch")
    if result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"]) or not assess_result(result, p, phase):
        raise ValueError("AMG feasibility worker policy/numerical gate failed")


def bounded_arm(directory, phase, arm, p):
    limits = p["resources"][phase]
    out, err = directory / f'{arm["name"]}.stdout', directory / f'{arm["name"]}.stderr'
    started, peak, failure = time.monotonic(), 0.0, None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, str(ROOT / "code/solvers/tcad_cps_amg_feasibility_worker.py"),
                                    "--phase", phase, "--arm", arm["name"]],
                                   cwd=directory, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            while process.poll() is None:
                peak = max(peak, rss_gib(process.pid))
                if time.monotonic()-started > limits["worker_timeout_s"]:
                    failure = "worker wall-time cap exceeded"
                    break
                if peak > limits["rss_gib_max"]:
                    failure = "worker RSS cap exceeded"
                    break
                time.sleep(.5)
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
    elapsed = time.monotonic()-started
    if failure is None and elapsed > limits["worker_timeout_s"]:
        failure = "worker wall-time cap exceeded at exit"
    record = {"arm": arm, "returncode": process.returncode, "elapsed_s": elapsed,
              "observed_peak_rss_gib": peak, "failure": failure, "passed": False,
              "files_sha256": {f.name: sha256_file(f) for f in (out, err)}}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, phase, arm, p, os.environ["SLURM_JOB_ID"])
            record.update(result=result, passed=True)
        except (ValueError, KeyError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr"
    atomic_write_json(directory / f'{arm["name"]}.json', record)
    return record


def validate_attempt(directory, phase, p):
    record = read_json(directory / "attempt.json")
    if record["phase"] != phase or any(record.get(k) != v for k, v in identity().items()):
        raise ValueError("AMG feasibility attempt phase/source mismatch")
    job = job_number(record["scheduler"]["JobId"])
    if directory != attempt_directory(phase, job) or record["runtime"] != expected_runtime(p):
        raise ValueError("AMG feasibility attempt path/runtime mismatch")
    expected = {a["name"]: a for a in arms_for(phase, p)}
    prefix = list(expected)[:len(record["arms"])]
    if set(record["arms"]) != set(prefix) or any(not record["arms"][n]["passed"] for n in prefix[:-1]):
        raise ValueError("AMG feasibility arm sequence skipped a failure or arm")
    expected_id = "smoke" if phase == "smoke" else p["recovery"]["layout_id"]
    if record["layout_id"] != expected_id:
        raise ValueError("AMG feasibility attempt geometry mismatch")
    for name, arm in record["arms"].items():
        if arm != read_json(directory / f"{name}.json") or arm["arm"] != expected[name]:
            raise ValueError("AMG feasibility arm receipt mismatch")
        if set(arm["files_sha256"]) != {f"{name}.stdout", f"{name}.stderr"}:
            raise ValueError("AMG feasibility raw-log closure mismatch")
        for filename, digest in arm["files_sha256"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("AMG feasibility raw-log hash mismatch")
        if arm["passed"]:
            limits = p["resources"][phase]
            if arm["returncode"] != 0 or arm["failure"] is not None or arm["elapsed_s"] > limits["worker_timeout_s"] or arm["observed_peak_rss_gib"] > limits["rss_gib_max"]:
                raise ValueError("AMG feasibility passed-arm resource/exit mismatch")
            if result_from_log(directory / f"{name}.stdout") != arm["result"]:
                raise ValueError("AMG feasibility result differs from raw log")
            validate_result(arm["result"], phase, expected[name], p, job)
    computed_pass = record["failure"] is None and set(record["arms"]) == set(expected) and all(a["passed"] for a in record["arms"].values())
    if record["passed"] != computed_pass:
        raise ValueError("AMG feasibility completion flag differs from exact coverage")
    return record


def accepted_smoke(p):
    job = job_number(os.environ["PCB_TCAD_SMOKE_JOB_ID"])
    directory = attempt_directory("smoke", job)
    record = validate_attempt(directory, "smoke", p)
    _, rows = accounting(job)
    if record["scheduler"]["JobId"] != job or not record["passed"] or len(rows) != 1 or not terminal_success(rows, job):
        raise ValueError("successful terminal source-bound smoke required")
    return {"job_id": job, "attempt_sha256": sha256_file(directory / "attempt.json"), "accounting": rows}


def run_phase(phase, p, scheduler, runtime):
    directory = attempt_directory(phase, os.environ["SLURM_JOB_ID"], create=True)
    record = {**identity(), "phase": phase, "scheduler": scheduler, "runtime": runtime,
              "layout_id": "smoke" if phase == "smoke" else p["recovery"]["layout_id"],
              "passed": False, "arms": {}, "failure": None}
    atomic_write_json(directory / "attempt.json", record)
    try:
        if phase == "feasibility":
            record["smoke"] = accepted_smoke(p)
        for arm in arms_for(phase, p):
            check_source()
            record["arms"][arm["name"]] = bounded_arm(directory, phase, arm, p)
            atomic_write_json(directory / "attempt.json", record)
            if not record["arms"][arm["name"]]["passed"]:
                break
        check_source()
        record["passed"] = len(record["arms"]) == len(arms_for(phase, p)) and all(a["passed"] for a in record["arms"].values())
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        record["failure"] = str(exc)
    atomic_write_json(directory / "attempt.json", record)
    print(json.dumps({"attempt": str(directory.relative_to(ROOT)), "passed": record["passed"]}))
    return record["passed"]


def finalize(p, scheduler, runtime):
    directory = attempt_directory("finalize", os.environ["SLURM_JOB_ID"], create=True)
    job = job_number(os.environ["PCB_TCAD_FEASIBILITY_JOB_ID"])
    path = attempt_directory("feasibility", job)
    receipt = path / "attempt.json"
    summary = {**identity(), **assess_feasibility({}, p), "scheduler": scheduler, "runtime": runtime,
               "feasibility_job_id": job, "accounting": [], "errors": [],
               "attempt_sha256": sha256_file(receipt) if receipt.exists() else None}
    try:
        raw, rows = accounting(job)
        (directory / "sacct.txt").write_text(raw + "\n")
        summary.update(accounting=rows, accounting_sha256=sha256_file(directory / "sacct.txt"))
        smoke = accepted_smoke(p)
        summary["smoke"] = smoke
        record = validate_attempt(path, "feasibility", p)
        if record["scheduler"]["JobId"] != job or record.get("smoke", {}).get("attempt_sha256") != smoke["attempt_sha256"]:
            raise ValueError("AMG feasibility job/prerequisite binding mismatch")
        summary["observed_arms"] = {n: {"passed": a["passed"], "failure": a["failure"]} for n, a in record["arms"].items()}
        if len(rows) != 1 or not terminal_success(rows, job):
            raise ValueError("AMG feasibility did not complete with zero exit and restarts")
        summary.update(assess_feasibility(record, p))
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        summary["errors"].append(str(exc))
    check_source()
    atomic_write_json(directory / "summary.json", summary)
    print(json.dumps({"summary": str(directory.relative_to(ROOT) / "summary.json"),
                      "complete": summary["complete"], "feasibility_passed": summary["feasibility_passed"]}))
    return summary["complete"] and not summary["errors"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("smoke", "feasibility", "finalize"), required=True)
    args = parser.parse_args()
    p = protocol()
    scheduler = check_allocation(args.phase, p)
    check_source()
    runtime = check_runtime(p)
    ok = finalize(p, scheduler, runtime) if args.phase == "finalize" else run_phase(args.phase, p, scheduler, runtime)
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()
