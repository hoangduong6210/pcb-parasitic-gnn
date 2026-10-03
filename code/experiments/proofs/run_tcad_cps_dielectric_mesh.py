#!/usr/bin/env python3
"""Bounded fresh mesh workers and byte-exact receipts, including partial payloads."""
from __future__ import annotations
import json
import os
import signal
import subprocess
import sys
import time

import tcad_cps_dielectric_mesh as c
from tcad_cps_dielectric_mesh_bundle import check_bundle
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import accounting, result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file, sha256_json


def mode_files(directory, mode):
    paths = {directory / f"{mode}.{suffix}" for suffix in ("stdout", "stderr")}
    payload = directory / f"{mode}.payload"
    if payload.is_symlink():
        raise ValueError("unsafe mesh payload directory")
    if payload.exists():
        for path in payload.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError("unsafe mesh payload member")
            if path.is_file():
                paths.add(path)
    return {str(path.relative_to(directory)): sha256_file(path) for path in sorted(paths)}


def validate_result(result, mode, p, job, directory):
    if any(result.get(k) != v for k, v in c.identity().items()):
        raise ValueError("mesh worker source mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p) or not c.assess_result(result, mode, p):
        raise ValueError("mesh worker job/runtime/result gate mismatch")
    payload = directory / f"{mode}.payload"
    if {path.name for path in payload.iterdir()} != {"raw", "final", "cad_report.json"}:
        raise ValueError("mesh payload top-level closure mismatch")
    if c.read_json(payload / "cad_report.json") != result["cad_report"]:
        raise ValueError("saved mesh CAD report differs from worker")
    for name in ("raw", "final"):
        manifest = check_bundle(payload / name, p[c.PHASE]["payload"])
        observed = {"manifest_sha256": sha256_file(payload / name / "manifest.json"),
            "packet_sha256": manifest["packet_sha256"], "payload_bytes": manifest["payload_bytes"]}
        if observed != result["bundles"][name]:
            raise ValueError("mesh bundle identity differs from worker")
        if name == "final":
            for array, count in (("node_tags", "mesh_nodes"), ("tetrahedron_tags", "mesh_tetrahedra"), ("triangle_tags", "mesh_triangles")):
                if manifest["arrays"][array]["shape"][0] != result["mesh_audit"][count]:
                    raise ValueError("final mesh bundle count differs from audit")
        else:
            for array, count in (("node_tags", "nodes"), ("tetrahedron_tags", "tetrahedra"), ("triangle_tags", "triangles")):
                if manifest["arrays"][array]["shape"][0] != result["quality_before"][count]:
                    raise ValueError("raw mesh bundle count differs from observation")


def bounded_mode(directory, mode, p):
    limits = p["worker_limits"][mode]
    out, err = directory / f"{mode}.stdout", directory / f"{mode}.stderr"
    started, peak, failure = time.monotonic(), 0., None
    with out.open("x") as stdout, err.open("x") as stderr:
        process = subprocess.Popen([sys.executable, "-u", str(c.ROOT / c.WORKER), "--mode", mode],
            cwd=directory, stdout=stdout, stderr=stderr, start_new_session=True,
            env={k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")})
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
        "elapsed_s": elapsed, "observed_peak_rss_gib": peak, "files_sha256": mode_files(directory, mode)}
    if process.returncode == 0 and failure is None:
        try:
            result = result_from_log(out)
            validate_result(result, mode, p, os.environ["SLURM_JOB_ID"], directory)
            record.update(result=result, passed=True)
        except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; retain stderr and partial payload"
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def validate_attempt(directory, p):
    if not directory.name.startswith("job_") or directory != c.attempt_directory(directory.name[4:]):
        raise ValueError("mesh attempt path mismatch")
    if (directory / "attempt.json").is_symlink():
        raise ValueError("unsafe mesh attempt receipt")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("mesh attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("mesh attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("mesh mode sequence skipped a mode or failure")
    top = {"attempt.json", *(f"{m}.{s}" for m in prefix for s in ("json", "stdout", "stderr"))}
    top |= {f"{m}.payload" for m in prefix if (directory / f"{m}.payload").exists()}
    if {f.name for f in directory.iterdir()} != top:
        raise ValueError("mesh attempt file closure mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe mesh attempt member")
    for mode, arm in record["modes"].items():
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool:
            raise ValueError("mesh mode receipt mismatch")
        if arm["files_sha256"] != mode_files(directory, mode):
            raise ValueError("mesh raw-log/payload hash closure mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("mesh parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("mesh saved result differs from raw log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("failed mesh mode needs explicit failure")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("mesh coverage/repeatability/claim flag mismatch")
    return record


def terminal_review(job, p):
    record = validate_attempt(c.attempt_directory(job), p)
    raw, rows = accounting(job)
    if len(rows) != 1 or rows[0]["JobID"] != job or rows[0]["Restarts"] != "0":
        raise ValueError("mesh exact zero-restart accounting required")
    expected = ("COMPLETED", "0:0") if record["complete"] else ("FAILED", "2:0")
    if (rows[0]["State"], rows[0]["ExitCode"]) != expected:
        raise ValueError("mesh terminal state differs from coverage")
    return {"attempt_sha256": sha256_file(c.attempt_directory(job) / "attempt.json"),
        "accounting": rows, "raw_accounting": raw, **c.assessment(record, p)}


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
    return record["complete"]


def main():
    p = c.protocol()
    scheduler = c.check_allocation(c.PHASE, p)
    c.check_source()
    runtime = c.check_runtime(p)
    raise SystemExit(0 if run(p, scheduler, runtime) else 2)


if __name__ == "__main__":
    main()
