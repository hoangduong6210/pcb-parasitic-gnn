#!/usr/bin/env python3
"""Bounded exact-plane planning workers and byte/metadata-only verification."""
import json
import os
import signal
import subprocess
import sys
import time

import tcad_cps_layer_grid_dyadic as c
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file


def mode_files(directory, mode):
    paths = [directory / f"{mode}.{s}" for s in ("stdout", "stderr")]
    report = directory / f"{mode}.report.json"
    if report.exists() or report.is_symlink():
        paths.append(report)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("unsafe grid planning output member")
    return {path.name: sha256_file(path) for path in paths}


def validate_result(result, mode, p, job, directory):
    """Check report bytes/identity/metadata; never regenerate real axes."""
    from geometry_contract import geometry_sha256
    from tcad_cps_layer_grid_dyadic_worker import SUMMARY_KEYS
    from math import prod, isfinite
    layout_id, layout, arm = c.mode_input(mode, p)
    path = directory / f"{mode}.report.json"
    if path.is_symlink() or not 0 < path.stat().st_size <= p[c.PHASE]["report_bytes_max"]:
        raise ValueError("unsafe/oversized grid planning report")
    if any(result.get(k) != v for k, v in c.identity().items()) or result["mode"] != mode:
        raise ValueError("grid planning worker identity mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p):
        raise ValueError("grid planning worker job/runtime mismatch")
    if result["report_sha256"] != sha256_file(path) or result["report_bytes"] != path.stat().st_size:
        raise ValueError("grid planning report byte identity mismatch")
    report = c.read_json(path)
    cad = c.cad_report(mode, p)
    if (report["schema"] != "pcb-gnn.layer-grid-dyadic-report.v1" or report["layout_id"] != layout_id
            or report["geometry_sha256"] != geometry_sha256(layout) or report["arm"] != arm
            or report["policy"] != c.policy(mode, p)
            or report["cad_report_sha256"] != p["dielectric_mesh"]["cad_report_sha256"][mode]
            or report["canonical_boxes_mm"] != cad["canonical_boxes_mm"] or report["domain_box_mm"] != cad["domain_box_mm"]
            or result["summary"] != {k: report[k] for k in SUMMARY_KEYS}
            or any(report[k] is not False or result[k] is not False for k in c.CLOSED)):
        raise ValueError("grid planning report identity/closed-gate mismatch")
    from fractions import Fraction
    def value(item):
        n, d = int(item["numerator"]), int(item["denominator"])
        if n <= 0 or d <= 0:
            raise ValueError("nonpositive dyadic width-budget metadata")
        return Fraction(n, d)
    budget = report["width_budget"]
    minimum = value(budget["minimum_canonical_gap_mm"])
    floor = value(budget["planning_width_floor_mm"])
    maximum = value(budget["maximum_target_width_mm"])
    nominal = Fraction.from_float(float(report["policy"]["far_size_mm"]))
    near = Fraction.from_float(float(report["policy"]["near_size_mm"]))
    if (budget["divisor"] != 12 or floor != min(minimum, near/4)
            or maximum != min(nominal, p[c.PHASE]["jacobian_condition_bound_max"]*floor/12)
            or budget["far_spacing_reduced"] is not (maximum < nominal)):
        raise ValueError("dyadic width-budget rule metadata mismatch")
    axes = report["axes"]
    if len(axes) != 3 or [a["axis"] for a in axes] != [0, 1, 2]:
        raise ValueError("grid planning axes lack coverage")
    for axis in axes:
        points = axis["points_mm"]
        k = 2*axis["axis"]
        canonical = sorted({cad["domain_box_mm"][k], cad["domain_box_mm"][k+1],
            *(b[j] for b in cad["canonical_boxes_mm"] for j in (k, k+1))})
        if (type(axis["point_count"]) is not int or len(points) != axis["point_count"]
                or not 2 <= len(points) <= p[c.PHASE]["axis_points_max"]
                or any(type(v) is not float or not isfinite(v) for v in points)
                or points != sorted(set(points)) or axis["points_hex_mm"] != [v.hex() for v in points]
                or axis["canonical_planes_mm"] != canonical or not set(canonical).issubset(points)
                or points[0] != canonical[0] or points[-1] != canonical[-1]):
            raise ValueError("grid planning axis metadata mismatch")
        leaves, segments = axis["leaf_intervals"], axis["segments"]
        if (axis["base_planes_mm"] != canonical or len(leaves) != len(points)-1
                or len(segments) != len(canonical)-1
                or sum(s["leaves"] for s in segments) != len(leaves)):
            raise ValueError("dyadic leaf/segment coverage mismatch")
        for index, leaf in enumerate(leaves):
            if (leaf["left_mm"] != points[index] or leaf["right_mm"] != points[index+1]
                    or type(leaf["depth"]) is not int or not 0 <= leaf["depth"] <= p[c.PHASE]["subdivision_depth_max"]
                    or type(leaf["near"]) is not bool or type(leaf["canonical_interval"]) is not int
                    or not 0 <= leaf["canonical_interval"] < len(segments)
                    or value(leaf["target_max_width_mm"]) != (min(maximum, near) if leaf["near"] else maximum)):
                raise ValueError("dyadic leaf metadata mismatch")
    if minimum != min(value(axis["minimum_base_gap_mm"]) for axis in axes):
        raise ValueError("dyadic canonical gap metadata mismatch")
    if (report["total_tensor_cells"] != prod(a["point_count"]-1 for a in axes)
            or report["tensor_node_upper_bound"] != prod(a["point_count"] for a in axes)
            or report["dielectric_cells"] != report["total_tensor_cells"]-sum(report["conductor_cell_counts"])
            or report["tetrahedra"] != 6*report["dielectric_cells"]
            or len(report["conductor_cell_counts"]) != len(layout["traces"])
            or len(report["conductor_cell_ranges"]) != len(layout["traces"])):
        raise ValueError("grid planning count metadata mismatch")
    limits = p["worker_limits"][mode]
    bound = report["jacobian_condition_upper_bound_squared"]
    numerator, denominator = int(bound["numerator"]), int(bound["denominator"])
    if numerator <= 0 or denominator <= 0:
        raise ValueError("grid planning bound must be positive")
    checks = {"node_upper_bound": report["tensor_node_upper_bound"] <= limits["mesh_nodes_max"],
        "tetrahedron_count": report["tetrahedra"] <= limits["mesh_tetrahedra_max"],
        "jacobian_condition_bound": numerator <= p[c.PHASE]["jacobian_condition_bound_max"]**2*denominator}
    if (report["planning_checks"] != checks or any(type(v) is not bool for v in report["planning_checks"].values())
            or report["planning_feasible"] is not all(checks.values())):
        raise ValueError("grid planning feasibility flag mismatch")
    if not c.bounded(result["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(result["peak_rss_gib"], limits["rss_gib_max"]):
        raise ValueError("grid planning worker cap mismatch")


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
        raise ValueError("grid planning attempt path mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe grid planning attempt member")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("grid planning attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("grid planning attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("grid planning mode sequence skipped mode/failure")
    expected = {"attempt.json"}
    for mode, arm in record["modes"].items():
        files = mode_files(directory, mode)
        expected.update(files)
        expected.add(f"{mode}.json")
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool or arm["files_sha256"] != files:
            raise ValueError("grid planning mode receipt/hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("grid planning parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("grid planning result differs from log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("grid planning failed mode needs explicit failure")
    if {f.name for f in directory.iterdir()} != expected:
        raise ValueError("grid planning attempt file closure mismatch")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("grid planning assessment mismatch")
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
