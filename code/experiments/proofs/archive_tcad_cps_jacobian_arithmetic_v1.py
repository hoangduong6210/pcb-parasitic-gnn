#!/usr/bin/env python3
"""Byte-only terminal preservation of complete/partial arithmetic reports."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import tcad_cps_jacobian_arithmetic as contract
from archive_tcad_cps_amg_diagnostic_v1 import safe_path
from run_tcad_cps_reference import accounting
from scientific_artifact import atomic_write_json, sha256_file, sha256_json

ROOT = contract.ROOT
JOB = "7652241"
COMMIT = "8168208a1248befcaf72a56ed139bf17d230ca56"
LOCK_SHA = "1bce5b7db75abf05ae4a954044e43880ba173a76791727f80c4a8914aae18278"
DIRECTORY = contract.BASE / f"job_{JOB}"
MANIFEST = contract.BASE / f"archive/job_{JOB}/manifest.json"
SUBMISSION = contract.BASE / "submission.json"
COLUMNS = ["JobID", "State", "ExitCode", "Restarts", "ElapsedRaw", "AllocCPUS", "ReqMem", "NodeList"]
REVIEW_PROGRAM = """import json,sys
sys.path.insert(0, 'code/experiments/proofs')
from tcad_cps_jacobian_arithmetic import check_source,attempt_directory,protocol
from run_tcad_cps_jacobian_arithmetic import validate_attempt
check_source(execution=False)
print(json.dumps(validate_attempt(attempt_directory(sys.argv[1]),protocol()),allow_nan=False))
"""


def review_attempt(root):
    if sha256_file(safe_path(root, contract.LOCK)) != LOCK_SHA:
        raise ValueError("arithmetic archive source-lock identity mismatch")
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    env.update(PCB_TCAD_SOURCE_COMMIT=COMMIT, PCB_TCAD_LOCK_SHA256=LOCK_SHA, PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run([sys.executable, "-c", REVIEW_PROGRAM, JOB], cwd=root,
        env=env, capture_output=True, text=True, check=True, timeout=240)
    return json.loads(completed.stdout)


def check_accounting(record, rows):
    if len(rows) != 1 or set(rows[0]) != set(COLUMNS):
        raise ValueError("arithmetic archive exact accounting closure required")
    row = rows[0]
    state = ("COMPLETED", "0:0") if record["diagnostic_passed"] else ("FAILED", "2:0")
    if (row["JobID"], row["Restarts"], row["State"], row["ExitCode"]) != (JOB, "0", *state):
        raise ValueError("arithmetic archive terminal accounting disagrees with outcome")
    scheduler = record["scheduler"]
    if row["NodeList"] != scheduler["NodeList"] or row["AllocCPUS"] != scheduler["NumCPUs"] or row["ReqMem"] != "8G":
        raise ValueError("arithmetic archive accounting/allocation mismatch")
    if not row["ElapsedRaw"].isdigit() or not 0 < int(row["ElapsedRaw"]) <= 900:
        raise ValueError("arithmetic archive accounting elapsed outside allocation")


def log_pairs():
    return [(Path("logs") / f"tcad_jacobian_arithmetic_{JOB}.{suffix}",
             MANIFEST.parent / "logs" / f"tcad_jacobian_arithmetic_{JOB}.{suffix}") for suffix in ("out", "err")]


def members(record):
    paths = {DIRECTORY / "attempt.json"}
    for mode, arm in record["modes"].items():
        paths.add(DIRECTORY / f"{mode}.json")
        for name in arm["files_sha256"]:
            part = Path(name)
            if part.is_absolute() or ".." in part.parts or not part.parts or str(part) not in (f"{mode}.stdout", f"{mode}.stderr", f"{mode}.report.json"):
                raise ValueError("arithmetic archive unsafe payload member")
            paths.add(DIRECTORY / part)
    return paths


def diagnosis(record):
    return {**contract.assessment(record, contract.protocol()),
        "observed_modes": {m: {"passed": r["passed"], "failure": r["failure"]} for m, r in record["modes"].items()}}


def parse_accounting(raw):
    rows = []
    for line in raw.strip().splitlines():
        values = line.split("|")
        if len(values) != len(COLUMNS):
            raise ValueError("arithmetic archive malformed raw accounting")
        rows.append(dict(zip(COLUMNS, values)))
    return rows


def check_submission():
    receipt = contract.read_json(safe_path(ROOT, SUBMISSION))
    if any(receipt[k] != v for k, v in {"job_id": JOB, "source_commit": COMMIT,
        "lock_sha256": LOCK_SHA, "protocol_sha256": sha256_file(ROOT / contract.PROTOCOL)}.items()):
        raise ValueError("arithmetic archive submission identity mismatch")


def check_archive():
    manifest = contract.read_json(safe_path(ROOT, MANIFEST))
    record = review_attempt(ROOT)
    expected = members(record) | {SUBMISSION, MANIFEST.parent / "sacct.txt", *(dst for _, dst in log_pairs())}
    if set(manifest["files_sha256"]) != {str(p) for p in expected} or manifest["source_commit"] != COMMIT or manifest["lock_sha256"] != LOCK_SHA:
        raise ValueError("arithmetic archive identity/member closure mismatch")
    for path, digest in manifest["files_sha256"].items():
        member = safe_path(ROOT, path)
        if not member.is_file() or sha256_file(member) != digest:
            raise ValueError("arithmetic archive member bytes changed")
    if {f.name for f in safe_path(ROOT, MANIFEST.parent).iterdir()} != {"manifest.json", "sacct.txt", "logs"}:
        raise ValueError("arithmetic archive extra metadata member")
    if {f.name for f in safe_path(ROOT, MANIFEST.parent / "logs").iterdir()} != {dst.name for _, dst in log_pairs()}:
        raise ValueError("arithmetic archive scheduler-log closure mismatch")
    rows = parse_accounting((ROOT / MANIFEST.parent / "sacct.txt").read_text())
    if rows != manifest["accounting"]:
        raise ValueError("arithmetic archive parsed/raw accounting mismatch")
    check_accounting(record, rows)
    check_submission()
    if sha256_json(manifest["diagnosis"]) != sha256_json(diagnosis(record)) or manifest["attempt_sha256"] != sha256_file(ROOT / DIRECTORY / "attempt.json"):
        raise ValueError("arithmetic archive assessment mismatch")
    return manifest


def collect(source):
    if source.is_symlink():
        raise ValueError("symlinked execution root")
    source = source.resolve(strict=True)
    if ROOT not in source.parents or source == ROOT:
        raise ValueError("source must be a separate worktree inside this workspace")
    if any(safe_path(ROOT, p).exists() for p in (DIRECTORY, MANIFEST.parent)):
        raise ValueError("refusing to overwrite arithmetic archive")
    check_submission()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, check=True, capture_output=True, text=True).stdout.strip()
    if head != COMMIT:
        raise ValueError("arithmetic archive execution commit mismatch")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=source, check=True, capture_output=True)
    record = review_attempt(source)
    raw, rows = accounting(JOB)
    if parse_accounting(raw) != rows:
        raise ValueError("arithmetic archive scheduler parse mismatch")
    check_accounting(record, rows)
    pairs = [(p, p) for p in sorted(members(record))] + log_pairs()
    before = {}
    for src, dst in pairs:
        if not safe_path(source, src).is_file() or safe_path(ROOT, dst).exists():
            raise ValueError("missing source or archive overwrite")
        before[src] = sha256_file(source / src)
    for src, dst in pairs:
        (ROOT / dst).parent.mkdir(parents=True, exist_ok=True)
        with (source / src).open("rb") as reader, (ROOT / dst).open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if sha256_file(source / src) != before[src] or sha256_file(ROOT / dst) != before[src]:
            raise ValueError("arithmetic archive copy changed bytes")
    with (ROOT / MANIFEST.parent / "sacct.txt").open("x") as stream:
        stream.write(raw + "\n")
    paths = {dst for _, dst in pairs} | {SUBMISSION, MANIFEST.parent / "sacct.txt"}
    atomic_write_json(ROOT / MANIFEST, {"schema": "pcb-gnn.tcad-cps-jacobian-arithmetic-archive.v1",
        "source_commit": COMMIT, "lock_sha256": LOCK_SHA, "accounting": rows,
        "attempt_sha256": before[DIRECTORY / "attempt.json"], "diagnosis": diagnosis(record),
        "scope": "byte-preserved saved-packet diagnosis; no new numerical replay, field or reference qualification",
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
        "complete": result["diagnosis"]["complete"], "diagnostic_passed": result["diagnosis"]["diagnostic_passed"]}))
