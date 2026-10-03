#!/usr/bin/env python3
"""Bounded fresh planar workers; terminal validation is byte/metadata-only."""
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from fractions import Fraction

import tcad_cps_edge_feasibility_v2 as c
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

sys.path.insert(0, str(c.ROOT / "code/solvers"))
from tcad_cps_column_bundle import check_bundle
from tcad_cps_edge_probe_metadata_v2 import NAMES, validate_probe_records


def mode_files(directory, mode):
    paths = [directory / f"{mode}.{s}" for s in ("stdout", "stderr")]
    payload = directory / f"{mode}.payload"
    if payload.is_symlink():
        raise ValueError("unsafe planar payload directory")
    if payload.exists():
        if not payload.is_dir():
            raise ValueError("planar payload is not a directory")
        for path in payload.rglob("*"):
            if path.is_symlink():
                raise ValueError("symlink in planar payload")
            if path.is_dir():
                if path != payload / "raw":
                    raise ValueError("unexpected planar payload directory")
                continue
            name = path.relative_to(payload).as_posix()
            if name not in ({n+".json" for n in NAMES} | {"raw/manifest.json"}) and not re.fullmatch(r"raw/[a-z_]+\.[0-9]{4}\.bin", name):
                raise ValueError("unexpected planar payload member")
            paths.append(path)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("unsafe planar output member")
    return {path.relative_to(directory).as_posix(): sha256_file(path) for path in sorted(paths)}


def rational(value, *, positive=False):
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise ValueError("invalid column rational metadata")
    if any(not isinstance(v, str) or not re.fullmatch(r"-?[0-9]+", v) for v in value.values()):
        raise ValueError("invalid column rational representation")
    n, d = int(value["numerator"]), int(value["denominator"])
    if d <= 0 or n < (1 if positive else 0):
        raise ValueError("nonpositive/negative column rational metadata")
    return Fraction(n, d)


def validate_result(result, mode, p, job, directory):
    """Identity, shape and scalar report closure; no real packet numerical replay."""
    from geometry_contract import geometry_sha256
    from tcad_cps_edge_builder_v2 import sizing_policy
    from tcad_cps_edge_sizing import validate_sizing
    layout_id, layout, arm = c.mode_input(mode, p)
    limits, cfg = p["worker_limits"][mode], p[c.PHASE]
    payload = directory / f"{mode}.payload"
    if payload.is_symlink() or not payload.is_dir():
        raise ValueError("unsafe/missing planar payload")
    if {f.name for f in payload.iterdir()} != ({n+".json" for n in NAMES} | {"raw"}):
        raise ValueError("complete planar payload closure mismatch")
    data = {}
    for name in NAMES:
        path = payload / f"{name}.json"
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= cfg["report_bytes_max"]:
            raise ValueError("unsafe/oversized planar metadata")
        data[name] = c.read_json(path)
    if (any(result.get(k) != v for k, v in c.identity().items()) or result["mode"] != mode
            or result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p)
            or result["stages"] != c.STAGES or result["planar_mesh_generated"] is not True
            or any(result[k] is not False for k in c.CLOSED)):
        raise ValueError("planar worker identity/runtime/stages mismatch")
    report, cad, sizing = (data[k] for k in ("report", "cad", "sizing"))
    original = c.cad_report(mode, p)
    if (report["schema"] != "pcb-gnn.edge-feasibility-report.v2" or report["layout_id"] != layout_id
            or report["geometry_sha256"] != geometry_sha256(layout) or report["arm"] != arm
            or report["canonical_cad_sha256"] != sha256_json(original)
            or report["planar_cad_sha256"] != sha256_json(cad) or report["sizing_sha256"] != sha256_json(sizing)
            or report["field_probe_sha256"] != sha256_json(data["field_probe"])
            or report["probe_original_state_unchanged"] is not True
            or report["files_sha256"] != {name+".json": sha256_file(payload / (name+".json")) for name in NAMES-{"report"}}
            or report["planar_mesh_generated"] is not True or any(report[k] is not False for k in c.CLOSED)
            or not isinstance(report["gmsh_build_options"], str) or not report["gmsh_build_options"]):
        raise ValueError("column report identity/closed-gate mismatch")
    if (cad["schema"] != "pcb-gnn.column-planar-cad.v1" or cad["canonical_boxes_mm"] != original["canonical_boxes_mm"]
            or cad["domain_box_mm"] != original["domain_box_mm"] or cad["options"] != p["dielectric_cad"]["cad_options"]
            or data["inputs"] != {k: cad[k] for k in ("canonical_boxes_mm", "domain_box_mm", "input_surface_tags", "before", "options")}
            or data["post_mesh_cad"] != cad["after"]
            or sizing["requested"] != sizing_policy(cad["canonical_boxes_mm"], c.policy(mode, p), p)
            or not validate_sizing(sizing, sizing_policy(cad["canonical_boxes_mm"], c.policy(mode, p), p))):
        raise ValueError("planar CAD/input/sizing/post-mesh closure mismatch")
    validate_probe_records(data, p, cfg)
    bundle = check_bundle(payload / "raw", cfg["payload"])
    if (result["bundle"] != {"manifest_sha256": sha256_file(payload / "raw/manifest.json"),
            "packet_sha256": bundle["packet_sha256"], "payload_bytes": bundle["payload_bytes"]}
            or result["report_sha256"] != sha256_file(payload / "report.json")
            or result["report_bytes"] != (payload / "report.json").stat().st_size):
        raise ValueError("planar report/bundle byte identity mismatch")
    plan = report["plan"]
    audit, capacity, condition = (plan[k] for k in ("planar_audit", "capacity", "conditioning"))
    if (plan["schema"] != "pcb-gnn.column-plan.v1" or plan["packet_sha256"] != bundle["packet_sha256"]
            or audit["schema"] != "pcb-gnn.column-planar-audit.v1" or capacity["schema"] != "pcb-gnn.column-capacity.v1"
            or condition["schema"] != "pcb-gnn.column-condition-summary.v1"
            or plan["policy"] != c.policy(mode, p) or plan["planar_mesh_validated"] is not True
            or any(plan[k] is not False for k in (*c.CLOSED, "coordinates_snapped", "raw_connectivity_changed"))
            or audit["packet_sha256"] != bundle["packet_sha256"] or audit["planar_mesh_validated"] is not True
            or any(audit[k] is not False for k in (*c.CLOSED, "coordinates_snapped", "raw_connectivity_changed", "native_quality_claimed"))
            or any(capacity[k] is not False for k in (*c.CLOSED, "planar_mesh_validated", "conditioning_validated", "coordinates_snapped"))):
        raise ValueError("planar audit scope/packet mismatch")
    for key, anchor in (("nodes", "node_tags"), ("triangles", "triangle_tags"), ("lines", "line_tags")):
        count = audit["planar_"+key]
        if type(count) is not int or not 0 < count <= limits["planar_"+key+"_max"] or count != bundle["arrays"][anchor]["shape"][0]:
            raise ValueError("planar count/bundle shape mismatch")
    rational(audit["minimum_exact_triangle_area_mm2"], positive=True)
    if (type(audit["raw_clockwise_triangles"]) is not int or not 0 <= audit["raw_clockwise_triangles"] <= audit["planar_triangles"]
            or len(audit["ownership_leakage_upper_bound_mm2"]) != len(cad["canonical_boxes_mm"])
            or rational(audit["leakage_bound_quantum_mm2"], positive=True) != Fraction(1, 1 << cfg["leakage_upper_bound_bits"])):
        raise ValueError("planar orientation/leakage metadata mismatch")
    geometry = p["dielectric_cad"]["geometry_checks"]
    for box, observed in zip(cad["canonical_boxes_mm"], audit["ownership_leakage_upper_bound_mm2"]):
        area = (Fraction(box[1])-Fraction(box[0]))*(Fraction(box[3])-Fraction(box[2]))
        if rational(observed) > max(Fraction(geometry["measure_atol_native"]), Fraction(geometry["measure_rtol"])*area):
            raise ValueError("planar reported ownership leakage exceeds gate")
    z = plan["vertical_axis"]
    canonical_z = sorted({cad["domain_box_mm"][4], cad["domain_box_mm"][5], *(b[k] for b in cad["canonical_boxes_mm"] for k in (4,5))})
    if (z["axis"] != 2 or type(z["point_count"]) is not int or not 2 <= z["point_count"] <= cfg["axis_points_max"]
            or any(type(v) is not float or not math.isfinite(v) for v in z["points_mm"])
            or len(z["points_mm"]) != z["point_count"] or z["points_mm"] != sorted(set(z["points_mm"]))
            or z["canonical_planes_mm"] != canonical_z or not set(canonical_z).issubset(z["points_mm"])
            or z["points_mm"][0] != canonical_z[0] or z["points_mm"][-1] != canonical_z[-1]
            or z["points_hex_mm"] != [v.hex() for v in z["points_mm"]]
            or capacity["vertical_points"] != z["point_count"] or capacity["planar_nodes"] != audit["planar_nodes"]
            or capacity["column_node_upper_bound"] != audit["planar_nodes"]*z["point_count"]
            or capacity["tetrahedra"] != 3*capacity["prisms"]
            or sum(g["prisms"] for g in capacity["groups"]) != capacity["prisms"]
            or [{"owners": g["owners"], "triangles": g["planar_triangles"]} for g in capacity["groups"]] != audit["groups"]
            or sum(g["triangles"] for g in audit["groups"]) != audit["planar_triangles"]):
        raise ValueError("column count/vertical metadata mismatch")
    for group in capacity["groups"]:
        kept = group["retained_z_intervals"]
        if (not isinstance(kept, list) or not kept or any(type(v) is not int or not 0 <= v < z["point_count"]-1 for v in kept)
                or kept != sorted(set(kept)) or group["prisms"] != group["planar_triangles"]*len(kept)):
            raise ValueError("column retained-interval/count metadata mismatch")
    bound = rational(condition["condition_upper_bound_squared"], positive=True)
    if (condition["triangles_checked"] != audit["planar_triangles"] or condition["templates_checked"] != 3*audit["planar_triangles"]
            or condition["condition_limit"] != cfg["jacobian_condition_bound_max"] or condition["native_quality_claimed"] is not False
            or type(condition["failed_triangles"]) is not int or not 0 <= condition["failed_triangles"] <= audit["planar_triangles"]
            or (condition["failed_triangles"] == 0) != (bound <= cfg["jacobian_condition_bound_max"]**2)
            or condition["conditioning_passed"] is not (condition["failed_triangles"] == 0)
            or condition["worst_witness"]["certificate"]["condition_upper_bound_squared"] != condition["condition_upper_bound_squared"]
            or not re.fullmatch("[a-f0-9]{64}", condition["certificate_sequence_sha256"])):
        raise ValueError("column conditioning metadata mismatch")
    rational(condition["minimum_positive_determinant_mm3"], positive=True)
    canonical_volume = rational(capacity["exact_dielectric_volume_mm3"], positive=True)
    if rational(plan["mesh_canonical_volume_limit_mm3"], positive=True) != max(Fraction(geometry["measure_atol_native"]), Fraction(geometry["measure_rtol"])*canonical_volume):
        raise ValueError("column reported volume tolerance changed")
    checks = {"node_upper_bound": capacity["column_node_upper_bound"] <= limits["mesh_nodes_max"],
        "tetrahedron_count": capacity["tetrahedra"] <= limits["mesh_tetrahedra_max"],
        "jacobian_condition_bound": bound <= cfg["jacobian_condition_bound_max"]**2,
        "prospective_mesh_volume": rational(plan["mesh_canonical_volume_error_mm3"]) <= rational(plan["mesh_canonical_volume_limit_mm3"], positive=True)}
    if (abs(rational(plan["prospective_mesh_volume_mm3"], positive=True)-rational(capacity["exact_dielectric_volume_mm3"], positive=True)) != rational(plan["mesh_canonical_volume_error_mm3"])
            or plan["planning_checks"] != checks or any(type(v) is not bool for v in plan["planning_checks"].values())
            or plan["planning_feasible"] is not all(checks.values()) or result["planning_feasible"] is not plan["planning_feasible"]
            or capacity["capacity_checks"] != {k: checks[k] for k in ("node_upper_bound", "tetrahedron_count")}
            or capacity["capacity_feasible"] is not all(capacity["capacity_checks"].values())):
        raise ValueError("column feasibility/volume metadata mismatch")
    if not c.bounded(result["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(result["peak_rss_gib"], limits["rss_gib_max"]):
        raise ValueError("column worker time/RSS metadata mismatch")


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
        except (OSError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            record["failure"] = str(exc)
    elif failure is None:
        record["failure"] = f"worker exited {process.returncode}; preserve all partial output"
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def validate_attempt(directory, p):
    if directory != c.attempt_directory(directory.name.removeprefix("job_")):
        raise ValueError("column attempt path mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe column attempt member")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("column attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("column attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("column mode sequence skipped mode/failure")
    expected = {"attempt.json"}
    for mode, arm in record["modes"].items():
        files = mode_files(directory, mode)
        expected.update(name.split("/")[0] for name in files)
        if (directory / f"{mode}.payload").exists():
            expected.add(f"{mode}.payload")
        expected.add(f"{mode}.json")
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool or arm["files_sha256"] != files:
            raise ValueError("column mode receipt/hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("column parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("column result differs from log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("column failed mode needs explicit failure")
    if {f.name for f in directory.iterdir()} != expected:
        raise ValueError("column attempt file closure mismatch")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("column assessment mismatch")
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
