#!/usr/bin/env python3
"""Fail-closed contracts for the Corpus V4 paired-latency study.

This module is deliberately solver-free.  It validates immutable protocol,
panel, task, checkpoint, and source roots so planning and CI remain safe on a
login node.  Timings and predictive outcomes are never inputs to panel
construction.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for _directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/experiments/proofs",
):
    sys.path.insert(0, str(_directory))

from corpus_v4_accuracy_contract import (  # noqa: E402
    load_json,
    load_jsonl,
    resolve_descendant_path,
    require_plain_int,
    require_repo_relative_path,
    resolve_repo_path,
    validate_execution_lock as validate_accuracy_execution_lock,
    validate_file_manifest as validate_accuracy_file_manifest,
    validate_plan as validate_accuracy_plan,
    validate_protocol as validate_accuracy_protocol,
    validate_root_closure as validate_accuracy_root_closure,
)
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    require_file_sha256,
    sha256_bytes,
    sha256_file,
)
from corpus_v4_accuracy_dataset import load_corpus_v4_accuracy_dataset  # noqa: E402


PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-protocol.v2"
PLAN_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-plan.v2"
PANEL_ROW_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-panel-row.v2"
TASK_ROW_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task-row.v2"
LOCK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-execution-lock.v2"
TASK_MANIFEST_SCHEMA = (
    "pcb-gnn.corpus-v4-paired-latency-task-artifact-manifest.v2"
)
PENDING_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-pending-set.v2"

DESIGNATED_TASK_ID = 12
DESIGNATED_SPLIT_SEED = 42
DESIGNATED_INIT_SEED = 42
EXPECTED_LAYOUTS = 306
EXPECTED_FAMILIES = 13
SHA256_RE = re.compile(r"[0-9a-f]{64}")

EXPECTED_INPUT_PATHS = {
    "accuracy_protocol": "protocols/corpus_v4_accuracy_v1.json",
    "accuracy_archive": "results/corpus_v4/accuracy/ARCHIVE_MANIFEST.json",
    "accuracy_accepted_set": (
        "results/corpus_v4/accuracy/resume/round_01/accepted_artifact_set.json"
    ),
    "accuracy_plan": "results/corpus_v4/accuracy/plan/v1/plan.json",
    "accuracy_task_manifest": (
        "results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl"
    ),
    "accuracy_execution_lock": (
        "protocols/corpus_v4_accuracy_execution_lock_v1.json"
    ),
    "evaluation_dataset": (
        "results/corpus_v4/accuracy/plan/v1/evaluation_dataset.jsonl"
    ),
    "accuracy_final_summary": (
        "results/corpus_v4/accuracy/final/job_6905011/summary.json"
    ),
    "accuracy_checkpoint_index": (
        "results/corpus_v4/accuracy/final/job_6905011/checkpoint_index.json"
    ),
    "designated_task_manifest": (
        "results/corpus_v4/accuracy/jobs/job_6904424/task_12/TASK_MANIFEST.json"
    ),
    "designated_task_result": (
        "results/corpus_v4/accuracy/jobs/job_6904424/task_12/result.json"
    ),
    "checkpoint_metadata": (
        "results/corpus_v4/accuracy/jobs/job_6904424/task_12/bundle/metadata.json"
    ),
    "checkpoint_archive": (
        "results/corpus_v4/accuracy/jobs/job_6904424/task_12/bundle/weights_and_norm.npz"
    ),
    "checkpoint_smoke_examples": (
        "results/corpus_v4/accuracy/jobs/job_6904424/task_12/smoke_examples.jsonl"
    ),
    "cps_multifidelity_protocol": "protocols/corpus_v4_cps_multifidelity_v1.json",
}
EXPECTED_INPUT_NAMES = frozenset(EXPECTED_INPUT_PATHS)

PLANNER_SOURCE_NAMES = (
    "code/core/geometry_contract.py",
    "code/core/scientific_artifact.py",
    "code/data/corpus_v4_accuracy_dataset.py",
    "code/experiments/proofs/corpus_v4_accuracy_contract.py",
    "code/experiments/proofs/corpus_v4_latency_contract.py",
    "code/experiments/proofs/plan_corpus_v4_latency.py",
)

# This closure intentionally names post-processing and verification sources as
# well as the task runner.  Lock construction must fail until every execution
# component exists at its final reviewed bytes.
EXECUTION_SOURCE_NAMES = (
    "requirements-proof.txt",
    "protocols/corpus_v4_latency_v1.json",
    "code/core/geometry_contract.py",
    "code/core/pcb_graph.py",
    "code/core/planar_to_graph.py",
    "code/core/scientific_artifact.py",
    "code/core/trace_peec.py",
    "code/data/corpus_v4_accuracy_dataset.py",
    "code/data/verified_geometry_corpus.py",
    "code/env.sh",
    "code/experiments/proofs/build_corpus_v4_latency_execution_lock.py",
    "code/experiments/proofs/corpus_v4_accuracy_contract.py",
    "code/experiments/proofs/corpus_v4_latency_contract.py",
    "code/experiments/proofs/experiments_corpus_v4_latency_task.py",
    "code/experiments/proofs/finalize_corpus_v4_latency.py",
    "code/experiments/proofs/plan_corpus_v4_latency.py",
    "code/experiments/proofs/plan_corpus_v4_latency_resume.py",
    "code/experiments/proofs/run_corpus_v4_accuracy_task.py",
    "code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py",
    "code/inference/corpus_v4_latency_inference.py",
    "code/inference/safe_npz_bundle.py",
    "code/jobs/slurm_job_env.sh",
    "code/jobs/submit_corpus_v4_latency_preflight.sh",
    "code/jobs/submit_corpus_v4_latency.sh",
    "code/jobs/submit_finalize_corpus_v4_latency.sh",
    "code/models/gnn/gnn_baseline.py",
    "code/quality/verify_corpus_v4_latency_archive.py",
    "code/solvers/fasthenry_latency.py",
    "code/solvers/fasthenry_ref.py",
    "code/solvers/fem_corpus_v4_latency.py",
    "code/solvers/fem_capacitance_3d.py",
    "code/solvers/fem_cps_bounded_worker.py",
    "code/solvers/fem_cps_diagnostic_worker.py",
)

SCIENTIFIC_BLAS_ENV_NAMES = (
    "BLIS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
)
SCHEDULER_RECORD_ALLOWLIST = (
    "AllocTRES",
    "ArrayJobId",
    "ArrayTaskId",
    "ArrayTaskThrottle",
    "CPUs/Task",
    "JobId",
    "JobState",
    "MinMemoryNode",
    "NumCPUs",
    "NumTasks",
    "Partition",
    "ReqTRES",
    "TimeLimit",
    "TresPerTask",
)


class LatencyContractError(ValueError):
    """Raised when a latency trust root differs from the frozen design."""


def _exact_json(actual: Any, expected: Any, label: str) -> None:
    try:
        equal = canonical_json_bytes(actual) == canonical_json_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise LatencyContractError(f"{label} is not finite JSON") from exc
    if not equal:
        raise LatencyContractError(f"{label} differs from the frozen design")


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise LatencyContractError(f"{label} is not a lowercase SHA-256")
    return value


def _input_paths(protocol: Mapping[str, Any]) -> dict[str, Path]:
    inputs = protocol.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != EXPECTED_INPUT_NAMES:
        raise LatencyContractError("latency protocol input closure is not exact")
    paths: dict[str, Path] = {}
    for name in sorted(EXPECTED_INPUT_NAMES):
        record = inputs[name]
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise LatencyContractError(f"input pin is malformed: {name}")
        if record.get("path") != EXPECTED_INPUT_PATHS[name]:
            raise LatencyContractError(f"input path is not canonical: {name}")
        _require_sha256(record.get("sha256"), f"input {name} SHA-256")
        path = resolve_repo_path(record["path"], f"latency input {name}")
        if path.is_symlink() or not path.is_file():
            raise LatencyContractError(f"input must be a regular file: {name}")
        require_file_sha256(path, record["sha256"], f"latency input {name}")
        paths[name] = path
    return paths


def resolve_protocol_inputs(protocol: Mapping[str, Any]) -> dict[str, Path]:
    """Resolve and authenticate every protocol input in the frozen closure."""
    return _input_paths(protocol)


def validate_protocol(
    path: Path, expected_sha256: str | None = None
) -> tuple[dict[str, Any], str]:
    """Validate the exact scientific design and all pinned upstream files."""
    if path.is_symlink() or not path.is_file():
        raise LatencyContractError("latency protocol must be a regular file")
    if path.resolve() != (ROOT / "protocols/corpus_v4_latency_v1.json").resolve():
        raise LatencyContractError("latency protocol is not at its canonical path")
    if expected_sha256 is not None:
        require_file_sha256(path, expected_sha256, "latency protocol")
    protocol = load_json(path)
    expected_top_level = {
        "checkpoint",
        "forbidden_actions",
        "gnn_timing",
        "inputs",
        "panel",
        "protocol_name",
        "resources",
        "runtime",
        "schema",
        "solver_workflow",
        "statistics",
    }
    if set(protocol) != expected_top_level:
        raise LatencyContractError("latency protocol top-level fields are not exact")
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("protocol_name")
        != "corpus-v4-current-checkpoint-paired-latency-v1"
    ):
        raise LatencyContractError("unexpected latency protocol identity")
    _input_paths(protocol)
    _exact_json(
        protocol.get("checkpoint"),
        {
            "accepted_before_latency_measurement": True,
            "bundle_format": "NumPy NPZ; allow_pickle=False",
            "bundle_schema": "pcb-gnn.safe-npz-bundle.v1",
            "designated_task_id": DESIGNATED_TASK_ID,
            "init_seed": DESIGNATED_INIT_SEED,
            "maximum_archive_bytes": 67_108_864,
            "maximum_uncompressed_bytes": 134_217_728,
            "smoke_examples": 5,
            "split_seed": DESIGNATED_SPLIT_SEED,
        },
        "latency checkpoint",
    )
    _exact_json(
        protocol.get("panel"),
        {
            "family_key": "swap-closed unordered turn-count pair",
            "layout_order": "ascending frozen layout_id within split-42 test membership",
            "n_designs": EXPECTED_LAYOUTS,
            "n_families": EXPECTED_FAMILIES,
            "scope": "all layouts in the frozen split-42 family-held-out test partition",
            "selection_uses_labels_predictions_or_timings": False,
            "split_seed": DESIGNATED_SPLIT_SEED,
        },
        "latency panel",
    )
    _exact_json(
        protocol.get("solver_workflow"),
        {
            "boundary_end": "all four target values parsed and materialized as float64",
            "boundary_start": "the same canonical UTF-8 JSON bytes resident in memory",
            "capacitance": {
                "fidelity_id": "cps_fem_r3_p16",
                "linear_solver": "pyamg_smoothed_aggregation_cg",
                "pad_mm": 16.0,
                "refine": 3,
                "target": "Cps_pF",
                "timeout_s": 1800,
            },
            "comparison_scope": (
                "sequential FastHenry-plus-FEM-R3P16 workflow used to obtain all "
                "four targets"
            ),
            "execution_order": ["FastHenry", "FEM-R3P16"],
            "inductance": {
                "binary_sha256": (
                    "ad5c8825d36523b62844df1851c816ae9b967ef12614887eb49c158af3b03056"
                ),
                "fidelity_id": "fasthenry_100khz_active_leg",
                "frequency_hz": 100_000.0,
                "targets": ["L_pri_nH", "L_sec_nH", "L_mut_nH"],
                "timeout_s": 300,
            },
            "reference_agreement_max_relative_error": 0.0001,
            "repetitions_per_design": 1,
            "sequential": True,
            "solver_result_cache_reuse": False,
            "timer": "time.perf_counter_ns",
        },
        "latency solver workflow",
    )
    _exact_json(
        protocol.get("gnn_timing"),
        {
            "batch_size": 1,
            "boundary_end": "four inverse-transformed target values materialized as float64",
            "boundary_name": "warm-loaded in-memory raw-JSON-record-to-four-output latency",
            "boundary_start": "canonical UTF-8 JSON bytes resident in memory",
            "cpu_only": True,
            "include": [
                "strict JSON parsing",
                "geometry validation",
                "graph construction",
                "feature normalization",
                "batch-one collation",
                "model forward pass",
                "inverse target transformation",
                "four-value output materialization",
            ],
            "measured_repetitions": 200,
            "measurement_blocks": [
                "100 repetitions before the solver workflow",
                "100 repetitions after the solver workflow",
            ],
            "measured_repetitions_per_block": 100,
            "model_load_excluded_and_reported_separately": True,
            "python_startup_excluded": True,
            "raw_record_serialization": (
                "canonical JSON; UTF-8; sorted keys; compact separators; finite values only"
            ),
            "storage_io_excluded": True,
            "timer": "time.perf_counter_ns",
            "torch_interop_threads": 1,
            "torch_intraop_threads": 1,
            "warmup_repetitions": 50,
        },
        "latency GNN timing",
    )
    _exact_json(
        protocol.get("resources"),
        {
            "finalizer": {
                "allocated_cpus_may_exceed_request": True,
                "cpus_per_task": 2,
                "memory_gib": 8,
                "partition": "nextgen",
                "scientific_threads": 2,
                "time_limit": "00:20:00",
            },
            "full_array": {
                "allocated_cpus_may_exceed_request": True,
                "array": "0-305%8",
                "cpus_per_task": 25,
                "memory_gib": 48,
                "partition": "nextgen",
                "scientific_threads": {"blas": 1, "gmsh": 25, "torch": 1},
                "time_limit": "02:00:00",
            },
            "preflight": {
                "allocated_cpus_may_exceed_request": True,
                "array": "0,152,305%1",
                "cpus_per_task": 25,
                "excluded_from_final_statistics": True,
                "memory_gib": 48,
                "partition": "nextgen",
                "task_ids": [0, 152, 305],
                "time_limit": "02:00:00",
            },
        },
        "latency resources",
    )
    runtime = protocol.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {
        "packages",
        "python",
        "thread_environment",
    }:
        raise LatencyContractError("latency runtime fields are not exact")
    if runtime.get("python") != "3.9.21":
        raise LatencyContractError("latency Python runtime is not frozen")
    expected_packages = {
        "gmsh": "4.15.2",
        "meshio": "5.3.5",
        "numpy": "2.0.2",
        "pyamg": "5.3.0",
        "scikit-fem": "11.0.0",
        "scipy": "1.13.1",
        "torch": "2.8.0",
    }
    _exact_json(runtime.get("packages"), expected_packages, "latency packages")
    _exact_json(
        runtime.get("thread_environment"),
        {
            "BLIS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "PCB_GNN_GMSH_THREADS": "25",
        },
        "latency thread policy",
    )
    _exact_json(
        protocol.get("statistics"),
        {
            "bootstrap": {
                "cluster_unit": "held-out geometry family",
                "label": (
                    "family-cluster bootstrap sensitivity interval on the evaluated "
                    "split and CPU-node class"
                ),
                "percentiles": [2.5, 97.5],
                "quantile_method": "Hyndman-Fan type 7",
                "resamples": 10_000,
                "seed": 20_260_820,
                "semantics": (
                    "descriptive sensitivity interval, not a population or hardware "
                    "confidence interval"
                ),
            },
            "design_gnn_latency": "median of 200 measured repetitions",
            "design_solver_latency": (
                "one sequential FastHenry-plus-FEM-R3P16 observation"
            ),
            "primary_estimand": (
                "median over 306 designs of paired solver latency divided by "
                "design-median GNN latency"
            ),
            "report_component_medians_descriptively": True,
            "report_every_design_ratio": True,
        },
        "latency statistics",
    )
    forbidden = protocol.get("forbidden_actions")
    expected_forbidden = {
        "aggregate_median_ratio_as_headline",
        "batching_across_designs",
        "capacitance_only_or_inductance_only_generalization",
        "fastest_attempt_selection",
        "hardware_or_population_confidence_interval_wording",
        "historical_4300x_or_670x_as_current_evidence",
        "layout_replacement_after_failure",
        "login_node_solver_execution",
        "outcome_or_timing_based_filtering",
        "solver_result_cache_reuse",
        "timeout_or_resource_change_on_retry",
    }
    if (
        not isinstance(forbidden, dict)
        or set(forbidden) != expected_forbidden
        or any(value is not True for value in forbidden.values())
    ):
        raise LatencyContractError("latency forbidden-action gates are not exact")
    return protocol, sha256_file(path)


def validate_upstream_closure(
    protocol: Mapping[str, Any], paths: Mapping[str, Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Close the latency roots to accepted accuracy task 12 without metrics."""
    canonical_paths = resolve_protocol_inputs(protocol)
    if set(paths) != EXPECTED_INPUT_NAMES or any(
        Path(paths[name]).resolve() != canonical_paths[name].resolve()
        for name in EXPECTED_INPUT_NAMES
    ):
        raise LatencyContractError("latency upstream path closure is not canonical")
    accuracy_protocol, accuracy_protocol_sha = validate_accuracy_protocol(
        paths["accuracy_protocol"], protocol["inputs"]["accuracy_protocol"]["sha256"]
    )
    accuracy_plan, task_rows, accuracy_plan_sha, accuracy_tasks_sha = (
        validate_accuracy_plan(
            paths["accuracy_plan"],
            paths["accuracy_task_manifest"],
            expected_plan_sha256=protocol["inputs"]["accuracy_plan"]["sha256"],
            expected_manifest_sha256=protocol["inputs"]["accuracy_task_manifest"]["sha256"],
        )
    )
    accuracy_lock, accuracy_lock_sha = validate_accuracy_execution_lock(
        paths["accuracy_execution_lock"],
        protocol["inputs"]["accuracy_execution_lock"]["sha256"],
    )
    validate_accuracy_root_closure(
        protocol=accuracy_protocol,
        protocol_sha256=accuracy_protocol_sha,
        plan=accuracy_plan,
        plan_path=paths["accuracy_plan"],
        task_rows=task_rows,
        task_manifest_sha256=accuracy_tasks_sha,
        lock=accuracy_lock,
        lock_sha256=accuracy_lock_sha,
    )
    evaluation_pin = accuracy_plan["artifact_sha256"]["evaluation_dataset.jsonl"]
    if evaluation_pin != protocol["inputs"]["evaluation_dataset"]["sha256"]:
        raise LatencyContractError("evaluation dataset differs from the accuracy plan")

    archive = load_json(paths["accuracy_archive"])
    if (
        archive.get("schema") != "pcb-gnn.corpus-v4-accuracy-archive.v1"
        or archive.get("bindings")
        != {
            "accepted_set_sha256": protocol["inputs"]["accuracy_accepted_set"]["sha256"],
            "execution_lock_sha256": accuracy_lock_sha,
            "expected_source_git_head": "f3074d2cb6082b6740452e9c8d0560d0d11eeb61",
            "plan_sha256": accuracy_plan_sha,
            "protocol_sha256": accuracy_protocol_sha,
            "task_manifest_sha256": accuracy_tasks_sha,
        }
    ):
        raise LatencyContractError("accuracy archive root bindings are not exact")
    verified = archive.get("verified_analysis_files_sha256", {})
    if (
        verified.get("summary.json")
        != protocol["inputs"]["accuracy_final_summary"]["sha256"]
        or verified.get("checkpoint_index.json")
        != protocol["inputs"]["accuracy_checkpoint_index"]["sha256"]
    ):
        raise LatencyContractError("accuracy archive does not bind summary/checkpoint index")

    accepted = load_json(paths["accuracy_accepted_set"])
    entries = accepted.get("entries")
    if (
        accepted.get("schema") != "pcb-gnn.corpus-v4-accuracy-accepted-set.v1"
        or accepted.get("n_accepted") != 25
        or accepted.get("n_expected") != 25
        or not isinstance(entries, list)
        or len(entries) != 25
    ):
        raise LatencyContractError("accuracy accepted set is not complete")
    accepted_entry = entries[DESIGNATED_TASK_ID]
    if (
        accepted_entry.get("task_id") != DESIGNATED_TASK_ID
        or accepted_entry.get("manifest_path")
        != protocol["inputs"]["designated_task_manifest"]["path"]
        or accepted_entry.get("manifest_sha256")
        != protocol["inputs"]["designated_task_manifest"]["sha256"]
        or accepted_entry.get("scheduler_completion", {}).get("State") != "COMPLETED"
        or accepted_entry.get("scheduler_completion", {}).get("ExitCode") != "0:0"
    ):
        raise LatencyContractError("designated accuracy task lacks accepted evidence")

    manifest = validate_accuracy_file_manifest(paths["designated_task_manifest"])
    required_task_files = {
        "bundle/metadata.json": "checkpoint_metadata",
        "bundle/weights_and_norm.npz": "checkpoint_archive",
        "result.json": "designated_task_result",
        "smoke_examples.jsonl": "checkpoint_smoke_examples",
    }
    for artifact_name, input_name in required_task_files.items():
        if manifest["files_sha256"].get(artifact_name) != protocol["inputs"][input_name]["sha256"]:
            raise LatencyContractError(f"designated task manifest does not bind {artifact_name}")

    result = load_json(paths["designated_task_result"])
    expected_identity = {
        "designated_downstream_checkpoint": True,
        "init_seed": DESIGNATED_INIT_SEED,
        "split_seed": DESIGNATED_SPLIT_SEED,
        "task_id": DESIGNATED_TASK_ID,
    }
    if (
        result.get("schema") != "pcb-gnn.corpus-v4-accuracy-task-result.v1"
        or result.get("task") != expected_identity
        or result.get("integrity") != {"passed": True}
        or result.get("evaluation")
        != {
            "test_or_r4_used_for_normalization_optimization_or_acceptance": False,
            "test_predictions_emitted": False,
        }
        or result.get("checkpoint")
        != {
            "archive_sha256": protocol["inputs"]["checkpoint_archive"]["sha256"],
            "metadata_sha256": protocol["inputs"]["checkpoint_metadata"]["sha256"],
            "smoke_examples_sha256": protocol["inputs"]["checkpoint_smoke_examples"]["sha256"],
        }
    ):
        raise LatencyContractError("designated task identity/checkpoint is not exact")

    summary = load_json(paths["accuracy_final_summary"])
    checkpoint_identity = summary.get("designated_downstream_checkpoint")
    if (
        summary.get("schema") != "pcb-gnn.corpus-v4-accuracy-final.v1"
        or not isinstance(checkpoint_identity, dict)
        or checkpoint_identity.get("task_id") != DESIGNATED_TASK_ID
        or checkpoint_identity.get("split_seed") != DESIGNATED_SPLIT_SEED
        or checkpoint_identity.get("init_seed") != DESIGNATED_INIT_SEED
        or checkpoint_identity.get("archive_sha256")
        != protocol["inputs"]["checkpoint_archive"]["sha256"]
        or checkpoint_identity.get("metadata_sha256")
        != protocol["inputs"]["checkpoint_metadata"]["sha256"]
        or checkpoint_identity.get("smoke_examples_sha256")
        != protocol["inputs"]["checkpoint_smoke_examples"]["sha256"]
    ):
        raise LatencyContractError("accuracy summary does not identify checkpoint task 12")

    checkpoint_index = load_json(paths["accuracy_checkpoint_index"])
    checkpoint_entries = checkpoint_index.get("entries")
    if (
        checkpoint_index.get("schema")
        != "pcb-gnn.corpus-v4-accuracy-checkpoint-index.v1"
        or not isinstance(checkpoint_entries, list)
        or len(checkpoint_entries) != 25
        or checkpoint_entries[DESIGNATED_TASK_ID] != checkpoint_identity
    ):
        raise LatencyContractError("checkpoint index differs from the final summary")

    metadata = load_json(paths["checkpoint_metadata"])
    payload = metadata.get("payload")
    if (
        metadata.get("schema") != protocol["checkpoint"]["bundle_schema"]
        or metadata.get("archive", {}).get("sha256")
        != protocol["inputs"]["checkpoint_archive"]["sha256"]
        or not isinstance(payload, dict)
        or payload.get("task_id") != DESIGNATED_TASK_ID
        or payload.get("split_seed") != DESIGNATED_SPLIT_SEED
        or payload.get("init_seed") != DESIGNATED_INIT_SEED
        or payload.get("designated_downstream_checkpoint") is not True
    ):
        raise LatencyContractError("safe checkpoint metadata identity is not exact")

    cps_protocol = load_json(paths["cps_multifidelity_protocol"])
    if (
        cps_protocol.get("schema") != "pcb-gnn.cps-multifidelity-protocol.v1"
        or cps_protocol.get("fidelities", {}).get("cps_fem_r3_p16")
        != {"coverage": 1500, "pad_mm": 16.0, "refine": 3, "role": "bulk_low_fidelity"}
        or cps_protocol.get("linear_solver", {}).get("reported")
        != "pyamg_smoothed_aggregation_cg"
    ):
        raise LatencyContractError("upstream FEM-R3P16 solver contract is not exact")

    task_row = task_rows[DESIGNATED_TASK_ID]
    if (
        task_row.get("task_id") != DESIGNATED_TASK_ID
        or task_row.get("split_seed") != DESIGNATED_SPLIT_SEED
        or task_row.get("init_seed") != DESIGNATED_INIT_SEED
        or task_row.get("designated_downstream_checkpoint") is not True
        or task_row.get("partition_counts", {}).get("test") != EXPECTED_LAYOUTS
        or task_row.get("partition_family_counts", {}).get("test") != EXPECTED_FAMILIES
    ):
        raise LatencyContractError("designated test partition is not split42/task12")
    return task_row, checkpoint_identity


def panel_row_sha256(row: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(row)))


def validate_plan(
    plan_path: Path,
    task_manifest_path: Path,
    panel_records_path: Path,
    *,
    expected_plan_sha256: str | None = None,
    expected_task_manifest_sha256: str | None = None,
    expected_panel_records_sha256: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str, str, str]:
    for path, label in (
        (plan_path, "latency plan"),
        (task_manifest_path, "latency task manifest"),
        (panel_records_path, "latency panel records"),
    ):
        if path.is_symlink() or not path.is_file():
            raise LatencyContractError(f"{label} must be a regular file")
    if expected_plan_sha256 is not None:
        require_file_sha256(plan_path, expected_plan_sha256, "latency plan")
    if expected_task_manifest_sha256 is not None:
        require_file_sha256(task_manifest_path, expected_task_manifest_sha256, "task manifest")
    if expected_panel_records_sha256 is not None:
        require_file_sha256(panel_records_path, expected_panel_records_sha256, "panel records")
    plan = load_json(plan_path)
    tasks = load_jsonl(task_manifest_path)
    panel = load_jsonl(panel_records_path)
    plan_sha = sha256_file(plan_path)
    task_sha = sha256_file(task_manifest_path)
    panel_sha = sha256_file(panel_records_path)
    if set(plan) != {
        "artifact_sha256",
        "checkpoint",
        "counts",
        "input_sha256",
        "panel",
        "planner_source_sha256",
        "protocol_sha256",
        "schema",
        "scientific_scope",
    } or plan.get("schema") != PLAN_SCHEMA:
        raise LatencyContractError("latency plan schema is not exact")
    if plan.get("artifact_sha256") != {
        "panel_records.jsonl": panel_sha,
        "task_manifest.jsonl": task_sha,
    }:
        raise LatencyContractError("latency plan artifact hashes are not exact")
    if len(tasks) != EXPECTED_LAYOUTS or len(panel) != EXPECTED_LAYOUTS:
        raise LatencyContractError("latency plan must contain exactly 306 tasks/records")
    layout_ids: list[int] = []
    family_counts: Counter[str] = Counter()
    for task_id, (task, record) in enumerate(zip(tasks, panel)):
        expected_task_fields = {
            "family_id",
            "geometry_sha256",
            "layout_id",
            "panel_record_sha256",
            "protocol_sha256",
            "schema",
            "task_id",
        }
        expected_record_fields = {
            "family_id",
            "geometry_sha256",
            "layout",
            "layout_id",
            "schema",
        }
        if set(task) != expected_task_fields or set(record) != expected_record_fields:
            raise LatencyContractError(f"latency task/record {task_id} fields are not exact")
        if (
            task.get("schema") != TASK_ROW_SCHEMA
            or record.get("schema") != PANEL_ROW_SCHEMA
            or task.get("task_id") != task_id
            or task.get("layout_id") != record.get("layout_id")
            or task.get("family_id") != record.get("family_id")
            or task.get("geometry_sha256") != record.get("geometry_sha256")
            or task.get("panel_record_sha256") != panel_row_sha256(record)
            or task.get("protocol_sha256") != plan.get("protocol_sha256")
        ):
            raise LatencyContractError(f"latency task/record {task_id} identity mismatch")
        layout_id = require_plain_int(task["layout_id"], "latency layout ID")
        _require_sha256(task["geometry_sha256"], "latency geometry SHA-256")
        if not isinstance(task["family_id"], str) or not task["family_id"]:
            raise LatencyContractError("latency family ID is invalid")
        layout_ids.append(layout_id)
        family_counts[task["family_id"]] += 1
    if layout_ids != sorted(set(layout_ids)) or len(family_counts) != EXPECTED_FAMILIES:
        raise LatencyContractError("latency panel order, uniqueness, or family count differs")
    if plan.get("counts") != {
        "families": EXPECTED_FAMILIES,
        "layouts": EXPECTED_LAYOUTS,
        "tasks": EXPECTED_LAYOUTS,
    }:
        raise LatencyContractError("latency plan counts are not exact")
    panel_summary = plan.get("panel", {})
    if (
        panel_summary.get("family_layout_counts")
        != {name: family_counts[name] for name in sorted(family_counts)}
        or panel_summary.get("layout_ids_sha256")
        != sha256_bytes(canonical_json_bytes(layout_ids))
        or panel_summary.get("task_order") != "ascending layout_id"
    ):
        raise LatencyContractError("latency panel summary differs from task rows")
    return plan, tasks, panel, plan_sha, task_sha, panel_sha


def validate_root_closure(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    plan: Mapping[str, Any],
    plan_path: Path,
    tasks: Sequence[Mapping[str, Any]],
    panel_records: Sequence[Mapping[str, Any]],
    task_manifest_sha256: str,
    panel_records_sha256: str,
) -> None:
    if plan.get("protocol_sha256") != protocol_sha256:
        raise LatencyContractError("latency plan does not bind the protocol")
    expected_inputs = {
        name: protocol["inputs"][name]["sha256"] for name in sorted(EXPECTED_INPUT_NAMES)
    }
    if plan.get("input_sha256") != expected_inputs:
        raise LatencyContractError("latency plan input roots differ from the protocol")
    if plan.get("artifact_sha256") != {
        "panel_records.jsonl": panel_records_sha256,
        "task_manifest.jsonl": task_manifest_sha256,
    }:
        raise LatencyContractError("latency plan artifact closure is inconsistent")
    expected_checkpoint = {
        "archive_sha256": protocol["inputs"]["checkpoint_archive"]["sha256"],
        "init_seed": DESIGNATED_INIT_SEED,
        "metadata_sha256": protocol["inputs"]["checkpoint_metadata"]["sha256"],
        "smoke_examples_sha256": protocol["inputs"]["checkpoint_smoke_examples"][
            "sha256"
        ],
        "split_seed": DESIGNATED_SPLIT_SEED,
        "task_id": DESIGNATED_TASK_ID,
    }
    if plan.get("checkpoint") != expected_checkpoint:
        raise LatencyContractError("latency plan checkpoint identity is not exact")
    if plan.get("scientific_scope") != {
        "all_designated_test_layouts_included": True,
        "labels_predictions_or_timings_used_for_selection": False,
        "selection_seed": None,
    }:
        raise LatencyContractError("latency plan scientific scope is not exact")
    planner_sources = plan.get("planner_source_sha256")
    if not isinstance(planner_sources, dict) or set(planner_sources) != set(PLANNER_SOURCE_NAMES):
        raise LatencyContractError("latency planner source closure is not exact")
    for name in PLANNER_SOURCE_NAMES:
        digest = _require_sha256(planner_sources[name], f"planner source {name}")
        require_file_sha256(resolve_repo_path(name, "latency planner source"), digest, name)
    # The plan may only describe upstream identities and the frozen panel.  No
    # timing, metric, prediction, or accuracy-outcome vocabulary is admitted.
    forbidden_tokens = re.compile(
        r"(^|_)(latency|timing|prediction|accuracy_metric|speedup|wall_s|mape)(_|$)",
        re.IGNORECASE,
    )
    for task in tasks:
        if any(forbidden_tokens.search(name) for name in task):
            raise LatencyContractError("task rows contain forbidden outcome/timing fields")
    for record in panel_records:
        if any(forbidden_tokens.search(name) for name in record):
            raise LatencyContractError("panel records contain forbidden outcome/timing fields")

    # Reconstruct the predesignated membership independently.  This makes an
    # apparently well-formed but substituted 306-row panel fail before a lock
    # can be emitted.
    paths = resolve_protocol_inputs(protocol)
    designated_task, _ = validate_upstream_closure(protocol, paths)
    dataset = load_corpus_v4_accuracy_dataset(
        root=ROOT,
        protocol_path=paths["accuracy_protocol"],
    )
    expected_ids = designated_task["partitions"]["test"]["layout_ids"]
    expected_families = designated_task["partitions"]["test"]["family_ids"]
    by_layout_id = dataset.sample_by_layout_id()
    if [task["layout_id"] for task in tasks] != expected_ids:
        raise LatencyContractError("latency tasks differ from task-12 test membership")
    if set(record["family_id"] for record in panel_records) != set(expected_families):
        raise LatencyContractError("latency panel differs from task-12 test families")
    for record in panel_records:
        sample = by_layout_id[record["layout_id"]]
        if (
            record["geometry_sha256"] != sample.geometry_sha256
            or record["family_id"] != sample.family_id
            or canonical_json_bytes(record["layout"])
            != canonical_json_bytes(dict(sample.layout))
        ):
            raise LatencyContractError(
                f"latency panel geometry differs at layout {sample.layout_id}"
            )


def build_file_manifest(directory: Path, names: Iterable[str]) -> dict[str, Any]:
    """Build an exact hash manifest for one latency-task artifact directory."""
    records: dict[str, str] = {}
    for name in sorted(set(names)):
        relative = require_repo_relative_path(name, "latency task artifact")
        artifact = resolve_descendant_path(
            directory, relative, "latency task artifact"
        )
        if artifact.is_symlink() or not artifact.is_file():
            raise FileNotFoundError(artifact)
        records[relative] = sha256_file(artifact)
    if not records:
        raise LatencyContractError("latency task manifest cannot be empty")
    return {"files_sha256": records, "schema": TASK_MANIFEST_SCHEMA}


def validate_file_manifest(path: Path) -> dict[str, Any]:
    """Validate every byte referenced by one latency task manifest."""
    if path.is_symlink() or not path.is_file():
        raise LatencyContractError(
            "latency task manifest must be a regular non-symlink file"
        )
    manifest = load_json(path)
    if set(manifest) != {"files_sha256", "schema"} or manifest.get(
        "schema"
    ) != TASK_MANIFEST_SCHEMA:
        raise LatencyContractError("unexpected latency task-manifest schema")
    records = manifest.get("files_sha256")
    if not isinstance(records, dict) or not records:
        raise LatencyContractError("latency task manifest has no files")
    for name, digest in records.items():
        relative = require_repo_relative_path(name, "latency task artifact")
        _require_sha256(digest, f"latency task artifact {relative}")
        artifact = resolve_descendant_path(
            path.parent, relative, "latency task artifact"
        )
        if artifact.is_symlink() or not artifact.is_file():
            raise LatencyContractError(
                f"latency task artifact is not a regular file: {relative}"
            )
        require_file_sha256(artifact, digest, relative)
    return manifest


def validate_pending_set(
    path: Path,
    expected_sha256: str,
    bindings: Mapping[str, str],
) -> tuple[dict[str, Any], list[int], str]:
    """Validate an externally pinned allowlist for exact task retries."""
    binding_names = {
        "execution_lock_sha256",
        "panel_records_sha256",
        "plan_sha256",
        "protocol_sha256",
        "task_manifest_sha256",
    }
    if set(bindings) != binding_names:
        raise LatencyContractError("latency pending-set bindings are not exact")
    for name in sorted(binding_names):
        _require_sha256(bindings[name], f"latency pending binding {name}")
    _require_sha256(expected_sha256, "latency pending-set external SHA-256")
    if path.is_symlink() or not path.is_file():
        raise LatencyContractError("latency pending set must be a regular file")
    require_file_sha256(path, expected_sha256, "latency pending set")
    payload = load_json(path)
    if set(payload) != binding_names | {
        "n_pending",
        "pending_task_ids",
        "schema",
    } or payload.get("schema") != PENDING_SCHEMA:
        raise LatencyContractError("latency pending-set fields are not exact")
    if any(payload.get(name) != bindings[name] for name in binding_names):
        raise LatencyContractError("latency pending set does not bind frozen roots")
    pending = payload.get("pending_task_ids")
    if (
        not isinstance(pending, list)
        or not pending
        or any(type(task_id) is not int for task_id in pending)
        or pending != sorted(set(pending))
        or any(task_id < 0 or task_id >= EXPECTED_LAYOUTS for task_id in pending)
        or payload.get("n_pending") != len(pending)
    ):
        raise LatencyContractError("latency pending task IDs are not canonical")
    return payload, pending, sha256_file(path)


def _parse_tres(value: Any) -> dict[str, str]:
    parsed: dict[str, str] = {}
    items = str(value or "").split(",")
    for item in items:
        key, separator, member = item.partition("=")
        if not separator or not key or not member or key in parsed:
            raise LatencyContractError("scheduler TRES contains a malformed field")
        parsed[key] = member
    return parsed


def _parse_scontrol_records(output: str) -> list[dict[str, str]]:
    return [
        {
            token.split("=", 1)[0]: token.split("=", 1)[1]
            for token in line.split()
            if "=" in token
        }
        for line in output.splitlines()
        if line.strip()
    ]


def _environment_int(name: str) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError) as exc:
        raise SystemExit(f"invalid or missing scheduler integer: {name}") from exc


def validate_slurm_allocation(
    protocol: Mapping[str, Any],
    *,
    stage: str,
    allowed_task_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Authenticate the active preflight, full-array, or finalizer component."""
    if stage not in {"preflight", "full_array", "finalizer"}:
        raise LatencyContractError("unknown latency scheduler stage")
    is_array = stage != "finalizer"
    required = [
        "SLURM_JOB_ID",
        "SLURM_CPUS_PER_TASK",
        "SLURM_MEM_PER_NODE",
        "SLURM_JOB_PARTITION",
        *SCIENTIFIC_BLAS_ENV_NAMES,
    ]
    if is_array:
        required.extend(
            [
                "PCB_GNN_GMSH_THREADS",
                "SLURM_ARRAY_JOB_ID",
                "SLURM_ARRAY_TASK_ID",
                "SLURM_ARRAY_TASK_MIN",
                "SLURM_ARRAY_TASK_MAX",
                "SLURM_ARRAY_TASK_COUNT",
            ]
        )
    missing = [name for name in required if os.environ.get(name) is None]
    if missing:
        raise SystemExit(f"SLURM {stage} environment is incomplete: {missing}")

    profile = protocol["resources"][stage]
    task_id = (
        _environment_int("SLURM_ARRAY_TASK_ID") if is_array else None
    )
    component = (
        f"{os.environ['SLURM_ARRAY_JOB_ID']}_{task_id}"
        if is_array
        else os.environ["SLURM_JOB_ID"]
    )
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", component],
        capture_output=True,
        check=False,
        text=True,
    )
    records = _parse_scontrol_records(query.stdout)
    matches = [
        record
        for record in records
        if record.get("JobId") == os.environ["SLURM_JOB_ID"]
    ]
    if query.returncode != 0 or len(matches) != 1:
        raise SystemExit("active SLURM latency component is missing or ambiguous")
    fields = matches[0]

    try:
        requested_cpu = require_plain_int(
            profile.get("cpus_per_task"), "latency cpus_per_task", minimum=1
        )
        requested_mem = require_plain_int(
            profile.get("memory_gib"), "latency memory_gib", minimum=1
        )
        requested = _parse_tres(fields.get("ReqTRES"))
        per_task = _parse_tres(fields.get("TresPerTask"))
        allocated = _parse_tres(fields.get("AllocTRES"))
        allocated_cpu = int(allocated.get("cpu", "0"))
        environment_cpu = _environment_int("SLURM_CPUS_PER_TASK")
        environment_mem = _environment_int("SLURM_MEM_PER_NODE")
        cpu_valid = (
            allocated_cpu >= requested_cpu
            if profile.get("allocated_cpus_may_exceed_request") is True
            else allocated_cpu == requested_cpu
        )
        expected_blas_threads = 2 if stage == "finalizer" else 1
        valid = (
            fields.get("JobState") in {"RUNNING", "COMPLETING"}
            and fields.get("Partition")
            == profile["partition"]
            == os.environ["SLURM_JOB_PARTITION"]
            and fields.get("TimeLimit") == profile["time_limit"]
            and environment_cpu == allocated_cpu
            and cpu_valid
            and environment_mem == requested_mem * 1024
            and int(fields.get("NumCPUs", "0")) == allocated_cpu
            and int(fields.get("NumTasks", "0")) == 1
            and int(fields.get("CPUs/Task", "0")) == allocated_cpu
            and requested.get("cpu") == str(requested_cpu)
            and requested.get("mem") == f"{requested_mem}G"
            and per_task.get("cpu") == str(requested_cpu)
            and allocated.get("mem") == f"{requested_mem}G"
            and fields.get("MinMemoryNode") == f"{requested_mem}G"
            and all(
                os.environ[name] == str(expected_blas_threads)
                for name in SCIENTIFIC_BLAS_ENV_NAMES
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("malformed active SLURM latency resource record") from exc

    if is_array:
        if stage == "preflight":
            canonical_allowed = list(protocol["resources"]["preflight"]["task_ids"])
            if allowed_task_ids is not None and list(allowed_task_ids) != canonical_allowed:
                raise SystemExit("preflight allowlist differs from the frozen task IDs")
            throttle = 1
        else:
            canonical_allowed = (
                list(range(EXPECTED_LAYOUTS))
                if allowed_task_ids is None
                else list(allowed_task_ids)
            )
            throttle = 8
        allowed = sorted(set(canonical_allowed))
        valid = valid and (
            allowed == canonical_allowed
            and bool(allowed)
            and all(type(value) is int and 0 <= value < EXPECTED_LAYOUTS for value in allowed)
            and task_id in allowed
            and fields.get("ArrayJobId") == os.environ["SLURM_ARRAY_JOB_ID"]
            and fields.get("ArrayTaskId") == str(task_id)
            and int(fields.get("ArrayTaskThrottle", "-1")) == throttle
            and _environment_int("SLURM_ARRAY_TASK_MIN") == allowed[0]
            and _environment_int("SLURM_ARRAY_TASK_MAX") == allowed[-1]
            and _environment_int("SLURM_ARRAY_TASK_COUNT") == len(allowed)
            and os.environ["PCB_GNN_GMSH_THREADS"] == "25"
        )
    elif allowed_task_ids is not None:
        raise LatencyContractError("finalizer cannot accept an array-task allowlist")

    if not valid:
        raise SystemExit(f"SLURM allocation differs from frozen {stage} resources")
    return {
        "allocated_cpus_per_task": allocated_cpu,
        "array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "array_task_id": task_id,
        "environment_cpus_per_task": environment_cpu,
        "job_id": os.environ["SLURM_JOB_ID"],
        "requested_cpus_per_task": requested_cpu,
        "requested_memory_gib": requested_mem,
        "scheduler_record": {
            name: fields[name]
            for name in SCHEDULER_RECORD_ALLOWLIST
            if name in fields
        },
        "scientific_blas_threads": expected_blas_threads,
        "stage": stage,
    }


def validate_execution_lock(
    path: Path,
    expected_sha256: str,
    *,
    protocol_sha256: str,
    plan_sha256: str,
    task_manifest_sha256: str,
    panel_records_sha256: str,
) -> tuple[dict[str, Any], str]:
    """Validate lock bytes, all roots, and every claim-bearing source file."""
    _require_sha256(expected_sha256, "latency execution-lock external SHA-256")
    if path.is_symlink() or not path.is_file():
        raise LatencyContractError("latency execution lock must be a regular file")
    require_file_sha256(path, expected_sha256, "latency execution lock")
    lock = load_json(path)
    if set(lock) != {
        "panel_records_sha256",
        "plan_sha256",
        "protocol_sha256",
        "schema",
        "source_sha256",
        "task_manifest_sha256",
    } or lock.get("schema") != LOCK_SCHEMA:
        raise LatencyContractError("unexpected latency execution-lock schema")
    expected_roots = {
        "panel_records_sha256": panel_records_sha256,
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "task_manifest_sha256": task_manifest_sha256,
    }
    for name, expected in expected_roots.items():
        _require_sha256(expected, f"latency external root {name}")
        if lock.get(name) != expected:
            raise LatencyContractError(f"latency execution lock does not bind {name}")
    sources = lock.get("source_sha256")
    if not isinstance(sources, dict) or set(sources) != set(EXECUTION_SOURCE_NAMES):
        raise LatencyContractError("latency execution source closure is not exact")
    for name in EXECUTION_SOURCE_NAMES:
        digest = _require_sha256(sources[name], f"latency execution source {name}")
        require_file_sha256(resolve_repo_path(name, "latency execution source"), digest, name)
    return lock, sha256_file(path)


def write_execution_lock(
    output: Path,
    *,
    protocol_path: Path,
    plan_path: Path,
    task_manifest_path: Path,
    panel_records_path: Path,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    protocol, protocol_sha = validate_protocol(protocol_path)
    validate_upstream_closure(protocol, resolve_protocol_inputs(protocol))
    plan, tasks, panel, plan_sha, task_sha, panel_sha = validate_plan(
        plan_path, task_manifest_path, panel_records_path
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=plan_path,
        tasks=tasks,
        panel_records=panel,
        task_manifest_sha256=task_sha,
        panel_records_sha256=panel_sha,
    )
    payload = {
        "panel_records_sha256": panel_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "schema": LOCK_SCHEMA,
        "source_sha256": {
            name: sha256_file(resolve_repo_path(name, "latency execution source"))
            for name in EXECUTION_SOURCE_NAMES
        },
        "task_manifest_sha256": task_sha,
    }
    atomic_write_json(output, payload)
    return payload


__all__ = [
    "DESIGNATED_INIT_SEED",
    "DESIGNATED_SPLIT_SEED",
    "DESIGNATED_TASK_ID",
    "EXECUTION_SOURCE_NAMES",
    "EXPECTED_FAMILIES",
    "EXPECTED_INPUT_NAMES",
    "EXPECTED_LAYOUTS",
    "LOCK_SCHEMA",
    "LatencyContractError",
    "PENDING_SCHEMA",
    "PANEL_ROW_SCHEMA",
    "PLAN_SCHEMA",
    "PLANNER_SOURCE_NAMES",
    "PROTOCOL_SCHEMA",
    "TASK_ROW_SCHEMA",
    "TASK_MANIFEST_SCHEMA",
    "build_file_manifest",
    "load_json",
    "load_jsonl",
    "panel_row_sha256",
    "resolve_protocol_inputs",
    "resolve_repo_path",
    "validate_execution_lock",
    "validate_file_manifest",
    "validate_pending_set",
    "validate_plan",
    "validate_protocol",
    "validate_root_closure",
    "validate_slurm_allocation",
    "validate_upstream_closure",
    "write_execution_lock",
]
