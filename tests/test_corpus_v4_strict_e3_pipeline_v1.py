"""Synthetic, solver-free contracts for the FEM-v2 coordinate-update study.

The tests exercise lifecycle and artifact-validation code only.  They never
load the production corpus, fit a model, or invoke an electromagnetic solver.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
for directory in ("code/experiments/proofs", "code/models/gnn", "code/models", "code/core"):
    sys.path.insert(0, str(ROOT / directory))

import corpus_v4_strict_e3_fem_v2_v1 as e3  # noqa: E402


def task_row(task_id: int) -> dict:
    """Return the canonical crossed split/initialization cell."""
    return {
        "task_id": task_id,
        "split_seed": 40 + task_id // 5,
        "init_seed": 40 + task_id % 5,
        "designated_downstream_checkpoint": task_id == 12,
    }


def bindings() -> dict[str, str]:
    return {
        "protocol_sha256": "a" * 64,
        "execution_lock_sha256": "b" * 64,
        "source_git_head": "c" * 40,
    }


def args(**updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "stage": "validate",
        "protocol": Path("protocol.json"),
        "execution_lock": Path("lock.json"),
        "expected_protocol_sha256": "a" * 64,
        "expected_execution_lock_sha256": "b" * 64,
        "expected_source_git_head": "c" * 40,
        "accepted_set": Path("accepted.json"),
        "expected_accepted_set_sha256": "d" * 64,
        "analysis_manifest": Path("ANALYSIS_MANIFEST.json"),
        "expected_analysis_manifest_sha256": "e" * 64,
        "out": Path("ARCHIVE_MANIFEST.json"),
        "output_root": Path("output"),
        "attempt_root": Path("attempt"),
        "probe_only": False,
        "check": False,
        "require_git_tracked": False,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def metric_grid() -> tuple[list[dict], list[dict]]:
    metrics, contrasts = [], []
    for task_id in range(25):
        task = task_row(task_id)
        for arm, value in (("strict96", 7.0), ("fixed96", 9.0), ("fixed_matched", 10.0)):
            for target in e3.TARGETS:
                metrics.append({
                    **task,
                    "arm": arm,
                    "target": target,
                    "metrics": {"family_macro_mape_pct": value, "n_nonpositive_predictions": 0},
                    "joint_prediction_diagnostic": {"n_inductance_psd_violations": 0},
                    "contextual_gnn_metrics": {"family_macro_mape_pct": 6.0},
                })
        for control, value in (("fixed96", 9.0), ("fixed_matched", 10.0)):
            for target in e3.TARGETS:
                contrasts.append({
                    **task,
                    "control": control,
                    "target": target,
                    "strict96_family_macro_mape_pct": 7.0,
                    "control_family_macro_mape_pct": value,
                    "strict96_minus_control_pp": 7.0 - value,
                    "positive_favors": "fixed-coordinate control",
                })
    return metrics, contrasts


def protocol() -> dict:
    return json.loads((ROOT / e3.PROTOCOL).read_text())


def seven_family_samples() -> dict[int, dict]:
    """Artificial validation panel required by the frozen symmetry gate."""
    samples = {}
    for index in range(7):
        nodes = np.zeros((2, 9), dtype=np.float64)
        nodes[:, :3] = [[index + 0.25, 0.0, 0.5], [index + 1.25, 1.0, -0.5]]
        nodes[:, 3:] = index + np.arange(6, dtype=np.float64)
        edges = np.zeros((2, 7), dtype=np.float64)
        edges[:, [1, 5, 6]] = [[1.0, 1.0, 0.0], [1.0, 0.0, 1.0]]
        samples[index] = {
            "node_feat": nodes,
            "edge_feat": edges,
            "edge_index": np.asarray([[0, 1], [1, 0]], dtype=np.int64),
            "reference_r3": np.asarray([10.0, 20.0, 30.0, 5.0]) + index,
            "family_id": f"family_{index}",
        }
    return samples


def test_execution_refuses_login_for_training_and_finalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither training nor held-out/replay work may start on the login node."""
    for key in tuple(os.environ):
        if key.startswith("SLURM_"):
            monkeypatch.delenv(key, raising=False)
    protocol = {"resources": {}}
    lock = {"source_sha256": {e3.WRAPPER: "0" * 64, e3.FINAL_WRAPPER: "1" * 64}}
    for stage in ("training", "finalizer"):
        with pytest.raises((ValueError, SystemExit), match="SLURM|scheduler|allocation"):
            e3.execution(args(stage=stage), protocol, lock, stage)


def test_evaluate_authenticates_all_checkpoints_before_heldout_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(*_values: object) -> None:
        raise ValueError("synthetic admission failure")

    monkeypatch.setattr(e3, "accepted_tasks", reject)
    monkeypatch.setattr(e3, "load_jsonl", lambda *_values: pytest.fail("held-out bytes opened before admission"))
    with pytest.raises(ValueError, match="admission failure"):
        e3.evaluate(args(), {}, {}, [task_row(i) for i in range(25)])


def test_training_namespace_requires_explicit_sandbox_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PCB_GNN_V4_ACCURACY_V3_SANDBOX_ACTIVE", raising=False)
    with pytest.raises((ValueError, SystemExit), match="sandbox|isolation"):
        e3._validate_training_sandbox(protocol(), {"training_dataset": {"path": "training_split_40.jsonl"}})


def test_training_context_does_not_deserialize_qualification_or_heldout_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = protocol()
    source_sha = {name: "1" * 64 for name in e3.SOURCES}
    input_sha = {name: "2" * 64 for name in e3.expected_input_names()}
    lock = {
        "schema": "pcb-gnn.corpus-v4-strict-e3-execution-lock.v1",
        "protocol_sha256": "a" * 64,
        "source_sha256": source_sha,
        "inputs": input_sha,
        "runtime": frozen["runtime"],
        "qualification": {
            "protocol_sha256": frozen["upstream"]["protocols/strict_e3_model_qualification_v1.json"],
            "receipt_sha256": frozen["upstream"][
                "results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json"
            ],
            "semantic_validation_passed": True,
        },
    }
    protocol_path, lock_path = Path("protocol.json"), Path("lock.json")
    opened: list[Path] = []

    def guarded_json(path: Path) -> dict:
        opened.append(path)
        if path == protocol_path:
            return frozen
        if path == lock_path:
            return lock
        pytest.fail(f"training context deserialized forbidden input: {path}")

    def digest(path: Path) -> str:
        if path == protocol_path:
            return "a" * 64
        if path == lock_path:
            return "b" * 64
        relative = path.relative_to(e3.ROOT).as_posix()
        if relative in source_sha:
            return source_sha[relative]
        if relative in input_sha:
            return input_sha[relative]
        raise AssertionError(f"unexpected training-context hash path: {path}")

    task_manifest = e3.ROOT / e3.PLAN / "task_manifest.jsonl"
    monkeypatch.setattr(e3, "load_json", guarded_json)
    monkeypatch.setattr(
        e3,
        "load_jsonl",
        lambda path: [e3.canonical_task_row(index) for index in range(25)]
        if path == task_manifest
        else pytest.fail(f"training context deserialized forbidden JSONL: {path}"),
    )
    monkeypatch.setattr(e3, "sha256_file", digest)
    monkeypatch.setattr(e3, "runtime", lambda: frozen["runtime"])
    monkeypatch.setattr(e3, "_source_state", lambda: ("c" * 40, False, False))
    observed_protocol, observed_lock, rows = e3.context(
        args(stage="train", protocol=protocol_path, execution_lock=lock_path), training=True
    )
    assert observed_protocol is frozen
    assert observed_lock is lock
    assert len(rows) == 25
    assert opened == [protocol_path, lock_path]


def test_evaluate_never_places_heldout_references_in_model_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """References stay in the metric path; inference work receives a dummy target."""

    class Captured(Exception):
        pass

    class LabelFreeNormalizer:
        def transform(self, sample: dict) -> dict:
            assert "reference_r3" not in sample
            return {"y": np.zeros(4, dtype=np.float32)}

    layout = {"layout_id": 0, "geometry_sha256": "g", "layout": {"synthetic": True}}
    reference = {
        "layout_id": 0,
        "family_id": "family_0",
        "geometry_sha256": "g",
        "training_reference": {target: {"value": float(index + 1)} for index, target in enumerate(e3.TARGETS)},
    }
    contextual = [{"layout_id": 0, "family_id": "family_0", "geometry_sha256": "g",
                   "reference_r3": [1.0, 2.0, 3.0, 4.0], "prediction": [1.0, 2.0, 3.0, 4.0]}]

    def records(path: Path) -> list[dict]:
        name = str(path)
        if name.endswith("datasets/corpus_v3/layouts.jsonl"):
            return [layout]
        if name.endswith("evaluation_dataset.jsonl"):
            return [reference]
        return contextual

    graph = SimpleNamespace(to_feature_matrices=lambda: (
        np.zeros((1, 9), dtype=np.float64),
        np.empty((0, 7), dtype=np.float64),
        np.empty((2, 0), dtype=np.int64),
    ))
    monkeypatch.setattr(e3, "authenticate_evaluation_inputs", lambda *_values: None)
    monkeypatch.setattr(e3, "load_jsonl", records)
    monkeypatch.setattr(e3, "build_graph_from_planar_layout", lambda _layout: graph)
    monkeypatch.setattr(e3, "load_arm", lambda *_values: ({}, object(), LabelFreeNormalizer()))

    def capture(_model: object, _normalizer: object, work: dict, _ids: list, _batch: int) -> np.ndarray:
        assert all(np.array_equal(row["y"], np.zeros(4, dtype=np.float32)) for row in work.values())
        raise Captured("held-out model batch is label-free")

    monkeypatch.setattr(e3, "_predict", capture)
    rows = [{**task_row(0), "partitions": {"test": {"layout_ids": [0]}}}]
    with pytest.raises(Captured, match="label-free"):
        e3.evaluate(args(), {"optimization": {"batch_size": 32}}, {}, rows,
                    accepted=[(Path("result.json"), {"task": task_row(0)})])


@pytest.mark.parametrize(
    "names",
    [
        [f"task_{i:02d}" for i in range(24)],
        [f"task_{i:02d}" for i in range(26)],
        [f"task_{i:02d}" for i in range(25)] + ["retry_00"],
    ],
)
def test_admission_requires_exactly_25_private_task_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, names: list[str]
) -> None:
    attempt = tmp_path / "jobs" / "job_123"
    attempt.mkdir(parents=True)
    for name in names:
        (attempt / name).mkdir()
    monkeypatch.setattr(e3, "ROOT", tmp_path)
    monkeypatch.setattr(e3, "context", lambda *_values, **_kw: (protocol(), {}, [task_row(i) for i in range(25)]))
    monkeypatch.setattr(e3, "execution", lambda *_values, **_kw: {})
    monkeypatch.setattr(e3, "configure_torch", lambda *_values: None)
    accepted_path = tmp_path / e3.BASE / "resume/round_00/accepted_artifact_set.json"
    with pytest.raises(ValueError, match="25|task|attempt"):
        e3.admit(args(attempt_root=attempt, accepted_set=accepted_path))


def test_accepted_set_requires_exact_ordered_cell_coverage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "schema": "pcb-gnn.corpus-v4-strict-e3-accepted.v1",
        "bindings": bindings(),
        "task_count": 25,
        "checkpoint_count": 75,
        "trained_symmetry_receipt_count": 75,
        "heldout_inference_permitted": True,
        "claim_eligible": False,
        "accepted": [{"task_id": i} for i in range(24)],
    }
    monkeypatch.setattr(e3, "ROOT", tmp_path)
    accepted_path = tmp_path / e3.BASE / "resume/round_00/accepted_artifact_set.json"
    monkeypatch.setattr(e3, "sha256_file", lambda _path: "d" * 64)
    monkeypatch.setattr(e3, "load_json", lambda _path: payload)
    with pytest.raises(ValueError, match="25|cover|task"):
        e3.accepted_tasks(args(accepted_set=accepted_path), {}, {}, [task_row(i) for i in range(25)])


def test_terminal_receipt_rejects_restart_and_ambiguous_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = {"job_id": "123", "array_job_id": "122", "array_task_id": 0}

    def accounting(command: list[str], **_kwargs: object) -> SimpleNamespace:
        fields = command[-1].removeprefix("--format=").split(",")
        row = {
            "JobIDRaw": "123",
            "State": "COMPLETED",
            "ExitCode": "0:0",
            "Restarts": "1",
            "Partition": "nextgen",
            "Timelimit": "04:00:00",
        }
        return SimpleNamespace(stdout="|".join(row.get(field, "") for field in fields) + "\n")

    monkeypatch.setattr(e3.subprocess, "run", accounting)
    with pytest.raises(ValueError, match="restart|identity|terminal"):
        e3.terminal(scheduler, "training")


def test_all_three_arm_schemas_are_numeric_and_roundtrip_without_pickle(tmp_path: Path) -> None:
    frozen = protocol()
    models, initialization = e3.make_arms(40)
    samples = seven_family_samples()
    normalizer = e3.SymmetryNormalizer(samples, list(samples))
    receipt = {"task": task_row(0), "initialization": initialization, "arms": {}}
    for arm in e3.ARMS:
        arrays = e3.state_arrays(models[arm], normalizer)
        specs = e3.expected_arm_specs(frozen, arm)
        assert set(arrays) == set(specs)
        assert all(np.dtype(spec.dtype).kind != "O" for spec in specs.values())
        folder = tmp_path / f"arm_{arm}"
        hashes = e3.write_safe_npz_bundle(
            folder,
            arrays=arrays,
            specs=specs,
            payload=e3.bundle_payload(args(), frozen, 0, arm, initialization),
            limits=e3.BundleLimits(
                max_archive_bytes=frozen["checkpoint"]["max_archive_bytes_per_arm"],
                max_expanded_bytes=frozen["checkpoint"]["max_expanded_bytes_per_arm"],
            ),
        )
        receipt["arms"][arm] = {
            "bundle_specs": {name: spec.to_json() for name, spec in specs.items()},
            "files": {
                f"arm_{arm}/metadata.json": hashes["metadata.json"],
                f"arm_{arm}/weights_and_norm.npz": hashes["weights_and_norm.npz"],
            },
        }
        with np.load(folder / "weights_and_norm.npz", allow_pickle=False) as archive:
            assert set(archive.files) == set(specs)
            assert all(archive[name].dtype.kind != "O" for name in archive.files)
        _arrays, loaded_model, loaded_normalizer = e3.load_arm(args(), frozen, tmp_path / "result.json", receipt, arm)
        assert type(loaded_model) is e3.ScalarDistanceModel
        assert loaded_normalizer.coordinate_scale == normalizer.coordinate_scale


def test_load_arm_rejects_invented_schema_before_opening_npz(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = protocol()
    models, initialization = e3.make_arms(40)
    del models
    result = {
        "task": task_row(0),
        "initialization": initialization,
        "arms": {"strict96": {"bundle_specs": {"pickle": {"dtype": "|O", "shape": []}}, "files": {}}},
    }
    monkeypatch.setattr(e3, "load_safe_npz_bundle", lambda *_a, **_kw: pytest.fail("bad schema reached NPZ loader"))
    with pytest.raises(ValueError, match="schema"):
        e3.load_arm(args(), frozen, Path("result.json"), result, "strict96")


def test_artifact_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(e3, "ROOT", tmp_path)
    (tmp_path / "real").mkdir()
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink|escape"):
        e3.checked_path("linked/checkpoint.npz")


def synthetic_task_receipt(frozen: dict) -> tuple[dict, dict, list[dict]]:
    row = {
        **task_row(0),
        "training_dataset": {"path": "training_split_40.jsonl", "sha256": "f" * 64},
    }
    initialization = {"synthetic": "paired initialization receipt"}
    symmetry = {
        "schema": "pcb-gnn.corpus-v4-strict-e3-trained-symmetry.v1",
        "arm": "",
        "fixture_layout_ids": list(range(7)),
        "fixture_family_ids": [f"family_{index}" for index in range(7)],
        "transform_count": 40,
        "includes_permutation": True,
        "relative_tolerance": frozen["trained_symmetry_gate"]["relative_tolerance"],
        "max_relative_residual": {
            "scalar_invariance": 0.0,
            "coordinate_equivariance": 0.0,
            "coordinate_unchanged": 0.0,
        },
        "coordinate_mode": "",
        "passed": True,
    }
    metric = e3.metric_set([1.0], [1.0], ["fixture"])
    common_order = e3.batch_order_sha256([100, 101], 40, frozen["optimization"]["epochs"])
    arms = {}
    for arm in e3.ARMS:
        arm_symmetry = copy.deepcopy(symmetry)
        arm_symmetry["arm"] = arm
        arm_symmetry["coordinate_mode"] = (
            "equivariant_update" if arm == "strict96" else "unchanged_input_coordinates"
        )
        arms[arm] = {
            "bundle_specs": {},
            "files": {
                f"arm_{arm}/metadata.json": "f" * 64,
                f"arm_{arm}/weights_and_norm.npz": "f" * 64,
                f"learning_curve_{arm}.jsonl": "f" * 64,
            },
            "batch_order_sha256": common_order,
            "epochs_completed": 200,
            "validation_diagnostic_only": {target: copy.deepcopy(metric) for target in e3.TARGETS},
            "trained_symmetry": arm_symmetry,
            "training_wall_s": 1.0,
        }
    receipt = {
        "schema": "pcb-gnn.corpus-v4-strict-e3-task.v1",
        "bindings": bindings(),
        "task": task_row(0),
        "scheduler": {"array_job_id": "122", "array_task_id": 0, "job_id": "123"},
        "sandbox": {
            "backend": "bubblewrap",
            "executable_sha256": frozen["sandbox"]["executable_sha256"],
            "filesystem_boundary_passed": True,
            "forbidden_roots_absent": True,
            "hidden_training_artifact_count": 4,
            "sandbox_root": "/workspace",
            "selected_training_artifact": "training_split_40.jsonl",
            "task_private_output_only": True,
            "other_task_checkpoints_visible": False,
            "prior_model_artifacts_visible": False,
            "heldout_artifacts_visible": False,
        },
        "source_sha256": {},
        "runtime": {},
        "training_dataset": {"path": f"{e3.PLAN}/training_split_40.jsonl", "sha256": "f" * 64},
        "heldout_bytes_opened": False,
        "training_started": True,
        "initialization": initialization,
        "arms": arms,
        "common_batch_order_sha256": common_order,
        "training_wall_s": 3.0,
        "all_75_checkpoint_admission_pending": True,
    }
    lock = {
        "source_sha256": {},
        "runtime": {},
        "inputs": {f"{e3.PLAN}/training_split_40.jsonl": "f" * 64},
    }
    return receipt, lock, [row]


def install_synthetic_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    receipt: dict,
    frozen: dict,
) -> Path:
    folder = tmp_path / e3.BASE / "jobs/job_122/task_00"
    folder.mkdir(parents=True)
    (folder / "result.json").write_text("synthetic")
    for arm in e3.ARMS:
        arm_folder = folder / f"arm_{arm}"
        arm_folder.mkdir()
        (arm_folder / "metadata.json").write_text("synthetic")
        (arm_folder / "weights_and_norm.npz").write_text("synthetic")
        (folder / f"learning_curve_{arm}.jsonl").write_text("synthetic")
    monkeypatch.setattr(e3, "ROOT", tmp_path)
    monkeypatch.setattr(e3, "load_json", lambda _path: receipt)
    monkeypatch.setattr(e3, "sha256_file", lambda _path: "f" * 64)
    monkeypatch.setattr(e3, "validate_scheduler_receipt", lambda *_values, **_kw: None)
    monkeypatch.setattr(e3, "make_verified_arms", lambda *_values, **_kw: ({}, receipt["initialization"]))
    curve = [{"epoch": index, "learning_rate": 0.1, "train_loss": 1.0,
              "validation_loss_diagnostic_only": 1.0} for index in range(1, 201)]
    monkeypatch.setattr(e3, "load_jsonl", lambda _path: curve)
    arrays = {name: np.ones(spec.shape, dtype=np.dtype(spec.dtype)) for name, spec in e3.NORMALIZATION_SPECS.items()}
    monkeypatch.setattr(e3, "load_arm", lambda *_values: (arrays, object(), object()))
    return folder / "result.json"


def test_task_receipt_requires_exact_sandbox_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = protocol()
    receipt, lock, rows = synthetic_task_receipt(frozen)
    receipt["sandbox"]["heldout_artifacts_visible"] = True
    path = install_synthetic_task(tmp_path, monkeypatch, receipt, frozen)
    with pytest.raises(ValueError, match="sandbox"):
        e3.check_task(args(), path, 0, frozen, lock, rows)


def test_task_rejects_stored_symmetry_residual_above_tolerance_before_dataset_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = protocol()
    receipt, lock, rows = synthetic_task_receipt(frozen)
    receipt["arms"]["strict96"]["trained_symmetry"]["max_relative_residual"]["scalar_invariance"] = 1e-3
    path = install_synthetic_task(tmp_path, monkeypatch, receipt, frozen)
    monkeypatch.setattr(
        e3,
        "load_training_split_dataset_v3",
        lambda *_values, **_kw: pytest.fail("failed symmetry receipt reached dataset replay"),
    )
    with pytest.raises(ValueError, match="symmetry.*exceeds|residual"):
        e3.check_task(args(), path, 0, frozen, lock, rows)


def test_task_rejects_malformed_validation_metric_schema_before_dataset_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = protocol()
    receipt, lock, rows = synthetic_task_receipt(frozen)
    receipt["arms"]["strict96"]["validation_diagnostic_only"][e3.TARGETS[0]].pop("family_macro_mape_pct")
    path = install_synthetic_task(tmp_path, monkeypatch, receipt, frozen)
    monkeypatch.setattr(
        e3,
        "load_training_split_dataset_v3",
        lambda *_values, **_kw: pytest.fail("malformed validation metric reached dataset replay"),
    )
    with pytest.raises(ValueError, match="validation diagnostic"):
        e3.check_task(args(), path, 0, frozen, lock, rows)


def test_task_requires_numerical_equality_with_replayed_symmetry_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = protocol()
    receipt, lock, rows = synthetic_task_receipt(frozen)
    path = install_synthetic_task(tmp_path, monkeypatch, receipt, frozen)
    dataset = SimpleNamespace(train_layout_ids=[100, 101], validation_layout_ids=list(range(7)))
    monkeypatch.setattr(e3, "authenticate", lambda _pin: Path("synthetic-training.jsonl"))
    monkeypatch.setattr(e3, "load_training_split_dataset_v3", lambda *_values, **_kw: dataset)
    monkeypatch.setattr(e3, "_graph_samples", lambda _dataset: seven_family_samples())

    def changed_replay(_model: object, _normalizer: object, _samples: dict, _ids: list, *, arm: str,
                       init_seed: int, protocol: dict) -> dict:
        del init_seed, protocol
        replay = copy.deepcopy(receipt["arms"][arm]["trained_symmetry"])
        replay["max_relative_residual"]["scalar_invariance"] = 1e-5
        return replay

    monkeypatch.setattr(e3, "trained_symmetry_gate", changed_replay)
    with pytest.raises(ValueError, match="residual differs"):
        e3.check_task(args(), path, 0, frozen, lock, rows)


def test_task_replays_validation_diagnostics_from_numeric_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = protocol()
    receipt, lock, rows = synthetic_task_receipt(frozen)
    samples = seven_family_samples()
    families = [samples[index]["family_id"] for index in range(7)]
    reference = np.stack([samples[index]["reference_r3"] for index in range(7)])
    expected = {
        target: e3.metric_set(reference[:, column], reference[:, column], families)
        for column, target in enumerate(e3.TARGETS)
    }
    for arm in e3.ARMS:
        receipt["arms"][arm]["validation_diagnostic_only"] = copy.deepcopy(expected)
    receipt["arms"]["strict96"]["validation_diagnostic_only"][e3.TARGETS[0]]["family_macro_mape_pct"] = 1.0
    path = install_synthetic_task(tmp_path, monkeypatch, receipt, frozen)
    dataset = SimpleNamespace(train_layout_ids=[100, 101], validation_layout_ids=list(range(7)))
    monkeypatch.setattr(e3, "authenticate", lambda _pin: Path("synthetic-training.jsonl"))
    monkeypatch.setattr(e3, "load_training_split_dataset_v3", lambda *_values, **_kw: dataset)
    monkeypatch.setattr(e3, "_graph_samples", lambda _dataset: samples)
    monkeypatch.setattr(
        e3,
        "trained_symmetry_gate",
        lambda _model, _normalizer, _samples, _ids, *, arm, init_seed, protocol:
            copy.deepcopy(receipt["arms"][arm]["trained_symmetry"]),
    )

    class DummyNormalizer:
        def transform(self, _sample: dict) -> dict:
            return {"y": np.zeros(4, dtype=np.float32)}

    arrays = {name: np.ones(spec.shape, dtype=np.dtype(spec.dtype)) for name, spec in e3.NORMALIZATION_SPECS.items()}
    monkeypatch.setattr(e3, "load_arm", lambda *_values: (arrays, object(), DummyNormalizer()))
    monkeypatch.setattr(e3, "_predict", lambda *_values: reference.copy())
    with pytest.raises(ValueError, match="numeric|diagnostic|differ"):
        e3.check_task(args(), path, 0, frozen, lock, rows)


def trained_receipt(arm: str, task_id: int) -> dict:
    scalar = task_id * 1e-8 + e3.ARMS.index(arm) * 1e-9
    return {
        "arm": arm,
        "passed": True,
        "relative_tolerance": 2e-5,
        "max_relative_residual": {
            "scalar_invariance": scalar,
            "coordinate_equivariance": task_id * 2e-8 if arm == "strict96" else 0.0,
            "coordinate_unchanged": task_id * 3e-8 if arm != "strict96" else 0.0,
        },
    }


def test_summary_aggregates_exact_75_checkpoint_symmetry_grid() -> None:
    accepted = []
    for task_id in range(25):
        accepted.append((Path(f"task_{task_id:02d}"), {
            "arms": {arm: {"trained_symmetry": trained_receipt(arm, task_id)} for arm in e3.ARMS}
        }))
    summary = e3.summarize_trained_symmetry(accepted)
    assert summary["checkpoint_receipts"] == 75
    assert summary["arm_transform_batches"] == 3000
    assert summary["graph_transform_evaluations"] == 21000
    assert summary["all_passed"] is True
    assert summary["maximum_strict96_coordinate_equivariance_residual"] == 24 * 2e-8
    assert summary["maximum_fixed_coordinate_unchanged_residual"]["fixed96"] == 24 * 3e-8
    with pytest.raises(ValueError, match="incomplete"):
        e3.summarize_trained_symmetry(accepted[:-1])


class _TranslationSensitiveModel(e3.ScalarDistanceModel):
    """Deliberately invalid model used to prove the gate fails closed."""

    def forward_states(self, batch):  # type: ignore[no-untyped-def]
        coordinates = batch.node_feat[:, :3]
        output = torch.zeros((batch.n_graphs, 4), dtype=coordinates.dtype)
        output.index_add_(0, batch.batch_index, coordinates[:, [0]].repeat(1, 4))
        hidden = torch.zeros((len(coordinates), 1), dtype=coordinates.dtype)
        return output, hidden, coordinates


def test_trained_symmetry_integrity_gate_rejects_noninvariant_model() -> None:
    samples = seven_family_samples()
    normalizer = e3.SymmetryNormalizer(samples, list(samples))
    frozen = protocol()
    frozen["trained_symmetry_gate"]["transforms_per_initialization_seed"] = 2
    invalid = _TranslationSensitiveModel(hidden=4, update_coordinates=False, n_layers=1)
    result = e3.trained_symmetry_gate(
        invalid,
        normalizer,
        samples,
        list(samples),
        arm="fixed96",
        init_seed=40,
        protocol=frozen,
    )
    assert result["passed"] is False
    assert result["max_relative_residual"]["scalar_invariance"] > result["relative_tolerance"]


class _GraphOffsetCoordinateModel(e3.ScalarDistanceModel):
    """Uses a fixed frame-dependent graph offset, violating coordinate equivariance."""

    def forward_states(self, batch):  # type: ignore[no-untyped-def]
        offset = batch.batch_index.to(batch.node_feat.dtype).unsqueeze(1) * torch.tensor(
            [[0.13, -0.07, 0.19]], dtype=batch.node_feat.dtype
        )
        coordinates = batch.node_feat[:, :3] + offset
        output = torch.zeros((batch.n_graphs, 4), dtype=batch.node_feat.dtype)
        hidden = torch.zeros((len(coordinates), 1), dtype=batch.node_feat.dtype)
        return output, hidden, coordinates


def test_multigraph_symmetry_gate_catches_coordinate_offset_after_permutation() -> None:
    samples = seven_family_samples()
    normalizer = e3.SymmetryNormalizer(samples, list(samples))
    frozen = protocol()
    frozen["trained_symmetry_gate"]["transforms_per_initialization_seed"] = 2
    invalid = _GraphOffsetCoordinateModel(hidden=4, update_coordinates=True, n_layers=2)
    result = e3.trained_symmetry_gate(
        invalid,
        normalizer,
        samples,
        list(samples),
        arm="strict96",
        init_seed=41,
        protocol=frozen,
    )
    assert result["includes_permutation"] is True
    assert len(result["fixture_layout_ids"]) == 7
    assert result["passed"] is False
    assert result["max_relative_residual"]["coordinate_equivariance"] > result["relative_tolerance"]


@pytest.mark.parametrize("mutation", ["missing_cell", "duplicate_cell", "wrong_seed", "wrong_sign", "unlinked", "nan_metric"])
def test_summary_rejects_incomplete_pairing_and_wrong_difference_sign(mutation: str) -> None:
    metrics, contrasts = metric_grid()
    if mutation == "missing_cell":
        contrasts.pop()
    elif mutation == "duplicate_cell":
        metrics[-1] = copy.deepcopy(metrics[0])
    elif mutation == "wrong_seed":
        metrics[0]["split_seed"] = 99
    elif mutation == "wrong_sign":
        contrasts[0]["strict96_minus_control_pp"] = 2.0
    elif mutation == "unlinked":
        contrasts[0]["strict96_family_macro_mape_pct"] += 1.0
        contrasts[0]["strict96_minus_control_pp"] += 1.0
    else:
        metrics[0]["metrics"]["family_macro_mape_pct"] = float("nan")
    with pytest.raises(ValueError):
        e3.summarize(metrics, contrasts)


def test_summary_difference_is_strict_minus_fixed() -> None:
    summary = e3.summarize(*metric_grid())
    for target in e3.TARGETS:
        assert summary["paired_contrasts"]["fixed96"][target]["mean_strict96_minus_control_pp"] == -2.0
        assert summary["paired_contrasts"]["fixed_matched"][target]["mean_strict96_minus_control_pp"] == -3.0
    assert "strict" in summary["difference_sign"]
    assert "fixed" in summary["difference_sign"]


def test_crossed_axis_interval_is_10000_draw_descriptive_reconstruction() -> None:
    metrics, contrasts = metric_grid()
    metric_lookup = {(row["task_id"], row["arm"], row["target"]): row for row in metrics}
    for row in contrasts:
        split_effect = row["split_seed"] - 42.0
        init_effect = 0.25 * (row["init_seed"] - 42.0)
        delta = split_effect + init_effect
        row["strict96_family_macro_mape_pct"] = 10.0 + delta
        row["control_family_macro_mape_pct"] = 10.0
        row["strict96_minus_control_pp"] = delta
        metric_lookup[(row["task_id"], "strict96", row["target"])]["metrics"]["family_macro_mape_pct"] = 10.0 + delta
        metric_lookup[(row["task_id"], row["control"], row["target"])]["metrics"]["family_macro_mape_pct"] = 10.0
    summary = e3.summarize(metrics, contrasts)
    rng = np.random.default_rng(20260913)
    split_draws = rng.integers(0, 5, size=(10000, 5))
    init_draws = rng.integers(0, 5, size=(10000, 5))
    draws = (split_draws - 2).mean(axis=1) + 0.25 * (init_draws - 2).mean(axis=1)
    expected = np.quantile(draws, [0.025, 0.975], method="linear")
    for target in e3.TARGETS:
        for control in ("fixed96", "fixed_matched"):
            np.testing.assert_allclose(summary["paired_contrasts"][control][target]["crossed_axis_95pct_interval_pp"], expected)
    assert summary["resampling"]["resamples"] == 10000
    assert "not a population" in summary["resampling"]["semantics"]


def test_verify_rejects_extra_analysis_file_before_numerical_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / e3.BASE / "final" / "job_123"
    folder.mkdir(parents=True)
    for name in ("ANALYSIS_MANIFEST.json", "summary.json", "metrics.json", "predictions.jsonl", "unexpected.txt"):
        (folder / name).write_text("synthetic fixture")
    monkeypatch.setattr(e3, "ROOT", tmp_path)
    monkeypatch.setattr(e3, "context", lambda *_values, **_kw: (protocol(), {}, [task_row(i) for i in range(25)]))
    monkeypatch.setattr(e3, "execution", lambda *_values, **_kw: {})
    monkeypatch.setattr(e3, "configure_torch", lambda *_values: None)
    monkeypatch.setattr(e3, "accepted_tasks", lambda *_values, **_kw: [])
    monkeypatch.setattr(e3, "canonical_argument", lambda path: path)
    monkeypatch.setattr(e3, "sha256_file", lambda _path: "e" * 64)
    monkeypatch.setattr(e3, "load_json", lambda _path: {
        "schema": "pcb-gnn.corpus-v4-strict-e3-analysis-manifest.v1",
        "bindings": bindings(),
        "counts": {},
        "files": {name: "e" * 64 for name in ("summary.json", "metrics.json", "predictions.jsonl")},
    })
    monkeypatch.setattr(e3, "evaluate", lambda *_values: pytest.fail("extra file reached numerical replay"))
    with pytest.raises(ValueError, match="inventory|unexpected|symlink"):
        e3.verify(args(analysis_manifest=folder / "ANALYSIS_MANIFEST.json", out=tmp_path / "ARCHIVE_MANIFEST.json"))


def test_tracked_archive_gate_covers_source_inputs_analysis_and_task_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / e3.BASE / "final/job_123"
    folder.mkdir(parents=True)
    for name in ("ANALYSIS_MANIFEST.json", "summary.json", "metrics.json", "predictions.jsonl"):
        (folder / name).write_text("synthetic")
    task_folder = tmp_path / e3.BASE / "jobs/job_122/task_00"
    task_folder.mkdir(parents=True)
    (task_folder / "result.json").write_text("synthetic")
    accepted_path = tmp_path / e3.BASE / "resume/round_00/accepted_artifact_set.json"
    accepted_path.parent.mkdir(parents=True)
    accepted_path.write_text("synthetic")
    out = tmp_path / e3.BASE / "ARCHIVE_MANIFEST.json"
    counts = {"tasks": 25, "checkpoints": 75}
    frozen = protocol()
    manifest = {
        "schema": "pcb-gnn.corpus-v4-strict-e3-analysis-manifest.v1",
        "bindings": bindings(),
        "counts": counts,
        "files": {name: "e" * 64 for name in ("summary.json", "metrics.json", "predictions.jsonl")},
    }
    symmetry_summary = {"all_75_passed": True}
    results = {"counts": counts, "trained_symmetry": symmetry_summary}
    summary = {
        "bindings": bindings(),
        "accepted_set_sha256": "d" * 64,
        "scheduler": {"job_id": "123"},
        "results": results,
        "claim_eligible": False,
    }
    accepted_json = {"accepted": [{"result": {"path": (task_folder / "result.json").relative_to(tmp_path).as_posix(),
                                                   "sha256": "f" * 64}}]}

    def load(path: Path) -> dict:
        if path == folder / "ANALYSIS_MANIFEST.json":
            return manifest
        if path == folder / "summary.json":
            return summary
        if path == folder / "metrics.json":
            return {"arm_target_cells": [], "paired_contrasts": []}
        if path == accepted_path:
            return accepted_json
        raise AssertionError(f"unexpected JSON read: {path}")

    git_calls: list[list[str]] = []

    def command(command: list[str], **_kwargs: object) -> SimpleNamespace:
        git_calls.append(command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(e3, "ROOT", tmp_path)
    monkeypatch.setattr(e3, "context", lambda *_values, **_kw: (
        frozen,
        {"source_sha256": {"code/source.py": "1" * 64}, "inputs": {"inputs/data.json": "2" * 64}},
        [task_row(i) for i in range(25)],
    ))
    monkeypatch.setattr(e3, "execution", lambda *_values, **_kw: {})
    monkeypatch.setattr(e3, "configure_torch", lambda *_values: None)
    monkeypatch.setattr(e3, "accepted_tasks", lambda *_values, **_kw: [(task_folder / "result.json", {})])
    monkeypatch.setattr(e3, "sha256_file", lambda _path: "e" * 64)
    monkeypatch.setattr(e3, "load_json", load)
    monkeypatch.setattr(e3, "load_jsonl", lambda _path: [])
    monkeypatch.setattr(e3, "terminal", lambda *_values: {"State": "COMPLETED"})
    monkeypatch.setattr(e3, "evaluate", lambda *_values, **_kw: ([], [], []))
    monkeypatch.setattr(e3, "summarize", lambda *_values: {"counts": counts})
    monkeypatch.setattr(e3, "summarize_trained_symmetry", lambda *_values: symmetry_summary)
    monkeypatch.setattr(e3, "pin", lambda name: {"path": name, "sha256": "f" * 64})
    monkeypatch.setattr(e3, "authenticate", lambda pin: tmp_path / pin["path"])
    monkeypatch.setattr(e3, "atomic_write_json", lambda *_values, **_kw: None)
    monkeypatch.setattr(e3.subprocess, "run", command)
    e3.verify(args(
        accepted_set=accepted_path,
        analysis_manifest=folder / "ANALYSIS_MANIFEST.json",
        out=out,
        require_git_tracked=True,
    ))
    assert len(git_calls) == 1
    command_line = git_calls[0]
    assert command_line[:3] == ["git", "ls-files", "--error-unmatch"]
    for required in (
        "code/source.py",
        "inputs/data.json",
        (folder / "summary.json").relative_to(tmp_path).as_posix(),
        (task_folder / "result.json").relative_to(tmp_path).as_posix(),
        accepted_path.relative_to(tmp_path).as_posix(),
        out.relative_to(tmp_path).as_posix(),
    ):
        assert required in command_line


def test_wrappers_are_slurm_only_and_training_mount_excludes_heldout() -> None:
    training_path = ROOT / e3.WRAPPER
    finalizer_path = ROOT / e3.FINAL_WRAPPER
    assert subprocess.run(["bash", "-n", str(training_path)], capture_output=True).returncode == 0
    assert subprocess.run(["bash", "-n", str(finalizer_path)], capture_output=True).returncode == 0
    training = training_path.read_text()
    finalizer = finalizer_path.read_text()
    for text in (training, finalizer):
        assert "/usr/bin/env -i" in text
        assert "--no-requeue" in text
        assert "PYTHONNOUSERSITE=1" in text
    assert "--array=0-24%" in training
    assert "evaluation_dataset.jsonl" not in training
    assert '--ro-bind "$EXECUTION_ROOT" /workspace' not in training
    assert '--bind "$EXECUTION_ROOT/$TASK_RELATIVE" "/workspace/$TASK_RELATIVE"' in training
    assert "finalize" in finalizer and "verify" in finalizer
