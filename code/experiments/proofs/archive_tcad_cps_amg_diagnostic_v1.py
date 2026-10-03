#!/usr/bin/env python3
"""Byte-preserved terminal diagnostic archive; metadata checks, no solver replay."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path

import tcad_cps_amg_diagnostic as diagnostic
from run_tcad_cps_reference import accounting, result_from_log, terminal_success
from geometry_contract import geometry_sha256
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = diagnostic.ROOT
BASE = diagnostic.BASE
JOB = "7647850"
DIRECTORY = BASE / f"job_{JOB}"
MANIFEST = BASE / f"archive/job_{JOB}/manifest.json"
COMMIT = "396e51f879ae8007de35d3301be284a519aabf48"
LOCK_SHA = "7ff24ed07bc4233318a5ec9ebef8a3b552c75b37f13ca607966ec2690ecfbec3"
ATTEMPT_SHA = "09c711ed345a51b7b54a3d5cd48e1fc0bfc746c6662d2dde00cb785da3141275"
MEMBERS = {"attempt.json", *(f"{mode}.{suffix}" for mode in ("toy", "local0") for suffix in ("json", "stdout", "stderr"))}


def safe_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe archive path")
    target = root / path
    for parent in [target, *target.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlinked archive path")
    return target


def review(root):
    diagnostic.check_source(execution=False)
    p = diagnostic.protocol()
    directory = safe_path(root, DIRECTORY)
    if {f.name for f in directory.iterdir()} != MEMBERS:
        raise ValueError("diagnostic file closure differs from expected members")
    for name in MEMBERS:
        if not safe_path(root, DIRECTORY / name).is_file():
            raise ValueError("non-file diagnostic member")
    if sha256_file(directory / "attempt.json") != ATTEMPT_SHA:
        raise ValueError("terminal diagnostic attempt changed")
    record = diagnostic.read_json(directory / "attempt.json")
    expected = {"source_commit": COMMIT, "lock_sha256": LOCK_SHA,
                "protocol_sha256": sha256_file(ROOT / diagnostic.PROTOCOL),
                "panel_sha256": sha256_file(ROOT / diagnostic.recovery.PANEL)}
    if any(record.get(k) != v for k, v in expected.items()) or record["scheduler"]["JobId"] != JOB:
        raise ValueError("diagnostic attempt identity mismatch")
    if record["passed"] is not True or record["failure"] is not None or set(record["modes"]) != {"toy", "local0"}:
        raise ValueError("incomplete diagnostic")
    if any(record[k] is not False for k in ("reference_qualified", "claim_eligible", "training_may_start", "automatic_feasibility_expansion")):
        raise ValueError("diagnostic claim boundary changed")
    expected_runtime = {"python": p["runtime"]["python"], "packages": p["runtime"]["packages"],
                        "threads": p["runtime"]["thread_environment"]}
    if record["runtime"] != expected_runtime:
        raise ValueError("diagnostic runtime mismatch")
    for mode, arm in record["modes"].items():
        if arm != diagnostic.read_json(directory / f"{mode}.json") or arm["passed"] is not True or arm["returncode"] != 0 or arm["failure"] is not None:
            raise ValueError("diagnostic arm receipt mismatch")
        if set(arm["files_sha256"]) != {f"{mode}.stdout", f"{mode}.stderr"}:
            raise ValueError("diagnostic raw-log closure mismatch")
        for name, digest in arm["files_sha256"].items():
            if sha256_file(directory / name) != digest:
                raise ValueError("diagnostic raw-log hash mismatch")
        result = result_from_log(directory / f"{mode}.stdout")
        layout_id, layout, specification = diagnostic.mode_input(mode, p)
        if result != arm["result"] or not diagnostic.assess_result(result, mode, p):
            raise ValueError("diagnostic saved result does not reconstruct")
        if any(result.get(k) != v for k, v in expected.items()) or result["scheduler"]["JobId"] != JOB:
            raise ValueError("diagnostic worker source/job mismatch")
        if (result["mode"], result["layout_id"], result["arm"], result["geometry_sha256"]) != (mode, layout_id, specification, geometry_sha256(layout)):
            raise ValueError("diagnostic geometry/mode mismatch")
        if result["runtime"] != expected_runtime or result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"]):
            raise ValueError("diagnostic runtime/mesh-policy mismatch")
        limits = p["worker_limits"][mode]
        if arm["elapsed_s"] > limits["worker_timeout_s"] or arm["observed_peak_rss_gib"] > limits["rss_gib_max"]:
            raise ValueError("diagnostic parent resource limit exceeded")
    return record


def check_archive():
    manifest = diagnostic.read_json(ROOT / MANIFEST)
    expected = {str(DIRECTORY / name) for name in MEMBERS}
    expected |= {str(MANIFEST.parent / "logs" / f"tcad_amg_diagnostic_{JOB}.{suffix}") for suffix in ("out", "err")}
    if set(manifest["files_sha256"]) != expected or manifest["source_commit"] != COMMIT or manifest["lock_sha256"] != LOCK_SHA:
        raise ValueError("diagnostic archive identity/closure mismatch")
    for path, digest in manifest["files_sha256"].items():
        if sha256_file(safe_path(ROOT, path)) != digest:
            raise ValueError("diagnostic archive member hash mismatch")
    if len(manifest["accounting"]) != 1 or not terminal_success(manifest["accounting"], JOB):
        raise ValueError("diagnostic successful terminal accounting missing")
    review(ROOT)
    return manifest


def collect(source):
    source = source.resolve(strict=True)
    if ROOT not in source.parents or source == ROOT:
        raise ValueError("source must be a separate worktree inside this workspace")
    review(source)
    rows = accounting(JOB)[1]
    if len(rows) != 1 or not terminal_success(rows, JOB):
        raise ValueError("diagnostic terminal success required")
    pairs = [(DIRECTORY / name, DIRECTORY / name) for name in sorted(MEMBERS)]
    pairs += [(Path("logs") / f"tcad_amg_diagnostic_{JOB}.{suffix}",
               MANIFEST.parent / "logs" / f"tcad_amg_diagnostic_{JOB}.{suffix}") for suffix in ("out", "err")]
    if safe_path(ROOT, MANIFEST).exists() or safe_path(ROOT, DIRECTORY).exists():
        raise ValueError("refusing to overwrite diagnostic archive")
    for src, dst in pairs:
        if not safe_path(source, src).is_file() or safe_path(ROOT, dst).exists():
            raise ValueError("missing source or archive overwrite")
    for src, dst in pairs:
        (ROOT / dst).parent.mkdir(parents=True, exist_ok=True)
        with (source / src).open("rb") as reader, (ROOT / dst).open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if sha256_file(source / src) != sha256_file(ROOT / dst):
            raise ValueError("archive copy changed bytes")
    atomic_write_json(ROOT / MANIFEST, {"schema": "pcb-gnn.tcad-amg-diagnostic-archive.v1",
        "source_commit": COMMIT, "lock_sha256": LOCK_SHA, "attempt_sha256": ATTEMPT_SHA,
        "accounting": rows, "scope": "terminal same-matrix backend checks only; no reference qualification",
        "files_sha256": {str(dst): sha256_file(ROOT / dst) for _, dst in pairs}})
    return check_archive()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check_archive() if args.check else collect(args.source_root)
    print(json.dumps({"files": len(result["files_sha256"]), "archive_sha256": sha256_file(ROOT / MANIFEST)}))
