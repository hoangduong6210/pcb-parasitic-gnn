#!/usr/bin/env python3
"""Finalize exact R3/R4 coverage from externally pinned accepted artifact sets."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    load_json,
    require_file_sha256,
    sha256_file,
)
from plan_corpus_v4_cps_resume import (  # noqa: E402
    ACCEPTED_SCHEMA,
    resolve_repo_path,
    validate_task_artifact,
)
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    EXECUTION_SOURCE_NAMES,
    scheduler_resource_contract_matches,
    validate_execution_lock,
    validate_frozen_inputs,
)
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402


SCHEMA = "pcb-gnn.cps-multifidelity-final.v1"
SOURCE_NAMES = EXECUTION_SOURCE_NAMES


def load_accepted_set(
    path: Path,
    expected_sha256: str,
    manifest_rows: list[dict[str, Any]],
    *,
    plan_sha256: str,
    protocol_sha256: str,
    manifest_sha256: str,
    protocol: dict[str, Any],
    execution_lock: dict[str, Any],
    execution_lock_sha256: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    require_file_sha256(path, expected_sha256, "accepted artifact set")
    artifact_set = load_json(path)
    if (
        artifact_set.get("schema") != ACCEPTED_SCHEMA
        or artifact_set.get("plan_sha256") != plan_sha256
        or artifact_set.get("protocol_sha256") != protocol_sha256
        or artifact_set.get("manifest_sha256") != manifest_sha256
        or artifact_set.get("execution_lock_sha256") != execution_lock_sha256
        or artifact_set.get("n_expected") != len(manifest_rows)
        or artifact_set.get("n_accepted") != len(manifest_rows)
    ):
        raise ValueError("accepted artifact set is incomplete or not canonical")
    entries = artifact_set.get("entries", [])
    if [entry.get("task_index") for entry in entries] != list(range(len(manifest_rows))):
        raise ValueError("accepted artifact set does not have exact dense coverage")
    payloads: list[dict[str, Any]] = []
    for entry, expected in zip(entries, manifest_rows):
        path = resolve_repo_path(entry["path"])
        require_file_sha256(path, entry["artifact_sha256"], entry["path"])
        payload = load_json(path)
        validate_task_artifact(
            payload,
            expected,
            plan_sha256=plan_sha256,
            protocol_sha256=protocol_sha256,
            manifest_sha256=manifest_sha256,
            protocol=protocol,
            execution_lock=execution_lock,
            execution_lock_sha256=execution_lock_sha256,
        )
        payloads.append(payload)
    return entries, payloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--r3-manifest", type=Path, required=True)
    parser.add_argument("--r4-manifest", type=Path, required=True)
    parser.add_argument("--r3-artifact-set", type=Path, required=True)
    parser.add_argument("--r3-artifact-set-sha256", required=True)
    parser.add_argument("--r4-artifact-set", type=Path, required=True)
    parser.add_argument("--r4-artifact-set-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("submit the multi-fidelity finalizer through SLURM")
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        raise SystemExit("refusing to overwrite a non-empty finalizer output directory")
    scheduler_query = subprocess.run(
        ["scontrol", "show", "job", "-o", os.environ["SLURM_JOB_ID"]],
        capture_output=True,
        check=False,
        text=True,
    )
    scheduler = {
        token.split("=", 1)[0]: token.split("=", 1)[1]
        for token in scheduler_query.stdout.split()
        if "=" in token
    }
    if (
        scheduler_query.returncode != 0
        or scheduler.get("JobState") not in {"RUNNING", "COMPLETING"}
        or scheduler.get("Partition") != "nextgen"
        or scheduler.get("TimeLimit") != "00:30:00"
        or not scheduler_resource_contract_matches(
            scheduler,
            allocated_cpus_per_task=int(os.environ.get("SLURM_CPUS_PER_TASK", "0")),
            mem_per_node_mb=int(os.environ.get("SLURM_MEM_PER_NODE", "0")),
            profile={"cpus_per_task": 2, "mem_gib": 16},
        )
    ):
        raise SystemExit("finalizer allocation is not confirmed by the scheduler")
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code", "protocols"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    if dirty or untracked_code:
        raise SystemExit("refusing finalization from dirty or untracked source")
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    source_hashes = {name: sha256_file(ROOT / name) for name in SOURCE_NAMES}
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if (
        not executed_batch.is_file()
        or sha256_file(executed_batch)
        != source_hashes["code/jobs/submit_finalize_corpus_v4_cps_multifidelity.sh"]
    ):
        raise SystemExit("executed finalizer batch script differs from tracked source")
    executed_batch_sha256 = sha256_file(executed_batch)
    execution_lock, execution_lock_sha256 = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    initial_input_hashes = {
        "plan": sha256_file(args.plan),
        "execution_lock": sha256_file(args.execution_lock),
        "r3_artifact_set": sha256_file(args.r3_artifact_set),
        "r3_manifest": sha256_file(args.r3_manifest),
        "r4_artifact_set": sha256_file(args.r4_artifact_set),
        "r4_manifest": sha256_file(args.r4_manifest),
    }

    protocol, _, r3_manifest, protocol_sha256, r3_manifest_sha = (
        validate_frozen_inputs(
            args.protocol,
            args.plan,
            args.expected_plan_sha256,
            args.r3_manifest,
        )
    )
    _, _, r4_manifest, _, r4_manifest_sha = validate_frozen_inputs(
        args.protocol,
        args.plan,
        args.expected_plan_sha256,
        args.r4_manifest,
    )
    r3_entries, r3_payloads = load_accepted_set(
        args.r3_artifact_set,
        args.r3_artifact_set_sha256,
        r3_manifest,
        plan_sha256=args.expected_plan_sha256,
        protocol_sha256=protocol_sha256,
        manifest_sha256=r3_manifest_sha,
        protocol=protocol,
        execution_lock=execution_lock,
        execution_lock_sha256=execution_lock_sha256,
    )
    r4_entries, r4_payloads = load_accepted_set(
        args.r4_artifact_set,
        args.r4_artifact_set_sha256,
        r4_manifest,
        plan_sha256=args.expected_plan_sha256,
        protocol_sha256=protocol_sha256,
        manifest_sha256=r4_manifest_sha,
        protocol=protocol,
        execution_lock=execution_lock,
        execution_lock_sha256=execution_lock_sha256,
    )
    geometry_records, corpus_summary = load_verified_geometry_corpus(
        args.corpus, protocol["input_geometry_corpus"]
    )
    if {payload["geometry"]["geometry_sha256"] for payload in r3_payloads} != {
        row["geometry_sha256"] for row in geometry_records
    }:
        raise ValueError("R3 accepted set does not cover the exact geometry corpus")

    observations: list[dict[str, Any]] = []
    for payload, entry in [
        *(zip(r3_payloads, r3_entries)),
        *(zip(r4_payloads, r4_entries)),
    ]:
        worker = payload["execution"]["worker_result"]
        observations.append(
            {
                "artifact_sha256": entry["artifact_sha256"],
                "cps_pf": worker["cps_pf"],
                "fidelity_id": payload["fidelity"]["fidelity_id"],
                "geometry_sha256": payload["geometry"]["geometry_sha256"],
                "layout_id": payload["geometry"]["layout_id"],
                "mesh_nodes": worker["mesh_nodes"],
                "mesh_tetrahedra": worker["mesh_tetrahedra"],
                "relative_residual": worker["relative_residual"],
                "units": "pF",
            }
        )
    observations.sort(key=lambda row: (row["layout_id"], row["fidelity_id"]))
    final_git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    final_dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    final_untracked_code = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all", "--", "code", "protocols"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    final_source_hashes = {name: sha256_file(ROOT / name) for name in SOURCE_NAMES}
    final_input_hashes = {
        "plan": sha256_file(args.plan),
        "execution_lock": sha256_file(args.execution_lock),
        "r3_artifact_set": sha256_file(args.r3_artifact_set),
        "r3_manifest": sha256_file(args.r3_manifest),
        "r4_artifact_set": sha256_file(args.r4_artifact_set),
        "r4_manifest": sha256_file(args.r4_manifest),
    }
    if (
        final_git_head != git_head
        or final_dirty
        or final_untracked_code
        or final_source_hashes != source_hashes
        or final_input_hashes != initial_input_hashes
        or sha256_file(executed_batch) != executed_batch_sha256
    ):
        raise SystemExit("finalizer source or input changed during validation")
    args.out.mkdir(parents=True, exist_ok=True)
    observations_path = args.out / "label_observations.jsonl"
    atomic_write_jsonl(observations_path, observations)
    summary = {
        "artifacts_sha256": {
            "label_observations.jsonl": sha256_file(observations_path),
        },
        "counts": {
            "geometries": len(geometry_records),
            "r3_observations": len(r3_payloads),
            "r4_observations": len(r4_payloads),
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "fidelity_semantics": protocol["scientific_semantics"],
        "input_artifact_set_sha256": {
            "r3": args.r3_artifact_set_sha256,
            "r4": args.r4_artifact_set_sha256,
        },
        "plan_sha256": args.expected_plan_sha256,
        "execution_lock_sha256": execution_lock_sha256,
        "provenance": {
            "git_dirty_paths": dirty,
            "git_head": git_head,
            "final_git_dirty_paths": final_dirty,
            "final_git_head": final_git_head,
            "final_input_sha256": final_input_hashes,
            "final_source_file_sha256": final_source_hashes,
            "final_untracked_code": final_untracked_code,
            "input_sha256": initial_input_hashes,
            "scheduler_record": scheduler,
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "source_file_sha256": source_hashes,
            "untracked_code": untracked_code,
        },
        "protocol_sha256": protocol_sha256,
        "schema": SCHEMA,
        "source_corpus_artifacts_sha256": corpus_summary["artifacts_sha256"],
    }
    atomic_write_json(args.out / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
