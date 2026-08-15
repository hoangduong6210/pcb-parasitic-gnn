"""Acceptance contracts for retry and final artifact-set construction."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

from plan_corpus_v4_cps_resume import (  # noqa: E402
    register_valid_attempt,
    validate_task_artifact,
)
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    evaluate_result,
    validate_frozen_inputs,
)


PLAN_ROOT = ROOT / "results/corpus_v4/cps_multifidelity/plan/v1"
PLAN_SHA256 = "419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a"
LOCK_PATH = ROOT / "protocols/corpus_v4_cps_execution_lock_v1.json"
LOCK_SHA256 = "cd46ae2f972955aac61ac20430ff892d63b50878cbcb2fce1fce1705add7b2ba"


def test_plan_requires_the_externally_pinned_root() -> None:
    protocol, plan, rows, protocol_sha, manifest_sha = validate_frozen_inputs(
        ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json",
        PLAN_ROOT / "plan.json",
        PLAN_SHA256,
        PLAN_ROOT / "r3_manifest.jsonl",
    )
    assert protocol["schema"] == "pcb-gnn.cps-multifidelity-protocol.v1"
    assert plan["counts"]["r3_tasks"] == 1500
    assert len(rows) == 1500
    assert len(protocol_sha) == len(manifest_sha) == 64

    with pytest.raises(ValueError, match="externally pinned root"):
        validate_frozen_inputs(
            ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json",
            PLAN_ROOT / "plan.json",
            "0" * 64,
            PLAN_ROOT / "r3_manifest.jsonl",
        )


def test_acceptance_rejects_dirty_or_incomplete_task_artifacts() -> None:
    expected = json.loads((PLAN_ROOT / "r3_manifest.jsonl").read_text().splitlines()[0])
    protocol = json.loads(
        (ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json").read_text()
    )
    fingerprint = "a" * 64
    protocol_sha = expected["protocol_sha256"]
    manifest_sha = json.loads((PLAN_ROOT / "plan.json").read_text())["artifact_sha256"][
        "r3_manifest.jsonl"
    ]
    execution = {
        "returncode": 0,
        "stages": [{"max_rss_kb": 10 * 1024 * 1024}],
        "telemetry_parse_errors": [],
        "timed_out": False,
        "wall_s": 500.0,
        "worker_result_count": 1,
        "worker_result": {
            "cps_pf": 72.0,
            "eps_r": 4.2,
            "input_system_sha256": fingerprint,
            "iterations": 20,
            "linear_solver": "pyamg_smoothed_aggregation_cg",
            "maxiter": 500,
            "mesh_nodes": 1000000,
            "mesh_tetrahedra": 5000000,
            "operator_complexity": 1.05,
            "pad_mm": 16.0,
            "refine": 3,
            "relative_residual": 5e-11,
            "rtol": 1e-10,
            "solver_info": 0,
            "system_sha256": fingerprint,
        },
    }
    gate = evaluate_result(execution, protocol, "cps_fem_r3_p16")
    source_hashes = {
        **json.loads(LOCK_PATH.read_text())["source_sha256"],
    }
    payload = {
        "execution": execution,
        "fidelity": {
            "fidelity_id": "cps_fem_r3_p16",
            "pad_mm": 16.0,
            "refine": 3,
        },
        "geometry": {
            "geometry_sha256": expected["geometry_sha256"],
            "layout_id": expected["layout_id"],
        },
        "numerical_resource_gate": gate,
        "provenance": {
            "environment": {
                "package_versions": protocol["runtime"]["packages"],
                "python": protocol["runtime"]["python"],
                "thread_environment": protocol["runtime"]["threads"],
            },
            "executed_batch_script": {
                "sha256": source_hashes["code/jobs/submit_corpus_v4_cps_r3.sh"]
            },
            "execution_lock_sha256": LOCK_SHA256,
            "final_executed_batch_script_sha256": source_hashes[
                "code/jobs/submit_corpus_v4_cps_r3.sh"
            ],
            "final_git_dirty_paths": [],
            "final_git_head": "c" * 40,
            "final_manifest_sha256": manifest_sha,
            "final_plan_sha256": PLAN_SHA256,
            "final_source_file_sha256": source_hashes,
            "final_untracked_code": [],
            "git_dirty_paths": [],
            "git_head": "c" * 40,
            "manifest_sha256": manifest_sha,
            "plan_sha256": PLAN_SHA256,
            "protocol_sha256": protocol_sha,
            "slurm": {
                "array_job_id": "12345",
                "array_task_id": 0,
                "canonical_task_index": 0,
                "cpus_per_task": 25,
                "mem_per_node_mb": 49152,
                "partition": "nextgen",
                "scheduler_record": {
                    "ArrayJobId": "12345",
                    "ArrayTaskId": "0",
                    "CPUs/Task": "25",
                    "NumCPUs": "25",
                    "NumTasks": "1",
                    "Partition": "nextgen",
                    "TimeLimit": "02:00:00",
                },
                "scheduler_array_record": {"ArrayTaskThrottle": "8"},
            },
            "source_file_sha256": source_hashes,
            "source_stable": True,
            "untracked_code": [],
        },
        "schema": "pcb-gnn.cps-multifidelity-task.v1",
        "solver_contract_id": expected["solver_contract_id"],
        "task_index": expected["task_index"],
        "task_pass": True,
    }
    validate_task_artifact(
        payload,
        expected,
        plan_sha256=PLAN_SHA256,
        protocol_sha256=protocol_sha,
        manifest_sha256=manifest_sha,
        protocol=protocol,
        execution_lock=json.loads(LOCK_PATH.read_text()),
        execution_lock_sha256=LOCK_SHA256,
    )
    payload["provenance"]["final_git_dirty_paths"] = ["M code/solver.py"]
    with pytest.raises(ValueError, match="not stable and clean"):
        validate_task_artifact(
            payload,
            expected,
            plan_sha256=PLAN_SHA256,
            protocol_sha256=protocol_sha,
            manifest_sha256=manifest_sha,
            protocol=protocol,
            execution_lock=json.loads(LOCK_PATH.read_text()),
            execution_lock_sha256=LOCK_SHA256,
        )
    payload["provenance"]["final_git_dirty_paths"] = []
    payload["execution"]["worker_result"]["relative_residual"] = 1e-3
    with pytest.raises(ValueError, match="does not recompute exactly"):
        validate_task_artifact(
            payload,
            expected,
            plan_sha256=PLAN_SHA256,
            protocol_sha256=protocol_sha,
            manifest_sha256=manifest_sha,
            protocol=protocol,
            execution_lock=json.loads(LOCK_PATH.read_text()),
            execution_lock_sha256=LOCK_SHA256,
        )


def test_duplicate_valid_attempts_are_ambiguous_and_fail_hard() -> None:
    accepted: dict[int, dict] = {}
    register_valid_attempt(accepted, 7, {"artifact_sha256": "a" * 64})
    with pytest.raises(RuntimeError, match="ambiguous duplicate"):
        register_valid_attempt(accepted, 7, {"artifact_sha256": "b" * 64})


def test_runner_validate_only_consumes_sparse_retry_set(tmp_path: Path) -> None:
    plan = json.loads((PLAN_ROOT / "plan.json").read_text())
    canonical = json.loads((PLAN_ROOT / "r3_manifest.jsonl").read_text().splitlines()[17])
    retry = {
        "fidelity_id": "cps_fem_r3_p16",
        "manifest_sha256": plan["artifact_sha256"]["r3_manifest.jsonl"],
        "pending": [
            {
                "geometry_sha256": canonical["geometry_sha256"],
                "layout_id": canonical["layout_id"],
                "task_index": canonical["task_index"],
            }
        ],
        "plan_sha256": PLAN_SHA256,
        "schema": "pcb-gnn.cps-multifidelity-pending-task-set.v1",
    }
    retry_path = tmp_path / "pending_task_set.json"
    retry_path.write_text(json.dumps(retry, indent=2, sort_keys=True) + "\n")
    retry_sha = hashlib.sha256(retry_path.read_bytes()).hexdigest()
    completed = subprocess.run(
        [
            "/usr/bin/python3",
            str(ROOT / "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py"),
            "--protocol",
            str(ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json"),
            "--plan",
            str(PLAN_ROOT / "plan.json"),
            "--expected-plan-sha256",
            PLAN_SHA256,
            "--manifest",
            str(PLAN_ROOT / "r3_manifest.jsonl"),
            "--execution-lock",
            str(LOCK_PATH),
            "--expected-execution-lock-sha256",
            LOCK_SHA256,
            "--retry-task-set",
            str(retry_path),
            "--expected-retry-task-set-sha256",
            retry_sha,
            "--validate-only",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["n_tasks"] == 1
    assert result["retry_task_set_sha256"] == retry_sha
