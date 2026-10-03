#!/usr/bin/env python3
"""Preserve the first seven-arm AMG attempt; scalar/metadata checks, no solving."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

import tcad_cps_amg_feasibility as contract
from archive_tcad_cps_amg_diagnostic_v1 import safe_path
from run_tcad_cps_amg_feasibility import expected_runtime
from run_tcad_cps_reference import accounting, result_from_log, terminal_success
from geometry_contract import geometry_sha256
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = contract.ROOT
BASE = contract.BASE
COMMIT = "b8d4b891d15d4dc7c261e92c310bc3273218daa6"
LOCK_SHA = "00f5b0f6b9d825597286edcb2e51ae0ac3c9bb1b557c6f33169c79ad24d31906"
JOBS = {"smoke": "7650458", "feasibility": "7650556", "finalize": "7650557"}
MANIFEST = BASE / "archive/feasibility_7650556/manifest.json"
SMOKE_SHA = "dae0319e5a94fbaad92b92d54405089c9b999a85a2bcd2849d3c2e1e815dc2de"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED"}


def directory(phase):
    return BASE / phase / f"job_{JOBS[phase]}"


def expected_identity():
    return {"source_commit": COMMIT, "lock_sha256": LOCK_SHA,
            "protocol_sha256": sha256_file(contract.ROOT / contract.PROTOCOL),
            "panel_sha256": sha256_file(contract.ROOT / contract.PANEL)}


def check_identity(record, phase, p):
    if any(record.get(k) != v for k, v in expected_identity().items()):
        raise ValueError("AMG terminal source identity mismatch")
    if record["scheduler"]["JobId"] != JOBS[phase] or record["runtime"] != expected_runtime(p):
        raise ValueError("AMG terminal job/runtime mismatch")


def check_accounting(rows):
    if len(rows) != 3 or {r["JobID"] for r in rows} != set(JOBS.values()):
        raise ValueError("AMG terminal accounting coverage mismatch")
    for row in rows:
        if row["State"].split()[0] not in TERMINAL or row["Restarts"] != "0":
            raise ValueError("zero-restart terminal accounting required")
    if not terminal_success(rows, JOBS["smoke"]):
        raise ValueError("admitted smoke must remain terminal successful")


def review_attempt(root, phase, p):
    relative = directory(phase)
    record = contract.read_json(safe_path(root, relative / "attempt.json"))
    check_identity(record, phase, p)
    if record["phase"] != phase or record["layout_id"] != ("smoke" if phase == "smoke" else 597):
        raise ValueError("AMG terminal phase/layout mismatch")
    specs = {a["name"]: a for a in contract.arms_for(phase, p)}
    prefix = list(specs)[:len(record["arms"])]
    if set(record["arms"]) != set(prefix) or any(record["arms"][n]["passed"] is not True for n in prefix[:-1]):
        raise ValueError("AMG terminal arm coverage skips a failure or arm")
    members = {"attempt.json", *(f"{n}.{suffix}" for n in prefix for suffix in ("json", "stdout", "stderr"))}
    if phase == "smoke":
        members |= {"terminal.json", f"tcad_amg_smoke_{JOBS['smoke']}.out", f"tcad_amg_smoke_{JOBS['smoke']}.err"}
    if {f.name for f in safe_path(root, relative).iterdir()} != members:
        raise ValueError("AMG terminal attempt file closure mismatch")
    for name in members:
        if not safe_path(root, relative / name).is_file():
            raise ValueError("non-file AMG terminal member")
    for name in prefix:
        arm = record["arms"][name]
        if arm != contract.read_json(root / relative / f"{name}.json") or arm["arm"] != specs[name]:
            raise ValueError("AMG terminal arm receipt mismatch")
        if not isinstance(arm["passed"], bool) or set(arm["files_sha256"]) != {f"{name}.stdout", f"{name}.stderr"}:
            raise ValueError("AMG terminal raw-log closure mismatch")
        for filename, digest in arm["files_sha256"].items():
            if sha256_file(root / relative / filename) != digest:
                raise ValueError("AMG terminal raw-log hash mismatch")
        if not arm["passed"]:
            continue
        result = result_from_log(root / relative / f"{name}.stdout")
        check_identity(result, phase, p)
        layout_id, layout, spec = contract.inputs(phase, name, p)
        if result != arm["result"] or (result["layout_id"], result["geometry_sha256"], result["arm"]) != (layout_id, geometry_sha256(layout), spec):
            raise ValueError("AMG terminal result/geometry mismatch")
        if result["mesh_policy_sha256"] != sha256_json(result["mesh_policy"]) or not contract.assess_result(result, p, phase):
            raise ValueError("AMG terminal worker numerical gate mismatch")
        limits = p["resources"][phase]
        bounded = lambda value, cap: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= cap
        if arm["returncode"] != 0 or arm["failure"] is not None or not bounded(arm["elapsed_s"], limits["worker_timeout_s"]) or not bounded(arm["observed_peak_rss_gib"], limits["rss_gib_max"]):
            raise ValueError("AMG terminal parent limit/exit mismatch")
    passed = record["failure"] is None and set(record["arms"]) == set(specs) and all(a["passed"] for a in record["arms"].values())
    if record["passed"] is not passed:
        raise ValueError("AMG terminal completion differs from coverage")
    return record, {relative / name for name in members}


def review(root, rows, *, smoke_root=None):
    """Reconstruct only seven scalar comparisons, never mesh/field observations."""
    contract.check_source(execution=False)
    if sha256_file(contract.ROOT / contract.LOCK) != LOCK_SHA:
        raise ValueError("AMG archive source lock changed")
    check_accounting(rows)
    p = contract.protocol()
    smoke_root = root if smoke_root is None else smoke_root
    smoke, smoke_members = review_attempt(smoke_root, "smoke", p)
    smoke_sha = sha256_file(smoke_root / directory("smoke") / "attempt.json")
    if smoke_sha != SMOKE_SHA or not smoke["passed"]:
        raise ValueError("AMG admitted smoke receipt changed")
    terminal = contract.read_json(smoke_root / directory("smoke") / "terminal.json")
    smoke_row = next(r for r in rows if r["JobID"] == JOBS["smoke"])
    for key, expected in {"job_id": JOBS["smoke"], "source_commit": COMMIT,
                          "lock_sha256": LOCK_SHA, "attempt_sha256": smoke_sha,
                          "state": "COMPLETED", "exit_code": "0:0", "restarts": 0,
                          "elapsed_s": int(smoke_row["ElapsedRaw"]), "allocated_cpus": int(smoke_row["AllocCPUS"]),
                          "node": smoke_row["NodeList"], "requested_memory": smoke_row["ReqMem"],
                          "same_matrix_backend_check_passed": True, "physical_validation": False,
                          "mesh_convergence_established": False}.items():
        if terminal.get(key) != expected:
            raise ValueError("AMG smoke terminal receipt mismatch")
    attempt, members = review_attempt(root, "feasibility", p)
    smoke_binding = {"job_id": JOBS["smoke"], "attempt_sha256": smoke_sha, "accounting": [smoke_row]}
    if attempt.get("smoke") != smoke_binding:
        raise ValueError("AMG feasibility prerequisite binding mismatch")
    summary_dir = safe_path(root, directory("finalize"))
    if {f.name for f in summary_dir.iterdir()} != {"summary.json", "sacct.txt"}:
        raise ValueError("AMG finalizer file closure mismatch")
    summary_path = safe_path(root, directory("finalize") / "summary.json")
    accounting_path = safe_path(root, directory("finalize") / "sacct.txt")
    summary = contract.read_json(summary_path)
    check_identity(summary, "finalize", p)
    feasibility_row = next(r for r in rows if r["JobID"] == JOBS["feasibility"])
    if summary["feasibility_job_id"] != JOBS["feasibility"] or summary["attempt_sha256"] != sha256_file(root / directory("feasibility") / "attempt.json"):
        raise ValueError("AMG finalizer attempt binding mismatch")
    if summary.get("smoke") != smoke_binding or summary["accounting"] != [feasibility_row] or summary["accounting_sha256"] != sha256_file(accounting_path):
        raise ValueError("AMG finalizer accounting/prerequisite mismatch")
    fields = ["JobID", "State", "ExitCode", "Restarts", "ElapsedRaw", "AllocCPUS", "ReqMem", "NodeList"]
    parsed = [dict(zip(fields, line.split("|"))) for line in accounting_path.read_text().splitlines() if line.strip()]
    if parsed != summary["accounting"]:
        raise ValueError("AMG saved scheduler log does not reconstruct")
    observed = {n: {"passed": a["passed"], "failure": a["failure"]} for n, a in attempt["arms"].items()}
    if summary.get("observed_arms") != observed:
        raise ValueError("AMG finalizer observed-arm mismatch")
    successful = terminal_success(rows, JOBS["feasibility"])
    expected = contract.assess_feasibility(attempt if successful else {}, p)
    if any(summary.get(k) != v for k, v in expected.items()):
        raise ValueError("AMG sensitivity/qualification summary does not reconstruct")
    errors = [] if successful else ["AMG feasibility did not complete with zero exit and restarts"]
    if summary["errors"] != errors or successful != attempt["passed"]:
        raise ValueError("AMG terminal completion/error disagreement")
    final_row = next(r for r in rows if r["JobID"] == JOBS["finalize"])
    final_expected = ("COMPLETED", "0:0") if summary["complete"] and not errors else ("FAILED", "2:0")
    if (final_row["State"], final_row["ExitCode"]) != final_expected:
        raise ValueError("AMG finalizer terminal state differs from summary")
    members |= {directory("finalize") / name for name in ("summary.json", "sacct.txt")}
    return {"attempt_sha256": summary["attempt_sha256"], "summary_sha256": sha256_file(summary_path),
            "observed_arms": observed, **expected}, members, smoke_members


def log_pairs():
    return [(Path("logs") / f"tcad_amg_{phase}_{JOBS[phase]}.{suffix}",
             MANIFEST.parent / "logs" / f"tcad_amg_{phase}_{JOBS[phase]}.{suffix}")
            for phase in ("feasibility", "finalize") for suffix in ("out", "err")]


def check_archive():
    manifest = contract.read_json(safe_path(ROOT, MANIFEST))
    diagnosis, members, smoke_members = review(ROOT, manifest["accounting"])
    expected = members | smoke_members | {dst for _, dst in log_pairs()}
    if set(manifest["files_sha256"]) != {str(p) for p in expected} or manifest["source_commit"] != COMMIT or manifest["lock_sha256"] != LOCK_SHA:
        raise ValueError("AMG archive identity/member closure mismatch")
    for path, digest in manifest["files_sha256"].items():
        if sha256_file(safe_path(ROOT, path)) != digest:
            raise ValueError("AMG archive member hash mismatch")
    log_dir = safe_path(ROOT, MANIFEST.parent / "logs")
    if {f.name for f in log_dir.iterdir()} != {dst.name for _, dst in log_pairs()}:
        raise ValueError("AMG scheduler-log file closure mismatch")
    if manifest["diagnosis"] != diagnosis:
        raise ValueError("AMG archive diagnosis mismatch")
    return manifest


def collect(source):
    source = source.resolve(strict=True)
    if ROOT not in source.parents or source == ROOT:
        raise ValueError("source must be a separate worktree inside this workspace")
    if any(safe_path(ROOT, path).exists() for path in (MANIFEST.parent, directory("feasibility"), directory("finalize"))):
        raise ValueError("refusing to overwrite AMG terminal archive")
    rows = [row for phase in JOBS for row in accounting(JOBS[phase])[1]]
    diagnosis, members, smoke_members = review(source, rows, smoke_root=ROOT)
    pairs = [(p, p) for p in sorted(members)] + log_pairs()
    for src, dst in pairs:
        if not safe_path(source, src).is_file() or safe_path(ROOT, dst).exists():
            raise ValueError("missing source or archive overwrite")
    for src, dst in pairs:
        (ROOT / dst).parent.mkdir(parents=True, exist_ok=True)
        with (source / src).open("rb") as reader, (ROOT / dst).open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if sha256_file(source / src) != sha256_file(ROOT / dst):
            raise ValueError("AMG archive copy changed bytes")
    paths = {dst for _, dst in pairs} | smoke_members
    atomic_write_json(ROOT / MANIFEST, {"schema": "pcb-gnn.tcad-amg-feasibility-archive.v1",
        "source_commit": COMMIT, "lock_sha256": LOCK_SHA, "accounting": rows,
        "diagnosis": diagnosis, "scope": "single-sentinel finite sensitivity only; no reference or training admission",
        "files_sha256": {str(p): sha256_file(ROOT / p) for p in sorted(paths)}})
    return check_archive()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source-root", type=Path)
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check_archive() if args.check else collect(args.source_root)
    print(json.dumps({"files": len(result["files_sha256"]), "archive_sha256": sha256_file(ROOT / MANIFEST),
                      "complete": result["diagnosis"]["complete"], "feasibility_passed": result["diagnosis"]["feasibility_passed"]}))
