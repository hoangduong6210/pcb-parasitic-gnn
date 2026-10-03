#!/usr/bin/env python3
"""Bounded archived-sizing diagnostic workers and byte/metadata-only verification."""
import json
import os
import signal
import subprocess
import sys
import time

import tcad_cps_sizing_budget as c
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file


def mode_files(directory, mode):
    paths = [directory / f"{mode}.{s}" for s in ("stdout", "stderr")]
    report = directory / f"{mode}.report.json"
    if report.exists() or report.is_symlink():
        paths.append(report)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("unsafe sizing diagnostic output member")
    return {path.name: sha256_file(path) for path in paths}


def validate_result(result, mode, p, job, directory):
    """Byte/scalar metadata checks only; no geometry, axis or mesh replay."""
    from fractions import Fraction
    from math import isfinite
    from geometry_contract import geometry_sha256
    from tcad_cps_sizing_budget_worker import SUMMARY_KEYS
    from tcad_cps_sizing_budget_math import logged_counts
    layout_id, layout, arm = c.mode_input(mode, p)
    path = directory / f"{mode}.report.json"
    if path.is_symlink() or not 0 < path.stat().st_size <= p[c.PHASE]["report_bytes_max"]:
        raise ValueError("unsafe/oversized sizing diagnostic report")
    if any(result.get(k) != v for k, v in c.identity().items()) or result["mode"] != mode:
        raise ValueError("sizing diagnostic worker identity mismatch")
    if result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p):
        raise ValueError("sizing diagnostic worker job/runtime mismatch")
    if result["report_sha256"] != sha256_file(path) or result["report_bytes"] != path.stat().st_size:
        raise ValueError("sizing diagnostic report byte identity mismatch")
    report, cad = c.read_json(path), c.cad_report(mode, p)
    paths, provenance = c.archived_inputs(mode, p)
    if (report["schema"] != "pcb-gnn.sizing-budget-report.v1" or report["layout_id"] != layout_id
            or report["geometry_sha256"] != geometry_sha256(layout) or report["arm"] != arm
            or report["policy"] != c.policy(mode, p) or report["archived_inputs"] != provenance
            or report["canonical_cad_sha256"] != p["dielectric_mesh"]["cad_report_sha256"][mode]
            or report["canonical_boxes_mm"] != cad["canonical_boxes_mm"] or report["domain_box_mm"] != cad["domain_box_mm"]
            or result["summary"] != {k: report[k] for k in SUMMARY_KEYS}
            or any(report[k] is not False or result[k] is not False for k in c.CLOSED)
            or any(report[k] is not False for k in ("step_field_index_is_node_prediction", "transition_function_replayed",
                "expanded_envelope_is_measured_transition_area", "candidate_selected", "coordinates_snapped"))):
        raise ValueError("sizing diagnostic report identity/closed-gate mismatch")
    def value(row):
        if set(row) != {"numerator", "denominator"} or any(type(v) is not str for v in row.values()):
            raise ValueError("invalid rational metadata")
        n, d = int(row["numerator"]), int(row["denominator"])
        v = Fraction(n, d)
        if n < 0 or d <= 0 or str(v.numerator) != row["numerator"] or str(v.denominator) != row["denominator"]:
            raise ValueError("negative or noncanonical rational metadata")
        return v
    cover = report["coverage"]
    if set(cover) != {"conductors", "near_core", "expanded_envelope"}:
        raise ValueError("sizing diagnostic scenario coverage differs")
    domain_area = value(cover["conductors"]["domain_area_mm2"])
    unions = []
    for name in ("conductors", "near_core", "expanded_envelope"):
        row = cover[name]
        counts = ("rectangle_count", "nonempty_clipped_rectangles", "unique_clipped_rectangles", "reference_cells")
        if (any(type(row[k]) is not int for k in counts)
                or row["rectangle_count"] != len(cad["canonical_boxes_mm"])
                or not 0 < row["unique_clipped_rectangles"] <= row["nonempty_clipped_rectangles"] <= row["rectangle_count"] <= p[c.PHASE]["rectangle_cap"]
                or not 0 < row["reference_cells"] <= p[c.PHASE]["reference_cells_max"]
                or value(row["domain_area_mm2"]) != domain_area):
            raise ValueError("sizing diagnostic coverage metadata invalid")
        multiplicities = [item["multiplicity"] for item in row["area_by_multiplicity_mm2"]]
        if (multiplicities != sorted(set(multiplicities)) or not multiplicities
                or any(type(k) is not int or not 0 <= k <= row["rectangle_count"] for k in multiplicities)):
            raise ValueError("sizing diagnostic multiplicity metadata invalid")
        areas = [(item["multiplicity"], value(item["area_mm2"])) for item in row["area_by_multiplicity_mm2"]]
        union, individual = value(row["union_area_mm2"]), value(row["sum_clipped_rectangle_areas_mm2"])
        if (any(a <= 0 for _,a in areas) or sum(a for _,a in areas) != domain_area
                or sum(k*a for k,a in areas) != individual or sum(a for k,a in areas if k) != union
                or individual-union != value(row["overlap_excess_area_mm2"])):
            raise ValueError("sizing diagnostic scalar area closure mismatch")
        near, far = (Fraction.from_float(float(report["policy"][k])) for k in ("near_size_mm", "far_size_mm"))
        if value(report["step_field_workload_indices"][name]) != union/near**2+(domain_area-union)/far**2:
            raise ValueError("sizing diagnostic step-index metadata mismatch")
        unions.append(union)
    if not 0 < unions[0] <= unions[1] <= unions[2] <= domain_area:
        raise ValueError("sizing diagnostic containment metadata mismatch")
    budget, limits = report["vertical_budget"], p["worker_limits"][mode]
    if budget["mesh_connectivity_observed"] is not False or budget["limits"] != {k: limits[k] for k in ("mesh_nodes_max", "mesh_tetrahedra_max", "planar_nodes_max", "planar_triangles_max")}:
        raise ValueError("sizing diagnostic changed original caps")
    z = budget["vertical_axis"]
    nz, points = z["point_count"], z["points_mm"]
    if (type(nz) is not int or nz != len(points) or not 2 <= nz <= p[c.PHASE]["axis_points_max"]
            or any(type(v) is not float or not isfinite(v) for v in points) or points != sorted(set(points))):
        raise ValueError("sizing diagnostic z metadata mismatch")
    groups = budget["groups"]
    if not groups or len({tuple(g["owners"]) for g in groups}) != len(groups):
        raise ValueError("sizing diagnostic group metadata invalid")
    for g in groups:
        owners, kept = g["owners"], g["retained_intervals"]
        if (owners != sorted(set(owners)) or any(type(i) is not int or not 0 <= i < len(cad["canonical_boxes_mm"]) for i in owners)
                or kept != sorted(set(kept)) or not kept or any(type(i) is not int or not 0 <= i < nz-1 for i in kept)
                or type(g["retained_interval_count"]) is not int or g["retained_interval_count"] != len(kept)
                or value(g["area_mm2"]) <= 0 or value(g["retained_height_mm"]) <= 0):
            raise ValueError("sizing diagnostic retained-interval metadata invalid")
    least, most = min(g["retained_interval_count"] for g in groups), max(g["retained_interval_count"] for g in groups)
    if (budget["minimum_retained_intervals"] != least or budget["maximum_retained_intervals"] != most
            or sum(value(g["area_mm2"]) for g in groups) != domain_area
            or sum(value(g["area_mm2"])*value(g["retained_height_mm"]) for g in groups) != value(budget["exact_dielectric_volume_mm3"])
            or budget["planar_node_budget_from_full_column_bound"] != limits["mesh_nodes_max"]//nz
            or budget["planar_node_budget_with_capture_cap"] != min(limits["planar_nodes_max"], limits["mesh_nodes_max"]//nz)
            or budget["planar_triangle_sufficient_budget"] != min(limits["planar_triangles_max"], limits["mesh_tetrahedra_max"]//(3*most))
            or budget["planar_triangle_necessary_ceiling"] != min(limits["planar_triangles_max"], limits["mesh_tetrahedra_max"]//(3*least))):
        raise ValueError("sizing diagnostic scalar budget closure mismatch")
    logged = logged_counts((c.ROOT / paths["native_stdout"]).read_text())
    full = logged["nodes"]*nz
    if (report["native_log_counts"] != logged or report["conditional_full_column_node_bound_from_log"] != full
            or report["logged_nodes_within_capture_cap"] is not (logged["nodes"] <= limits["planar_nodes_max"])
            or report["conditional_full_column_node_bound_passes"] is not (full <= limits["mesh_nodes_max"])):
        raise ValueError("sizing diagnostic log/conditional-count metadata mismatch")
    if not c.bounded(result["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(result["peak_rss_gib"], limits["rss_gib_max"]):
        raise ValueError("sizing diagnostic worker cap mismatch")

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
        raise ValueError("sizing diagnostic attempt path mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe sizing diagnostic attempt member")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("sizing diagnostic attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("sizing diagnostic attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("sizing diagnostic mode sequence skipped mode/failure")
    expected = {"attempt.json"}
    for mode, arm in record["modes"].items():
        files = mode_files(directory, mode)
        expected.update(files)
        expected.add(f"{mode}.json")
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool or arm["files_sha256"] != files:
            raise ValueError("sizing diagnostic mode receipt/hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("sizing diagnostic parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("sizing diagnostic result differs from log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("sizing diagnostic failed mode needs explicit failure")
    if {f.name for f in directory.iterdir()} != expected:
        raise ValueError("sizing diagnostic attempt file closure mismatch")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("sizing diagnostic assessment mismatch")
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
