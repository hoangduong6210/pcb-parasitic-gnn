#!/usr/bin/env python3
"""One guarded mesh-only allocation, three bounded fresh processes and no retry."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time

from tcad_cps_mesh_probe import (ROOT, assessment, assess_result, attempt_directory, bounded,
    check_allocation, check_runtime, check_source, identity, protocol, read_json)
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import accounting, result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file


def validate_result(result, mode, p, job):
    if any(result.get(k) != v for k, v in identity().items()):
        raise ValueError("mesh-probe worker source mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p):
        raise ValueError("mesh-probe worker job/runtime mismatch")
    if not assess_result(result, mode, p):
        raise ValueError("mesh-probe worker result gate failed")


def bounded_mode(directory, mode, p):
    limits = p["worker_limits"][mode]
    out, err = directory / f"{mode}.stdout", directory / f"{mode}.stderr"
    started, peak, failure = time.monotonic(), 0.0, None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, "-u", str(ROOT / "code/solvers/tcad_cps_mesh_probe_worker.py"), "--mode", mode],
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
    record = {"mode": mode, "passed": False, "returncode": process.returncode, "failure": failure,
              "elapsed_s": elapsed, "observed_peak_rss_gib": peak,
              "files_sha256": {f.name: sha256_file(f) for f in (out, err)}}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, mode, p, os.environ["SLURM_JOB_ID"])
            record.update(result=result, passed=True)
        except (KeyError, TypeError, ValueError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr"
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def validate_attempt(directory, p):
    if not directory.name.startswith("job_") or directory != attempt_directory(directory.name[4:]):
        raise ValueError("mesh-probe attempt path mismatch")
    if (directory / "attempt.json").is_symlink():
        raise ValueError("unsafe mesh-probe attempt receipt")
    record = read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("mesh-probe attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != attempt_directory(job):
        raise ValueError("mesh-probe attempt path/job mismatch")
    prefix = p["mesh_probe"]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("mesh-probe sequence skipped a mode or failure")
    expected_files = {"attempt.json", *(f"{m}.{s}" for m in prefix for s in ("json", "stdout", "stderr"))}
    if {f.name for f in directory.iterdir()} != expected_files:
        raise ValueError("mesh-probe attempt file closure mismatch")
    for name in expected_files:
        if (directory / name).is_symlink() or not (directory / name).is_file():
            raise ValueError("unsafe mesh-probe attempt member")
    for mode, arm in record["modes"].items():
        if arm != read_json(directory / f"{mode}.json") or arm["mode"] != mode or not isinstance(arm["passed"], bool):
            raise ValueError("mesh-probe mode receipt mismatch")
        if set(arm["files_sha256"]) != {f"{mode}.stdout", f"{mode}.stderr"}:
            raise ValueError("mesh-probe raw-log closure mismatch")
        for filename, digest in arm["files_sha256"].items():
            if sha256_file(directory / filename) != digest:
                raise ValueError("mesh-probe raw-log hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("mesh-probe parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("mesh-probe saved result differs from raw log")
            validate_result(arm["result"], mode, p, job)
    if any(record.get(k) is not v for k, v in assessment(record, p).items()):
        raise ValueError("mesh-probe coverage/repeatability/claim flag mismatch")
    return record


def terminal_review(job, p):
    """Read-only closure/scalar review; never run a mesh or solver on login."""
    record = validate_attempt(attempt_directory(job), p)
    raw, rows = accounting(job)
    if len(rows) != 1 or rows[0]["JobID"] != job or rows[0]["Restarts"] != "0":
        raise ValueError("mesh-probe exact zero-restart accounting required")
    expected = ("COMPLETED", "0:0") if record["complete"] else ("FAILED", "2:0")
    if (rows[0]["State"], rows[0]["ExitCode"]) != expected:
        raise ValueError("mesh-probe terminal state differs from coverage")
    return {"attempt_sha256": sha256_file(attempt_directory(job) / "attempt.json"),
            "accounting": rows, "raw_accounting": raw, "complete": record["complete"],
            "mesh_feasible": record["mesh_feasible"], "reference_qualified": False}


def run(p, scheduler, runtime):
    directory = attempt_directory(os.environ["SLURM_JOB_ID"], create=True)
    record = {**identity(), "scheduler": scheduler, "runtime": runtime, "modes": {}, "failure": None}
    record.update(assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    try:
        for mode in p["mesh_probe"]["modes"]:
            check_source()
            record["modes"][mode] = bounded_mode(directory, mode, p)
            record.update(assessment(record, p))
            atomic_write_json(directory / "attempt.json", record)
            if not record["modes"][mode]["passed"]:
                break
        check_source()
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        record["failure"] = str(exc)
    record.update(assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    validate_attempt(directory, p)
    print(json.dumps({"attempt": str(directory.relative_to(ROOT)), "complete": record["complete"],
                      "mesh_feasible": record["mesh_feasible"], "terminal_admission_pending": True}))
    # A complete negative repeatability result is valid finalization, not a pass.
    return record["complete"]


def main():
    p = protocol()
    scheduler = check_allocation("mesh_probe", p)
    check_source()
    runtime = check_runtime(p)
    raise SystemExit(0 if run(p, scheduler, runtime) else 2)


if __name__ == "__main__":
    main()
