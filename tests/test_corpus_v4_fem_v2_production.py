from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "code/experiments/proofs/corpus_v4_fem_v2_production.py"
SPEC = importlib.util.spec_from_file_location("corpus_v4_fem_v2_production", MODULE_PATH)
assert SPEC and SPEC.loader
production = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = production
SPEC.loader.exec_module(production)

PROTOCOL = ROOT / production.PROTOCOL_RELATIVE
PLAN = ROOT / production.PLAN_ROOT_RELATIVE / "plan.json"
LOCK = ROOT / production.LOCK_RELATIVE


def load_protocol() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def test_protocol_binds_both_positive_generation_permissions() -> None:
    protocol, protocol_sha = production.authenticate_protocol(PROTOCOL)
    records, authorities = production.validate_authorities(protocol)
    assert len(records) == 1500
    assert protocol_sha == "ba66f1ecfccd9eea3d2b36b9824dcae3f2399ffa2e9a73883f786ddca33dc709"
    assert authorities["gate_b_admission"] == "e87aedba663ce970fb7c55d5fd2db12c63db09594e4c221ef3968cb34bf6b02b"
    assert authorities["gate_c_admission"] == "7c93909df0a63930b0b54522e60b32570c6f4e9eb20feb853b2e9966b882dca1"


def test_protocol_freezes_one_thread_distinct_fidelities() -> None:
    protocol = load_protocol()
    production.validate_protocol(protocol)
    assert set(protocol["fidelities"]) == set(production.FIDELITIES)
    assert protocol["runtime"]["threads"]["PCB_GNN_GMSH_THREADS"] == "1"
    assert protocol["resource_profiles"][production.FIDELITIES[0]]["slurm"]["cpus_per_task"] == 1
    assert protocol["resource_profiles"][production.FIDELITIES[1]]["slurm"]["cpus_per_task"] == 1
    assert protocol["scientific_semantics"]["mesh_converged"] is False
    assert protocol["scientific_semantics"]["postterminal_package_admission_required_for_training"] is True


def test_protocol_rejects_weakened_scientific_semantics() -> None:
    protocol = load_protocol()
    weakened = copy.deepcopy(protocol)
    weakened["scientific_semantics"]["mesh_converged"] = True
    with pytest.raises(ValueError, match="semantics"):
        production.validate_protocol(weakened)


def test_plan_and_lock_replay_exactly() -> None:
    protocol, protocol_sha = production.authenticate_protocol(PROTOCOL)
    plan, plan_sha = production.validate_plan(
        protocol,
        protocol_sha,
        PLAN,
        "5193b000a9884fde364f3d0a05f84b5ad4c4c33bfaa477b6fa8f37db03277e20",
    )
    lock, lock_sha = production.validate_lock(
        protocol,
        protocol_sha,
        plan_sha,
        LOCK,
        "84c832aa08fc8800e604979730c315e1950d26fa4d0a2f1f7c34b9f2f34e402a",
    )
    assert plan["counts"] == {"geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198}
    assert lock["source_sha256"] == protocol["computational_sources"]
    assert lock_sha == "84c832aa08fc8800e604979730c315e1950d26fa4d0a2f1f7c34b9f2f34e402a"


@pytest.mark.parametrize(
    ("slug", "expected_count", "shard_sizes"),
    (("r3", 1500, [400, 400, 400, 300]), ("r4", 198, [198])),
)
def test_manifests_and_dispatches_have_exact_coverage(
    slug: str, expected_count: int, shard_sizes: list[int]
) -> None:
    protocol, protocol_sha = production.authenticate_protocol(PROTOCOL)
    plan, _ = production.validate_plan(
        protocol,
        protocol_sha,
        PLAN,
        "5193b000a9884fde364f3d0a05f84b5ad4c4c33bfaa477b6fa8f37db03277e20",
    )
    manifest_path = PLAN.parent / f"{slug}_manifest.jsonl"
    rows, manifest_sha, fidelity = production.validate_manifest(
        protocol, protocol_sha, plan, manifest_path
    )
    flattened: list[int] = []
    for shard_index, expected_size in enumerate(shard_sizes):
        dispatch_path = PLAN.parent / f"{slug}_dispatch_{shard_index:03d}.json"
        digest = plan["artifact_sha256"][dispatch_path.name]
        dispatch, _ = production.validate_dispatch(
            protocol_sha,
            plan,
            dispatch_path,
            digest,
            manifest_sha,
            fidelity,
            rows,
        )
        assert len(dispatch["entries"]) == expected_size
        flattened.extend(entry["task_index"] for entry in dispatch["entries"])
    assert len(rows) == expected_count
    assert flattened == list(range(expected_count))


def test_r3_manifest_maps_dense_layout_ids_and_r4_matches_frozen_registry() -> None:
    r3 = production.load_jsonl(PLAN.parent / "r3_manifest.jsonl", "R3 manifest")
    r4 = production.load_jsonl(PLAN.parent / "r4_manifest.jsonl", "R4 manifest")
    registry = json.loads(
        (ROOT / "results/corpus_v4/cps_multifidelity/plan/v1/hf_selection_registry.json").read_text(encoding="utf-8")
    )
    assert [row["layout_id"] for row in r3] == list(range(1500))
    assert [row["layout_id"] for row in r4] == sorted(
        row["layout_id"] for row in registry["rows"]
    )
    assert {row["geometry_sha256"] for row in r4} == {
        row["geometry_sha256"] for row in registry["rows"]
    }


def test_wrappers_require_dynamic_hash_pinned_dispatch_and_one_thread() -> None:
    for slug, throttle in (("r3", "%8"), ("r4", "%2")):
        text = (ROOT / f"code/jobs/submit_corpus_v4_fem_v2_{slug}.sh").read_text(encoding="utf-8")
        assert "#SBATCH --cpus-per-task=1" in text
        assert f"#SBATCH --array=0-0{throttle}" in text
        assert "#SBATCH --no-requeue" in text
        assert "export PCB_GNN_GMSH_THREADS=1" in text
        assert "PCB_GNN_V4_FEM_V2_DISPATCH_SHA256" in text
        assert "PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256" in text
        assert "--expected-source-git-head" in text
        assert "cps_multifidelity/r" not in text


def test_retry_dispatch_requires_exact_prior_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(production, "ROOT", tmp_path)
    plan_path = tmp_path / production.PLAN_ROOT_RELATIVE / "plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("{}\n", encoding="utf-8")
    plan_sha = production.sha256_file(plan_path)
    lock_sha = "3" * 64
    source_head = "4" * 40
    fidelity = production.FIDELITIES[0]
    manifest = [{"geometry_sha256": "0" * 64, "layout_id": 0, "task_index": 0}]
    retry = (
        tmp_path
        / production.OUTPUT_ROOT_RELATIVE
        / "waves/r3/wave_000/final/source_set_test/finalizer_job_7/pending_task_set.json"
    )
    retry.parent.mkdir(parents=True)
    retry.write_text(
        json.dumps(
            {
                "entries": manifest,
                "execution_lock_sha256": lock_sha,
                "fidelity_id": fidelity,
                "manifest_sha256": "5" * 64,
                "plan_sha256": plan_sha,
                "protocol_sha256": "6" * 64,
                "schema": production.PENDING_SET_SCHEMA,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    retry_sha = production.sha256_file(retry)
    admission = (
        tmp_path
        / production.OUTPUT_ROOT_RELATIVE
        / "waves/r3/wave_000/admission/source_set_test/finalizer_job_7/FINAL_ADMISSION.json"
    )
    admission.parent.mkdir(parents=True)
    admission.write_text(
        json.dumps(
            {
                "admission_eligible": True,
                "artifact_stage": "postterminal_wave_admission",
                "decision": {
                    "retry_may_start": True,
                    "scientific_outcome": "INDETERMINATE",
                    "terminal_negative": False,
                },
                "fidelity_id": fidelity,
                "preterminal_files": {
                    "pending_set_path": retry.relative_to(tmp_path).as_posix(),
                    "pending_set_sha256": retry_sha,
                },
                "roots": {
                    "execution_lock_sha256": lock_sha,
                    "plan_sha256": plan_sha,
                    "protocol_sha256": "6" * 64,
                    "source_git_head": source_head,
                },
                "schema": production.WAVE_ADMISSION_SCHEMA,
                "training_may_start": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="prior admission"):
        production.validate_dispatch(
            "6" * 64,
            {},
            retry,
            retry_sha,
            "5" * 64,
            fidelity,
            manifest,
            execution_lock_sha256=lock_sha,
            expected_source_git_head=source_head,
        )
    observed, digest = production.validate_dispatch(
        "6" * 64,
        {},
        retry,
        retry_sha,
        "5" * 64,
        fidelity,
        manifest,
        execution_lock_sha256=lock_sha,
        expected_source_git_head=source_head,
        prior_admission=admission,
        expected_prior_admission_sha256=production.sha256_file(admission),
    )
    assert observed["schema"] == production.PENDING_SET_SCHEMA
    assert digest == retry_sha


def test_validate_only_never_requires_slurm_or_runs_solver() -> None:
    command = [
        sys.executable,
        str(MODULE_PATH),
        "run",
        "--expected-protocol-sha256",
        "ba66f1ecfccd9eea3d2b36b9824dcae3f2399ffa2e9a73883f786ddca33dc709",
        "--expected-plan-sha256",
        "5193b000a9884fde364f3d0a05f84b5ad4c4c33bfaa477b6fa8f37db03277e20",
        "--expected-execution-lock-sha256",
        "84c832aa08fc8800e604979730c315e1950d26fa4d0a2f1f7c34b9f2f34e402a",
        "--manifest",
        str(PLAN.parent / "r4_manifest.jsonl"),
        "--dispatch",
        str(PLAN.parent / "r4_dispatch_000.json"),
        "--expected-dispatch-sha256",
        "897cf14c87e167115e364f3e8ffcf9f62bd0c5e3205cb81f6ec6c0ed76a4330a",
        "--output-root",
        str(ROOT / "results/corpus_v4/cps_reference_v2/production/v1/attempts/r4"),
        "--validate-only",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=True, text=True)
    payload = json.loads(completed.stdout)
    assert payload["solver_executed"] is False
    assert payload["n_tasks"] == 198


def test_execution_without_slurm_fails_before_any_attempt_write() -> None:
    output = ROOT / "results/corpus_v4/cps_reference_v2/production/v1/attempts/r4"
    before = list(output.rglob("*")) if output.exists() else []
    command = [
        sys.executable,
        str(MODULE_PATH),
        "run",
        "--expected-protocol-sha256",
        "ba66f1ecfccd9eea3d2b36b9824dcae3f2399ffa2e9a73883f786ddca33dc709",
        "--expected-plan-sha256",
        "5193b000a9884fde364f3d0a05f84b5ad4c4c33bfaa477b6fa8f37db03277e20",
        "--expected-execution-lock-sha256",
        "84c832aa08fc8800e604979730c315e1950d26fa4d0a2f1f7c34b9f2f34e402a",
        "--manifest",
        str(PLAN.parent / "r4_manifest.jsonl"),
        "--dispatch",
        str(PLAN.parent / "r4_dispatch_000.json"),
        "--expected-dispatch-sha256",
        "897cf14c87e167115e364f3e8ffcf9f62bd0c5e3205cb81f6ec6c0ed76a4330a",
        "--expected-source-git-head",
        "0" * 40,
        "--output-root",
        str(output),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, check=False, text=True)
    assert completed.returncode != 0
    assert "SLURM array environment is incomplete" in completed.stderr
    after = list(output.rglob("*")) if output.exists() else []
    assert after == before


@pytest.mark.parametrize(
    ("execution", "numerical", "expected"),
    (
        (
            {"timed_out": True, "stderr_tail": [], "stages": [], "returncode": None},
            {"pass": False, "checks": {"worker_execution": False}},
            "genuine_numerical_or_resource_failure",
        ),
        (
            {
                "timed_out": False,
                "stderr_tail": ["RuntimeError: configured resource limit exceeded: n_nodes"],
                "stages": [],
                "returncode": 1,
            },
            {"pass": False, "checks": {"worker_execution": False}},
            "genuine_numerical_or_resource_failure",
        ),
        (
            {
                "timed_out": False,
                "stderr_tail": [],
                "stages": [{"stage": "mesh_ready"}],
                "returncode": -9,
            },
            {"pass": False, "checks": {"worker_execution": False}},
            "genuine_numerical_or_resource_failure",
        ),
        (
            {
                "timed_out": False,
                "stderr_tail": ["ImportError: gmsh"],
                "stages": [],
                "returncode": 1,
            },
            {"pass": False, "checks": {"worker_execution": False}},
            "infrastructure_or_integrity_failure",
        ),
        (
            {"timed_out": False, "stderr_tail": [], "stages": [], "returncode": 0},
            {"pass": False, "checks": {"worker_execution": True}},
            "genuine_numerical_or_resource_failure",
        ),
    ),
)
def test_failure_classification_never_retries_numerical_or_resource_outcomes(
    execution: dict, numerical: dict, expected: str
) -> None:
    assert (
        production.classify_failure(
            execution,
            numerical,
            {"pass": True},
            True,
        )
        == expected
    )


def test_success_has_no_failure_class() -> None:
    assert (
        production.classify_failure(
            {"timed_out": False, "stderr_tail": [], "stages": [], "returncode": 0},
            {"pass": True, "checks": {"worker_execution": True}},
            {"pass": True},
            True,
        )
        is None
    )
