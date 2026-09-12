"""Contracts for the Corpus-v4 FEM-v2 paired-latency pipeline.

The suite is intentionally solver-free.  It authenticates the frozen
accuracy-v3 task-12 checkpoint, the admitted FEM-v2 dataset, the one-thread
runtime boundary, planning/statistical contracts, and SLURM-only execution
guards without launching FastHenry, Gmsh, or an electrostatic solve.
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

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"
JOBS = ROOT / "code/jobs"
QUALITY = ROOT / "code/quality"

PROTOCOL_PATH = ROOT / "protocols/corpus_v4_latency_fem_v2_v1.json"
OLD_PROTOCOL_PATH = ROOT / "protocols/corpus_v4_latency_v1.json"
PLAN_ROOT = ROOT / "results/corpus_v4/latency_fem_v2/plan/v1"
TASK_SCRIPT = PROOFS / "experiments_corpus_v4_latency_task_v2.py"
ADMISSION_SCRIPT = PROOFS / "admit_corpus_v4_latency_preflight_v2.py"
FINALIZER_SCRIPT = PROOFS / "finalize_corpus_v4_latency_v2.py"
PLANNER_SCRIPT = PROOFS / "plan_corpus_v4_latency_v2.py"
RESUME_SCRIPT = PROOFS / "plan_corpus_v4_latency_resume_v2.py"
CONTRACT_SCRIPT = PROOFS / "corpus_v4_latency_contract_v2.py"
ARCHIVE_VERIFIER = QUALITY / "verify_corpus_v4_latency_archive_v2.py"

SCHEMA_PREFIX = "pcb-gnn.corpus-v4-fem-v2-paired-latency"
PROTOCOL_SCHEMA = f"{SCHEMA_PREFIX}-protocol.v1"
TASK_SCHEMA = f"{SCHEMA_PREFIX}-task.v1"
RECORD_SCHEMA = f"{SCHEMA_PREFIX}-record.v1"
FINAL_SCHEMA = f"{SCHEMA_PREFIX}-final.v1"
PREFLIGHT_ADMISSION_SCHEMA = f"{SCHEMA_PREFIX}-preflight-admission.v1"
PROTOCOL_SHA256 = "6459fb716b79f0a95436691c9430e6505d5590d493f1e7e3ff191cbd602b4bf9"

# These pins are copied from independent accuracy-v3/FEM-v2 evidence roots.
# A path and a digest are both frozen so a correctly hashed legacy artifact
# cannot silently re-enter the latency closure.
EXPECTED_INPUT_PINS: dict[str, tuple[str, str]] = {
    "accuracy_accepted_set": (
        "results/corpus_v4/accuracy_v3/resume/round_01/accepted_artifact_set.json",
        "291a76231ef348d150fcec0f1cb70031537f1db5530ff0813365ed2932e326fe",
    ),
    "accuracy_analysis_manifest": (
        "results/corpus_v4/accuracy_v3/final/job_7102842/ANALYSIS_MANIFEST.json",
        "4af78d1b2fe65f249bd3d136fd8f53e3d88fdc577f414eaf74c1a463d3f28afc",
    ),
    "accuracy_archive": (
        "results/corpus_v4/accuracy_v3/ARCHIVE_MANIFEST.json",
        "a741b0ff1002f11b5ac5eef466baff81137da1245a8ea6e609b2a608279e8f06",
    ),
    "accuracy_checkpoint_index": (
        "results/corpus_v4/accuracy_v3/final/job_7102842/checkpoint_index.json",
        "820cd6c414b274f7d4013f7d87e3180ad0a783da90f852447b931d2a5f93fa02",
    ),
    "accuracy_final_summary": (
        "results/corpus_v4/accuracy_v3/final/job_7102842/summary.json",
        "e48fa58aa48304353cc471e33f5a3e3559fa0628728eb938098dae089c05eb3b",
    ),
    "accuracy_finalizer_execution_lock": (
        "protocols/corpus_v4_accuracy_finalizer_execution_lock_v1.json",
        "cdb53640f9d9c206b37651e28a04781a19d5dda81d520cf50b77c628468cadf3",
    ),
    "accuracy_plan": (
        "results/corpus_v4/accuracy_v3/plan/v1/plan.json",
        "04fab5efbc8428682fa0ea572001d95b1179b86e912b03deb4c8d5c4accbb40f",
    ),
    "accuracy_protocol": (
        "protocols/corpus_v4_accuracy_v3.json",
        "d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1",
    ),
    "accuracy_task_manifest": (
        "results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl",
        "e5a444204e99bc92462ac87d3b4721d5a4d33db9bd7d3b8e7d274ebe5d723b71",
    ),
    "accuracy_training_execution_lock": (
        "protocols/corpus_v4_accuracy_execution_lock_v3r2.json",
        "8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c",
    ),
    "checkpoint_archive": (
        "results/corpus_v4/accuracy_v3/jobs/job_7087054/task_12/bundle/weights_and_norm.npz",
        "8efc90f4209a818f9a334e2eefcf43a30ae38363262c5de39302e328d736e2b5",
    ),
    "checkpoint_metadata": (
        "results/corpus_v4/accuracy_v3/jobs/job_7087054/task_12/bundle/metadata.json",
        "99136b0b28b731494dc20442a0bdb2b8ba4fb858458c334d37f6e57ffd1e2d02",
    ),
    "checkpoint_smoke_examples": (
        "results/corpus_v4/accuracy_v3/jobs/job_7087054/task_12/smoke_examples.jsonl",
        "3a9716838c36c2a519d0242075abe1b18960238a963fa4b9faab587dc1dbb752",
    ),
    "designated_task_manifest": (
        "results/corpus_v4/accuracy_v3/jobs/job_7087054/task_12/TASK_MANIFEST.json",
        "57bc95abbfa4f00210d69405d200b6c46ef3c0d851b98e7ee7034eee53ba73eb",
    ),
    "designated_task_result": (
        "results/corpus_v4/accuracy_v3/jobs/job_7087054/task_12/result.json",
        "2e695b44dc96181bab3a4864793c8c26eaa1505e64f8dd03080ec05a81283cb9",
    ),
    "evaluation_dataset": (
        "results/corpus_v4/accuracy_v3/plan/v1/evaluation_dataset.jsonl",
        "ff02a28aa41f2526bea1b087e1222479d743f5eb766d13e4dfa48f42cc791046",
    ),
    "fem_v2_dataset_admission": (
        "results/corpus_v4/cps_reference_v2/production/v1/dataset/admission/"
        "source_set_f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b/"
        "finalizer_job_7084776/FINAL_ADMISSION.json",
        "b38e5225ee474aa1a848fc1884bc643bb4772c801287052fde0891a292ac7bed",
    ),
    "fem_v2_dataset_archive": (
        "results/corpus_v4/cps_reference_v2/production/v1/ARCHIVE_MANIFEST.json",
        "89b2e235ff5d1aaa06ab589a95578f7a3ef129d60f2386494ea2d1686de6dbbc",
    ),
    "fem_v2_final_observations": (
        "results/corpus_v4/cps_reference_v2/production/v1/dataset/final/"
        "source_set_f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b/"
        "finalizer_job_7084776/label_observations.jsonl",
        "83a771bf318c0660731c6e5d1e5e91a6b15642e178b8172b2b46dedb656a1784",
    ),
    "fem_v2_production_lock": (
        "protocols/corpus_v4_fem_v2_production_lock_v1.json",
        "84c832aa08fc8800e604979730c315e1950d26fa4d0a2f1f7c34b9f2f34e402a",
    ),
    "fem_v2_production_protocol": (
        "protocols/corpus_v4_fem_v2_production_v1.json",
        "ba66f1ecfccd9eea3d2b36b9824dcae3f2399ffa2e9a73883f786ddca33dc709",
    ),
}


def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"missing latency-v2 module: {path.relative_to(ROOT)}"
    for directory in (
        PROOFS,
        ROOT / "code/core",
        ROOT / "code/data",
        ROOT / "code/inference",
        ROOT / "code/models/gnn",
        ROOT / "code/solvers",
    ):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _protocol() -> dict[str, Any]:
    assert PROTOCOL_PATH.is_file()
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_only(script: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(script), "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def _sbatch_directives(path: Path) -> dict[str, str]:
    directives: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#SBATCH "):
            continue
        token = line.removeprefix("#SBATCH ").strip()
        if "=" in token:
            key, value = token.split("=", 1)
        else:
            key, value = token.split(maxsplit=1)
        directives[key] = value
    return directives


def _base_record(
    *,
    layout_id: int = 10,
    family_id: str = "turns-04-04",
    fasthenry_ms: float = 4.0,
    fem_ms: float = 500.0,
    inference_ms: float = 2.0,
    residual_ms: float = 0.25,
) -> dict[str, Any]:
    pre = [inference_ms] * 100
    post = [inference_ms] * 100
    repetitions = pre + post
    model_only_repetitions = [0.5] * 200
    paired_ms = fasthenry_ms + fem_ms + residual_ms
    paired_start_ns = 1_000_000
    fast_start_ns = 1_100_000
    fast_stop_ns = fast_start_ns + int(fasthenry_ms * 1e6)
    fem_start_ns = fast_stop_ns
    fem_stop_ns = fem_start_ns + int(fem_ms * 1e6)
    paired_stop_ns = paired_start_ns + int(paired_ms * 1e6)
    median_ms = float(np.median(repetitions))
    geometry_sha256 = f"{layout_id:064x}"
    fem_system_sha256 = "a" * 64
    return {
        "family_id": family_id,
        "fem_v2_reference_identity": {
            "geometry_sha256": geometry_sha256,
            "mesh_nodes": 1_000,
            "mesh_tetrahedra": 4_000,
            "system_sha256": fem_system_sha256,
        },
        "geometry_sha256": geometry_sha256,
        "inference_model_only_ms": {
            "median": float(np.median(model_only_repetitions)),
            "physical_prediction": [1.0, 2.0, 3.0, 0.5],
            "repetitions": model_only_repetitions,
            "timed_repetitions": 200,
            "warmups": 50,
        },
        "inference_raw_record_ms": {
            "median": median_ms,
            "post_solver_median": float(np.median(post)),
            "post_solver_repetitions": post,
            "pre_solver_median": float(np.median(pre)),
            "pre_solver_repetitions": pre,
            "repetitions": repetitions,
            "timed_repetitions": 200,
            "warmups": 50,
        },
        "layout_id": layout_id,
        "model_load_ms": 10.0,
        "prediction": [1.0, 2.0, 3.0, 0.5],
        "reference": [1.0, 2.0, 3.0, 0.5],
        "rerun_reference": [1.0, 2.0, 3.0, 0.5],
        "schema": RECORD_SCHEMA,
        "solver_label_max_relative_drift": 0.0,
        "solver_label_relative_drift": [0.0, 0.0, 0.0, 0.0],
        "solver_ms": {
            "fasthenry": fasthenry_ms,
            "fem_v2_r3_p16_t1": fem_ms,
            "orchestration_residual": residual_ms,
            "paired_four_target": paired_ms,
        },
        "solver_telemetry": {
            "fasthenry": {
                "returncode": 0,
                "start_ns": fast_start_ns,
                "stop_ns": fast_stop_ns,
            },
            "fem_v2_r3_p16_t1": {
                "checks": {"converged": True, "gmsh_one_thread": True},
                "observed": {
                    "cps_pf": 1.0,
                    "gmsh_threads": 1,
                    "mesh_nodes": 1_000,
                    "mesh_tetrahedra": 4_000,
                    "pad_mm": 16.0,
                    "refine": 3,
                    "solver_info": 0,
                    "system_sha256": fem_system_sha256,
                },
                "start_ns": fem_start_ns,
                "stop_ns": fem_stop_ns,
            },
            "paired_outer_wall": {
                "start_ns": paired_start_ns,
                "stop_ns": paired_stop_ns,
            },
        },
        "speedup_fasthenry_three_target_x": fasthenry_ms / median_ms,
        "speedup_fem_v2_capacitance_x": fem_ms / median_ms,
        "speedup_paired_four_target_x": paired_ms / median_ms,
        "timer": {"clock": "perf_counter_ns", "monotonic": True},
        "winding_coupling_coefficient": 0.5,
    }


def test_protocol_authenticates_accuracy_v3_task12_and_fem_v2_t1() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_protocol_contract")
    protocol, digest = contract.validate_protocol(PROTOCOL_PATH, PROTOCOL_SHA256)

    assert digest == PROTOCOL_SHA256
    assert protocol["schema"] == PROTOCOL_SCHEMA
    assert protocol["protocol_name"] == "corpus-v4-fem-v2-paired-latency-v1"
    assert protocol["checkpoint"]["designated_task_id"] == 12
    assert protocol["checkpoint"]["split_seed"] == 42
    assert protocol["checkpoint"]["init_seed"] == 42
    assert protocol["panel"]["n_designs"] == 306
    assert protocol["panel"]["n_families"] == 13
    assert protocol["panel"]["selection_uses_labels_predictions_or_timings"] is False

    solver = protocol["solver_workflow"]
    assert solver["capacitance"] == {
        "fidelity_id": "cps_fem_r3_p16_t1_v2",
        "linear_solver": "pyamg_smoothed_aggregation_cg",
        "pad_mm": 16.0,
        "refine": 3,
        "target": "Cps_pF",
        "timeout_s": 1800,
    }
    assert solver["execution_order"] == ["FastHenry", "FEM-v2-R3P16-one-thread"]
    assert solver["reference_agreement_max_relative_error"] == 1e-4
    assert solver["solver_result_cache_reuse"] is False
    assert protocol["resources"]["full_array"]["cpus_per_task"] == 1
    assert protocol["resources"]["full_array"]["scientific_threads"] == {
        "blas": 1,
        "gmsh": 1,
        "torch": 1,
    }
    assert set(protocol["runtime"]["thread_environment"].values()) == {"1"}
    assert protocol["gnn_timing"]["model_only_supporting"] == {
        "boundary_end": "standardized four-output CPU tensor resident",
        "boundary_start": "normalized batch-one graph tensors resident",
        "measured_repetitions": 200,
        "role": "secondary diagnostic; never the denominator of the solver-workflow speedup",
        "timer": "time.perf_counter_ns",
        "warmup_repetitions": 50,
    }

    bootstrap = protocol["statistics"]["bootstrap"]
    assert bootstrap["cluster_unit"] == "held-out geometry family"
    assert bootstrap["resamples"] == 10_000
    assert bootstrap["seed"] == 20260820
    assert "descriptive" in bootstrap["semantics"]
    assert "not a population or hardware confidence interval" in bootstrap["semantics"]


def test_protocol_input_paths_and_hashes_are_the_exact_frozen_closure() -> None:
    protocol = _protocol()
    assert set(protocol["inputs"]) == set(EXPECTED_INPUT_PINS)
    for name, (path, digest) in EXPECTED_INPUT_PINS.items():
        assert protocol["inputs"][name] == {"path": path, "sha256": digest}
        artifact = ROOT / path
        assert artifact.is_file(), f"missing frozen input: {path}"
        assert _sha256(artifact) == digest, f"hash drift: {path}"


def test_old_v1_protocol_paths_and_repeatability_receipt_are_rejected() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_legacy_rejection")
    with pytest.raises(ValueError, match="canonical path"):
        contract.validate_protocol(OLD_PROTOCOL_PATH)

    protocol = _protocol()
    old_accuracy = copy.deepcopy(protocol)
    old_accuracy["inputs"]["checkpoint_archive"]["path"] = (
        "results/corpus_v4/accuracy/jobs/job_legacy/task_12/weights.npz"
    )
    with pytest.raises(ValueError, match="canonical"):
        contract.resolve_protocol_inputs(old_accuracy)

    old_receipt = copy.deepcopy(protocol)
    old_receipt["inputs"]["fem_repeatability_admission"] = {
        "path": (
            "results/corpus_v4/fem_repeatability/v1/admission/"
            "source_job_6916045/finalizer_job_6916047/FINAL_ADMISSION.json"
        ),
        "sha256": "776adb39aaa41dea09972089413977d7762457f453e57dc429d65bd5d0a209fc",
    }
    with pytest.raises(ValueError, match="closure"):
        contract.resolve_protocol_inputs(old_receipt)

    frozen_paths = "\n".join(path for path, _ in EXPECTED_INPUT_PINS.values())
    assert "results/corpus_v4/accuracy/" not in frozen_paths
    assert "results/corpus_v4/latency/" not in frozen_paths
    assert "fem_repeatability/v1/admission" not in frozen_paths
    assert "fem_repeatability_admission" not in protocol["inputs"]


def test_positive_fem_v2_dataset_admission_replaces_repeatability_receipt() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_dataset_admission")
    path, digest = EXPECTED_INPUT_PINS["fem_v2_dataset_admission"]
    payload = contract.validate_fem_v2_dataset_admission(ROOT / path, digest)

    assert payload["schema"] == "pcb-gnn.corpus-v4-fem-v2-production-dataset-admission.v1"
    assert payload["admission_eligible"] is True
    assert payload["solver_executed"] is False
    assert payload["decision"]["dataset_generation_admitted"] is True


def test_plan_is_exactly_accuracy_v3_task12_test_membership() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_plan_contract")
    plan, tasks, panel, _, _, _ = contract.validate_plan(
        PLAN_ROOT / "plan.json",
        PLAN_ROOT / "task_manifest.jsonl",
        PLAN_ROOT / "panel_records.jsonl",
    )
    accuracy_rows = [
        json.loads(line)
        for line in (
            ROOT / "results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    task12 = accuracy_rows[12]

    assert len(tasks) == len(panel) == 306
    assert [row["task_id"] for row in tasks] == list(range(306))
    assert [row["layout_id"] for row in tasks] == task12["partitions"]["test"]["layout_ids"]
    assert {row["family_id"] for row in panel} == set(
        task12["partitions"]["test"]["family_ids"]
    )
    assert len({row["family_id"] for row in panel}) == 13
    assert plan["checkpoint"] == {
        "archive_sha256": EXPECTED_INPUT_PINS["checkpoint_archive"][1],
        "init_seed": 42,
        "metadata_sha256": EXPECTED_INPUT_PINS["checkpoint_metadata"][1],
        "smoke_examples_sha256": EXPECTED_INPUT_PINS["checkpoint_smoke_examples"][1],
        "split_seed": 42,
        "task_id": 12,
    }


def test_execution_source_closure_uses_only_latency_v2_entry_points() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_source_contract")
    required = {
        "protocols/corpus_v4_latency_fem_v2_v1.json",
        "protocols/corpus_v4_fem_v2_production_v1.json",
        "code/experiments/proofs/corpus_v4_latency_contract_v2.py",
        "code/experiments/proofs/admit_corpus_v4_latency_preflight_v2.py",
        "code/experiments/proofs/plan_corpus_v4_latency_v2.py",
        "code/experiments/proofs/experiments_corpus_v4_latency_task_v2.py",
        "code/experiments/proofs/finalize_corpus_v4_latency_v2.py",
        "code/inference/corpus_v4_latency_inference_v2.py",
        "code/jobs/submit_corpus_v4_latency_v2.sh",
        "code/jobs/submit_corpus_v4_latency_preflight_v2.sh",
        "code/jobs/submit_finalize_corpus_v4_latency_v2.sh",
        "code/quality/verify_corpus_v4_latency_archive_v2.py",
        "code/solvers/fem_corpus_v4_latency_v2.py",
    }
    legacy = {
        "protocols/corpus_v4_latency_v1.json",
        "code/experiments/proofs/corpus_v4_latency_contract.py",
        "code/experiments/proofs/experiments_corpus_v4_latency_task.py",
        "code/jobs/submit_corpus_v4_latency.sh",
        "code/solvers/fem_corpus_v4_latency.py",
    }
    sources = set(contract.EXECUTION_SOURCE_NAMES)
    assert required <= sources
    assert legacy.isdisjoint(sources)


def test_protocol_input_hash_drift_is_rejected_before_execution() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_hash_drift")
    protocol = _protocol()
    assert set(contract.resolve_protocol_inputs(protocol)) == set(EXPECTED_INPUT_PINS)
    changed = copy.deepcopy(protocol)
    changed["inputs"]["checkpoint_archive"]["sha256"] = "d" * 64
    with pytest.raises(ValueError, match="hash|SHA-256|digest"):
        contract.resolve_protocol_inputs(changed)


def test_raw_record_timer_honors_warmup_and_two_block_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inference = _load_module(
        ROOT / "code/inference/corpus_v4_latency_inference_v2.py",
        "latency_v2_inference_timer",
    )
    raw_record = b'{"resident":"bytes"}'
    observed: list[bytes] = []

    def fake_predict(model: Any, normalizer: Any, raw_layout: bytes) -> np.ndarray:
        del model, normalizer
        observed.append(raw_layout)
        return np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)

    ticks = iter(range(0, 1_000_000_000, 1_000_000))
    monkeypatch.setattr(inference, "predict_raw_record", fake_predict)
    monkeypatch.setattr(inference.time, "perf_counter_ns", lambda: next(ticks))
    pre = inference.measure_raw_record_inference(
        object(), object(), raw_record, warmups=50, repetitions=100
    )
    post = inference.measure_raw_record_inference(
        object(), object(), raw_record, warmups=0, repetitions=100
    )
    combined = inference.combine_raw_record_blocks(
        pre,
        post,
        expected_repetitions=200,
        expected_warmups=50,
        block_median_ratio_max=1.25,
    )

    assert len(observed) == 250
    assert all(value is raw_record for value in observed)
    assert combined["warmups"] == 50
    assert combined["timed_repetitions"] == 200
    assert combined["median"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "raw_record",
    (b'{"root":1,"root":2}', b'{"root":NaN}', b'{ "root":1}', b""),
)
def test_raw_record_boundary_rejects_duplicate_nonfinite_or_noncanonical_json(
    raw_record: bytes,
) -> None:
    inference = _load_module(
        ROOT / "code/inference/corpus_v4_latency_inference_v2.py",
        "latency_v2_inference_json",
    )
    with pytest.raises(ValueError):
        inference.parse_canonical_layout(raw_record)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda row: row["solver_ms"].__setitem__("fasthenry", 0.0),
        lambda row: row["solver_ms"].__setitem__("fem_v2_r3_p16_t1", np.inf),
        lambda row: row["solver_ms"].__setitem__("paired_four_target", 999.0),
        lambda row: row["solver_ms"].__setitem__("orchestration_residual", -1.0),
        lambda row: row["inference_raw_record_ms"]["repetitions"].__setitem__(0, np.nan),
        lambda row: row["inference_raw_record_ms"].__setitem__("median", 0.0),
        lambda row: row["inference_model_only_ms"].__setitem__("median", 0.0),
        lambda row: row["inference_model_only_ms"]["physical_prediction"].__setitem__(0, 9.0),
        lambda row: row["fem_v2_reference_identity"].__setitem__("mesh_nodes", 999),
        lambda row: row.__setitem__("speedup_fem_v2_capacitance_x", -1.0),
        lambda row: row.pop("geometry_sha256"),
    ),
)
def test_fem_v2_timing_record_rejects_malformed_values(mutation: Any) -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_record_validator")
    record = _base_record()
    finalizer.validate_timing_record(record, expected_repetitions=200)
    changed = copy.deepcopy(record)
    mutation(changed)
    with pytest.raises(ValueError):
        finalizer.validate_timing_record(changed, expected_repetitions=200)


def test_summary_uses_median_of_per_design_ratios_and_family_sensitivity() -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_summary")
    records = [
        _base_record(layout_id=1, family_id="a", fasthenry_ms=1.0, fem_ms=1.0),
        _base_record(layout_id=2, family_id="a", fasthenry_ms=50.0, fem_ms=50.0, inference_ms=10.0),
        _base_record(layout_id=3, family_id="b", fasthenry_ms=50.0, fem_ms=50.0, inference_ms=100.0),
        _base_record(layout_id=4, family_id="b", fasthenry_ms=4.0, fem_ms=4.0),
    ]
    summary = finalizer.summarize_records(
        records,
        expected_repetitions=200,
        bootstrap_resamples=1_000,
        bootstrap_seed=20260820,
    )
    ratios = np.asarray(
        [record["speedup_paired_four_target_x"] for record in records],
        dtype=np.float64,
    )
    ratio_of_medians = float(
        np.median([record["solver_ms"]["paired_four_target"] for record in records])
        / np.median([record["inference_raw_record_ms"]["median"] for record in records])
    )

    assert summary["median_speedup_x"]["paired_four_target"] == pytest.approx(
        float(np.median(ratios))
    )
    assert summary["median_speedup_x"]["paired_four_target"] != pytest.approx(
        ratio_of_medians
    )
    assert summary["bootstrap_cluster"] == "family"
    assert summary["bootstrap_resamples"] == 1_000
    assert "not a population confidence interval" in summary["interval_semantics"]


def test_slurm_wrappers_freeze_one_thread_fem_v2_profile() -> None:
    full = _sbatch_directives(JOBS / "submit_corpus_v4_latency_v2.sh")
    preflight = _sbatch_directives(JOBS / "submit_corpus_v4_latency_preflight_v2.sh")
    finalizer = _sbatch_directives(JOBS / "submit_finalize_corpus_v4_latency_v2.sh")

    assert full["--account"] == preflight["--account"] == "pgs0407"
    assert full["--partition"] == preflight["--partition"] == "nextgen"
    assert full["--cpus-per-task"] == preflight["--cpus-per-task"] == "1"
    assert full["--mem"] == preflight["--mem"] == "48G"
    assert full["--time"] == preflight["--time"] == "02:00:00"
    assert full["--array"] == "0-305%8"
    assert preflight["--array"] == "0,152,305%1"
    assert finalizer["--cpus-per-task"] == "2"
    assert finalizer["--mem"] == "8G"

    wrapper_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            JOBS / "submit_corpus_v4_latency_v2.sh",
            JOBS / "submit_corpus_v4_latency_preflight_v2.sh",
            JOBS / "submit_finalize_corpus_v4_latency_v2.sh",
        )
    )
    assert "protocols/corpus_v4_latency_fem_v2_v1.json" in wrapper_source
    assert "results/corpus_v4/latency_fem_v2/" in wrapper_source
    assert "PCB_GNN_GMSH_THREADS=1" in wrapper_source
    assert "corpus_v4_latency_v1.json" not in wrapper_source
    assert "results/corpus_v4/latency/" not in wrapper_source
    assert "FEM_REPEATABILITY_ADMISSION" not in wrapper_source
    assert "fem-repeatability-admission" not in wrapper_source


def _preflight_environment(
    monkeypatch: pytest.MonkeyPatch, *, account: str = "pgs0407"
) -> None:
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)
    values = {
        "BLIS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "PCB_GNN_GMSH_THREADS": "1",
        "SLURM_ARRAY_JOB_ID": "8300000",
        "SLURM_ARRAY_TASK_COUNT": "3",
        "SLURM_ARRAY_TASK_ID": "152",
        "SLURM_ARRAY_TASK_MAX": "305",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "1",
        "SLURM_JOB_ACCOUNT": account,
        "SLURM_JOB_ID": "8300152",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": str(48 * 1024),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _scheduler_fields(*, account: str = "pgs0407") -> dict[str, str]:
    return {
        "Account": account,
        "AllocTRES": "cpu=1,mem=48G",
        "ArrayJobId": "8300000",
        "ArrayTaskId": "152",
        "ArrayTaskThrottle": "1",
        "CPUs/Task": "1",
        "JobId": "8300152",
        "JobState": "RUNNING",
        "MinMemoryNode": "48G",
        "NumCPUs": "1",
        "NumTasks": "1",
        "Partition": "nextgen",
        "ReqTRES": "cpu=1,mem=48G",
        "TimeLimit": "02:00:00",
        "TresPerTask": "cpu=1",
    }


def _mock_scontrol(
    monkeypatch: pytest.MonkeyPatch,
    contract: ModuleType,
    fields: dict[str, str],
) -> None:
    output = " ".join(f"{name}={value}" for name, value in fields.items()) + "\n"

    def run(command: list[str], **_: Any) -> SimpleNamespace:
        assert command == ["scontrol", "show", "job", "-o", "8300000_152"]
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(contract.subprocess, "run", run)


def test_slurm_guard_accepts_exact_one_thread_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_slurm_pass")
    _preflight_environment(monkeypatch)
    _mock_scontrol(monkeypatch, contract, _scheduler_fields())
    receipt = contract.validate_slurm_allocation(_protocol(), stage="preflight")

    assert receipt["requested_cpus_per_task"] == 1
    assert receipt["allocated_cpus_per_task"] == 1
    assert receipt["scientific_blas_threads"] == 1
    assert receipt["scheduler_record"]["Account"] == "pgs0407"


@pytest.mark.parametrize(
    ("environment_account", "scheduler_account"),
    (("wrong-account", "pgs0407"), ("pgs0407", "wrong-account")),
)
def test_slurm_guard_rejects_account_drift(
    monkeypatch: pytest.MonkeyPatch,
    environment_account: str,
    scheduler_account: str,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_slurm_reject")
    _preflight_environment(monkeypatch, account=environment_account)
    _mock_scontrol(monkeypatch, contract, _scheduler_fields(account=scheduler_account))
    with pytest.raises(SystemExit, match="frozen preflight resources"):
        contract.validate_slurm_allocation(_protocol(), stage="preflight")


def test_task_argument_contract_has_no_repeatability_receipt() -> None:
    runner = _load_module(TASK_SCRIPT, "latency_v2_task_args")
    values = {
        "protocol": Path("protocol.json"),
        "expected_protocol_sha256": "1" * 64,
        "plan": Path("plan.json"),
        "expected_plan_sha256": "2" * 64,
        "task_manifest": Path("tasks.jsonl"),
        "expected_task_manifest_sha256": "3" * 64,
        "execution_lock": Path("lock.json"),
        "expected_execution_lock_sha256": "4" * 64,
        "expected_source_git_head": "5" * 40,
        "output_root": Path("results"),
        "pending_set": None,
        "expected_pending_set_sha256": None,
        "preflight_admission": None,
        "expected_preflight_admission_sha256": None,
        "stage": "full_array",
    }
    with pytest.raises(SystemExit, match="requires preflight admission"):
        runner._require_runtime_args(SimpleNamespace(**values))

    values["stage"] = "preflight"
    values["preflight_admission"] = Path("admission.json")
    values["expected_preflight_admission_sha256"] = "6" * 64
    with pytest.raises(SystemExit, match="cannot consume its own admission"):
        runner._require_runtime_args(SimpleNamespace(**values))

    source = TASK_SCRIPT.read_text(encoding="utf-8")
    assert "fem_repeatability_admission" not in source
    assert "--fem-repeatability-admission" not in source
    assert "--pending-set" not in source
    assert "fem_v2_dataset_admission" in source


def test_full_array_retry_is_fail_closed() -> None:
    protocol = _protocol()
    assert protocol["forbidden_actions"]["within_study_full_array_retry"] is True
    wrapper = (JOBS / "submit_corpus_v4_latency_v2.sh").read_text(encoding="utf-8")
    resume = RESUME_SCRIPT.read_text(encoding="utf-8")
    assert "PENDING_SET" not in wrapper
    assert "--pending-set" not in wrapper
    assert "this protocol forbids within-study" in resume
    assert 'action="append"' not in resume
    assert 'root.glob("job_*/task_*/TASK_MANIFEST.json")' not in resume
    assert "exactly one canonical full-array job root" in resume
    finalizer = FINALIZER_SCRIPT.read_text(encoding="utf-8")
    assert 'result_bindings.get("retry_pending_set") is not None' in finalizer
    assert "--source-array-job-id" not in finalizer


def test_full_array_candidate_scan_accepts_only_one_canonical_job_root(
    tmp_path: Path,
) -> None:
    resume = _load_module(RESUME_SCRIPT, "latency_v2_single_job_root")
    resume.ROOT = tmp_path
    job_root = (
        tmp_path
        / "results/corpus_v4/latency_fem_v2/jobs/attempts/job_8301000"
    )
    manifests = []
    for task_id in range(306):
        task_root = job_root / f"task_{task_id:03d}"
        task_root.mkdir(parents=True)
        manifest = task_root / "TASK_MANIFEST.json"
        manifest.write_text("{}\n", encoding="utf-8")
        (task_root / "result.json").write_text("{}\n", encoding="utf-8")
        manifests.append(manifest)

    job_id, selected = resume._manifest_candidates(job_root)
    assert job_id == "8301000"
    assert selected == manifests
    with pytest.raises(ValueError, match="one canonical latency job directory"):
        resume._manifest_candidates(job_root.parent)
    another_job = job_root.parent / "job_8301002"
    another_job.mkdir()
    with pytest.raises(ValueError, match="another full-array dispatch"):
        resume._manifest_candidates(job_root)
    another_job.rmdir()
    another_job.symlink_to(job_root, target_is_directory=True)
    with pytest.raises(ValueError, match="another full-array dispatch"):
        resume._manifest_candidates(job_root)


def test_full_array_mesh_reference_covers_the_entire_admitted_r3_panel() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_admitted_mesh_contract")
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_admitted_mesh_finalizer")
    protocol, _ = contract.validate_protocol(PROTOCOL_PATH, PROTOCOL_SHA256)
    admitted = finalizer.load_admitted_mesh_identities(protocol)
    assert len(admitted) == 1500
    assert all(
        set(identity)
        == {"geometry_sha256", "mesh_nodes", "mesh_tetrahedra", "system_sha256"}
        for identity in admitted.values()
    )


def test_terminal_accounting_rejects_scheduler_restart() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_restart_gate")
    scheduler = {
        "array_job_id": "8301000",
        "array_task_id": 0,
        "job_id": "8301001",
        "scheduler_record": {
            "Account": "pgs0407",
            "AllocTRES": "cpu=1,mem=48G",
            "ReqTRES": "cpu=1,mem=48G",
        },
    }
    accounting = [{
        "Account": "pgs0407",
        "AllocTRES": "cpu=1,mem=48G",
        "ExitCode": "0:0",
        "JobID": "8301000_0",
        "JobIDRaw": "8301001",
        "ReqTRES": "cpu=1,mem=48G",
        "Restarts": "1",
        "State": "COMPLETED",
    }]
    assert contract.validate_terminal_array_completion(scheduler, accounting) is None
    accounting[0]["Restarts"] = "0"
    assert contract.validate_terminal_array_completion(scheduler, accounting) is not None


def test_latency_v2_schemas_propagate_fem_v2_namespace() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_schema_contract")
    runner = _load_module(TASK_SCRIPT, "latency_v2_schema_runner")
    resume = _load_module(RESUME_SCRIPT, "latency_v2_schema_resume")
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_schema_finalizer")
    archive = _load_module(ARCHIVE_VERIFIER, "latency_v2_schema_archive")

    assert contract.SCHEMA_PREFIX == SCHEMA_PREFIX
    assert contract.PROTOCOL_SCHEMA == PROTOCOL_SCHEMA
    assert runner.TASK_SCHEMA == TASK_SCHEMA
    assert runner.RECORD_SCHEMA == RECORD_SCHEMA
    assert contract.PENDING_SCHEMA == f"{SCHEMA_PREFIX}-pending-set.v1"
    assert resume.CANDIDATE_SCHEMA == f"{SCHEMA_PREFIX}-candidate-index.v1"
    assert resume.ACCEPTED_SCHEMA == f"{SCHEMA_PREFIX}-accepted-set.v1"
    assert finalizer.FINAL_SCHEMA == FINAL_SCHEMA
    assert finalizer.ANALYSIS_MANIFEST_SCHEMA == f"{SCHEMA_PREFIX}-analysis-manifest.v1"
    assert archive.ARCHIVE_SCHEMA == f"{SCHEMA_PREFIX}-archive.v1"


def test_no_login_node_solver_path_and_guard_precedes_solver_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_login_guard")
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="SLURM"):
        contract.validate_slurm_allocation(_protocol(), stage="full_array")

    tree = ast.parse(TASK_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]

    def call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    guards = [node.lineno for node in calls if call_name(node) == "validate_slurm_allocation"]
    solvers = [node.lineno for node in calls if call_name(node) == "run_solver_workflow"]
    assert guards and solvers
    assert min(guards) < min(solvers)


def test_runner_places_solver_between_two_gnn_measurement_blocks() -> None:
    tree = ast.parse(TASK_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    measurements = sorted(
        (node for node in calls if call_name(node) == "measure_raw_record_inference"),
        key=lambda node: node.lineno,
    )
    solvers = sorted(
        (node for node in calls if call_name(node) == "run_solver_workflow"),
        key=lambda node: node.lineno,
    )
    assert len(measurements) == 2
    assert len(solvers) == 1
    assert measurements[0].lineno < solvers[0].lineno < measurements[1].lineno
    post_warmups = next(
        keyword.value for keyword in measurements[1].keywords if keyword.arg == "warmups"
    )
    assert isinstance(post_warmups, ast.Constant)
    assert post_warmups.value == 0


def test_source_stability_gate_brackets_authenticated_failure_write() -> None:
    tree = ast.parse(TASK_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]

    def call_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    stability = sorted(
        node.lineno for node in calls if call_name(node) == "_validate_source_stability"
    )
    failures = sorted(
        node.lineno for node in calls if call_name(node) == "_atomic_failure_directory"
    )
    assert len(stability) == 2
    assert len(failures) == 1
    assert stability[0] < failures[0] < stability[1]


def test_validate_only_reports_current_fem_v2_schemas_without_solver() -> None:
    task = _validate_only(TASK_SCRIPT)
    final = _validate_only(FINALIZER_SCRIPT)
    assert task == {
        "array_tasks": 306,
        "fem_fidelity_id": "cps_fem_r3_p16_t1_v2",
        "schema": TASK_SCHEMA,
        "status": "validation-ok",
        "timed_repetitions": 200,
        "timing_boundary": "in-memory-raw-json-record-to-four-output",
        "warmups": 50,
    }
    assert final == {
        "bootstrap_cluster": "family",
        "bootstrap_resamples": 10_000,
        "schema": FINAL_SCHEMA,
        "status": "validation-ok",
    }


def test_archive_verifier_supports_offline_clean_clone_check() -> None:
    assert ARCHIVE_VERIFIER.is_file()
    completed = subprocess.run(
        [sys.executable, str(ARCHIVE_VERIFIER), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--check" in completed.stdout
    assert "--require-git-tracked" in completed.stdout


def test_frozen_hash_constants_are_well_formed_and_nonplaceholder() -> None:
    digests = [PROTOCOL_SHA256, *(digest for _, digest in EXPECTED_INPUT_PINS.values())]
    for digest in digests:
        assert len(digest) == 64
        int(digest, 16)
        assert len(set(digest)) > 8
