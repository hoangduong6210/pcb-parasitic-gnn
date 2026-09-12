#!/usr/bin/env python3
"""Finalize admitted Corpus V4 paired-latency tasks under SLURM."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_latency_contract_v2 import (  # noqa: E402
    EXECUTION_SOURCE_NAMES,
    EXPECTED_FAMILIES,
    EXPECTED_LAYOUTS,
    SCHEMA_PREFIX,
    TASK_MANIFEST_SCHEMA,
    TASK_RESULT_SCHEMA,
    load_json,
    load_jsonl,
    resolve_repo_path,
    validate_execution_lock,
    validate_plan,
    validate_preflight_admission,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
    validate_terminal_array_completion,
)
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


TASK_SCHEMA = TASK_RESULT_SCHEMA
RECORD_SCHEMA = f"{SCHEMA_PREFIX}-record.v1"
ARTIFACT_MANIFEST_SCHEMA = TASK_MANIFEST_SCHEMA
ACCEPTED_SCHEMA = f"{SCHEMA_PREFIX}-accepted-set.v1"
FINAL_SCHEMA = f"{SCHEMA_PREFIX}-final.v1"
ANALYSIS_MANIFEST_SCHEMA = f"{SCHEMA_PREFIX}-analysis-manifest.v1"
TASK_INDEX_SCHEMA = f"{SCHEMA_PREFIX}-task-index.v1"

PRIMARY_RATIO_FIELD = "speedup_paired_four_target_x"
FASTHENRY_RATIO_FIELD = "speedup_fasthenry_three_target_x"
FEM_V2_RATIO_FIELD = "speedup_fem_v2_capacitance_x"
RATIO_FIELDS = {
    "paired_four_target": PRIMARY_RATIO_FIELD,
    "fasthenry_three_target": FASTHENRY_RATIO_FIELD,
    "fem_v2_capacitance": FEM_V2_RATIO_FIELD,
}


def _positive(value: Any, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return result


def _nonnegative(value: Any, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be nonnegative and finite")
    return result


def _finite_vector(value: Any, length: int, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{label} must contain exactly {length} finite values")
    return array


def validate_timing_record(
    record: Mapping[str, Any],
    *,
    expected_repetitions: int = 200,
    block_median_ratio_max: float = 1.25,
) -> dict[str, Any]:
    """Recompute every timing-derived value from retained raw observations."""
    expected_fields = {
        "family_id",
        "fem_v2_reference_identity",
        "geometry_sha256",
        "inference_raw_record_ms",
        "inference_model_only_ms",
        "layout_id",
        "model_load_ms",
        "prediction",
        "reference",
        "rerun_reference",
        "schema",
        "solver_label_max_relative_drift",
        "solver_label_relative_drift",
        "solver_ms",
        "solver_telemetry",
        "speedup_fasthenry_three_target_x",
        "speedup_fem_v2_capacitance_x",
        "speedup_paired_four_target_x",
        "timer",
        "winding_coupling_coefficient",
    }
    if set(record) != expected_fields or record.get("schema") != RECORD_SCHEMA:
        raise ValueError("latency record schema or fields are not exact")
    layout_id = record.get("layout_id")
    family_id = record.get("family_id")
    geometry = record.get("geometry_sha256")
    if (
        type(layout_id) is not int
        or layout_id < 0
        or not isinstance(family_id, str)
        or not family_id
        or not isinstance(geometry, str)
        or len(geometry) != 64
        or any(character not in "0123456789abcdef" for character in geometry)
    ):
        raise ValueError("latency record design identity is malformed")

    solver = record.get("solver_ms")
    if not isinstance(solver, dict) or set(solver) != {
        "fasthenry",
        "fem_v2_r3_p16_t1",
        "orchestration_residual",
        "paired_four_target",
    }:
        raise ValueError("solver timing components are not exact")
    fasthenry_ms = _positive(solver["fasthenry"], "FastHenry latency")
    fem_ms = _positive(solver["fem_v2_r3_p16_t1"], "one-thread FEM-v2 latency")
    residual_ms = _nonnegative(
        solver["orchestration_residual"], "solver orchestration residual"
    )
    paired_ms = _positive(solver["paired_four_target"], "paired solver latency")
    if not math.isclose(
        paired_ms,
        fasthenry_ms + fem_ms + residual_ms,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError("paired solver latency differs from the outer-wall decomposition")

    inference = record.get("inference_raw_record_ms")
    expected_inference_fields = {
        "median",
        "post_solver_median",
        "post_solver_repetitions",
        "pre_solver_median",
        "pre_solver_repetitions",
        "repetitions",
        "timed_repetitions",
        "warmups",
    }
    if not isinstance(inference, dict) or set(inference) != expected_inference_fields:
        raise ValueError("GNN timing record fields are not exact")
    repetitions = _finite_vector(
        inference["repetitions"], expected_repetitions, "GNN repetitions"
    )
    pre = _finite_vector(
        inference["pre_solver_repetitions"],
        expected_repetitions // 2,
        "pre-solver GNN repetitions",
    )
    post = _finite_vector(
        inference["post_solver_repetitions"],
        expected_repetitions // 2,
        "post-solver GNN repetitions",
    )
    if np.any(repetitions <= 0.0) or np.any(pre <= 0.0) or np.any(post <= 0.0):
        raise ValueError("GNN repetitions must be strictly positive")
    if not np.array_equal(repetitions, np.concatenate((pre, post))):
        raise ValueError("combined GNN repetitions differ from pre/post blocks")
    if (
        inference.get("timed_repetitions") != expected_repetitions
        or inference.get("warmups") != 50
    ):
        raise ValueError("GNN warmup/repetition counts differ from protocol")
    medians = {
        "median": float(np.median(repetitions)),
        "pre_solver_median": float(np.median(pre)),
        "post_solver_median": float(np.median(post)),
    }
    for name, expected in medians.items():
        observed = _positive(inference.get(name), f"GNN {name}")
        if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"stored GNN {name} differs from raw repetitions")

    block_limit = _positive(block_median_ratio_max, "GNN block-median ratio gate")
    if block_limit < 1.0:
        raise ValueError("GNN block-median ratio gate cannot be below one")
    block_ratio = max(
        medians["pre_solver_median"], medians["post_solver_median"]
    ) / min(medians["pre_solver_median"], medians["post_solver_median"])
    if block_ratio > block_limit:
        raise ValueError("GNN pre/post block-median drift exceeds the frozen gate")

    expected_ratios = {
        PRIMARY_RATIO_FIELD: paired_ms / medians["median"],
        FASTHENRY_RATIO_FIELD: fasthenry_ms / medians["median"],
        FEM_V2_RATIO_FIELD: fem_ms / medians["median"],
    }
    for field, expected in expected_ratios.items():
        observed = _positive(record.get(field), field)
        if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError(f"stored {field} differs from timing reconstruction")
    _positive(record.get("model_load_ms"), "model-load latency")
    _finite_vector(record.get("prediction"), 4, "prediction")
    reference = _finite_vector(record.get("reference"), 4, "reference")
    rerun = _finite_vector(record.get("rerun_reference"), 4, "rerun reference")
    if np.any(reference <= 0.0):
        raise ValueError("frozen references must be positive")
    expected_drift = np.abs(rerun - reference) / np.maximum(np.abs(reference), 1e-12)
    drift = _finite_vector(record.get("solver_label_relative_drift"), 4, "solver drift")
    if not np.allclose(drift, expected_drift, rtol=1e-12, atol=1e-15):
        raise ValueError("stored solver drift differs from reference reconstruction")
    maximum = float(np.max(drift))
    if not math.isclose(
        float(record.get("solver_label_max_relative_drift")), maximum,
        rel_tol=1e-12, abs_tol=1e-15,
    ):
        raise ValueError("stored maximum solver drift is inconsistent")
    coupling = float(record.get("winding_coupling_coefficient"))
    if not math.isfinite(coupling) or coupling < 0.0 or coupling > 1.000001:
        raise ValueError("winding coupling coefficient violates passivity")
    if record.get("timer") != {"clock": "perf_counter_ns", "monotonic": True}:
        raise ValueError("latency timer contract is not exact")
    model_only = record.get("inference_model_only_ms")
    if not isinstance(model_only, dict) or set(model_only) != {
        "median",
        "physical_prediction",
        "repetitions",
        "timed_repetitions",
        "warmups",
    }:
        raise ValueError("model-only timing record fields are not exact")
    model_only_repetitions = _finite_vector(
        model_only["repetitions"], expected_repetitions, "model-only repetitions"
    )
    model_only_prediction = _finite_vector(
        model_only["physical_prediction"], 4, "model-only physical prediction"
    )
    if (
        np.any(model_only_repetitions <= 0.0)
        or model_only.get("timed_repetitions") != expected_repetitions
        or model_only.get("warmups") != 50
        or not math.isclose(
            _positive(model_only.get("median"), "model-only median"),
            float(np.median(model_only_repetitions)),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
        or not np.allclose(
            model_only_prediction,
            np.asarray(record["prediction"], dtype=np.float64),
            rtol=1e-12,
            atol=1e-12,
        )
    ):
        raise ValueError("model-only timing or prediction differs from its raw evidence")
    telemetry = record.get("solver_telemetry")
    if not isinstance(telemetry, dict) or set(telemetry) != {
        "fasthenry", "fem_v2_r3_p16_t1", "paired_outer_wall"
    }:
        raise ValueError("solver telemetry fields are not exact")
    fast_telemetry = telemetry["fasthenry"]
    fem_telemetry = telemetry["fem_v2_r3_p16_t1"]
    paired_telemetry = telemetry["paired_outer_wall"]
    if (
        not isinstance(fast_telemetry, dict)
        or set(fast_telemetry) != {"returncode", "start_ns", "stop_ns"}
        or fast_telemetry["returncode"] != 0
        or type(fast_telemetry["start_ns"]) is not int
        or type(fast_telemetry["stop_ns"]) is not int
        or fast_telemetry["stop_ns"] <= fast_telemetry["start_ns"]
        or not math.isclose(
            (fast_telemetry["stop_ns"] - fast_telemetry["start_ns"]) / 1e6,
            fasthenry_ms,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("FastHenry telemetry differs from its timing record")
    if (
        not isinstance(fem_telemetry, dict)
        or set(fem_telemetry) != {"checks", "observed", "start_ns", "stop_ns"}
        or not isinstance(fem_telemetry["checks"], dict)
        or not fem_telemetry["checks"]
        or any(value is not True for value in fem_telemetry["checks"].values())
        or not isinstance(fem_telemetry["observed"], dict)
        or fem_telemetry["observed"].get("refine") != 3
        or fem_telemetry["observed"].get("pad_mm") != 16.0
        or fem_telemetry["observed"].get("solver_info") != 0
        or type(fem_telemetry["start_ns"]) is not int
        or type(fem_telemetry["stop_ns"]) is not int
        or fem_telemetry["stop_ns"] <= fem_telemetry["start_ns"]
        or not math.isclose(
            (fem_telemetry["stop_ns"] - fem_telemetry["start_ns"]) / 1e6,
            fem_ms,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("FEM-v2 telemetry differs from its R3P16 timing record")
    reference_identity = record.get("fem_v2_reference_identity")
    expected_identity_fields = {
        "geometry_sha256",
        "mesh_nodes",
        "mesh_tetrahedra",
        "system_sha256",
    }
    if (
        not isinstance(reference_identity, dict)
        or set(reference_identity) != expected_identity_fields
        or reference_identity.get("geometry_sha256") != geometry
        or type(reference_identity.get("mesh_nodes")) is not int
        or reference_identity["mesh_nodes"] <= 0
        or type(reference_identity.get("mesh_tetrahedra")) is not int
        or reference_identity["mesh_tetrahedra"] <= 0
        or not isinstance(reference_identity.get("system_sha256"), str)
        or len(reference_identity["system_sha256"]) != 64
        or any(
            fem_telemetry["observed"].get(name) != reference_identity[name]
            for name in ("mesh_nodes", "mesh_tetrahedra", "system_sha256")
        )
    ):
        raise ValueError("FEM-v2 fresh mesh/system identity differs from the admitted row")
    if (
        not isinstance(paired_telemetry, dict)
        or set(paired_telemetry) != {"start_ns", "stop_ns"}
        or type(paired_telemetry["start_ns"]) is not int
        or type(paired_telemetry["stop_ns"]) is not int
        or paired_telemetry["stop_ns"] <= paired_telemetry["start_ns"]
        or paired_telemetry["start_ns"] > fast_telemetry["start_ns"]
        or fast_telemetry["stop_ns"] > fem_telemetry["start_ns"]
        or paired_telemetry["stop_ns"] < fem_telemetry["stop_ns"]
        or not math.isclose(
            (paired_telemetry["stop_ns"] - paired_telemetry["start_ns"]) / 1e6,
            paired_ms,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("paired outer-wall telemetry differs from its timing record")
    return dict(record)


def load_expected_references(protocol: Mapping[str, Any]) -> dict[int, list[float]]:
    """Load the immutable four-target reference vector for every layout."""
    target_order = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
    rows = load_jsonl(
        resolve_repo_path(
            protocol["inputs"]["evaluation_dataset"]["path"],
            "latency evaluation dataset",
        )
    )
    references: dict[int, list[float]] = {}
    for row in rows:
        layout_id = row.get("layout_id")
        table = row.get("training_reference")
        if type(layout_id) is not int or not isinstance(table, Mapping):
            raise ValueError("latency evaluation reference row is malformed")
        values = [float(table[name]["value"]) for name in target_order]
        if (
            layout_id in references
            or any(not math.isfinite(value) or value <= 0.0 for value in values)
        ):
            raise ValueError("latency evaluation references are ambiguous or nonfinite")
        references[layout_id] = values
    if len(references) != 1500:
        raise ValueError("latency evaluation reference coverage differs from 1,500")
    return references


def load_admitted_mesh_identities(
    protocol: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    """Bind every fresh R3 solve to its admitted geometry and FEM system."""
    rows = load_jsonl(
        resolve_repo_path(
            protocol["inputs"]["fem_v2_final_observations"]["path"],
            "FEM-v2 final observations",
        )
    )
    identities: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.get("fidelity_id") != "cps_fem_r3_p16_t1_v2":
            continue
        layout_id = row.get("layout_id")
        if type(layout_id) is not int or layout_id in identities:
            raise ValueError("admitted R3 mesh identities have an invalid layout ID")
        identities[layout_id] = {
            name: row[name]
            for name in (
                "geometry_sha256", "mesh_nodes", "mesh_tetrahedra", "system_sha256"
            )
        }
    if len(identities) != 1500:
        raise ValueError("admitted R3 mesh identities do not cover 1,500 layouts")
    return identities


def validate_full_task_result(
    result: Mapping[str, Any],
    *,
    task: Mapping[str, Any],
    bindings: Mapping[str, str],
    preflight_admission: Mapping[str, str],
    checkpoint_archive_sha256: str,
    external_solver_sha256: str,
    fem_v2_dataset_admission: Mapping[str, str],
    expected_source_git_head: str,
    locked_source_sha256: Mapping[str, str],
    expected_runtime: Mapping[str, Any],
    expected_array_job_id: str,
    expected_reference: Sequence[float],
    expected_mesh_identity: Mapping[str, Any],
    expected_repetitions: int,
    block_median_ratio_max: float,
    reference_agreement_tolerance: float,
) -> None:
    """Authenticate one full-array result before it can enter an accepted set."""
    expected_task = {
        "family_id": task["family_id"],
        "geometry_sha256": task["geometry_sha256"],
        "layout_id": task["layout_id"],
        "task_id": task["task_id"],
    }
    result_bindings = result.get("bindings")
    expected_binding_fields = {
        *bindings,
        "checkpoint_archive_sha256",
        "fem_v2_dataset_admission",
        "preflight_admission",
        "retry_pending_set",
    }
    provenance = result.get("provenance")
    expected_provenance_fields = {
        "executed_batch_sha256",
        "external_solver",
        "hardware",
        "runtime",
        "scheduler",
        "source_git_head",
        "source_sha256",
    }
    expected_top_fields = {
        "bindings",
        "created_utc",
        "integrity",
        "provenance",
        "record",
        "schema",
        "stage",
        "task",
    }
    if (
        set(result) != expected_top_fields
        or result.get("schema") != TASK_SCHEMA
        or result.get("stage") != "full_array"
        or result.get("task") != expected_task
        or result.get("integrity") != {"passed": True}
        or not isinstance(result_bindings, Mapping)
        or set(result_bindings) != expected_binding_fields
        or any(result_bindings.get(name) != digest for name, digest in bindings.items())
        or result_bindings.get("checkpoint_archive_sha256")
        != checkpoint_archive_sha256
        or result_bindings.get("fem_v2_dataset_admission")
        != dict(fem_v2_dataset_admission)
        or result_bindings.get("preflight_admission") != dict(preflight_admission)
        or result_bindings.get("retry_pending_set") is not None
        or not isinstance(provenance, Mapping)
        or set(provenance) != expected_provenance_fields
        or provenance.get("source_git_head") != expected_source_git_head
        or provenance.get("source_sha256") != dict(locked_source_sha256)
        or provenance.get("runtime") != dict(expected_runtime)
        or provenance.get("executed_batch_sha256")
        != locked_source_sha256.get("code/jobs/submit_corpus_v4_latency_v2.sh")
    ):
        raise ValueError("full-array result differs from frozen roots or task identity")
    if provenance.get("external_solver") != {
        "label": "external/fasthenry",
        "sha256": external_solver_sha256,
    }:
        raise ValueError("full-array result external solver identity differs")
    scheduler = provenance.get("scheduler")
    if (
        not isinstance(scheduler, Mapping)
        or scheduler.get("stage") != "full_array"
        or scheduler.get("array_job_id") != expected_array_job_id
        or scheduler.get("array_task_id") != task["task_id"]
    ):
        raise ValueError("full-array result scheduler stage differs")
    hardware = provenance.get("hardware")
    hardware_fields = {
        "affinity_cpu_count",
        "anonymous_class_sha256",
        "architecture",
        "cpu_model",
        "kernel",
    }
    if not isinstance(hardware, Mapping) or set(hardware) != hardware_fields:
        raise ValueError("full-array hardware identity is malformed")
    anonymous_payload = {
        name: hardware[name]
        for name in ("affinity_cpu_count", "architecture", "cpu_model", "kernel")
    }
    if hardware.get("anonymous_class_sha256") != sha256_bytes(
        canonical_json_bytes(anonymous_payload)
    ):
        raise ValueError("full-array hardware class digest differs")
    record = result.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("full-array timing record is missing")
    if record.get("fem_v2_reference_identity") != dict(expected_mesh_identity):
        raise ValueError("full-array FEM mesh identity differs from the admitted row")
    validate_timing_record(
        record,
        expected_repetitions=expected_repetitions,
        block_median_ratio_max=block_median_ratio_max,
    )
    if any(
        record.get(name) != expected_task[name]
        for name in ("layout_id", "family_id", "geometry_sha256")
    ):
        raise ValueError("full-array timing record identity differs from its task")
    observed_reference = np.asarray(record.get("reference"), dtype=np.float64)
    frozen_reference = np.asarray(expected_reference, dtype=np.float64)
    if not np.array_equal(observed_reference, frozen_reference):
        raise ValueError("full-array reference vector differs from the frozen dataset")
    if float(record.get("solver_label_max_relative_drift", math.inf)) > float(
        reference_agreement_tolerance
    ):
        raise ValueError("full-array solver replay exceeds the frozen tolerance")


def finalizer_runtime_identity(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Authenticate the runtime that computes claim-bearing aggregates."""
    expected = protocol["runtime"]
    actual = {
        "packages": {
            name: importlib.metadata.version(name)
            for name in expected["packages"]
        },
        "python": platform.python_version(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "BLIS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
            )
        },
    }
    expected_finalizer = {
        "packages": expected["packages"],
        "python": expected["python"],
        "thread_environment": {
            name: "2" for name in actual["thread_environment"]
        },
    }
    if actual != expected_finalizer:
        raise SystemExit("latency finalizer runtime differs from the frozen contract")
    return actual


def validate_finalizer_source(
    lock: Mapping[str, Any], expected_source_git_head: str
) -> dict[str, str]:
    """Require the actual clean finalizer checkout and every locked source byte."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_source = subprocess.run(
        [
            "git", "status", "--short", "--untracked-files=all", "--",
            "code", "protocols", "requirements-proof.txt",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    source_hashes = {
        name: sha256_file(resolve_repo_path(name, "finalizer source"))
        for name in EXECUTION_SOURCE_NAMES
    }
    if (
        head != expected_source_git_head
        or dirty
        or untracked_source
        or source_hashes != lock.get("source_sha256")
    ):
        raise SystemExit("latency finalizer requires the exact clean source commit")
    return source_hashes


def _family_cluster_interval(
    records: Sequence[Mapping[str, Any]],
    *,
    ratio_field: str,
    resamples: int,
    seed: int,
) -> list[float]:
    by_family: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_family[str(record["family_id"])].append(float(record[ratio_field]))
    families = sorted(by_family)
    if len(families) < 2:
        raise ValueError("family-cluster bootstrap requires at least two families")
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        selected = rng.choice(families, size=len(families), replace=True)
        values = [value for family in selected for value in by_family[str(family)]]
        draws[index] = float(np.median(np.asarray(values, dtype=np.float64)))
    return [
        float(value)
        for value in np.quantile(draws, [0.025, 0.975], method="linear")
    ]


def summarize_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_repetitions: int = 200,
    bootstrap_resamples: int = 10_000,
    bootstrap_seed: int = 20260820,
    block_median_ratio_max: float = 1.25,
) -> dict[str, Any]:
    if type(bootstrap_resamples) is not int or bootstrap_resamples < 1:
        raise ValueError("bootstrap resamples must be a positive integer")
    validated = [
        validate_timing_record(
            record,
            expected_repetitions=expected_repetitions,
            block_median_ratio_max=block_median_ratio_max,
        )
        for record in records
    ]
    layout_ids = [record["layout_id"] for record in validated]
    geometries = [record["geometry_sha256"] for record in validated]
    if len(layout_ids) != len(set(layout_ids)) or len(geometries) != len(set(geometries)):
        raise ValueError("duplicate layout or geometry in latency records")
    ratio_vectors = {
        name: np.asarray([record[field] for record in validated], dtype=np.float64)
        for name, field in RATIO_FIELDS.items()
    }
    paired = np.asarray(
        [record["solver_ms"]["paired_four_target"] for record in validated],
        dtype=np.float64,
    )
    fast = np.asarray(
        [record["solver_ms"]["fasthenry"] for record in validated], dtype=np.float64
    )
    fem = np.asarray(
        [record["solver_ms"]["fem_v2_r3_p16_t1"] for record in validated],
        dtype=np.float64,
    )
    residual = np.asarray(
        [record["solver_ms"]["orchestration_residual"] for record in validated],
        dtype=np.float64,
    )
    gnn = np.asarray(
        [record["inference_raw_record_ms"]["median"] for record in validated],
        dtype=np.float64,
    )
    model_load = np.asarray(
        [record["model_load_ms"] for record in validated], dtype=np.float64
    )
    model_only = np.asarray(
        [record["inference_model_only_ms"]["median"] for record in validated],
        dtype=np.float64,
    )
    block_ratios = np.asarray(
        [
            max(
                record["inference_raw_record_ms"]["pre_solver_median"],
                record["inference_raw_record_ms"]["post_solver_median"],
            )
            / min(
                record["inference_raw_record_ms"]["pre_solver_median"],
                record["inference_raw_record_ms"]["post_solver_median"],
            )
            for record in validated
        ],
        dtype=np.float64,
    )
    family_sensitivity = {
        name: _family_cluster_interval(
            validated,
            ratio_field=RATIO_FIELDS[name],
            resamples=bootstrap_resamples,
            seed=bootstrap_seed,
        )
        for name in RATIO_FIELDS
    }
    median_ratios = {
        name: float(np.median(values)) for name, values in ratio_vectors.items()
    }
    ratio_quantiles = {
        name: {
            "p05": float(np.quantile(values, 0.05, method="linear")),
            "p95": float(np.quantile(values, 0.95, method="linear")),
        }
        for name, values in ratio_vectors.items()
    }
    return {
        "bootstrap_cluster": "family",
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": bootstrap_seed,
        "component_medians_ms": {
            "fasthenry": float(np.median(fast)),
            "fem_v2_r3_p16_t1": float(np.median(fem)),
            "model_load": float(np.median(model_load)),
            "model_only_forward": float(np.median(model_only)),
            "orchestration_residual": float(np.median(residual)),
            "paired_four_target": float(np.median(paired)),
            "warm_loaded_raw_record_gnn": float(np.median(gnn)),
        },
        "family_cluster_bootstrap_95_sensitivity_interval_x": family_sensitivity,
        "interval_semantics": (
            "descriptive family-cluster sensitivity interval on the evaluated split "
            "and CPU-node class; not a population confidence interval"
        ),
        "median_speedup_x": median_ratios,
        "model_only_supporting": {
            "median_raw_to_model_only_overhead_x": float(np.median(gnn / model_only)),
            "role": "secondary diagnostic; excluded from solver-workflow ratios",
        },
        "n_designs": len(validated),
        "n_families": len({record["family_id"] for record in validated}),
        "per_design_speedup_quantiles_x": ratio_quantiles,
        "primary_estimand": (
            "median of per-design sequential all-four-target solver-to-GNN ratios"
        ),
        "ratio_of_component_medians_x": {
            "fasthenry_three_target": float(np.median(fast) / np.median(gnn)),
            "fem_v2_capacitance": float(np.median(fem) / np.median(gnn)),
            "paired_four_target": float(np.median(paired) / np.median(gnn)),
        },
        "secondary_estimands": {
            "fasthenry_three_target": (
                "median of per-design FastHenry-to-GNN ratios for three inductance targets"
            ),
            "fem_v2_capacitance": (
                "median of per-design one-thread FEM-v2-to-GNN ratios for capacitance"
            ),
        },
        "secondary_estimand_scope": (
            "descriptive component ratios against the same all-four-output GNN call; "
            "they do not replace the primary paired workflow comparison"
        ),
        "timing_stability": {
            "block_median_ratio_gate": float(block_median_ratio_max),
            "maximum_observed_block_median_ratio": float(np.max(block_ratios)),
            "median_observed_block_median_ratio": float(np.median(block_ratios)),
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--expected-protocol-sha256")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--expected-task-manifest-sha256")
    parser.add_argument("--execution-lock", type=Path)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--accepted-set", type=Path)
    parser.add_argument("--expected-accepted-set-sha256")
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _runtime_required(args: argparse.Namespace) -> None:
    names = (
        "protocol", "expected_protocol_sha256", "plan", "expected_plan_sha256",
        "task_manifest", "expected_task_manifest_sha256", "execution_lock",
        "expected_execution_lock_sha256", "accepted_set",
        "expected_accepted_set_sha256", "expected_source_git_head", "output_root",
    )
    missing = [name for name in names if getattr(args, name) is None]
    if missing:
        raise SystemExit(f"missing latency finalizer arguments: {missing}")


def _accepted_entries(
    path: Path,
    expected_sha256: str,
    *,
    bindings: Mapping[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str], str]:
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("accepted set is missing or hash-mismatched")
    payload = load_json(path)
    expected_fields = {
        *bindings,
        "candidate_index",
        "entries",
        "full_array_job_id",
        "n_accepted",
        "n_expected",
        "preflight_admission",
        "schema",
    }
    entries = payload.get("entries")
    full_array_job_id = payload.get("full_array_job_id")
    preflight_admission = payload.get("preflight_admission")
    if (
        set(payload) != expected_fields
        or payload.get("schema") != ACCEPTED_SCHEMA
        or any(payload.get(name) != digest for name, digest in bindings.items())
        or payload.get("n_expected") != EXPECTED_LAYOUTS
        or payload.get("n_accepted") != EXPECTED_LAYOUTS
        or not isinstance(entries, list)
        or len(entries) != EXPECTED_LAYOUTS
        or not isinstance(full_array_job_id, str)
        or not full_array_job_id.isdigit()
        or not isinstance(preflight_admission, dict)
        or set(preflight_admission) != {"path", "sha256"}
    ):
        raise ValueError("accepted set is not the exact complete latency closure")
    if [entry.get("task_id") for entry in entries] != list(range(EXPECTED_LAYOUTS)):
        raise ValueError("accepted latency entries are not dense tasks 0..305")
    return entries, preflight_admission, full_array_job_id


def _load_task_result(
    entry: Mapping[str, Any],
    *,
    task: Mapping[str, Any],
    bindings: Mapping[str, str],
    preflight_admission: Mapping[str, str],
    checkpoint_archive_sha256: str,
    external_solver_sha256: str,
    fem_v2_dataset_admission: Mapping[str, str],
    expected_source_git_head: str,
    locked_source_sha256: Mapping[str, str],
    expected_runtime: Mapping[str, Any],
    expected_array_job_id: str,
    expected_reference: Sequence[float],
    expected_mesh_identity: Mapping[str, Any],
    expected_repetitions: int,
    block_median_ratio_max: float,
    reference_agreement_tolerance: float,
) -> tuple[dict[str, Any], Path]:
    manifest_path = resolve_repo_path(entry.get("manifest_path"), "accepted task manifest")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("accepted task manifest is missing")
    if sha256_file(manifest_path) != entry.get("manifest_sha256"):
        raise ValueError("accepted task manifest hash differs")
    manifest = load_json(manifest_path)
    result_path = manifest_path.parent / "result.json"
    if (
        result_path.is_symlink()
        or not result_path.is_file()
        or set(manifest) != {"files_sha256", "schema"}
        or manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA
        or manifest.get("files_sha256") != {"result.json": sha256_file(result_path)}
    ):
        raise ValueError("accepted task artifact manifest is invalid")
    result = load_json(result_path)
    scheduler = result.get("provenance", {}).get("scheduler", {})
    expected_manifest = (
        ROOT
        / "results/corpus_v4/latency_fem_v2/jobs/attempts"
        / f"job_{scheduler.get('array_job_id')}"
        / f"task_{task['task_id']:03d}"
        / "TASK_MANIFEST.json"
    ).resolve()
    observed_files = {
        child.name
        for child in manifest_path.parent.iterdir()
        if child.is_file() and not child.is_symlink()
    }
    if (
        manifest_path.resolve() != expected_manifest
        or observed_files != {"TASK_MANIFEST.json", "result.json"}
        or any(child.is_symlink() for child in manifest_path.parent.iterdir())
    ):
        raise ValueError("accepted task directory is not canonical or exact")
    validate_full_task_result(
        result,
        task=task,
        bindings=bindings,
        preflight_admission=preflight_admission,
        checkpoint_archive_sha256=checkpoint_archive_sha256,
        external_solver_sha256=external_solver_sha256,
        fem_v2_dataset_admission=fem_v2_dataset_admission,
        expected_source_git_head=expected_source_git_head,
        locked_source_sha256=locked_source_sha256,
        expected_runtime=expected_runtime,
        expected_array_job_id=expected_array_job_id,
        expected_reference=expected_reference,
        expected_mesh_identity=expected_mesh_identity,
        expected_repetitions=expected_repetitions,
        block_median_ratio_max=block_median_ratio_max,
        reference_agreement_tolerance=reference_agreement_tolerance,
    )
    completion = entry.get("scheduler_completion")
    scheduler = result["provenance"]["scheduler"]
    validated_completion = (
        validate_terminal_array_completion(scheduler, [completion])
        if isinstance(completion, dict)
        else None
    )
    if validated_completion is None or validated_completion != completion:
        raise ValueError("accepted task lacks matching terminal SLURM accounting")
    return result, manifest_path


def main() -> None:
    args = _parse_args()
    if args.validate_only:
        print(
            json.dumps(
                {
                    "bootstrap_cluster": "family",
                    "bootstrap_resamples": 10_000,
                    "schema": FINAL_SCHEMA,
                    "status": "validation-ok",
                },
                sort_keys=True,
            )
        )
        return
    _runtime_required(args)
    protocol, protocol_sha = validate_protocol(args.protocol, args.expected_protocol_sha256)
    panel_path = args.plan.parent / "panel_records.jsonl"
    plan, tasks, panel, plan_sha, task_sha, panel_sha = validate_plan(
        args.plan,
        args.task_manifest,
        panel_path,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_task_manifest_sha256=args.expected_task_manifest_sha256,
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=args.plan,
        tasks=tasks,
        panel_records=panel,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock,
        args.expected_execution_lock_sha256,
        protocol_sha256=protocol_sha,
        plan_sha256=plan_sha,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    finalizer_source_sha256 = validate_finalizer_source(
        lock, args.expected_source_git_head
    )
    finalizer_runtime = finalizer_runtime_identity(protocol)
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch = "code/jobs/submit_finalize_corpus_v4_latency_v2.sh"
    if (
        executed_batch.is_symlink()
        or not executed_batch.is_file()
        or sha256_file(executed_batch) != lock["source_sha256"].get(expected_batch)
    ):
        raise SystemExit("executed finalizer batch script differs from the source lock")
    scheduler = validate_slurm_allocation(protocol, stage="finalizer")
    bindings = {
        "execution_lock_sha256": lock_sha,
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_sha,
    }
    entries, admission_reference, full_array_job_id = _accepted_entries(
        args.accepted_set, args.expected_accepted_set_sha256, bindings=bindings
    )
    validate_preflight_admission(
        resolve_repo_path(admission_reference["path"], "preflight admission"),
        admission_reference["sha256"],
        bindings=bindings,
        expected_source_git_head=args.expected_source_git_head,
        tasks=tasks,
        lock=lock,
        checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"]["sha256"],
    )
    results: list[dict[str, Any]] = []
    manifests: list[Path] = []
    expected_repetitions = int(protocol["gnn_timing"]["measured_repetitions"])
    block_median_ratio_max = float(
        protocol["gnn_timing"]["block_median_ratio_max"]
    )
    fem_v2_dataset_admission = dict(
        protocol["inputs"]["fem_v2_dataset_admission"]
    )
    references = load_expected_references(protocol)
    tolerance = float(
        protocol["solver_workflow"]["reference_agreement_max_relative_error"]
    )
    admitted_r3 = load_admitted_mesh_identities(protocol)
    for task, entry in zip(tasks, entries):
        result, manifest = _load_task_result(
            entry,
            task=task,
            bindings=bindings,
            preflight_admission=admission_reference,
            checkpoint_archive_sha256=protocol["inputs"]["checkpoint_archive"][
                "sha256"
            ],
            external_solver_sha256=protocol["solver_workflow"]["inductance"][
                "binary_sha256"
            ],
            fem_v2_dataset_admission=fem_v2_dataset_admission,
            expected_source_git_head=args.expected_source_git_head,
            locked_source_sha256=lock["source_sha256"],
            expected_runtime=protocol["runtime"],
            expected_array_job_id=full_array_job_id,
            expected_reference=references[task["layout_id"]],
            expected_mesh_identity=admitted_r3[task["layout_id"]],
            expected_repetitions=expected_repetitions,
            block_median_ratio_max=block_median_ratio_max,
            reference_agreement_tolerance=tolerance,
        )
        results.append(result)
        manifests.append(manifest)
    records = [result["record"] for result in results]
    if [record["layout_id"] for record in records] != [row["layout_id"] for row in panel]:
        raise ValueError("accepted latency records differ from frozen panel order")
    if len({record["family_id"] for record in records}) != EXPECTED_FAMILIES:
        raise ValueError("accepted latency records do not cover all held-out families")
    if any(
        record["fem_v2_reference_identity"] != admitted_r3.get(record["layout_id"])
        for record in records
    ):
        raise ValueError("latency records do not bind the admitted FEM-v2 R3 identities")
    if any(
        float(record["solver_label_max_relative_drift"]) > tolerance
        for record in records
    ):
        raise ValueError("an accepted solver rerun exceeds the frozen reference tolerance")
    hardware_classes = {
        result["provenance"]["hardware"]["anonymous_class_sha256"] for result in results
    }
    if len(hardware_classes) != 1:
        raise ValueError("latency evidence spans multiple CPU-node classes")
    summary = summarize_records(
        records,
        expected_repetitions=expected_repetitions,
        bootstrap_resamples=int(protocol["statistics"]["bootstrap"]["resamples"]),
        bootstrap_seed=int(protocol["statistics"]["bootstrap"]["seed"]),
        block_median_ratio_max=block_median_ratio_max,
    )
    if summary["n_designs"] != EXPECTED_LAYOUTS or summary["n_families"] != EXPECTED_FAMILIES:
        raise ValueError("final latency summary cardinality differs from protocol")

    output = args.output_root / f"job_{scheduler['job_id']}"
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        atomic_write_jsonl(temporary / "records.jsonl", records)
        atomic_write_json(
            temporary / "task_index.json",
            {
                "entries": [
                    {
                        "manifest_path": path.relative_to(ROOT).as_posix(),
                        "manifest_sha256": sha256_file(path),
                        "scheduler_completion": entry["scheduler_completion"],
                        "task_id": index,
                    }
                    for index, (path, entry) in enumerate(zip(manifests, entries))
                ],
                "schema": TASK_INDEX_SCHEMA,
            },
        )
        final = {
            "bindings": {
                **bindings,
                "accepted_set_sha256": args.expected_accepted_set_sha256,
                "expected_source_git_head": args.expected_source_git_head,
                "full_array_job_id": full_array_job_id,
                "preflight_admission": admission_reference,
            },
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "provenance": {
                "hardware_class_sha256": next(iter(hardware_classes)),
                "runtime": finalizer_runtime,
                "scheduler": scheduler,
                "source_git_head": args.expected_source_git_head,
                "source_sha256": finalizer_source_sha256,
            },
            "schema": FINAL_SCHEMA,
            "scientific_scope": {
                "checkpoint_task_id": 12,
                "comparison": (
                    "sequential FastHenry-plus-one-thread-FEM-v2-R3P16 all-four-target "
                    "workflow versus warm-loaded batch-one in-memory "
                    "raw-JSON-record-to-four-output GNN"
                ),
                "primary_comparison": "paired_four_target",
                "secondary_comparisons": [
                    "fasthenry_three_target",
                    "fem_v2_capacitance",
                ],
                "split_seed": 42,
            },
            "summary": summary,
        }
        atomic_write_json(temporary / "summary.json", final)
        analysis_files = {
            name: sha256_file(temporary / name)
            for name in ("records.jsonl", "summary.json", "task_index.json")
        }
        atomic_write_json(
            temporary / "ANALYSIS_MANIFEST.json",
            {
                "accepted_set": {
                    "path": args.accepted_set.resolve().relative_to(ROOT.resolve()).as_posix(),
                    "sha256": args.expected_accepted_set_sha256,
                },
                "files_sha256": analysis_files,
                "schema": ANALYSIS_MANIFEST_SCHEMA,
            },
        )
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(output.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
