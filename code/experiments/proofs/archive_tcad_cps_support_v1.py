#!/usr/bin/env python3
"""Collect the rejected support attempt without numerical replay or overwrite."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path

import tcad_cps_support_recovery as recovery
from run_tcad_cps_reference import accounting
from scientific_artifact import atomic_write_json, sha256_file

ROOT = recovery.ROOT
BASE = recovery.BASE
MANIFEST = BASE / "archive/feasibility_7647612/manifest.json"
COMMIT = "546fb480a451e143178c49b1fa3e4b3ecd39f774"
LOCK_SHA = "b79411aeb3e327a96b61c0a746fae3ec2d4774542677eaff8cafa9616f45fd39"
ATTEMPT = BASE / "feasibility/job_7647612/attempt.json"
SUMMARY = BASE / "finalize/job_7647619/summary.json"
ATTEMPT_SHA = "5ca56cb413484b0301dcd29e5e3cc76c1ccfdfedb4dbd90bb815b74056ed426b"
SUMMARY_SHA = "5ec5ad7653d0f075efdcbd25a6234b6896c63b76d7f163a63e8b1838d26887eb"


def review(root):
    recovery.check_source(execution=False)
    for path, digest in ((ATTEMPT, ATTEMPT_SHA), (SUMMARY, SUMMARY_SHA)):
        if sha256_file(root / path) != digest:
            raise ValueError("terminal support receipt differs from inspected bytes")
    attempt, summary = (recovery.read_json(root / p) for p in (ATTEMPT, SUMMARY))
    for receipt in (attempt, summary):
        if receipt["source_commit"] != COMMIT or receipt["lock_sha256"] != LOCK_SHA:
            raise ValueError("support source mismatch")
    if attempt["layout_id"] != 597 or attempt["passed"] or set(attempt["arms"]) != {"local0"}:
        raise ValueError("unexpected support coverage")
    arm = attempt["arms"]["local0"]
    if arm != recovery.read_json(root / ATTEMPT.parent / "local0.json") or arm["passed"]:
        raise ValueError("failed arm mismatch")
    if set(arm["files_sha256"]) != {"local0.stdout", "local0.stderr"}:
        raise ValueError("unexpected support logs")
    for name, digest in arm["files_sha256"].items():
        if sha256_file(root / ATTEMPT.parent / name) != digest:
            raise ValueError("support raw-log mismatch")
    if summary["complete"] or summary["feasibility_passed"] or summary["comparisons"]:
        raise ValueError("incomplete support study was relabelled")
    if summary["attempt_sha256"] != ATTEMPT_SHA or summary["claim_eligible"]:
        raise ValueError("finalizer binding mismatch")
    stdout = (root / ATTEMPT.parent / "local0.stdout").read_text()
    stderr = (root / ATTEMPT.parent / "local0.stderr").read_text()
    stages = [json.loads(line[6:]) for line in stdout.splitlines() if line.startswith("STAGE=")]
    by_name = {s["stage"]: s for s in stages}
    if len(by_name) != len(stages) or "RESULT=" in stdout or "cg_solve_started" in by_name:
        raise ValueError("unexpected support execution sequence")
    if "ValueError: frozen operator_complexity_max exceeded" not in stderr:
        raise ValueError("unexpected support failure")
    return {"mesh_nodes": by_name["mesh_generated"]["n_nodes"],
            "mesh_tetrahedra": by_name["mesh_extracted"]["n_tetrahedra"],
            "n_free": by_name["system_condensed"]["n_free"],
            "nnz": by_name["system_condensed"]["nnz"],
            "system_sha256": by_name["solver_input_fingerprinted"]["system_sha256"],
            "operator_complexity": by_name["amg_setup_completed"]["operator_complexity"],
            "worker_elapsed_s": arm["elapsed_s"], "peak_rss_gib": arm["observed_peak_rss_gib"],
            "failure": "operator_complexity_max exceeded before CG; no capacitance"}


def check_archive():
    manifest = recovery.read_json(ROOT / MANIFEST)
    for name, digest in manifest["files_sha256"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or (ROOT / path).is_symlink():
            raise ValueError("unsafe archive member")
        if sha256_file(ROOT / path) != digest:
            raise ValueError("support archive mismatch")
    if manifest["diagnosis"] != review(ROOT):
        raise ValueError("support diagnosis does not reconstruct")
    expected = {"7647612", "7647619"}
    rows = manifest["accounting"]
    if len(rows) != 2 or {r["JobID"] for r in rows} != expected or any(
            (r["State"], r["ExitCode"], r["Restarts"]) != ("FAILED", "2:0", "0") for r in rows):
        raise ValueError("unexpected support terminal accounting")
    return manifest


def collect(source):
    source = source.resolve(strict=True)
    if ROOT not in source.parents or source == ROOT:
        raise ValueError("source must be a separate worktree inside this workspace")
    diagnosis = review(source)
    rows = accounting("7647612")[1] + accounting("7647619")[1]
    if len(rows) != 2 or {r["JobID"] for r in rows} != {"7647612", "7647619"} or any(
            (r["State"], r["ExitCode"], r["Restarts"]) != ("FAILED", "2:0", "0") for r in rows):
        raise ValueError("terminal failed accounting required")
    copies = []
    for directory in (ATTEMPT.parent, SUMMARY.parent):
        if (ROOT / directory).exists():
            raise ValueError("refusing to overwrite terminal directory")
        for path in (source / directory).rglob("*"):
            if path.is_symlink():
                raise ValueError("symlinked terminal artifact")
            if path.is_file():
                copies.append((path, ROOT / path.relative_to(source)))
    for phase, job in (("feasibility", "7647612"), ("finalize", "7647619")):
        for suffix in ("out", "err"):
            name = f"tcad_support_{phase}_{job}.{suffix}"
            copies.append((source / "logs" / name, ROOT / MANIFEST.parent / "logs" / name))
    if (ROOT / MANIFEST).exists():
        raise ValueError("refusing to overwrite support archive")
    for src, dst in copies:
        if src.is_symlink() or not src.is_file() or dst.exists():
            raise ValueError("unsafe copy or overwrite")
        for ancestor in dst.parents:
            if ancestor == ROOT:
                break
            if ancestor.is_symlink():
                raise ValueError("symlinked archive ancestor")
    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open("rb") as reader, dst.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if sha256_file(src) != sha256_file(dst):
            raise ValueError("copied artifact changed bytes")
    atomic_write_json(ROOT / MANIFEST, {
        "schema": "pcb-gnn.tcad-support-terminal-archive.v1", "source_commit": COMMIT,
        "lock_sha256": LOCK_SHA, "accounting": rows, "diagnosis": diagnosis,
        "scientific_status": "rejected incomplete study; archive does not repair it",
        "files_sha256": {str(dst.relative_to(ROOT)): sha256_file(dst) for _, dst in sorted(copies)},
    })
    return check_archive()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = check_archive() if args.check else collect(args.source_root)
    print(json.dumps({"files": len(manifest["files_sha256"]), "archive_sha256": sha256_file(ROOT / MANIFEST)}))
