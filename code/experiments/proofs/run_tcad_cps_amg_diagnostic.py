#!/usr/bin/env python3
"""One guarded job, two bounded workers; no automatic feasibility expansion."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time

from tcad_cps_amg_diagnostic import (ROOT, assess_result, attempt_directory, check_allocation,
    check_runtime, check_source, identity, mode_input, protocol, read_json)
from run_tcad_cps_reference import result_from_log, rss_gib
from geometry_contract import geometry_sha256
from scientific_artifact import atomic_write_json, sha256_file, sha256_json


def validate_result(result, mode, p):
    layout_id, layout, arm = mode_input(mode, p)
    if result["mode"] != mode or result["layout_id"] != layout_id or result["arm"] != arm or result["geometry_sha256"] != geometry_sha256(layout):
        raise ValueError("diagnostic mode/geometry mismatch")
    if any(result.get(k) != v for k, v in identity().items()):
        raise ValueError("diagnostic source mismatch")
    if result["scheduler"]["JobId"] != os.environ["SLURM_JOB_ID"]:
        raise ValueError("diagnostic worker job mismatch")
    if result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"]) or not assess_result(result, mode, p):
        raise ValueError("diagnostic worker gate failed")


def bounded_mode(directory, mode, p):
    limits = p["worker_limits"][mode]
    out, err = directory / f"{mode}.stdout", directory / f"{mode}.stderr"
    started, peak, failure = time.monotonic(), 0.0, None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, str(ROOT / "code/solvers/tcad_cps_amg_worker.py"), "--mode", mode],
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
    record = {"mode": mode, "returncode": process.returncode, "elapsed_s": time.monotonic()-started,
              "observed_peak_rss_gib": peak, "failure": failure, "passed": False,
              "files_sha256": {f.name: sha256_file(f) for f in (out, err)}}
    if failure is None and record["elapsed_s"] > limits["worker_timeout_s"]:
        failure = record["failure"] = "worker wall-time cap exceeded at exit"
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, mode, p)
            record.update(result=result, passed=True)
        except (ValueError, KeyError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr"
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def run(p, scheduler, runtime):
    directory = attempt_directory(os.environ["SLURM_JOB_ID"], create=True)
    record = {**identity(), "scheduler": scheduler, "runtime": runtime, "modes": {}, "passed": False,
              "failure": None, "reference_qualified": False, "claim_eligible": False,
              "training_may_start": False, "automatic_feasibility_expansion": False}
    atomic_write_json(directory / "attempt.json", record)
    try:
        for mode in p["diagnostic"]["modes"]:
            check_source()
            record["modes"][mode] = bounded_mode(directory, mode, p)
            atomic_write_json(directory / "attempt.json", record)
            if not record["modes"][mode]["passed"]:
                break
        check_source()
        record["passed"] = set(record["modes"]) == set(p["diagnostic"]["modes"]) and all(r["passed"] for r in record["modes"].values())
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        record["failure"] = str(exc)
    atomic_write_json(directory / "attempt.json", record)
    print(json.dumps({"attempt": str(directory.relative_to(ROOT)), "passed": record["passed"], "terminal_admission_pending": True}))
    return record["passed"]


def main():
    p = protocol()
    scheduler = check_allocation("diagnostic", p)
    check_source()
    runtime = check_runtime(p)
    raise SystemExit(0 if run(p, scheduler, runtime) else 2)


if __name__ == "__main__":
    main()
