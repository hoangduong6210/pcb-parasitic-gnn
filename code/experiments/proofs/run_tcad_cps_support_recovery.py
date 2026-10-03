#!/usr/bin/env python3
"""Bounded single-sentinel feasibility; no automatic three-sentinel expansion."""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
import time

from tcad_cps_support_recovery import (ROOT, assess_feasibility, assess_result,
    attempt_directory, check_allocation, check_runtime, check_source, identity, protocol, target)
from tcad_cps_reference import job_number, read_json
from run_tcad_cps_reference import accounting, result_from_log, rss_gib, terminal_success
from scientific_artifact import atomic_write_json, sha256_file, sha256_json


def arms_for(phase, p):
    return [p["smoke"]["arm"]] if phase == "smoke" else p["recovery"]["recovery_arms"]


def bounded_arm(directory, phase, arm, p):
    limits = p["resources"][phase]
    out, err = directory / f'{arm["name"]}.stdout', directory / f'{arm["name"]}.stderr'
    started, peak, failure = time.monotonic(), 0.0, None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, str(ROOT / "code/solvers/tcad_cps_support_worker.py"),
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
    record = {"arm": arm, "returncode": process.returncode, "elapsed_s": time.monotonic()-started,
              "observed_peak_rss_gib": peak, "failure": failure, "passed": False,
              "files_sha256": {f.name: sha256_file(f) for f in (out, err)}}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, phase, arm, p)
            record.update(result=result, passed=True)
        except (ValueError, KeyError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr"
    atomic_write_json(directory / f'{arm["name"]}.json', record)
    return record


def validate_result(result, phase, arm, p):
    if result["arm"] != arm or any(result.get(k) != v for k, v in identity().items()):
        raise ValueError("recovery worker arm/source mismatch")
    from geometry_contract import geometry_sha256
    expected_id, geometry = ("smoke", p["smoke"]["layout"]) if phase == "smoke" else (p["recovery"]["layout_id"], target(p)["layout"])
    if result["layout_id"] != expected_id or result["geometry_sha256"] != geometry_sha256(geometry):
        raise ValueError("recovery worker geometry mismatch")
    if result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"]):
        raise ValueError("recovery mesh-policy digest mismatch")
    if not assess_result(result, p, phase):
        raise ValueError("recovery result gate failed")


def validate_attempt(directory, phase, p):
    record = read_json(directory / "attempt.json")
    if record["phase"] != phase or any(record.get(k) != v for k, v in identity().items()):
        raise ValueError("recovery attempt phase/source mismatch")
    expected = {a["name"]: a for a in arms_for(phase, p)}
    if not set(record["arms"]).issubset(expected):
        raise ValueError("unexpected arm in recovery attempt")
    expected_id = "smoke" if phase == "smoke" else p["recovery"]["layout_id"]
    if record["layout_id"] != expected_id:
        raise ValueError("recovery attempt geometry mismatch")
    for name, arm in record["arms"].items():
        if arm != read_json(directory / f"{name}.json") or arm["arm"] != expected[name]:
            raise ValueError("recovery arm receipt mismatch")
        if set(arm["files_sha256"]) != {f"{name}.stdout", f"{name}.stderr"}:
            raise ValueError("recovery raw-log closure mismatch")
        for filename, digest in arm["files_sha256"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("recovery raw-log hash mismatch")
        if arm["passed"]:
            if result_from_log(directory / f"{name}.stdout") != arm["result"]:
                raise ValueError("recovery result not reconstructible from raw log")
            validate_result(arm["result"], phase, expected[name], p)
    computed_pass = set(record["arms"]) == set(expected) and all(a["passed"] for a in record["arms"].values())
    if record["passed"] != computed_pass:
        raise ValueError("recovery completion flag differs from exact arm coverage")
    return record


def accepted_smoke(p):
    job = job_number(os.environ["PCB_TCAD_SMOKE_JOB_ID"])
    directory = attempt_directory("smoke", job)
    record = validate_attempt(directory, "smoke", p)
    _, rows = accounting(job)
    if record["scheduler"]["JobId"] != job or not record["passed"] or not terminal_success(rows, job):
        raise ValueError("successful terminal recovery smoke required")
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
    raw, rows = accounting(job)
    (directory / "sacct.txt").write_text(raw + "\n")
    path = attempt_directory("feasibility", job)
    receipt = path / "attempt.json"
    summary = {**identity(), **assess_feasibility({}, p), "scheduler": scheduler, "runtime": runtime,
               "feasibility_job_id": job, "accounting": rows, "errors": [],
               "accounting_sha256": sha256_file(directory / "sacct.txt"),
               "attempt_sha256": sha256_file(receipt) if receipt.exists() else None}
    try:
        smoke = accepted_smoke(p)
        summary["smoke"] = smoke
        record = validate_attempt(path, "feasibility", p)
        if record["scheduler"]["JobId"] != job or record.get("smoke", {}).get("attempt_sha256") != smoke["attempt_sha256"]:
            raise ValueError("recovery job/prerequisite binding mismatch")
        summary["observed_arms"] = {n: {"passed": a["passed"], "failure": a["failure"]} for n, a in record["arms"].items()}
        if not terminal_success(rows, job):
            raise ValueError("recovery did not complete with zero exit and restarts")
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
