"""Static and numeric contracts for the SLURM-only multi-fidelity runner."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    evaluate_result,
    parse_prefixed,
    validate_slurm_contract,
)


def _protocol() -> dict:
    return json.loads(
        (ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json").read_text()
    )


def _passing_execution() -> dict:
    fingerprint = "a" * 64
    return {
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


def test_numeric_gate_accepts_only_the_exact_solver_contract() -> None:
    protocol = _protocol()
    execution = _passing_execution()
    assert evaluate_result(execution, protocol, "cps_fem_r3_p16")["pass"] is True

    execution["worker_result"]["relative_residual"] = 2e-9
    gate = evaluate_result(execution, protocol, "cps_fem_r3_p16")
    assert gate["pass"] is False
    assert gate["checks"]["relative_residual"] is False


def test_system_fingerprints_must_match() -> None:
    execution = _passing_execution()
    execution["worker_result"]["system_sha256"] = "b" * 64
    gate = evaluate_result(execution, _protocol(), "cps_fem_r3_p16")
    assert gate["pass"] is False
    assert gate["checks"]["system_fingerprint"] is False


def test_fidelity_fields_must_match_protocol() -> None:
    for field, value in (("refine", 4), ("pad_mm", 12.0), ("eps_r", 3.9)):
        execution = _passing_execution()
        execution["worker_result"][field] = value
        gate = evaluate_result(execution, _protocol(), "cps_fem_r3_p16")
        assert gate["pass"] is False
        assert gate["checks"]["fidelity"] is False


def test_malformed_and_missing_results_become_json_safe_failures() -> None:
    for worker_result in (None, {}, {"iterations": None}, {"cps_pf": float("nan")}):
        execution = _passing_execution()
        execution["worker_result"] = worker_result
        if worker_result is None:
            execution["worker_result_count"] = 0
        gate = evaluate_result(execution, _protocol(), "cps_fem_r3_p16")
        assert gate["pass"] is False
        json.dumps(gate, allow_nan=False)

    for field in ("wall_s",):
        execution = _passing_execution()
        execution[field] = -1.0
        assert evaluate_result(execution, _protocol(), "cps_fem_r3_p16")["pass"] is False
    execution = _passing_execution()
    execution["stages"] = [{"max_rss_kb": -1}]
    assert evaluate_result(execution, _protocol(), "cps_fem_r3_p16")["pass"] is False
    execution = _passing_execution()
    execution["stages"] = [{"max_rss_kb": "bad"}]
    execution["worker_result"]["maxiter"] = None
    gate = evaluate_result(execution, _protocol(), "cps_fem_r3_p16")
    assert gate["pass"] is False
    json.dumps(gate, allow_nan=False)

    records, errors = parse_prefixed(['RESULT={"cps_pf":NaN}'], "RESULT=")
    assert records == []
    assert errors


def test_batch_resources_and_array_ranges_match_protocol() -> None:
    protocol = _protocol()
    expectations = {
        "cps_fem_r3_p16": ("submit_corpus_v4_cps_r3.sh", "0-1000%8", "48G", "02:00:00"),
        "cps_fem_r4_p16": ("submit_corpus_v4_cps_r4.sh", "0-197%2", "160G", "03:00:00"),
    }
    for fidelity_id, (filename, array, memory, wall) in expectations.items():
        script = (ROOT / "code/jobs" / filename).read_text()
        profile = protocol["resource_profiles"][fidelity_id]["slurm"]
        assert f"#SBATCH --array={array}" in script
        assert f"#SBATCH --mem={memory}" in script
        assert f"#SBATCH --time={wall}" in script
        assert f"#SBATCH --cpus-per-task={profile['cpus_per_task']}" in script
        assert "PCB_GNN_CPS_EXECUTION_LOCK_SHA256" in script
    assert "R3 requires a dense dispatch or retry task set" in (
        ROOT / "code/jobs/submit_corpus_v4_cps_r3.sh"
    ).read_text()


def test_runner_has_no_local_solver_fallback() -> None:
    runner = (
        ROOT / "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py"
    ).read_text()
    assert "SLURM_ARRAY_JOB_ID" in runner
    assert "SLURM_ARRAY_TASK_ID" in runner
    assert "SLURM allocation differs from frozen protocol" in runner
    assert "--validate-only" in runner
    assert "run_worker(" in runner


def test_scheduler_contract_enforces_array_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = {
        "SLURM_ARRAY_JOB_ID": "12345",
        "SLURM_ARRAY_TASK_COUNT": "1500",
        "SLURM_ARRAY_TASK_ID": "0",
        "SLURM_ARRAY_TASK_MAX": "1499",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "25",
        "SLURM_JOB_ID": "12346",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "49152",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    outputs = iter(
        (
            "JobId=12346 ArrayJobId=12345 ArrayTaskId=0 Partition=nextgen "
            "NumCPUs=25 NumTasks=1 CPUs/Task=25 "
            "ReqTRES=cpu=25,mem=48G,node=1,billing=25 "
            "AllocTRES=cpu=25,mem=48G,node=1,billing=25 "
            "MinMemoryNode=48G TresPerTask=cpu=25 "
            "TimeLimit=02:00:00 JobState=RUNNING",
            "JobId=12345 ArrayTaskThrottle=8",
        )
    )
    monkeypatch.setattr(
        "run_corpus_v4_cps_multifidelity_task.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=next(outputs), stderr=""
        ),
    )
    observed = validate_slurm_contract("cps_fem_r3_p16", 1500, _protocol())
    assert observed["scheduler_array_record"]["ArrayTaskThrottle"] == "8"

    outputs = iter(
        (
            "JobId=12346 ArrayJobId=12345 ArrayTaskId=0 Partition=nextgen "
            "NumCPUs=25 NumTasks=1 CPUs/Task=25 "
            "ReqTRES=cpu=25,mem=48G,node=1,billing=25 "
            "AllocTRES=cpu=25,mem=48G,node=1,billing=25 "
            "MinMemoryNode=48G TresPerTask=cpu=25 "
            "TimeLimit=02:00:00 JobState=RUNNING",
            "JobId=12345 ArrayTaskThrottle=99",
        )
    )
    with pytest.raises(SystemExit, match="differs from frozen protocol"):
        validate_slurm_contract("cps_fem_r3_p16", 1500, _protocol())


@pytest.mark.parametrize(
    "resource_fields",
    (
        "NumCPUs=50 NumTasks=1 CPUs/Task=25",
        "NumCPUs=25 NumTasks=2 CPUs/Task=25",
        "NumCPUs=25 NumTasks=1 CPUs/Task=24",
    ),
)
def test_scheduler_contract_rejects_nonexact_cpu_shape(
    monkeypatch: pytest.MonkeyPatch, resource_fields: str
) -> None:
    environment = {
        "SLURM_ARRAY_JOB_ID": "12345",
        "SLURM_ARRAY_TASK_COUNT": "1500",
        "SLURM_ARRAY_TASK_ID": "0",
        "SLURM_ARRAY_TASK_MAX": "1499",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "25",
        "SLURM_JOB_ID": "12346",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "49152",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    outputs = iter(
        (
            "JobId=12346 ArrayJobId=12345 ArrayTaskId=0 Partition=nextgen "
            f"{resource_fields} ReqTRES=cpu=25,mem=48G,node=1,billing=25 "
            "AllocTRES=cpu=25,mem=48G,node=1,billing=25 "
            "MinMemoryNode=48G TresPerTask=cpu=25 "
            "TimeLimit=02:00:00 JobState=RUNNING",
            "JobId=12345 ArrayTaskThrottle=8",
        )
    )
    monkeypatch.setattr(
        "run_corpus_v4_cps_multifidelity_task.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=next(outputs), stderr=""
        ),
    )
    with pytest.raises(SystemExit, match="differs from frozen protocol"):
        validate_slurm_contract("cps_fem_r3_p16", 1500, _protocol())


def test_scheduler_contract_accepts_memory_inflated_cpu_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "SLURM_ARRAY_JOB_ID": "22345",
        "SLURM_ARRAY_TASK_COUNT": "198",
        "SLURM_ARRAY_TASK_ID": "0",
        "SLURM_ARRAY_TASK_MAX": "197",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "41",
        "SLURM_JOB_ID": "22346",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "163840",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    outputs = iter(
        (
            "JobId=22346 ArrayJobId=22345 ArrayTaskId=0 Partition=nextgen "
            "NumCPUs=41 NumTasks=1 CPUs/Task=41 "
            "ReqTRES=cpu=25,mem=160G,node=1,billing=25 "
            "AllocTRES=cpu=41,mem=160G,node=1,billing=41 "
            "MinMemoryNode=160G TresPerTask=cpu=25 "
            "TimeLimit=03:00:00 JobState=RUNNING",
            "JobId=22345 ArrayTaskThrottle=2",
        )
    )
    monkeypatch.setattr(
        "run_corpus_v4_cps_multifidelity_task.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=next(outputs), stderr=""
        ),
    )
    observed = validate_slurm_contract("cps_fem_r4_p16", 198, _protocol())
    assert observed["requested_cpus_per_task"] == 25
    assert observed["allocated_cpus_per_task"] == 41


@pytest.mark.parametrize(
    "allocated_tres",
    (
        "cpu=24,mem=48G,node=1,billing=24",
        "cpu=25,mem=47G,node=1,billing=25",
    ),
)
def test_scheduler_contract_rejects_inconsistent_allocated_tres(
    monkeypatch: pytest.MonkeyPatch, allocated_tres: str
) -> None:
    environment = {
        "SLURM_ARRAY_JOB_ID": "32345",
        "SLURM_ARRAY_TASK_COUNT": "1500",
        "SLURM_ARRAY_TASK_ID": "0",
        "SLURM_ARRAY_TASK_MAX": "1499",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "25",
        "SLURM_JOB_ID": "32346",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": "49152",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    outputs = iter(
        (
            "JobId=32346 ArrayJobId=32345 ArrayTaskId=0 Partition=nextgen "
            "NumCPUs=25 NumTasks=1 CPUs/Task=25 "
            "ReqTRES=cpu=25,mem=48G,node=1,billing=25 "
            f"AllocTRES={allocated_tres} MinMemoryNode=48G "
            "TresPerTask=cpu=25 TimeLimit=02:00:00 JobState=RUNNING",
            "JobId=32345 ArrayTaskThrottle=8",
        )
    )
    monkeypatch.setattr(
        "run_corpus_v4_cps_multifidelity_task.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=next(outputs), stderr=""
        ),
    )
    with pytest.raises(SystemExit, match="differs from frozen protocol"):
        validate_slurm_contract("cps_fem_r3_p16", 1500, _protocol())
