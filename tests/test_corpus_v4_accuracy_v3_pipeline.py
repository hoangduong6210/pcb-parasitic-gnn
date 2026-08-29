"""Cross-module leakage, metric, task, and scheduler contracts for Corpus V4."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
for directory in (
    ROOT / "code/experiments/proofs",
    ROOT / "code/models/gnn",
    ROOT / "code/inference",
):
    sys.path.insert(0, str(directory))

import corpus_v4_accuracy_contract_v3 as contract  # noqa: E402
import finalize_corpus_v4_accuracy_v3 as finalizer  # noqa: E402
import plan_corpus_v4_accuracy_v3 as planner  # noqa: E402
import plan_corpus_v4_accuracy_resume_v3 as resume  # noqa: E402
import run_corpus_v4_accuracy_task_v3 as runner  # noqa: E402


R2_LOCK_PATH = ROOT / "protocols/corpus_v4_accuracy_execution_lock_v3r2.json"
R2_LOCK_SHA256 = "8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c"


def _materialize(artifacts: dict[str, bytes], directory: Path) -> None:
    directory.mkdir(exist_ok=True)
    for name, content in artifacts.items():
        (directory / name).write_bytes(content)


def test_contract_reads_the_deterministic_25_cell_plan(tmp_path: Path) -> None:
    artifacts = planner.build_artifacts(root=ROOT, protocol_path=planner.DEFAULT_PROTOCOL)
    _materialize(artifacts, tmp_path)
    plan, rows, plan_sha, manifest_sha = contract.validate_plan(
        tmp_path / "plan.json", tmp_path / "task_manifest.jsonl"
    )
    assert plan_sha == contract.sha256_file(tmp_path / "plan.json")
    assert manifest_sha == contract.sha256_file(tmp_path / "task_manifest.jsonl")
    assert [contract.canonical_task_row(index) for index in range(25)] == [
        {
            key: row[key]
            for key in (
                "task_id",
                "split_seed",
                "init_seed",
                "designated_downstream_checkpoint",
            )
        }
        for row in rows
    ]
    assert plan["artifact_sha256"]["task_manifest.jsonl"] == manifest_sha


def test_root_and_execution_source_closures_are_exact(tmp_path: Path) -> None:
    artifacts = planner.build_artifacts(root=ROOT, protocol_path=planner.DEFAULT_PROTOCOL)
    _materialize(artifacts, tmp_path)
    protocol, protocol_sha = contract.validate_protocol(planner.DEFAULT_PROTOCOL)
    plan, rows, plan_sha, manifest_sha = contract.validate_plan(
        tmp_path / "plan.json", tmp_path / "task_manifest.jsonl"
    )

    evaluation_sha = contract.validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=tmp_path / "plan.json",
        task_rows=rows,
        task_manifest_sha256=manifest_sha,
    )
    assert evaluation_sha == contract.sha256_file(tmp_path / "evaluation_dataset.jsonl")
    assert set(plan["planner_source_sha256"]) == set(contract.PLANNER_SOURCE_NAMES)
    assert "code/core/scientific_artifact.py" in plan["planner_source_sha256"]
    assert contract.TASK_ROW_SCHEMA != contract.TASK_MANIFEST_SCHEMA

    lock_path = tmp_path / "execution_lock.json"
    payload = contract.write_execution_lock(
        lock_path,
        protocol_path=planner.DEFAULT_PROTOCOL,
        plan_path=tmp_path / "plan.json",
        task_manifest_path=tmp_path / "task_manifest.jsonl",
    )
    lock, lock_sha = contract.validate_execution_lock(
        lock_path, contract.sha256_file(lock_path)
    )
    assert set(payload["source_sha256"]) == set(contract.EXECUTION_SOURCE_NAMES)
    assert "code/env.sh" in payload["source_sha256"]
    contract.validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=tmp_path / "plan.json",
        task_rows=rows,
        task_manifest_sha256=manifest_sha,
        lock=lock,
        lock_sha256=lock_sha,
    )
    assert lock["plan_sha256"] == plan_sha

    missing_source = copy.deepcopy(payload)
    del missing_source["source_sha256"]["code/env.sh"]
    invalid_lock_path = tmp_path / "missing-source-lock.json"
    invalid_lock_path.write_text(
        json.dumps(missing_source, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source closure is not exact"):
        contract.validate_execution_lock(
            invalid_lock_path, contract.sha256_file(invalid_lock_path)
        )


def test_checked_in_r2_execution_lock_is_exact() -> None:
    lock, lock_sha = contract.validate_execution_lock(R2_LOCK_PATH, R2_LOCK_SHA256)
    script_path = ROOT / "code/jobs/submit_corpus_v4_accuracy_v3.sh"

    assert lock_sha == R2_LOCK_SHA256
    assert lock["source_sha256"][script_path.relative_to(ROOT).as_posix()] == (
        contract.sha256_file(script_path)
    )


def test_protocol_rejects_type_coercion_in_frozen_fields(tmp_path: Path) -> None:
    changed = json.loads(planner.DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
    changed["optimization"]["batch_size"] = True
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="frozen protocol"):
        contract.validate_protocol(path)


@pytest.mark.parametrize(
    "content",
    (
        '{"root": 1, "root": 2}\n',
        '{"root": NaN}\n',
        '{"root": Infinity}\n',
    ),
)
def test_control_json_rejects_duplicate_keys_and_nonfinite_constants(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "control.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid strict JSON"):
        contract.load_json(path)
    with pytest.raises(planner.AccuracyPlanError, match="invalid strict JSON"):
        planner.load_json(path)


def test_control_jsonl_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "control.jsonl"
    path.write_text('{"task_id": 1, "task_id": 2}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        contract.load_jsonl(path)
    with pytest.raises(planner.AccuracyPlanError, match="duplicate JSON object key"):
        planner.load_jsonl(path)


def test_task_identity_rejects_bool_and_out_of_range() -> None:
    assert contract.canonical_task_row(12) == {
        "designated_downstream_checkpoint": True,
        "init_seed": 42,
        "split_seed": 42,
        "task_id": 12,
    }
    with pytest.raises(ValueError):
        contract.canonical_task_row(True)
    with pytest.raises(ValueError):
        contract.canonical_task_row(25)


def test_repo_path_rejects_intermediate_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "artifact.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(contract, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="traverses a symlink"):
        contract.resolve_repo_path("alias/artifact.json", "candidate artifact")


def test_task_manifest_rejects_intermediate_bundle_symlink(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    external = tmp_path / "external"
    attempt.mkdir()
    external.mkdir()
    payload = external / "metadata.json"
    payload.write_text("external bytes\n", encoding="utf-8")
    (attempt / "bundle").symlink_to(external, target_is_directory=True)
    manifest = attempt / "TASK_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "files_sha256": {
                    "bundle/metadata.json": contract.sha256_file(payload)
                },
                "schema": contract.TASK_MANIFEST_SCHEMA,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="traverses a symlink"):
        contract.validate_file_manifest(manifest)


def _synthetic_samples() -> dict[int, dict]:
    samples: dict[int, dict] = {}
    for index in range(4):
        samples[index] = {
            "node_feat": np.full((2, 9), index + 1.0, dtype=np.float32),
            "edge_feat": np.full((2, 7), index + 2.0, dtype=np.float32),
            "edge_index": np.asarray([[0, 1], [1, 0]], dtype=np.int64),
            "reference_r3": np.asarray([index + 1.0, index + 2.0, index + 3.0, index + 4.0], dtype=np.float64),
        }
    return samples


def test_normalization_is_fitted_only_on_train_membership() -> None:
    samples = _synthetic_samples()
    first = runner.TrainOnlyNormalizer(samples, [0, 1]).arrays()
    mutated = copy.deepcopy(samples)
    mutated[2]["node_feat"] *= 1e6
    mutated[2]["edge_feat"] *= 1e6
    mutated[2]["reference_r3"] *= 1e6
    mutated[3]["node_feat"] *= 1e9
    mutated[3]["reference_r3"] *= 1e9
    second = runner.TrainOnlyNormalizer(mutated, [0, 1]).arrays()
    assert set(first) == set(second)
    for name in first:
        np.testing.assert_array_equal(first[name], second[name])


def test_metric_reconstruction_has_known_family_macro_value() -> None:
    metrics = contract.metric_set(
        prediction=[11.0, 18.0, 33.0],
        reference=[10.0, 20.0, 30.0],
        family_ids=["a", "a", "b"],
    )
    assert metrics["family_macro_mape_pct"] == pytest.approx(10.0)
    assert metrics["mean_ape_pct"] == pytest.approx(10.0)
    assert metrics["median_ape_pct"] == pytest.approx(10.0)
    assert metrics["n_families"] == 2
    assert metrics["n_nonpositive_predictions"] == 0
    assert metrics["nonpositive_prediction_rate_pct"] == 0.0
    with pytest.raises(ValueError, match="non-finite predictions"):
        contract.metric_set([1.0, np.nan], [1.0, 2.0], ["a", "b"])


def test_finalizer_reconstructs_three_scopes_without_r4_substitution() -> None:
    evaluation: dict[int, dict] = {}
    predictions: list[dict] = []
    for layout_id in range(39):
        lp = float(layout_id + 2)
        ls = float(layout_id + 3)
        reference = [
            float(layout_id + 1),
            lp,
            ls,
            0.5 * float(np.sqrt(lp * ls)),
        ]
        evaluation[layout_id] = {
            "evaluation_only_r4_cps": {
                "fidelity_id": "cps_fem_r4_p16_t1_v2",
                "units": "pF",
                "value": reference[0] * 0.9,
            },
            "family_id": f"family-{layout_id % 13}",
            "geometry_sha256": f"{layout_id:064x}",
            "layout_id": layout_id,
            "training_reference": {
                target: {"fidelity_id": "test", "units": "test", "value": value}
                for target, value in zip(contract.TARGETS, reference)
            },
        }
        predictions.append(
            {
                "family_id": evaluation[layout_id]["family_id"],
                "geometry_sha256": evaluation[layout_id]["geometry_sha256"],
                "layout_id": layout_id,
                    "prediction": list(reference),
                    "reference_r3": list(reference),
                "reference_r4_cps_pf": reference[0] * 0.9,
                "schema": finalizer.PREDICTION_SCHEMA,
                "target_order": list(contract.TARGETS),
            }
        )
    task = {
        "partitions": {"test": {"layout_ids": list(range(39))}},
        "r4_test_layout_ids": list(range(39)),
    }
    metrics = finalizer.recompute_task_metrics(
        predictions, task, evaluation, relative_tolerance=1e-9
    )
    assert metrics["r3_full_test"]["Cps_pF"]["mean_ape_pct"] == 0.0
    assert metrics["r4_panel_r3"]["Cps_pF"]["mean_ape_pct"] == 0.0
    assert metrics["r4_panel_r4"]["Cps_pF"]["mean_ape_pct"] == pytest.approx(100.0 / 9.0)
    assert metrics["physical_validity"]["prediction"]["n_violations"] == 0
    assert metrics["physical_validity"]["reference_r3"]["n_violations"] == 0
    nonpassive = copy.deepcopy(predictions)
    nonpassive[0]["prediction"][3] = 10.0 * float(
        np.sqrt(nonpassive[0]["prediction"][1] * nonpassive[0]["prediction"][2])
    )
    nonpassive_metrics = finalizer.recompute_task_metrics(
        nonpassive, task, evaluation, relative_tolerance=1e-9
    )
    assert nonpassive_metrics["physical_validity"]["prediction"]["n_violations"] == 1
    assert (
        nonpassive_metrics["physical_validity"]["prediction"][
            "max_abs_coupling_factor"
        ]
        == pytest.approx(10.0)
    )
    tampered = copy.deepcopy(predictions)
    tampered[0]["reference_r4_cps_pf"] = tampered[0]["reference_r3"][0]
    with pytest.raises(ValueError, match="identity mismatch"):
        finalizer.recompute_task_metrics(
            tampered, task, evaluation, relative_tolerance=1e-9
        )


def test_crossed_interval_is_deterministic_and_labeled_descriptive() -> None:
    protocol = json.loads((ROOT / "protocols/corpus_v4_accuracy_v3.json").read_text())
    matrix = np.arange(25, dtype=np.float64).reshape(5, 5)
    first = finalizer.crossed_seed_grid_summary(matrix, protocol)
    second = finalizer.crossed_seed_grid_summary(matrix, protocol)
    assert first == second
    assert first["mean_across_25_cells"] == 12.0
    assert "descriptive" in first["interval_semantics"]
    assert "confidence" in first["interval_semantics"]


def test_reference_fidelity_gap_is_stored_once_per_split_and_registry() -> None:
    evaluation = {
        layout_id: {
            "evaluation_only_r4_cps": {"value": float(layout_id + 1)},
            "family_id": f"family-{layout_id % 66}",
            "training_reference": {
                "Cps_pF": {"value": 1.1 * float(layout_id + 1)}
            },
        }
        for layout_id in range(198)
    }
    tasks = []
    for task_id in range(25):
        row = contract.canonical_task_row(task_id)
        row["r4_test_layout_ids"] = list(range(39))
        tasks.append(row)

    gap = finalizer.build_reference_fidelity_gap(tasks, evaluation)

    assert gap["schema"] == finalizer.REFERENCE_GAP_SCHEMA
    assert len(gap["per_split"]) == 5
    assert [row["split_seed"] for row in gap["per_split"]] == [40, 41, 42, 43, 44]
    complete = gap["complete_selected_registry"]
    assert len(complete["layout_ids"]) == 198
    assert complete["metrics_r3_as_prediction_r4_as_reference"][
        "mean_ape_pct"
    ] == pytest.approx(10.0)


def test_slurm_guard_fails_before_scheduler_query_when_environment_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = json.loads((ROOT / "protocols/corpus_v4_accuracy_v3.json").read_text())
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="environment is incomplete"):
        contract.validate_slurm_allocation(protocol, stage="training")


def _protocol() -> dict[str, Any]:
    return json.loads((ROOT / "protocols/corpus_v4_accuracy_v3.json").read_text())


def _clear_slurm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)


def _training_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cpus_per_task: int = 8,
    job_id: str | None = None,
    task_id: int = 12,
    task_min: int = 0,
    task_max: int = 24,
    task_count: int = 25,
) -> None:
    _clear_slurm_environment(monkeypatch)
    values = {
        "MKL_NUM_THREADS": "8",
        "NUMEXPR_NUM_THREADS": "8",
        "OMP_NUM_THREADS": "8",
        "OPENBLAS_NUM_THREADS": "8",
        "SLURM_ARRAY_JOB_ID": "8100000",
        "SLURM_ARRAY_TASK_COUNT": str(task_count),
        "SLURM_ARRAY_TASK_ID": str(task_id),
        "SLURM_ARRAY_TASK_MAX": str(task_max),
        "SLURM_ARRAY_TASK_MIN": str(task_min),
        "SLURM_CPUS_PER_TASK": str(cpus_per_task),
        # SLURM_JOB_ID is the numeric child allocation identity.  The logical
        # array component remains ArrayJobId_ArrayTaskId.
        "SLURM_JOB_ID": job_id or "8101234",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": str(48 * 1024),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _training_scheduler_fields(
    *,
    allocated_cpus: int = 8,
    cpus_per_task: int = 8,
    job_id: str | None = None,
    task_id: int = 12,
) -> dict[str, str]:
    return {
        "AllocTRES": f"cpu={allocated_cpus},mem=48G",
        "ArrayJobId": "8100000",
        "ArrayTaskId": str(task_id),
        "ArrayTaskThrottle": "5",
        "CPUs/Task": str(cpus_per_task),
        "Command": "/private/spool/script",
        "JobId": job_id or "8101234",
        "JobState": "RUNNING",
        "MinMemoryNode": "48G",
        "NumCPUs": str(allocated_cpus),
        "NumTasks": "1",
        "Partition": "nextgen",
        "ReqTRES": "cpu=8,mem=48G",
        "TimeLimit": "04:00:00",
        "TresPerTask": "cpu=8",
        "WorkDir": "/private/worktree",
    }


def _mock_scontrol(
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, str],
    *,
    expected_component: str,
) -> None:
    output = " ".join(f"{name}={value}" for name, value in fields.items()) + "\n"

    def run(command: list[str], **_: Any) -> SimpleNamespace:
        assert command == ["scontrol", "show", "job", "-o", expected_component]
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(contract.subprocess, "run", run)


def test_training_slurm_guard_accepts_exact_allocation_and_sanitizes_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _training_environment(monkeypatch)
    fields = _training_scheduler_fields()
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="training")

    assert receipt["array_task_id"] == 12
    assert receipt["allocated_cpus_per_task"] == 8
    assert receipt["requested_cpus_per_task"] == 8
    assert set(receipt["scheduler_record"]) == set(
        contract.SCHEDULER_RECORD_ALLOWLIST
    )
    assert "Command" not in receipt["scheduler_record"]
    assert "WorkDir" not in receipt["scheduler_record"]


def test_training_slurm_guard_accepts_memory_inflated_cpu_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _training_environment(monkeypatch, cpus_per_task=13)
    fields = _training_scheduler_fields(allocated_cpus=13, cpus_per_task=13)
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="training")

    assert receipt["requested_cpus_per_task"] == 8
    assert receipt["allocated_cpus_per_task"] == 13
    assert receipt["environment_cpus_per_task"] == 13
    assert receipt["scheduler_record"]["CPUs/Task"] == "13"
    assert receipt["scheduler_record"]["NumCPUs"] == "13"
    assert receipt["scheduler_record"]["ReqTRES"] == "cpu=8,mem=48G"
    assert receipt["scheduler_record"]["AllocTRES"] == "cpu=13,mem=48G"


def test_training_slurm_guard_rejects_thread_environment_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _training_environment(monkeypatch)
    monkeypatch.setenv("OMP_NUM_THREADS", "7")
    fields = _training_scheduler_fields()
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    with pytest.raises(SystemExit, match="frozen training protocol"):
        contract.validate_slurm_allocation(_protocol(), stage="training")


def test_training_slurm_guard_accepts_numeric_child_job_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_job_id = "8101234"
    _training_environment(monkeypatch, job_id=child_job_id)
    fields = _training_scheduler_fields(job_id=child_job_id)
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="training")

    assert receipt["job_id"] == child_job_id
    assert receipt["array_job_id"] == "8100000"
    assert receipt["array_task_id"] == 12
    assert receipt["scheduler_record"]["JobId"] == child_job_id


def test_training_slurm_guard_accepts_final_element_base_job_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _training_environment(monkeypatch, job_id="8100000", task_id=24)
    fields = _training_scheduler_fields(job_id="8100000", task_id=24)
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_24")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="training")

    assert receipt["job_id"] == "8100000"
    assert receipt["array_job_id"] == "8100000"
    assert receipt["array_task_id"] == 24
    assert receipt["scheduler_record"]["JobId"] == "8100000"


def test_finalizer_slurm_guard_accepts_exact_nonarray_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_slurm_environment(monkeypatch)
    for name, value in {
        "MKL_NUM_THREADS": "2",
        "NUMEXPR_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "SLURM_CPUS_PER_TASK": "2",
        "SLURM_JOB_ID": "8200000",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": str(16 * 1024),
    }.items():
        monkeypatch.setenv(name, value)
    fields = {
        "AllocTRES": "cpu=2,mem=16G",
        "CPUs/Task": "2",
        "JobId": "8200000",
        "JobState": "RUNNING",
        "MinMemoryNode": "16G",
        "NumCPUs": "2",
        "NumTasks": "1",
        "Partition": "nextgen",
        "ReqTRES": "cpu=2,mem=16G",
        "TimeLimit": "00:30:00",
        "TresPerTask": "cpu=2",
    }
    _mock_scontrol(monkeypatch, fields, expected_component="8200000")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="finalizer")

    assert receipt["array_job_id"] is None
    assert receipt["array_task_id"] is None
    assert receipt["requested_memory_gib"] == 16


def test_finalizer_slurm_guard_accepts_memory_inflated_cpu_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_slurm_environment(monkeypatch)
    for name, value in {
        "MKL_NUM_THREADS": "2",
        "NUMEXPR_NUM_THREADS": "2",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "SLURM_CPUS_PER_TASK": "3",
        "SLURM_JOB_ID": "8200000",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": str(16 * 1024),
    }.items():
        monkeypatch.setenv(name, value)
    fields = {
        "AllocTRES": "cpu=3,mem=16G",
        "CPUs/Task": "3",
        "JobId": "8200000",
        "JobState": "RUNNING",
        "MinMemoryNode": "16G",
        "NumCPUs": "3",
        "NumTasks": "1",
        "Partition": "nextgen",
        "ReqTRES": "cpu=2,mem=16G",
        "TimeLimit": "00:30:00",
        "TresPerTask": "cpu=2",
    }
    _mock_scontrol(monkeypatch, fields, expected_component="8200000")

    receipt = contract.validate_slurm_allocation(_protocol(), stage="finalizer")

    assert receipt["requested_cpus_per_task"] == 2
    assert receipt["allocated_cpus_per_task"] == 3
    assert receipt["scheduler_record"]["CPUs/Task"] == "3"
    assert receipt["scheduler_record"]["NumCPUs"] == "3"


def test_training_slurm_guard_accepts_exact_sparse_retry_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed = [3, 7, 12]
    _training_environment(
        monkeypatch, task_id=7, task_min=3, task_max=12, task_count=3
    )
    fields = _training_scheduler_fields(task_id=7)
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_7")

    receipt = contract.validate_slurm_allocation(
        _protocol(), stage="training", allowed_training_task_ids=allowed
    )

    assert receipt["array_task_id"] == 7


def _pending_bindings() -> dict[str, str]:
    return {
        "execution_lock_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "task_manifest_sha256": "d" * 64,
    }


def _write_pending_set(
    path: Path, pending: list[dict[str, Any]]
) -> tuple[dict[str, Any], str]:
    payload: dict[str, Any] = {
        **_pending_bindings(),
        "n_pending": len(pending),
        "pending": pending,
        "schema": contract.PENDING_SCHEMA,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload, contract.sha256_file(path)


def test_pending_set_accepts_exact_ordered_sparse_task_ids(tmp_path: Path) -> None:
    path = tmp_path / "pending.json"
    payload, digest = _write_pending_set(
        path, [contract.canonical_task_row(index) for index in (3, 7, 12)]
    )

    observed, task_ids, observed_digest = contract.validate_pending_set(
        path, digest, _pending_bindings()
    )

    assert observed == payload
    assert task_ids == [3, 7, 12]
    assert observed_digest == digest


@pytest.mark.parametrize("case", ("bool", "float", "duplicate", "reordered"))
def test_pending_set_rejects_noncanonical_task_ids(
    tmp_path: Path, case: str
) -> None:
    rows = [contract.canonical_task_row(index) for index in (3, 7, 12)]
    if case == "bool":
        rows[0] = contract.canonical_task_row(1)
        rows[0]["task_id"] = True
    elif case == "float":
        rows[0]["task_id"] = 3.0
    elif case == "duplicate":
        rows[1] = copy.deepcopy(rows[0])
    elif case == "reordered":
        rows.reverse()
    else:  # pragma: no cover - the parametrization above is the allowlist
        raise AssertionError(case)
    path = tmp_path / f"pending-{case}.json"
    _, digest = _write_pending_set(path, rows)

    with pytest.raises(ValueError):
        contract.validate_pending_set(path, digest, _pending_bindings())


def test_pending_set_rejects_external_hash_and_root_binding_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pending.json"
    _, digest = _write_pending_set(
        path, [contract.canonical_task_row(index) for index in (3, 7, 12)]
    )
    with pytest.raises(ValueError):
        contract.validate_pending_set(path, "0" * 64, _pending_bindings())

    changed = _pending_bindings()
    changed["plan_sha256"] = "e" * 64
    with pytest.raises(ValueError):
        contract.validate_pending_set(path, digest, changed)


def _write_checkpoint_only_attempt(
    root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, str], dict[str, Any]]:
    attempt = root / "task_12"
    bundle = attempt / "bundle"
    bundle.mkdir(parents=True)
    validation_ids = [5, 10, 20, 52, 58]
    test_ids = [3, 6, 7, 19, 22]
    layouts = {
        row["layout_id"]: row
        for row in planner.load_jsonl(ROOT / "datasets/corpus_v3/layouts.jsonl")
    }
    smoke_rows = [
        {
            "geometry_sha256": layouts[layout_id]["geometry_sha256"],
            "layout": layouts[layout_id]["layout"],
            "layout_id": layout_id,
        }
        for layout_id in validation_ids
    ]
    (attempt / "smoke_examples.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in smoke_rows)
    )
    curve = [
        {
            "epoch": epoch,
            "learning_rate": 1e-3,
            "schema": "pcb-gnn.corpus-v4-accuracy-learning-curve.v3",
            "train_loss": 1.0 / epoch,
            "validation_loss_diagnostic_only": 2.0 / epoch,
        }
        for epoch in range(1, 201)
    ]
    (attempt / "learning_curve.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in curve)
    )
    (bundle / "metadata.json").write_text("{}\n")
    (bundle / "weights_and_norm.npz").write_bytes(b"safe-bundle-fixture")

    roots = {
        "execution_lock_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "task_manifest_sha256": "d" * 64,
    }
    task_row = {
        **contract.canonical_task_row(12),
        "evaluation_dataset_sha256": "e" * 64,
        "partition_family_ids_sha256": {
            "test": "2" * 64,
            "train": "3" * 64,
            "validation": "4" * 64,
        },
        "partition_layout_ids_sha256": {
            "test": "5" * 64,
            "train": "6" * 64,
            "validation": "7" * 64,
        },
        "partitions": {
            "test": {"layout_ids": test_ids},
            "validation": {"layout_ids": validation_ids},
        },
        "r4_test_layout_ids_sha256": "8" * 64,
        "training_dataset": {
            "path": "training_split_42.jsonl",
            "sha256": "9" * 64,
        },
    }
    batch_hash = "0" * 64
    source_hashes = {
        "code/example.py": "f" * 64,
        "code/jobs/submit_corpus_v4_accuracy_v3.sh": batch_hash,
    }
    scheduler_fields = _training_scheduler_fields(job_id="8101234")
    scheduler = {
        "allocated_cpus_per_task": 8,
        "array_job_id": "8100000",
        "array_task_id": 12,
        "environment_cpus_per_task": 8,
        "job_id": "8101234",
        "requested_cpus_per_task": 8,
        "requested_memory_gib": 48,
        "scheduler_record": {
            name: scheduler_fields[name]
            for name in contract.SCHEDULER_RECORD_ALLOWLIST
        },
        "scientific_threads": 8,
    }
    result: dict[str, Any] = {
        "bindings": {
            "expected_source_git_head": "1" * 40,
            "heldout_commitment_sha256": task_row["evaluation_dataset_sha256"],
            "retry_pending_set": None,
            "training_dataset_sha256": task_row["training_dataset"]["sha256"],
            **roots,
        },
        "checkpoint": {},
        "created_utc": "2026-08-29T12:00:00+00:00",
        "evaluation": {
            "heldout_bytes_opened": False,
            "heldout_used_for_normalization_optimization_or_acceptance": False,
            "test_predictions_emitted": False,
        },
        "integrity": {"passed": True},
        "membership_sha256": {
            "partition_family_ids": task_row["partition_family_ids_sha256"],
            "partition_layout_ids": task_row["partition_layout_ids_sha256"],
            "r4_test_layout_ids": task_row["r4_test_layout_ids_sha256"],
        },
        "provenance": {
            "executed_batch_script_sha256": batch_hash,
            "final_git_dirty_paths": [],
            "final_git_head": "1" * 40,
            "final_source_file_sha256": source_hashes,
            "final_untracked_source_paths": [],
            "git_dirty_paths": [],
            "sandbox": {
                "backend": "bubblewrap",
                "executable_sha256": _protocol()["sandbox"]["executable_sha256"],
                "filesystem_boundary_passed": True,
                "forbidden_roots_absent": True,
                "hidden_training_artifact_count": 4,
                "sandbox_root": "/workspace",
                "selected_training_artifact": "training_split_42.jsonl",
            },
            "scheduler": scheduler,
            "software": {
                **contract.runtime_identity(),
                "scipy": "1.13.1",
                "torch_build": "2.8.0+cu128",
            },
            "source_file_sha256": source_hashes,
            "source_git_head": "1" * 40,
            "untracked_source_paths": [],
        },
        "schema": contract.TASK_RESULT_SCHEMA,
        "task": contract.canonical_task_row(12),
        "training": {
            "epochs_completed": 200,
            "final_epoch": 200,
            "model_selection": "fixed final epoch; validation diagnostic only",
            "wall_s": 123.0,
        },
    }
    artifact_names = (
        "bundle/metadata.json",
        "bundle/weights_and_norm.npz",
        "learning_curve.jsonl",
        "result.json",
        "smoke_examples.jsonl",
    )
    result["checkpoint"] = {
        "archive_sha256": contract.sha256_file(bundle / "weights_and_norm.npz"),
        "metadata_sha256": contract.sha256_file(bundle / "metadata.json"),
        "smoke_examples_sha256": contract.sha256_file(
            attempt / "smoke_examples.jsonl"
        ),
    }
    (attempt / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    manifest = contract.build_file_manifest(attempt, artifact_names)
    manifest_path = attempt / "TASK_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    lock = {"source_sha256": source_hashes}
    return manifest_path, manifest, task_row, roots, lock


def _validate_checkpoint_only_attempt(
    manifest_path: Path,
    task_row: dict[str, Any],
    roots: dict[str, str],
    lock: dict[str, Any],
) -> dict[str, Any]:
    return resume.validate_attempt(
        manifest_path,
        task_row=task_row,
        protocol=_protocol(),
        protocol_sha256=roots["protocol_sha256"],
        plan_sha256=roots["plan_sha256"],
        task_manifest_sha256=roots["task_manifest_sha256"],
        lock=lock,
        lock_sha256=roots["execution_lock_sha256"],
        expected_source_git_head="1" * 40,
    )


def _refresh_attempt_manifest(manifest_path: Path) -> None:
    manifest = contract.build_file_manifest(
        manifest_path.parent,
        (
            "bundle/metadata.json",
            "bundle/weights_and_norm.npz",
            "learning_curve.jsonl",
            "result.json",
            "smoke_examples.jsonl",
        ),
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_resume_accepts_checkpoint_only_with_validation_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _, task_row, roots, lock = _write_checkpoint_only_attempt(
        tmp_path
    )
    monkeypatch.setattr(resume, "load_safe_npz_bundle", lambda *args, **kwargs: None)

    result = _validate_checkpoint_only_attempt(
        manifest_path, task_row, roots, lock
    )

    assert result["evaluation"] == {
        "heldout_bytes_opened": False,
        "heldout_used_for_normalization_optimization_or_acceptance": False,
        "test_predictions_emitted": False,
    }


@pytest.mark.parametrize(
    "field",
    (
        "heldout_bytes_opened",
        "heldout_used_for_normalization_optimization_or_acceptance",
        "test_predictions_emitted",
    ),
)
def test_resume_rejects_preacceptance_test_or_r4_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    manifest_path, _, task_row, roots, lock = _write_checkpoint_only_attempt(
        tmp_path
    )
    result_path = manifest_path.parent / "result.json"
    result = json.loads(result_path.read_text())
    result["evaluation"][field] = True
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    _refresh_attempt_manifest(manifest_path)
    monkeypatch.setattr(resume, "load_safe_npz_bundle", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="checkpoint-before-test"):
        _validate_checkpoint_only_attempt(manifest_path, task_row, roots, lock)


@pytest.mark.parametrize(
    "boundary",
    ("result", "evaluation", "smoke", "curve"),
)
def test_resume_rejects_extra_fields_at_nested_trust_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    manifest_path, _, task_row, roots, lock = _write_checkpoint_only_attempt(
        tmp_path
    )
    if boundary in {"result", "evaluation"}:
        result_path = manifest_path.parent / "result.json"
        result = json.loads(result_path.read_text())
        if boundary == "result":
            result["unexpected"] = "forbidden"
        else:
            result["evaluation"]["unexpected"] = False
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    elif boundary == "smoke":
        smoke_path = manifest_path.parent / "smoke_examples.jsonl"
        rows = [json.loads(line) for line in smoke_path.read_text().splitlines()]
        rows[0]["unexpected"] = "forbidden"
        smoke_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        )
    else:
        curve_path = manifest_path.parent / "learning_curve.jsonl"
        rows = [json.loads(line) for line in curve_path.read_text().splitlines()]
        rows[0]["unexpected"] = "forbidden"
        curve_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        )
    _refresh_attempt_manifest(manifest_path)
    monkeypatch.setattr(resume, "load_safe_npz_bundle", lambda *args, **kwargs: None)

    with pytest.raises(ValueError):
        _validate_checkpoint_only_attempt(manifest_path, task_row, roots, lock)


def _accounting_result(
    task_id: int = 12, *, job_id: str = "8101234"
) -> dict[str, Any]:
    fields = _training_scheduler_fields(
        allocated_cpus=16,
        cpus_per_task=16,
        job_id=job_id,
        task_id=task_id,
    )
    fields["ReqTRES"] = "cpu=8,mem=48G,node=1,billing=8"
    fields["AllocTRES"] = "cpu=16,mem=48G,node=1,billing=16"
    return {
        "provenance": {
            "scheduler": {
                "allocated_cpus_per_task": 16,
                "array_job_id": "8100000",
                "array_task_id": task_id,
                "environment_cpus_per_task": 16,
                "job_id": job_id,
                "requested_cpus_per_task": 8,
                "requested_memory_gib": 48,
                "scheduler_record": {
                    name: fields[name]
                    for name in contract.SCHEDULER_RECORD_ALLOWLIST
                },
                "scientific_threads": 8,
            }
        }
    }


def _mock_sacct(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str,
    returncode: int = 0,
    component: str = "8100000_12",
) -> None:
    def run(command: list[str], **_: Any) -> SimpleNamespace:
        assert command == [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            component,
            "--format=JobIDRaw,JobID,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ]
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(resume.subprocess, "run", run)


@pytest.mark.parametrize(
    "validator", (resume.completed_slurm_accounting, finalizer._completed_accounting)
)
def test_completed_slurm_accounting_accepts_one_exact_terminal_component(
    monkeypatch: pytest.MonkeyPatch, validator: Any
) -> None:
    _mock_sacct(
        monkeypatch,
        stdout=(
            "8101234|8100000_12|COMPLETED+|0:0|123|billing=8,cpu=8,mem=48G,node=1|billing=16,cpu=16,mem=48G,node=1|\n"
            "8101234.batch|8100000_12.batch|COMPLETED|0:0|122|billing=8,cpu=8,mem=48G,node=1|billing=16,cpu=16,mem=48G,node=1|\n"
        ),
    )

    accounting = validator(_accounting_result())

    assert accounting == {
        "AllocTRES": "billing=16,cpu=16,mem=48G,node=1",
        "ElapsedRaw": "123",
        "ExitCode": "0:0",
        "JobID": "8100000_12",
        "JobIDRaw": "8101234",
        "ReqTRES": "billing=8,cpu=8,mem=48G,node=1",
        "State": "COMPLETED",
    }


@pytest.mark.parametrize(
    ("returncode", "stdout"),
    (
        (
            1,
            "8101234|8100000_12|COMPLETED|0:0|123|cpu=8,mem=48G|cpu=16,mem=48G|\n",
        ),
        (
            0,
            "8101234|8100000_12|FAILED|0:0|123|cpu=8,mem=48G|cpu=16,mem=48G|\n",
        ),
        (
            0,
            "8101234|8100000_12|COMPLETED|1:0|123|cpu=8,mem=48G|cpu=16,mem=48G|\n",
        ),
        (
            0,
            "8101234|8100000_12|COMPLETED|0:0|123|cpu=8,mem=48G|cpu=16,mem=48G|\n"
            "8101235|8100000_12|COMPLETED|0:0|123|cpu=8,mem=48G|cpu=16,mem=48G|\n",
        ),
    ),
)
@pytest.mark.parametrize(
    "validator", (resume.completed_slurm_accounting, finalizer._completed_accounting)
)
def test_completed_slurm_accounting_rejects_query_state_exit_and_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    validator: Any,
) -> None:
    _mock_sacct(monkeypatch, stdout=stdout, returncode=returncode)

    with pytest.raises(ValueError, match="exact successful SLURM accounting"):
        validator(_accounting_result())


@pytest.mark.parametrize(
    "validator", (resume.completed_slurm_accounting, finalizer._completed_accounting)
)
def test_completed_slurm_accounting_rejects_terminal_resource_drift(
    monkeypatch: pytest.MonkeyPatch, validator: Any
) -> None:
    _mock_sacct(
        monkeypatch,
        stdout=(
            "8101234|8100000_12|COMPLETED|0:0|123|cpu=8,mem=48G|cpu=8,mem=48G|\n"
        ),
    )

    with pytest.raises(ValueError, match="terminal resources differ"):
        validator(_accounting_result())


@pytest.mark.parametrize(
    "validator", (resume.completed_slurm_accounting, finalizer._completed_accounting)
)
def test_completed_slurm_accounting_rejects_raw_job_identity_mismatch(
    monkeypatch: pytest.MonkeyPatch, validator: Any
) -> None:
    _mock_sacct(
        monkeypatch,
        stdout=(
            "8109999|8100000_12|COMPLETED|0:0|123|"
            "billing=8,cpu=8,mem=48G,node=1|"
            "billing=16,cpu=16,mem=48G,node=1|\n"
        ),
    )

    with pytest.raises(ValueError, match="raw job identity"):
        validator(_accounting_result())


@pytest.mark.parametrize(
    "validator", (resume.completed_slurm_accounting, finalizer._completed_accounting)
)
def test_completed_slurm_accounting_accepts_final_element_base_raw_id(
    monkeypatch: pytest.MonkeyPatch, validator: Any
) -> None:
    _mock_sacct(
        monkeypatch,
        component="8100000_24",
        stdout=(
            "8100000|8100000_24|COMPLETED|0:0|530|billing=8,cpu=8,mem=48G,node=1|billing=16,cpu=16,mem=48G,node=1|\n"
        ),
    )

    accounting = validator(_accounting_result(task_id=24, job_id="8100000"))

    assert accounting["JobIDRaw"] == "8100000"
    assert accounting["State"] == "COMPLETED"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    (
        ("cpu=8,mem=48G,node=1,billing=8", "billing=8,cpu=8,mem=48G,node=1", True),
        ("cpu=8,mem=48G", "cpu=8,mem=47G", False),
        ("cpu=8,cpu=8,mem=48G", "cpu=8,mem=48G", False),
        ("cpu=8,malformed", "cpu=8", False),
        ("cpu =8,mem=48G", "cpu=8,mem=48G", False),
        ("", "", False),
    ),
)
def test_tres_equivalent_is_order_independent_and_fail_closed(
    left: str, right: str, expected: bool
) -> None:
    assert contract.tres_equivalent(left, right) is expected


def test_canonical_tres_rejects_duplicate_and_malformed_fields() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        contract.canonical_tres("cpu=8,cpu=8,mem=48G")
    with pytest.raises(ValueError, match="malformed"):
        contract.canonical_tres("cpu=8,malformed")


def _accepted_set_fixture(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], dict[str, str], list[Path]]:
    monkeypatch.setattr(contract, "ROOT", root)
    monkeypatch.setattr(finalizer, "ROOT", root)
    manifest_paths: list[Path] = []
    candidate_entries: list[dict[str, Any]] = []
    accepted_entries: list[dict[str, Any]] = []
    for task_id in range(25):
        manifest_path = root / "attempts" / f"task_{task_id:02d}" / "TASK_MANIFEST.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({"task_id": task_id}) + "\n")
        relative = manifest_path.relative_to(root).as_posix()
        digest = contract.sha256_file(manifest_path)
        accounting = {
            "AllocTRES": "cpu=8,mem=48G",
            "ElapsedRaw": "123",
            "ExitCode": "0:0",
            "JobID": f"8100000_{task_id}",
            "JobIDRaw": str(8101000 + task_id),
            "ReqTRES": "cpu=8,mem=48G",
            "State": "COMPLETED",
        }
        manifest_paths.append(manifest_path)
        candidate_entries.append(
            {"path": relative, "sha256": digest, "task_id": task_id}
        )
        accepted_entries.append(
            {
                "manifest_path": relative,
                "manifest_sha256": digest,
                "scheduler_completion": accounting,
                "task_id": task_id,
            }
        )
    candidate = {
        "entries": candidate_entries,
        "schema": "pcb-gnn.corpus-v4-accuracy-candidate-index.v3",
    }
    candidate_path = root / "candidate_index.json"
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
    bindings = {
        "execution_lock_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "protocol_sha256": "c" * 64,
        "task_manifest_sha256": "d" * 64,
    }
    payload: dict[str, Any] = {
        **bindings,
        "candidate_index": {
            "path": candidate_path.relative_to(root).as_posix(),
            "sha256": contract.sha256_file(candidate_path),
        },
        "decision": {
            "checkpoint_set_complete": True,
            "claim_eligible": False,
            "held_out_inference_may_start": True,
            "speed_claim_eligible": False,
        },
        "candidate_dispositions": [
            {
                "candidate": candidate,
                "outcome": "accepted",
                "reason_code": None,
                "scheduler_completion": accepted["scheduler_completion"],
            }
            for candidate, accepted in zip(candidate_entries, accepted_entries)
        ],
        "entries": accepted_entries,
        "n_accepted": 25,
        "n_expected": 25,
        "schema": contract.ACCEPTED_SCHEMA,
    }
    accepted_path = root / "accepted_set.json"
    accepted_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return accepted_path, payload, bindings, manifest_paths


def test_accepted_set_closes_entries_to_candidate_path_and_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, payload, bindings, _ = _accepted_set_fixture(tmp_path, monkeypatch)

    entries = finalizer._validate_accepted_set(path, payload, bindings=bindings)

    assert [entry["task_id"] for entry in entries] == list(range(25))


@pytest.mark.parametrize("case", ("candidate_path", "candidate_hash", "manifest_tamper"))
def test_accepted_set_rejects_candidate_path_hash_and_byte_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    path, payload, bindings, manifests = _accepted_set_fixture(tmp_path, monkeypatch)
    changed = copy.deepcopy(payload)
    if case == "candidate_path":
        changed["candidate_index"]["path"] = "../candidate_index.json"
    elif case == "candidate_hash":
        changed["candidate_index"]["sha256"] = "0" * 64
    elif case == "manifest_tamper":
        manifests[12].write_text('{"task_id":12,"tampered":true}\n')
    else:  # pragma: no cover - the parametrization above is the allowlist
        raise AssertionError(case)

    with pytest.raises(ValueError):
        finalizer._validate_accepted_set(path, changed, bindings=bindings)


def _finalizer_evaluation_fixture(
    root: Path,
) -> tuple[
    Path,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, str],
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[int, SimpleNamespace],
    dict[str, np.ndarray],
]:
    attempt = root / "task_12"
    (attempt / "bundle").mkdir(parents=True)
    (attempt / "smoke_examples.jsonl").write_text("{}\n")
    manifest_path = attempt / "TASK_MANIFEST.json"
    manifest_path.write_text("{}\n")
    train_ids = [100, 101]
    test_ids = list(range(39))
    samples: dict[int, dict[str, Any]] = {}
    for layout_id in train_ids + test_ids:
        base = float(layout_id + 1)
        lp = base + 1.0
        ls = base + 2.0
        samples[layout_id] = {
            "edge_feat": np.full((2, 7), base + 0.5, dtype=np.float32),
            "edge_index": np.asarray([[0, 1], [1, 0]], dtype=np.int64),
            "family_id": f"family-{layout_id % 13}",
            "geometry_sha256": f"{layout_id:064x}",
            "node_feat": np.full((2, 9), base, dtype=np.float32),
            "reference_r3": np.asarray(
                [base, lp, ls, 0.5 * float(np.sqrt(lp * ls))], dtype=np.float64
            ),
        }
    evaluation: dict[int, dict[str, Any]] = {}
    r4_evaluation: dict[int, SimpleNamespace] = {}
    for layout_id in test_ids:
        sample = samples[layout_id]
        reference = sample["reference_r3"].tolist()
        r4_value = float(reference[0] * 1.01)
        evaluation[layout_id] = {
            "evaluation_only_r4_cps": {"value": r4_value},
            "family_id": sample["family_id"],
            "geometry_sha256": sample["geometry_sha256"],
            "layout_id": layout_id,
            "training_reference": {
                target: {"value": value}
                for target, value in zip(contract.TARGETS, reference)
            },
        }
        r4_evaluation[layout_id] = SimpleNamespace(
            cps_r4_pf=r4_value, geometry_sha256=sample["geometry_sha256"]
        )
    task_row = {
        "partitions": {
            "test": {"layout_ids": test_ids},
            "train": {"layout_ids": train_ids},
        },
        "r4_test_layout_ids": test_ids,
        "training_dataset": {
            "path": "training_split_42.jsonl",
            "sha256": "1" * 64,
        },
    }
    result = {
        "checkpoint": {
            "metadata_sha256": "a" * 64,
            "smoke_examples_sha256": "b" * 64,
        },
        "task": contract.canonical_task_row(12),
    }
    protocol = {
        "checkpoint": {
            "maximum_bundle_bytes": 1024,
            "maximum_uncompressed_bytes": 2048,
        },
        "optimization": {"batch_size": 32},
        "evaluation": {"passivity_relative_tolerance": 1e-9},
    }
    bindings = {
        "execution_lock_sha256": "d" * 64,
        "heldout_commitment_sha256": "c" * 64,
        "plan_sha256": "e" * 64,
        "protocol_sha256": "f" * 64,
        "task_manifest_sha256": "0" * 64,
        "training_dataset_sha256": "1" * 64,
    }
    arrays = runner.TrainOnlyNormalizer(samples, train_ids).arrays()
    return (
        manifest_path,
        task_row,
        result,
        protocol,
        bindings,
        samples,
        evaluation,
        r4_evaluation,
        arrays,
    )


def test_finalizer_evaluates_accepted_checkpoint_and_owns_prediction_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        manifest_path,
        task_row,
        result,
        protocol,
        bindings,
        samples,
        evaluation,
        r4_evaluation,
        arrays,
    ) = _finalizer_evaluation_fixture(tmp_path)
    predicted = np.stack(
        [samples[index]["reference_r3"] for index in task_row["partitions"]["test"]["layout_ids"]]
    )
    monkeypatch.setattr(
        finalizer,
        "load_safe_npz_bundle",
        lambda *args, **kwargs: SimpleNamespace(arrays=arrays),
    )
    monkeypatch.setattr(finalizer, "expected_bundle_specs", lambda: {})
    monkeypatch.setattr(finalizer, "_model_from_arrays", lambda _: object())
    monkeypatch.setattr(finalizer, "_predict", lambda *args, **kwargs: predicted)

    rows, metrics = finalizer.evaluate_accepted_checkpoint(
        manifest_path,
        task_row=task_row,
        result=result,
        protocol=protocol,
        bindings=bindings,
        samples=samples,
        evaluation=evaluation,
        r4_evaluation=r4_evaluation,
    )

    assert [row["layout_id"] for row in rows] == list(range(39))
    assert rows[12]["prediction"] == predicted[12].tolist()
    assert rows[12]["reference_r4_cps_pf"] == pytest.approx(13.0 * 1.01)
    assert all(row["schema"] == finalizer.PREDICTION_SCHEMA for row in rows)
    assert metrics["r3_full_test"]["Cps_pF"]["mean_ape_pct"] == 0.0


def test_finalizer_rejects_checkpoint_normalization_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        manifest_path,
        task_row,
        result,
        protocol,
        bindings,
        samples,
        evaluation,
        r4_evaluation,
        arrays,
    ) = _finalizer_evaluation_fixture(tmp_path)
    tampered = {name: value.copy() for name, value in arrays.items()}
    tampered["norm.node_mean"][0] += 1.0
    monkeypatch.setattr(
        finalizer,
        "load_safe_npz_bundle",
        lambda *args, **kwargs: SimpleNamespace(arrays=tampered),
    )
    monkeypatch.setattr(finalizer, "expected_bundle_specs", lambda: {})

    with pytest.raises(ValueError, match="normalization.*norm.node_mean"):
        finalizer.evaluate_accepted_checkpoint(
            manifest_path,
            task_row=task_row,
            result=result,
            protocol=protocol,
            bindings=bindings,
            samples=samples,
            evaluation=evaluation,
            r4_evaluation=r4_evaluation,
        )


@pytest.mark.parametrize(
    "allowed",
    (
        [True, 3, 7],
        [3.0, 7, 12],
        [3, 7, 7],
    ),
)
def test_training_slurm_guard_rejects_noncanonical_retry_ids(
    monkeypatch: pytest.MonkeyPatch, allowed: list[object]
) -> None:
    _training_environment(
        monkeypatch, task_id=7, task_min=3, task_max=12, task_count=3
    )
    fields = _training_scheduler_fields(task_id=7)
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_7")

    with pytest.raises((SystemExit, ValueError), match="frozen training protocol|integer"):
        contract.validate_slurm_allocation(
            _protocol(), stage="training", allowed_training_task_ids=allowed
        )


def test_training_slurm_guard_rejects_scheduler_job_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _training_environment(monkeypatch)
    fields = _training_scheduler_fields()
    fields["JobId"] = "8100000_11"
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    with pytest.raises(SystemExit, match="missing or ambiguous"):
        contract.validate_slurm_allocation(_protocol(), stage="training")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ArrayJobId", "8100001"),
        ("ArrayTaskId", "11"),
        ("ArrayTaskThrottle", "4"),
        ("ReqTRES", "cpu=7,mem=48G"),
        ("ReqTRES", "cpu=8,mem=47G"),
        ("TresPerTask", "cpu=7"),
        ("AllocTRES", "cpu=7,mem=48G"),
        ("AllocTRES", "cpu=8,mem=47G"),
        ("CPUs/Task", "7"),
        ("NumCPUs", "7"),
        ("Partition", "debug"),
        ("JobState", "PENDING"),
        ("TimeLimit", "03:59:59"),
        ("MinMemoryNode", "47G"),
    ),
)
def test_training_slurm_guard_rejects_identity_resource_and_time_mismatch(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    _training_environment(monkeypatch)
    fields = _training_scheduler_fields()
    fields[field] = value
    _mock_scontrol(monkeypatch, fields, expected_component="8100000_12")

    with pytest.raises(SystemExit, match="frozen training protocol"):
        contract.validate_slurm_allocation(_protocol(), stage="training")


def test_batch_resources_and_no_login_training_contract() -> None:
    training = (ROOT / "code/jobs/submit_corpus_v4_accuracy_v3.sh").read_text()
    final = (ROOT / "code/jobs/submit_finalize_corpus_v4_accuracy_v3.sh").read_text()
    assert "#SBATCH --array=0-24%5" in training
    assert "#SBATCH --cpus-per-task=8" in training
    assert "#SBATCH --mem=48G" in training
    assert "#SBATCH --time=04:00:00" in training
    assert "run_corpus_v4_accuracy_task_v3.py" in training
    assert "PCB_GNN_V4_ACCURACY_V3_SANDBOX_PROBE_ONLY" in training
    assert "--sandbox-probe-only" in training
    assert "SLURM_ARRAY_TASK_COUNT\" == \"1" in training
    assert "/usr/bin/env -i" in training
    assert "--clearenv" not in training
    assert "corpus_v4_accuracy_execution_lock_v3r2.json" in training
    assert "--ro-bind /etc/passwd /etc/passwd" in training
    assert "--ro-bind /etc/group /etc/group" in training
    assert "--ro-bind /run/munge /run/munge" in training
    assert "--ro-bind /run/munge /var/run/munge" in training
    assert "--ro-bind /run/slurm /run/slurm" in training
    assert (
        "--ro-bind /var/spool/slurmd/conf-cache "
        "/var/spool/slurmd/conf-cache" in training
    )
    assert "#SBATCH --cpus-per-task=2" in final
    assert "#SBATCH --mem=16G" in final
    assert "#SBATCH --time=00:30:00" in final
    assert "finalize_corpus_v4_accuracy_v3.py" in final
