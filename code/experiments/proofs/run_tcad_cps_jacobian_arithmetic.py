#!/usr/bin/env python3
"""Bounded fresh saved-packet workers and byte-only terminal verification."""
import json
import os
import signal
import subprocess
import sys
import time

import tcad_cps_jacobian_arithmetic as c
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file


def mode_files(directory, mode):
    paths = [directory / f"{mode}.{s}" for s in ("stdout", "stderr")]
    report = directory / f"{mode}.report.json"
    if report.exists() or report.is_symlink():
        paths.append(report)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("unsafe arithmetic output member")
    return {path.name: sha256_file(path) for path in paths}


def validate_result(result, mode, p, job, directory):
    """Read report metadata/coverage only; never recompute real determinants."""
    expected = p[c.PHASE]["inputs"][c.input_kind(mode, p)]
    path = directory / f"{mode}.report.json"
    if path.is_symlink() or not 0 < path.stat().st_size <= p[c.PHASE]["report_bytes_max"]:
        raise ValueError("unsafe/oversized arithmetic report")
    if any(result.get(k) != v for k, v in c.identity().items()) or result["mode"] != mode:
        raise ValueError("arithmetic worker identity mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p):
        raise ValueError("arithmetic worker job/runtime mismatch")
    if result["packet_sha256"] != expected["packet_sha256"] or result["report_sha256"] != sha256_file(path) or result["report_bytes"] != path.stat().st_size:
        raise ValueError("arithmetic report byte identity mismatch")
    report = c.read_json(path)
    summary = report["summary"]
    if (report["schema"] != "pcb-gnn.jacobian-arithmetic-report.v1" or report["packet_sha256"] != expected["packet_sha256"]
            or report["jacobian_rtol"] != p[c.PHASE]["jacobian_rtol"] or report["jacobian_atol"] != 0
            or summary != result["summary"] or summary["tetrahedra"] != expected["tetrahedra"]
            or len(report["rows"]) != expected["tetrahedra"] or summary["exact_methods_agree"] is not True
            or any(report[k] is not False or result[k] is not False for k in c.CLOSED)):
        raise ValueError("arithmetic report coverage/gate mismatch")
    tags = [r["tetrahedron_tag"] for r in report["rows"]]
    if tags != sorted(set(tags)) or any(type(t) is not int or t <= 0 for t in tags):
        raise ValueError("arithmetic report native tag closure mismatch")
    if any(type(r["original_gate_close"]) is not bool for r in report["rows"]):
        raise ValueError("arithmetic gate flags must be explicit booleans")
    if summary["original_gate_mismatches"] != sum(r["original_gate_close"] is False for r in report["rows"]):
        raise ValueError("arithmetic mismatch count differs from rows")
    if summary["interesting_tetrahedron_tags"] != [r["tetrahedron_tag"] for r in report["rows"] if "coordinates_hex_mm" in r]:
        raise ValueError("arithmetic interesting-row index mismatch")
    for key in ("native", "vector", "scalar"):
        flags = [r["errors_against_exact"][key]["within_rtol"] for r in report["rows"]]
        if any(type(v) is not bool for v in flags) or summary["outside_rtol_against_exact"][key] != sum(v is False for v in flags):
            raise ValueError("arithmetic exact-error count differs from rows")
    for key in ("native", "vector", "scalar", "exact"):
        counts = summary["sign_counts"][key]
        if set(counts) != {"negative", "zero", "positive"} or any(type(v) is not int or v < 0 for v in counts.values()) or sum(counts.values()) != len(tags):
            raise ValueError("arithmetic sign counts lack full coverage")
    limits = p["worker_limits"][mode]
    if not c.bounded(result["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(result["peak_rss_gib"], limits["rss_gib_max"]):
        raise ValueError("arithmetic worker cap mismatch")


def bounded_mode(directory, mode, p):
    limits = p["worker_limits"][mode]
    out, err = (directory / f"{mode}.{s}" for s in ("stdout", "stderr"))
    started, peak, failure = time.monotonic(), 0., None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, "-u", str(c.ROOT / c.WORKER), "--mode", mode],
            cwd=directory, stdout=stdout, stderr=stderr, start_new_session=True,
            env={k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")})
        try:
            while process.poll() is None:
                peak = max(peak, rss_gib(process.pid))
                if time.monotonic()-started > limits["worker_timeout_s"] or peak > limits["rss_gib_max"]:
                    failure = "worker time/RSS cap exceeded"
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
        "elapsed_s": elapsed, "observed_peak_rss_gib": peak, "files_sha256": mode_files(directory, mode)}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, mode, p, os.environ["SLURM_JOB_ID"], directory)
            record.update(result=result, passed=True)
        except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; preserve all partial output"
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def validate_attempt(directory, p):
    if directory != c.attempt_directory(directory.name.removeprefix("job_")):
        raise ValueError("arithmetic attempt path mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe arithmetic attempt member")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("arithmetic attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("arithmetic attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("arithmetic mode sequence skipped mode/failure")
    expected = {"attempt.json"}
    for mode, arm in record["modes"].items():
        files = mode_files(directory, mode)
        expected.update(files)
        expected.add(f"{mode}.json")
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool or arm["files_sha256"] != files:
            raise ValueError("arithmetic mode receipt/hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("arithmetic parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("arithmetic result differs from log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("arithmetic failed mode needs explicit failure")
    if {f.name for f in directory.iterdir()} != expected:
        raise ValueError("arithmetic attempt file closure mismatch")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("arithmetic assessment mismatch")
    return record


def run(p, scheduler, runtime):
    directory = c.attempt_directory(os.environ["SLURM_JOB_ID"], create=True)
    record = {**c.identity(), "scheduler": scheduler, "runtime": runtime, "modes": {}, "failure": None}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    try:
        for mode in p[c.PHASE]["modes"]:
            c.check_source()
            record["modes"][mode] = bounded_mode(directory, mode, p)
            record.update(c.assessment(record, p))
            atomic_write_json(directory / "attempt.json", record)
            if not record["modes"][mode]["passed"]:
                break
        c.check_source()
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        record["failure"] = str(exc)
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    validate_attempt(directory, p)
    print(json.dumps({"attempt": str(directory.relative_to(c.ROOT)), **c.assessment(record, p)}))
    return record["diagnostic_passed"]


def main():
    p = c.protocol()
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    raise SystemExit(0 if run(p, scheduler, runtime) else 2)


if __name__ == "__main__":
    main()
