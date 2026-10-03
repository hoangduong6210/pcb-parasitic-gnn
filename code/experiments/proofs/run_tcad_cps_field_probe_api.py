#!/usr/bin/env python3
"""Bounded synthetic native API workers; terminal byte/scalar/fixture checks."""
import json
import os
import signal
import subprocess
import sys
import time

import tcad_cps_field_probe_api as c
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import result_from_log, rss_gib
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

sys.path.insert(0,str(c.ROOT / "code/solvers"))
from tcad_cps_model_field_probe import EVENTS, TEMP_MODEL, validate_data

NAMES = {"fixture","sizing","before","after","comparison","report"} | {stem+"."+event for stem in ("distance","size") for event in EVENTS}


def mode_files(directory,mode):
    paths = [directory / f"{mode}.{suffix}" for suffix in ("stdout","stderr")]
    payload = directory / f"{mode}.payload"
    if payload.is_symlink(): raise ValueError("unsafe field probe payload")
    if payload.exists():
        if not payload.is_dir(): raise ValueError("field probe payload is not a directory")
        for path in payload.iterdir():
            if path.is_symlink() or not path.is_file() or path.name not in {name+".json" for name in NAMES}:
                raise ValueError("unexpected field probe payload member")
            paths.append(path)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("unsafe field probe output member")
    return {path.relative_to(directory).as_posix():sha256_file(path) for path in sorted(paths)}


def validate_result(result,mode,p,job,directory):
    import tcad_cps_edge_sizing as edge
    from tcad_cps_model_field_probe import comparison
    cfg,probe_cfg = p[c.PHASE],c.probe_config(p)
    payload = directory / f"{mode}.payload"
    if payload.is_symlink() or not payload.is_dir() or {path.name for path in payload.iterdir()} != {name+".json" for name in NAMES}:
        raise ValueError("complete field probe payload closure differs")
    data = {}
    for name in NAMES:
        path = payload / f"{name}.json"
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= cfg["report_bytes_max"]:
            raise ValueError("unsafe/oversized field probe metadata")
        data[name] = c.read_json(path)
    report,sizing,before = data["report"],data["sizing"],data["before"]
    fixture = cfg["fixture"]
    if (any(result.get(k) != v for k,v in c.identity().items()) or result["mode"] != mode
            or result["scheduler"]["JobId"] != job or result["runtime"] != expected_runtime(p)
            or result["report_sha256"] != sha256_file(payload / "report.json")
            or result["report_bytes"] != (payload / "report.json").stat().st_size
            or report["schema"] != "pcb-gnn.field-probe-api-report.v1"
            or report["fixture"] != fixture or data["fixture"] != fixture
            or any(result[k] is not False or report[k] is not False for k in c.CLOSED)
            or result["synthetic_probe_elements_only"] is not True or report["synthetic_probe_elements_only"] is not True
            or report["original_state_unchanged"] is not True
            or not isinstance(report["gmsh_build_options"],str) or not report["gmsh_build_options"]
            or report["files_sha256"] != {name+".json":sha256_file(payload / (name+".json")) for name in NAMES-{"report"}}):
        raise ValueError("field probe report identity/bytes/scope differs")
    expected = edge.sizing_policy(fixture["boxes_mm"],cfg["policy"],probe_cfg,p["mesh"])
    edge.validate_sizing(sizing,expected)
    # This is only the frozen tiny synthetic fixture, never an actual layout.
    points = edge.probe_points(fixture["boxes_mm"],fixture["domain_mm"],expected,probe_cfg)
    if len(points) > cfg["fixture_points_max"]:
        raise ValueError("synthetic probe point cap exceeded")
    tags = list(range(1,len(points)+1))
    original = before["session"]
    if (original["current_model"] != "tcad_field_probe_fixture" or original["views"]
            or original["models"].count(original["current_model"]) != 1 or TEMP_MODEL in original["models"]
            or before != data["after"] or any(before["mesh"][k] for k in ("node_tags","coordinates_mm","parametric","element_types","element_tags","element_nodes"))
            or before["options"] != {**p["dielectric_cad"]["cad_options"],**expected["options"]}):
        raise ValueError("original model/CAD/options/empty-mesh restoration differs")
    wanted_fields = {"tags":[r["tag"] for r in sizing["distance_fields"]]+[sizing["minimum_tag"],sizing["background_tag"]],
        "expressions":[{"tag":r["tag"],"type":"MathEval","F":r["expression"]} for r in sizing["distance_fields"]],
        "minimum":{"tag":sizing["minimum_tag"],"type":"Min","FieldsList":[r["tag"] for r in sizing["distance_fields"]]},
        "threshold":{"tag":sizing["background_tag"],"type":"Threshold","settings":sizing["threshold_settings"]}}
    if before["fields"] != wanted_fields: raise ValueError("original native fields differ from requested sizing")
    scaffold = {"entities":[[0,1]],"node_tags":tags,"coordinates_mm":[v for point in points for v in point],
        "parametric":[],"element_types":[15],"element_tags":[tags],"element_nodes":[tags]}
    values = {}
    for stem,field in (("distance",sizing["minimum_tag"]),("size",sizing["background_tag"])):
        request = {"field_tag":field,"points_mm":points,"before":original,
            "temporary_model":TEMP_MODEL,"temporary_entity":[0,1],"point_element_type":15}
        out = data[stem+".view_after"]
        view = out["view_tag"]
        if (data[stem+".request"] != request or data[stem+".scaffold"] != scaffold
                or data[stem+".cleanup"] != original or out["scaffold_after"] != scaffold
                or type(view) is not int or view < 0 or out["returned_view"] != view
                or out["active"] != {"current_model":original["current_model"],"models":[*original["models"],TEMP_MODEL],"views":[view]}
                or validate_data(data[stem+".view_before"],tags) != [-12345.]*len(tags)):
            raise ValueError("native model-backed probe stage closure differs")
        values[stem] = validate_data(out["data"],tags)
    observed = data["comparison"]
    if (observed != comparison(points,sizing,probe_cfg,values["distance"],values["size"])
            or report["point_count"] != len(points) or report["comparison_sha256"] != sha256_json(observed)):
        raise ValueError("native field comparison/raw-value binding differs")
    edge.validate_probe(observed,sizing,probe_cfg)
    if not c.bounded(result["elapsed_s"],cfg["worker_timeout_s"]) or not c.bounded(result["peak_rss_gib"],cfg["rss_gib_max"]):
        raise ValueError("field probe worker resource cap differs")


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
        raise ValueError("field probe API attempt path mismatch")
    if any(path.is_symlink() for path in directory.iterdir()):
        raise ValueError("unsafe field probe API attempt member")
    record = c.read_json(directory / "attempt.json")
    if any(record.get(k) != v for k, v in c.identity().items()) or record["runtime"] != expected_runtime(p):
        raise ValueError("field probe API attempt source/runtime mismatch")
    job = record["scheduler"]["JobId"]
    if directory != c.attempt_directory(job):
        raise ValueError("field probe API attempt path/job mismatch")
    prefix = p[c.PHASE]["modes"][:len(record["modes"])]
    if set(record["modes"]) != set(prefix) or any(record["modes"][m]["passed"] is not True for m in prefix[:-1]):
        raise ValueError("field probe API mode sequence skipped mode/failure")
    expected = {"attempt.json"}
    for mode, arm in record["modes"].items():
        files = mode_files(directory, mode)
        expected.update(name.split("/")[0] for name in files)
        if (directory / f"{mode}.payload").exists(): expected.add(f"{mode}.payload")
        expected.add(f"{mode}.json")
        if arm != c.read_json(directory / f"{mode}.json") or arm["mode"] != mode or type(arm["passed"]) is not bool or arm["files_sha256"] != files:
            raise ValueError("field probe API mode receipt/hash mismatch")
        if arm["passed"]:
            limits = p["worker_limits"][mode]
            if arm["returncode"] != 0 or arm["failure"] is not None or not c.bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not c.bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
                raise ValueError("field probe API parent cap/exit mismatch")
            if result_from_log(directory / f"{mode}.stdout") != arm["result"]:
                raise ValueError("field probe API result differs from log")
            validate_result(arm["result"], mode, p, job, directory)
        elif not isinstance(arm["failure"], str) or not arm["failure"]:
            raise ValueError("field probe API failed mode needs explicit failure")
    if {f.name for f in directory.iterdir()} != expected:
        raise ValueError("field probe API attempt file closure mismatch")
    if any(record.get(k) is not v for k, v in c.assessment(record, p).items()):
        raise ValueError("field probe API assessment mismatch")
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
