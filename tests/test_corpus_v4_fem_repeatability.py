"""Contracts for the SLURM-only Corpus-v4 FEM repeatability diagnostic.

No test in this module launches Gmsh or a field solver.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "protocols/corpus_v4_fem_repeatability_v1.json"
RUNNER_PATH = (
    ROOT / "code/experiments/proofs/experiments_corpus_v4_fem_repeatability.py"
)
SUBMIT_PATH = ROOT / "code/jobs/submit_corpus_v4_fem_repeatability.sh"
FINALIZER_PATH = (
    ROOT / "code/experiments/proofs/finalize_corpus_v4_fem_repeatability.py"
)
FINALIZER_SUBMIT_PATH = (
    ROOT / "code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh"
)


def _load_runner() -> ModuleType:
    for directory in (
        ROOT / "code/core",
        ROOT / "code/data",
        ROOT / "code/experiments/proofs",
        ROOT / "code/solvers",
    ):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    spec = importlib.util.spec_from_file_location("fem_repeatability_for_test", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_finalizer() -> ModuleType:
    for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    spec = importlib.util.spec_from_file_location(
        "fem_repeatability_finalizer_for_test", FINALIZER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _worker_result(cps_pf: float, fingerprint: str, *, nodes: int, tets: int) -> dict[str, Any]:
    return {
        "amg_levels": 4,
        "cps_pf": cps_pf,
        "eps_r": 4.2,
        "input_system_sha256": fingerprint,
        "iterations": 25,
        "linear_solver": "pyamg_smoothed_aggregation_cg",
        "maxiter": 500,
        "mesh_nodes": nodes,
        "mesh_tetrahedra": tets,
        "operator_complexity": 1.1,
        "pad_mm": 16.0,
        "refine": 3,
        "relative_residual": 5e-11,
        "rtol": 1e-10,
        "solver_info": 0,
        "system_sha256": fingerprint,
    }


def _observation(
    panel: dict[str, Any],
    arm: dict[str, Any],
    repeat_id: int,
    *,
    cps_pf: float | None = None,
    fingerprint: str | None = None,
    nodes: int = 1_700_000,
    tets: int = 10_300_000,
) -> dict[str, Any]:
    value = float(panel["frozen_r3_cps_pf"] if cps_pf is None else cps_pf)
    identity = fingerprint or hashlib.sha256(
        f"{panel['layout_id']}:{arm['arm_id']}".encode("ascii")
    ).hexdigest()
    return {
        "arm": copy.deepcopy(arm),
        "geometry": {
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "layout_id": panel["layout_id"],
        },
        "gmsh_thread_gate": {
            "expected_gmsh_threads": arm["gmsh_threads"],
            "observation_count": 1,
            "observed_gmsh_threads": arm["gmsh_threads"],
            "pass": True,
            "telemetry_contract": "pcb-gnn.gmsh-thread-observation.v1",
        },
        "numerical_resource_gate": {"pass": True},
        "repeat_id": repeat_id,
        "worker_result": _worker_result(value, identity, nodes=nodes, tets=tets),
    }


def _complete_observations(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _observation(panel, arm, repeat_id)
        for panel in protocol["panel"]
        for repeat_id in range(5)
        for arm in protocol["arms"]
    ]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _full_arm_record(
    panel: dict[str, Any],
    arm: dict[str, Any],
    repeat_id: int,
    order_position: int,
    *,
    cps_protocol: dict[str, Any],
    evaluator: Any,
) -> dict[str, Any]:
    fingerprint = hashlib.sha256(
        f"{panel['layout_id']}:{arm['arm_id']}".encode("ascii")
    ).hexdigest()
    worker_result = _worker_result(
        float(panel["frozen_r3_cps_pf"]),
        fingerprint,
        nodes=1_700_000 + int(panel["layout_id"]),
        tets=10_300_000 + int(panel["layout_id"]),
    )
    execution = {
        "returncode": 0,
        "stages": [
            {
                "gmsh_threads": arm["gmsh_threads"],
                "max_rss_kb": 10 * 1024 * 1024,
                "stage": "repeatability_environment",
                "telemetry_contract": "pcb-gnn.gmsh-thread-observation.v1",
            }
        ],
        "telemetry_parse_errors": [],
        "timed_out": False,
        "wall_s": 500.0,
        "worker_result": copy.deepcopy(worker_result),
        "worker_result_count": 1,
    }
    canonical = lambda value: json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "arm": copy.deepcopy(arm),
        "claim_eligible": False,
        "completed_utc": "2026-08-20T00:00:00+00:00",
        "execution": execution,
        "execution_sha256": hashlib.sha256(canonical(execution)).hexdigest(),
        "frozen_reference": {
            "cps_pf": panel["frozen_r3_cps_pf"],
            "units": "pF",
        },
        "geometry": {
            "family_id": panel["family_id"],
            "geometry_sha256": panel["geometry_sha256"],
            "layout_id": panel["layout_id"],
        },
        "gmsh_thread_gate": {
            "expected_gmsh_threads": arm["gmsh_threads"],
            "observation_count": 1,
            "observed_gmsh_threads": arm["gmsh_threads"],
            "pass": True,
            "telemetry_contract": "pcb-gnn.gmsh-thread-observation.v1",
        },
        "numerical_resource_gate": evaluator(
            execution, cps_protocol, "cps_fem_r3_p16"
        ),
        "old_reference_relative_drift": 0.0,
        "old_reference_signed_relative_drift": 0.0,
        "order_position": order_position,
        "repeat_id": repeat_id,
        "schema": "pcb-gnn.corpus-v4-fem-repeatability-arm.v1",
        "speed_claim_eligible": False,
        "worker_result": worker_result,
        "worker_result_sha256": hashlib.sha256(canonical(worker_result)).hexdigest(),
    }


def _materialize_finalizer_fixture(
    root: Path,
    protocol: dict[str, Any],
    *,
    source_job: str = "7100000",
    source_head: str = "1" * 40,
    failed_task: int | None = None,
) -> list[dict[str, str]]:
    protocol_sha = _sha256(PROTOCOL_PATH)
    bindings = {
        label: binding["sha256"] for label, binding in protocol["inputs"].items()
    }
    source_hashes = copy.deepcopy(protocol["computational_sources"])
    accounting: list[dict[str, str]] = []
    source_dir = root / "attempts" / f"job_{source_job}"
    source_dir.mkdir(parents=True)
    runner = _load_runner()
    cps_protocol = json.loads(
        (ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json").read_text(
            encoding="utf-8"
        )
    )
    for task_id in range(15):
        panel, repeat_id = runner.task_mapping(task_id, protocol)
        order = runner.arm_order(repeat_id, protocol)
        task_dir = source_dir / f"task_{task_id:02d}"
        task_dir.mkdir()
        raw_job_id = str(7_200_000 + task_id)
        node_name = f"ascend-repeatability-{task_id:02d}"
        scheduler = {
            "array_job_id": source_job,
            "array_task_count": 15,
            "array_task_id": task_id,
            "array_task_max": 14,
            "array_task_min": 0,
            "cpus_per_task": 25,
            "job_account": "pgs0407",
            "job_id": raw_job_id,
            "memory": "49152",
            "partition": "nextgen",
            "scheduler_record": {
                "Account": "pgs0407",
                "AllocTRES": "cpu=25,mem=48G,node=1,billing=25",
                "ArrayJobId": source_job,
                "ArrayTaskId": str(task_id),
                "ArrayTaskThrottle": "3",
                "CPUs/Task": "25",
                "JobId": raw_job_id,
                "JobState": "RUNNING",
                "MinMemoryNode": "48G",
                "NodeList": node_name,
                "NumCPUs": "25",
                "NumTasks": "1",
                "Partition": "nextgen",
                "ReqTRES": "cpu=25,mem=48G,node=1,billing=25",
                "TimeLimit": "02:00:00",
                "TresPerTask": "cpu=25",
            },
            "slurmd_nodename": node_name,
        }
        hardware_identity = {
            "affinity_cpu_count": 25,
            "architecture": "x86_64",
            "cpu_model": "fixture-cpu",
            "kernel": "fixture-kernel",
        }
        started = {
            "array_task_id": task_id,
            "arm_order": [arm["arm_id"] for arm in order],
            "claim_eligible": False,
            "input_bindings": bindings,
            "panel": panel,
            "protocol_sha256": protocol_sha,
            "repeat_id": repeat_id,
            "schema": "pcb-gnn.corpus-v4-fem-repeatability-start.v1",
            "source_git_head": source_head,
            "source_sha256": source_hashes,
            "speed_claim_eligible": False,
            "started_utc": "2026-08-20T00:00:00+00:00",
        }
        arms = [
            _full_arm_record(
                panel,
                arm,
                repeat_id,
                position,
                cps_protocol=cps_protocol,
                evaluator=runner.evaluate_result,
            )
            for position, arm in enumerate(order)
        ]
        result = {
            "admission_eligible": False,
            "arms": arms,
            "claim_eligible": False,
            "completed_utc": "2026-08-20T00:00:01+00:00",
            "integrity": {"passed": True},
            "provenance": {
                "executed_batch_sha256": source_hashes[
                    "code/jobs/submit_corpus_v4_fem_repeatability.sh"
                ],
                "hardware": {
                    **hardware_identity,
                    "anonymous_class_sha256": hashlib.sha256(
                        json.dumps(
                            hardware_identity,
                            allow_nan=False,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                },
                "hostname": node_name,
                "input_bindings": bindings,
                "protocol_sha256": protocol_sha,
                "runtime": copy.deepcopy(protocol["runtime"]),
                "scheduler": scheduler,
                "source_git_head": source_head,
                "source_sha256": source_hashes,
            },
            "schema": "pcb-gnn.corpus-v4-fem-repeatability-attempt.v1",
            "speed_claim_eligible": False,
            "task": {
                "array_task_id": task_id,
                "family_id": panel["family_id"],
                "geometry_sha256": panel["geometry_sha256"],
                "latency_task_id": panel["latency_task_id"],
                "layout_id": panel["layout_id"],
                "repeat_id": repeat_id,
            },
        }
        _write_json(task_dir / "started.json", started)
        for arm in arms:
            _write_json(task_dir / f"{arm['arm']['arm_id']}.json", arm)
        _write_json(task_dir / "result.json", result)
        files = {
            path.name: _sha256(path)
            for path in task_dir.iterdir()
            if path.is_file()
        }
        _write_json(
            task_dir / "TASK_MANIFEST.json",
            {
                "files_sha256": files,
                "protocol_sha256": protocol_sha,
                "schema": "pcb-gnn.corpus-v4-fem-repeatability-attempt-manifest.v1",
            },
        )
        failed = task_id == failed_task
        accounting.append(
            {
                "Account": "pgs0407",
                "AllocTRES": "billing=25,cpu=25,mem=48G,node=1",
                "ElapsedRaw": "900",
                "ExitCode": "1:0" if failed else "0:0",
                "JobID": f"{source_job}_{task_id}",
                "JobIDRaw": raw_job_id,
                "NodeList": node_name,
                "Partition": "nextgen",
                "ReqTRES": "billing=25,cpu=25,mem=48G,node=1",
                "Restarts": "0",
                "State": "FAILED" if failed else "COMPLETED",
                "Timelimit": "02:00:00",
            }
        )
    return accounting


def _refresh_task_manifest(task_dir: Path) -> None:
    manifest_path = task_dir / "TASK_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files_sha256"] = {
        path.name: _sha256(path)
        for path in task_dir.iterdir()
        if path.is_file() and path.name != "TASK_MANIFEST.json"
    }
    _write_json(manifest_path, manifest)


def _fixture_accounting_provenance(
    finalizer: ModuleType, accounting: list[dict[str, str]]
) -> dict[str, Any]:
    raw_text = "\n".join(
        "|".join(row[field] for field in finalizer.ACCOUNTING_FIELDS) + "|"
        for row in accounting
    ) + "\n"
    return finalizer.build_accounting_provenance(
        rows=accounting,
        raw_text=raw_text,
        origin="test_fixture",
        command=[],
        queried_utc="2026-08-20T00:00:02+00:00",
    )


def _finalizer_provenance(
    protocol: dict[str, Any], source_head: str, finalizer_job_id: str
) -> dict[str, Any]:
    node = "ascend-finalizer-01"
    hardware_identity = {
        "affinity_cpu_count": 3,
        "architecture": "x86_64",
        "cpu_model": "fixture-cpu",
        "kernel": "fixture-kernel",
    }
    canonical = lambda value: json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "executed_batch_sha256": protocol["computational_sources"][
            "code/jobs/submit_finalize_corpus_v4_fem_repeatability.sh"
        ],
        "finalizer_hardware": {
            **hardware_identity,
            "anonymous_class_sha256": hashlib.sha256(
                canonical(hardware_identity)
            ).hexdigest(),
        },
        "finalizer_hostname": f"{node}.ten.osc.edu",
        "finalizer_runtime": copy.deepcopy(protocol["runtime"]),
        "finalizer_scheduler": {
            "allocated_cpus_per_task": 3,
            "job_account": "pgs0407",
            "job_id": finalizer_job_id,
            "memory_mib": 8192,
            "partition": "nextgen",
            "requested_cpus_per_task": 2,
            "scheduler_record": {
                "Account": "pgs0407",
                "AllocTRES": "billing=3,cpu=3,mem=8G,node=1",
                "CPUs/Task": "3",
                "JobState": "RUNNING",
                "MinMemoryNode": "8G",
                "NodeList": node,
                "NumCPUs": "3",
                "NumTasks": "1",
                "Partition": "nextgen",
                "ReqTRES": "billing=2,cpu=2,mem=8G,node=1",
                "TimeLimit": "00:30:00",
                "TresPerTask": "cpu=2",
            },
            "slurmd_nodename": node,
        },
        "input_bindings": {
            label: binding["sha256"] for label, binding in protocol["inputs"].items()
        },
        "source_git_head": source_head,
        "source_sha256": copy.deepcopy(protocol["computational_sources"]),
    }


def test_protocol_freezes_panel_arms_repeats_resources_and_tolerance() -> None:
    runner = _load_runner()
    protocol = _protocol()
    runner.validate_protocol(protocol)
    assert [row["latency_task_id"] for row in protocol["panel"]] == [0, 152, 305]
    assert [row["layout_id"] for row in protocol["panel"]] == [3, 734, 1495]
    assert [arm["gmsh_threads"] for arm in protocol["arms"]] == [25, 1]
    assert protocol["repetitions"]["independent_repeats_per_layout_arm"] == 5
    assert protocol["repetitions"]["array_task_ids"] == list(range(15))
    assert protocol["resources"] == {
        "finalizer": {
            "account": "pgs0407",
            "allocated_cpus_may_exceed_request": True,
            "cpus_per_task": 2,
            "memory_gib": 8,
            "nodes": 1,
            "ntasks": 1,
            "partition": "nextgen",
            "time_limit": "00:30:00",
        },
        "source_array": {
            "account": "pgs0407",
            "allocated_cpus_may_exceed_request": False,
            "array": "0-14%3",
            "array_throttle": 3,
            "cpus_per_task": 25,
            "memory_gib": 48,
            "nodes": 1,
            "ntasks": 1,
            "partition": "nextgen",
            "time_limit": "02:00:00",
        },
    }
    assert protocol["gates"]["relative_tolerance"] == 1e-4
    assert protocol["diagnostic_semantics"] == {
        "claim_eligible": False,
        "old_labels_may_be_replaced": False,
        "speed_claim_eligible": False,
        "tolerance_may_be_changed_after_observation": False,
    }


def test_protocol_source_and_input_hashes_are_live() -> None:
    protocol = _protocol()
    for relative, expected in protocol["computational_sources"].items():
        assert _sha256(ROOT / relative) == expected
    for binding in protocol["inputs"].values():
        assert _sha256(ROOT / binding["path"]) == binding["sha256"]


def test_dense_array_mapping_and_parity_order_are_exact() -> None:
    runner = _load_runner()
    protocol = _protocol()
    expected_layouts = [3] * 5 + [734] * 5 + [1495] * 5
    for array_task_id, expected_layout in enumerate(expected_layouts):
        panel, repeat_id = runner.task_mapping(array_task_id, protocol)
        assert panel["layout_id"] == expected_layout
        assert repeat_id == array_task_id % 5
        order = [arm["arm_id"] for arm in runner.arm_order(repeat_id, protocol)]
        assert order == (
            ["arm_a_threads25", "arm_b_threads1"]
            if repeat_id % 2 == 0
            else ["arm_b_threads1", "arm_a_threads25"]
        )
    for invalid in (-1, 15, 1.0):
        with pytest.raises(ValueError):
            runner.task_mapping(invalid, protocol)


def test_validate_only_authenticates_inputs_without_running_solver() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--protocol",
            str(PROTOCOL_PATH),
            "--expected-protocol-sha256",
            _sha256(PROTOCOL_PATH),
            "--validate-only",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(completed.stdout.splitlines()[-1])
    assert payload["schema"] == "pcb-gnn.corpus-v4-fem-repeatability-validation.v1"
    assert payload["solver_executed"] is False
    assert payload["array_task_count"] == 15
    assert payload["panel_layout_ids"] == [3, 734, 1495]
    assert payload["verified_geometry_records"] == 1500


def test_run_arm_reuses_worker_and_preserves_raw_result_and_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    protocol = _protocol()
    panel = protocol["panel"][0]
    arm = protocol["arms"][0]
    fingerprint = "a" * 64
    raw = _worker_result(12.0, fingerprint, nodes=100, tets=500)
    seen: dict[str, Any] = {}

    def fake_worker(layout: dict[str, Any], refine: int, pad: float, timeout: int) -> dict[str, Any]:
        seen.update(
            {
                "gmsh_threads": os.environ.get("PCB_GNN_GMSH_THREADS"),
                "layout": layout,
                "pad": pad,
                "refine": refine,
                "timeout": timeout,
            }
        )
        return {
            "returncode": 0,
            "stages": [
                {
                    "gmsh_threads": int(
                        os.environ["PCB_GNN_GMSH_THREADS"]
                    ),
                    "stage": "repeatability_environment",
                    "telemetry_contract": "pcb-gnn.gmsh-thread-observation.v1",
                }
            ],
            "worker_result": copy.deepcopy(raw),
        }

    monkeypatch.setattr(runner, "run_repeatability_worker", fake_worker)
    monkeypatch.setattr(runner, "evaluate_result", lambda *args: {"pass": True})
    record = runner.run_arm(
        arm=arm,
        layout={"traces": []},
        panel=panel,
        repeat_id=0,
        order_position=0,
        cps_protocol={},
    )
    assert seen == {
        "gmsh_threads": "25",
        "layout": {"traces": []},
        "pad": 16.0,
        "refine": 3,
        "timeout": 1800,
    }
    assert record["worker_result"] == raw
    assert record["gmsh_thread_gate"]["pass"] is True
    expected_hash = hashlib.sha256(
        json.dumps(
            raw,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert record["worker_result_sha256"] == expected_hash
    expected_signed_drift = (12.0 - panel["frozen_r3_cps_pf"]) / panel[
        "frozen_r3_cps_pf"
    ]
    assert record["old_reference_signed_relative_drift"] == pytest.approx(
        expected_signed_drift
    )
    assert record["old_reference_relative_drift"] == pytest.approx(
        abs(expected_signed_drift)
    )
    assert record["claim_eligible"] is False
    assert record["speed_claim_eligible"] is False
    assert "speedup" not in json.dumps(record).lower()


def test_summary_passes_only_complete_mesh_identical_strict_reference_panel() -> None:
    runner = _load_runner()
    protocol = _protocol()
    summary = runner.summarize_repeatability(_complete_observations(protocol), protocol)
    assert summary["decision"] == {
        "arm_a_all_gates_pass": True,
        "arm_b_repeatability_gates_pass": True,
        "paired_latency_preflight_may_resume": True,
        "tolerance_changed": False,
    }
    assert summary["claim_eligible"] is False
    assert summary["speed_claim_eligible"] is False
    assert len(summary["groups"]) == 6
    assert all(group["mesh"]["system_sha256_unique_count"] == 1 for group in summary["groups"])
    assert all(
        group["frozen_reference"]["signed_relative_drifts_by_repeat"] == [0.0] * 5
        for group in summary["groups"]
    )


def test_summary_fails_closed_on_mesh_or_reference_drift() -> None:
    runner = _load_runner()
    protocol = _protocol()
    observations = _complete_observations(protocol)
    target = next(
        observation
        for observation in observations
        if observation["geometry"]["layout_id"] == 3
        and observation["repeat_id"] == 4
        and observation["arm"]["arm_id"] == "arm_a_threads25"
    )
    target["worker_result"]["system_sha256"] = "f" * 64
    target["worker_result"]["input_system_sha256"] = "f" * 64
    target["worker_result"]["mesh_nodes"] += 1
    target["worker_result"]["cps_pf"] *= 1.0002
    summary = runner.summarize_repeatability(observations, protocol)
    failed = next(
        group
        for group in summary["groups"]
        if group["layout_id"] == 3 and group["arm_id"] == "arm_a_threads25"
    )
    assert failed["gate"]["mesh_identity_pass"] is False
    assert failed["gate"]["repeatability_pass"] is False
    assert failed["frozen_reference"]["all_five_pass"] is False
    assert summary["decision"]["paired_latency_preflight_may_resume"] is False


def test_summary_rejects_missing_or_duplicate_attempts() -> None:
    runner = _load_runner()
    protocol = _protocol()
    observations = _complete_observations(protocol)
    with pytest.raises(ValueError, match="incomplete"):
        runner.summarize_repeatability(observations[:-1], protocol)
    with pytest.raises(ValueError, match="duplicate"):
        runner.summarize_repeatability(observations + [observations[0]], protocol)


def test_tolerance_cannot_be_relaxed_without_protocol_rejection() -> None:
    runner = _load_runner()
    protocol = _protocol()
    protocol["gates"]["relative_tolerance"] = 3e-4
    with pytest.raises(ValueError, match="1e-4 tolerance changed"):
        runner.validate_protocol(protocol)


def test_slurm_allocation_is_required_and_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    protocol = _protocol()
    for name in tuple(os.environ):
        if name.startswith("SLURM_"):
            monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="SLURM-only"):
        runner.validate_slurm_allocation(protocol)

    environment = {
        "SLURM_ARRAY_JOB_ID": "7000000",
        "SLURM_ARRAY_TASK_COUNT": "15",
        "SLURM_ARRAY_TASK_ID": "4",
        "SLURM_ARRAY_TASK_MAX": "14",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "25",
        "SLURM_JOB_ACCOUNT": "pgs0407",
        "SLURM_JOB_ID": "7000005",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "49152",
        "SLURMD_NODENAME": "ascend-repeatability-04",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    record = (
        "JobId=7000005 ArrayJobId=7000000 ArrayTaskId=4 ArrayTaskThrottle=3 "
        "Account=pgs0407 Partition=nextgen JobState=RUNNING CPUs/Task=25 "
        "NumCPUs=25 NumTasks=1 MinMemoryNode=48G TresPerTask=cpu=25 "
        "NodeList=ascend-repeatability-04 "
        "ReqTRES=cpu=25,mem=48G,node=1,billing=25 "
        "AllocTRES=cpu=25,mem=48G,node=1,billing=25 TimeLimit=02:00:00"
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=record, stderr=""),
    )
    observed = runner.validate_slurm_allocation(protocol)
    assert observed["array_task_id"] == 4
    assert observed["scheduler_record"]["ArrayTaskThrottle"] == "3"

    bad_tres_values = (
        "billing=25,cpu=25,mem=48G2,node=1",
        "billing=25,cpu=25,mem=48G,node=1,gpu=0",
        "billing=25,cpu=25,mem=48G,node",
    )
    for bad_tres in bad_tres_values:
        bad_record = record.replace(
            "ReqTRES=cpu=25,mem=48G,node=1,billing=25",
            f"ReqTRES={bad_tres}",
            1,
        )
        monkeypatch.setattr(
            runner.subprocess,
            "run",
            lambda *args, _record=bad_record, **kwargs: SimpleNamespace(
                returncode=0, stdout=_record, stderr=""
            ),
        )
        with pytest.raises(SystemExit, match="ReqTRES differs"):
            runner.validate_slurm_allocation(protocol)


def test_submit_script_is_exact_slurm_only_contract() -> None:
    script = SUBMIT_PATH.read_text(encoding="utf-8")
    for directive in (
        "#SBATCH --account=pgs0407",
        "#SBATCH --partition=nextgen",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=25",
        "#SBATCH --mem=48G",
        "#SBATCH --time=02:00:00",
        "#SBATCH --array=0-14%3",
    ):
        assert directive in script
    assert "PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256" in script
    assert "PCB_GNN_V4_SOURCE_COMMIT" in script
    assert "--validate-only" not in script
    assert "PCB_GNN_GMSH_THREADS=" not in script
    runner = RUNNER_PATH.read_text(encoding="utf-8")
    assert "run_repeatability_worker(layout, 3, 16.0, 1800)" in runner
    assert "exist_ok=False" in runner
    assert "speedup" not in runner.lower()


def test_finalizer_allocation_accepts_site_cpu_overallocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    environment = {
        "SLURM_CPUS_PER_TASK": "3",
        "SLURM_JOB_ACCOUNT": "pgs0407",
        "SLURM_JOB_ID": "7300000",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "8192",
        "SLURMD_NODENAME": "ascend-finalizer-01.ten.osc.edu",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("SLURM_ARRAY_JOB_ID", raising=False)
    monkeypatch.delenv("SLURM_ARRAY_TASK_ID", raising=False)
    record = (
        "JobId=7300000 Account=pgs0407 Partition=nextgen JobState=RUNNING "
        "CPUs/Task=3 NumCPUs=3 NumTasks=1 MinMemoryNode=8G "
        "TresPerTask=cpu=2 NodeList=ascend-finalizer-01 "
        "ReqTRES=billing=2,cpu=2,mem=8G,node=1 "
        "AllocTRES=billing=3,cpu=3,mem=8G,node=1 TimeLimit=00:30:00"
    )
    monkeypatch.setattr(
        finalizer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=record, stderr=""
        ),
    )
    observed = finalizer.validate_finalizer_slurm_allocation(protocol)
    assert observed["requested_cpus_per_task"] == 2
    assert observed["allocated_cpus_per_task"] == 3
    assert observed["scheduler_record"]["AllocTRES"].startswith("billing=3")


def test_finalizer_success_authenticates_15_tasks_and_30_observations(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "1" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    payload = finalizer.build_final_payload(
        protocol=protocol,
        protocol_sha256=_sha256(PROTOCOL_PATH),
        expected_source_git_head=source_head,
        source_array_job_id="7100000",
        finalizer_job_id="7300000",
        input_root=tmp_path,
        accounting_rows=accounting,
        accounting_provenance=_fixture_accounting_provenance(finalizer, accounting),
    )
    assert payload["schema"] == "pcb-gnn.corpus-v4-fem-repeatability-final.v1"
    assert payload["claim_eligible"] is False
    assert payload["speed_claim_eligible"] is False
    assert payload["source_array"]["completed_zero_count"] == 15
    assert len(payload["source_array"]["task_receipts"]) == 15
    assert len(payload["repeatability_summary"]["groups"]) == 6
    assert payload["admission_eligible"] is False
    assert payload["artifact_stage"] == "preterminal_finalizer_output"
    assert payload["decision"] == {
        "all_15_scheduler_rows_completed_zero": True,
        "arm_a_all_gates_pass": True,
        "paired_latency_preflight_may_resume": False,
        "provisional_preterminal_gate_pass": True,
    }
    assert payload["post_run_admission"] == {
        "finalizer_job_id": "7300000",
        "required": True,
        "required_exit_code": "0:0",
        "required_state": "COMPLETED",
        "terminal_accounting_verified": False,
    }
    assert payload["source_array"]["accounting_provenance"]["origin"] == "test_fixture"

    payload["source_array"]["accounting_provenance"]["origin"] = "live_sacct"
    payload["source_array"]["accounting_provenance"]["command"] = [
        "sacct",
        "-X",
        "-n",
        "-P",
        "-j",
        "7100000",
        "--format=" + ",".join(finalizer.ACCOUNTING_FIELDS),
    ]
    payload["provenance"] = _finalizer_provenance(
        protocol, source_head, "7300000"
    )
    finalizer.validate_preterminal_payload(
        payload,
        protocol=protocol,
        protocol_sha256=_sha256(PROTOCOL_PATH),
        expected_source_git_head=source_head,
        source_array_job_id="7100000",
        finalizer_job_id="7300000",
        input_root=tmp_path,
    )
    forged = copy.deepcopy(payload)
    forged["decision"]["provisional_preterminal_gate_pass"] = False
    with pytest.raises(ValueError, match="decision differs from recomputation"):
        finalizer.validate_preterminal_payload(
            forged,
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
        )


def test_finalizer_keeps_complete_failed_diagnostic_but_closes_resume(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "2" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head, failed_task=7
    )
    payload = finalizer.build_final_payload(
        protocol=protocol,
        protocol_sha256=_sha256(PROTOCOL_PATH),
        expected_source_git_head=source_head,
        source_array_job_id="7100000",
        finalizer_job_id="7300000",
        input_root=tmp_path,
        accounting_rows=accounting,
        accounting_provenance=_fixture_accounting_provenance(finalizer, accounting),
    )
    assert payload["source_array"]["completed_zero_count"] == 14
    assert payload["source_array"]["accounting"][7]["terminal_success"] is False
    assert payload["source_array"]["accounting"][7]["State"] == "FAILED"
    assert payload["repeatability_summary"]["decision"][
        "paired_latency_preflight_may_resume"
    ] is False
    assert payload["decision"]["paired_latency_preflight_may_resume"] is False


def test_finalizer_rejects_wrong_raw_job_id_and_missing_or_duplicate_rows(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "3" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    wrong_raw = copy.deepcopy(accounting)
    wrong_raw[4]["JobIDRaw"] = "9999999"
    with pytest.raises(ValueError, match="scheduler provenance"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
            accounting_rows=wrong_raw,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, wrong_raw
            ),
        )
    with pytest.raises(ValueError, match="exactly tasks 0..14"):
        finalizer.validate_source_accounting(accounting[:-1], "7100000", protocol)
    duplicated = accounting + [copy.deepcopy(accounting[0])]
    with pytest.raises(ValueError, match="duplicated"):
        finalizer.validate_source_accounting(duplicated, "7100000", protocol)
    duplicate_raw = copy.deepcopy(accounting)
    duplicate_raw[8]["JobIDRaw"] = duplicate_raw[7]["JobIDRaw"]
    with pytest.raises(ValueError, match="not unique"):
        finalizer.validate_source_accounting(duplicate_raw, "7100000", protocol)
    for field, invalid in (
        ("ElapsedRaw", "0"),
        ("ElapsedRaw", "7201"),
        ("Partition", "wrong"),
        ("Timelimit", "01:59:59"),
        ("NodeList", "(null)"),
        ("Restarts", "1"),
    ):
        invalid_accounting = copy.deepcopy(accounting)
        invalid_accounting[0][field] = invalid
        with pytest.raises(ValueError, match="identity"):
            finalizer.validate_source_accounting(
                invalid_accounting, "7100000", protocol
            )


def test_terminal_state_annotations_are_normalized_without_losing_raw_state(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    accounting = _materialize_finalizer_fixture(tmp_path, protocol)
    completed = copy.deepcopy(accounting)
    completed[0]["State"] = "COMPLETED+"
    normalized = finalizer.validate_source_accounting(
        completed, "7100000", protocol
    )
    assert normalized[0]["State"] == "COMPLETED+"
    assert normalized[0]["normalized_state"] == "COMPLETED"
    assert normalized[0]["terminal_success"] is True

    cancelled = copy.deepcopy(accounting)
    cancelled[0]["State"] = "CANCELLED by 12345"
    cancelled[0]["ExitCode"] = "1:0"
    normalized = finalizer.validate_source_accounting(
        cancelled, "7100000", protocol
    )
    assert normalized[0]["State"] == "CANCELLED by 12345"
    assert normalized[0]["normalized_state"] == "CANCELLED"
    assert normalized[0]["terminal_success"] is False


def test_finalizer_rejects_task_hash_and_source_provenance_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "4" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    result_path = (
        tmp_path / "attempts/job_7100000/task_00/result.json"
    )
    result_path.write_bytes(result_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file hash"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )

    clean_root = tmp_path / "source-drift"
    accounting = _materialize_finalizer_fixture(
        clean_root, protocol, source_head=source_head
    )
    task_dir = clean_root / "attempts/job_7100000/task_00"
    result_path = task_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["provenance"]["source_sha256"] = {
        **result["provenance"]["source_sha256"],
        "code/core/geometry_contract.py": "0" * 64,
    }
    _write_json(result_path, result)
    _refresh_task_manifest(task_dir)
    with pytest.raises(ValueError, match="source/protocol/input provenance"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=clean_root,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )


def test_finalizer_recomputes_and_rejects_tampered_numerical_gate(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "5" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    task_dir = tmp_path / "attempts/job_7100000/task_00"
    arm_path = task_dir / "arm_a_threads25.json"
    arm = json.loads(arm_path.read_text(encoding="utf-8"))
    arm["numerical_resource_gate"]["pass"] = False
    _write_json(arm_path, arm)
    result_path = task_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["arms"][0]["arm"]["arm_id"] == "arm_a_threads25"
    result["arms"][0] = arm
    result["integrity"] = {"passed": False}
    _write_json(result_path, result)
    _refresh_task_manifest(task_dir)
    with pytest.raises(ValueError, match="raw recomputation"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )


def test_finalizer_rejects_retained_runtime_and_hardware_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "6" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    task_dir = tmp_path / "attempts/job_7100000/task_00"
    result_path = task_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["provenance"]["runtime"]["python"] = "0.0.0"
    _write_json(result_path, result)
    _refresh_task_manifest(task_dir)
    with pytest.raises(ValueError, match="runtime identity"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )

    hardware_root = tmp_path / "hardware-drift"
    accounting = _materialize_finalizer_fixture(
        hardware_root, protocol, source_head=source_head
    )
    task_dir = hardware_root / "attempts/job_7100000/task_00"
    result_path = task_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["provenance"]["hardware"]["affinity_cpu_count"] = 24
    _write_json(result_path, result)
    _refresh_task_manifest(task_dir)
    with pytest.raises(ValueError, match="hardware identity"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=hardware_root,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )


def test_finalizer_rejects_tampered_child_gmsh_thread_observation(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    protocol = _protocol()
    source_head = "7" * 40
    accounting = _materialize_finalizer_fixture(
        tmp_path, protocol, source_head=source_head
    )
    task_dir = tmp_path / "attempts/job_7100000/task_00"
    arm_path = task_dir / "arm_a_threads25.json"
    arm = json.loads(arm_path.read_text(encoding="utf-8"))
    arm["execution"]["stages"][0]["gmsh_threads"] = 1
    arm["execution_sha256"] = hashlib.sha256(
        json.dumps(
            arm["execution"],
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    _write_json(arm_path, arm)
    result_path = task_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["arms"][0] = arm
    _write_json(result_path, result)
    _refresh_task_manifest(task_dir)
    with pytest.raises(ValueError, match="child telemetry"):
        finalizer.build_final_payload(
            protocol=protocol,
            protocol_sha256=_sha256(PROTOCOL_PATH),
            expected_source_git_head=source_head,
            source_array_job_id="7100000",
            finalizer_job_id="7300000",
            input_root=tmp_path,
            accounting_rows=accounting,
            accounting_provenance=_fixture_accounting_provenance(
                finalizer, accounting
            ),
        )


def test_accounting_fixture_parser_is_pure_and_exact() -> None:
    finalizer = _load_finalizer()
    header = "|".join(finalizer.ACCOUNTING_FIELDS)
    row = (
        "7100000_0|7200000|COMPLETED|0:0|pgs0407|nextgen|02:00:00|"
        "ascend-repeatability-00|0|900|"
        "billing=25,cpu=25,mem=48G,node=1|"
        "billing=25,cpu=25,mem=48G,node=1"
    )
    assert finalizer.parse_accounting(f"{header}|\n{row}|\n") == [
        dict(zip(finalizer.ACCOUNTING_FIELDS, row.split("|")))
    ]
    with pytest.raises(ValueError, match="field count"):
        finalizer.parse_accounting(row + "||\n")


def test_live_accounting_receipt_binds_raw_and_canonical_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finalizer = _load_finalizer()
    row = (
        "7100000_0|7200000|COMPLETED|0:0|pgs0407|nextgen|02:00:00|"
        "ascend-repeatability-00|0|900|"
        "billing=25,cpu=25,mem=48G,node=1|"
        "billing=25,cpu=25,mem=48G,node=1|\n"
    )
    monkeypatch.setattr(
        finalizer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=row, stderr=""
        ),
    )
    rows, receipt = finalizer.query_live_accounting("7100000")
    assert receipt["origin"] == "live_sacct"
    assert receipt["row_count"] == 1
    assert receipt["raw_stdout_sha256"] == hashlib.sha256(
        row.encode("utf-8")
    ).hexdigest()
    assert receipt["canonical_rows_sha256"] == hashlib.sha256(
        json.dumps(
            rows,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert receipt["command"][-1] == "--format=" + ",".join(
        finalizer.ACCOUNTING_FIELDS
    )


def test_production_finalizer_has_no_accounting_fixture_cli() -> None:
    source = FINALIZER_PATH.read_text(encoding="utf-8")
    assert "--accounting-file" not in source
    assert "query_live_accounting" in source


def test_finalizer_wrapper_resources_and_ast_have_no_solver_path() -> None:
    script = FINALIZER_SUBMIT_PATH.read_text(encoding="utf-8")
    for directive in (
        "#SBATCH --account=pgs0407",
        "#SBATCH --partition=nextgen",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=2",
        "#SBATCH --mem=8G",
        "#SBATCH --time=00:30:00",
    ):
        assert directive in script
    assert "#SBATCH --array" not in script
    assert "PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID" in script
    assert "PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256" in script
    assert "PCB_GNN_V4_SOURCE_COMMIT" in script

    source = FINALIZER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"run_worker", "run_arm"}.isdisjoint(called_names)
    assert "evaluate_result" in called_names
    assert "code/solvers" not in source
    assert "speedup" not in source.lower()


def test_finalizer_writes_one_atomic_immutable_result_and_manifest(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    target = tmp_path / "source_job_7100000"
    payload = {
        "post_run_admission": {"finalizer_job_id": "7300000"},
        "protocol_sha256": "a" * 64,
        "source_array": {"array_job_id": "7100000"},
    }
    finalizer._atomic_final_directory(target, payload)
    assert {path.name for path in target.iterdir()} == {
        "FINAL_MANIFEST.json",
        "result.json",
    }
    manifest = json.loads((target / "FINAL_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["files_sha256"] == {"result.json": _sha256(target / "result.json")}
    with pytest.raises(SystemExit, match="immutable"):
        finalizer._atomic_final_directory(target, payload)
    dangling = tmp_path / "dangling-source-job"
    dangling.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    assert dangling.exists() is False and dangling.is_symlink() is True
    with pytest.raises(SystemExit, match="immutable"):
        finalizer._atomic_final_directory(dangling, payload)
