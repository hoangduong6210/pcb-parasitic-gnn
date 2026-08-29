#!/usr/bin/env python3
"""Shared fail-closed contract for the Corpus V4 crossed accuracy study.

This module is deliberately solver-free.  It contains only immutable task
mapping, metric reconstruction, artifact hashing, and scheduler validation so
CI can exercise the scientific contract without training on a login node.
"""
from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
for _directory in (ROOT / "code/core",):
    sys.path.insert(0, str(_directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    canonical_json_bytes,
    require_file_sha256,
    sha256_bytes,
    sha256_file,
)


PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-accuracy-protocol.v2"
PLAN_SCHEMA = "pcb-gnn.corpus-v4-accuracy-plan.v2"
TASK_ROW_SCHEMA = "pcb-gnn.corpus-v4-accuracy-task-row.v2"
LOCK_SCHEMA = "pcb-gnn.corpus-v4-accuracy-execution-lock.v2"
TASK_RESULT_SCHEMA = "pcb-gnn.corpus-v4-accuracy-task-result.v2"
TASK_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-accuracy-task-artifact-manifest.v2"
CANDIDATE_SCHEMA = "pcb-gnn.corpus-v4-accuracy-candidate-index.v2"
ACCEPTED_SCHEMA = "pcb-gnn.corpus-v4-accuracy-accepted-set.v2"
PENDING_SCHEMA = "pcb-gnn.corpus-v4-accuracy-pending-set.v2"
FINAL_SCHEMA = "pcb-gnn.corpus-v4-accuracy-final.v2"
TARGETS = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
SEEDS = (40, 41, 42, 43, 44)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
EXPECTED_INPUT_NAMES = frozenset(
    {
        "archive_manifest",
        "dataset_admission",
        "final_observations",
        "geometry_families",
        "hf_selection_registry",
        "inductance_labels",
        "layouts",
        "source_corpus_summary",
        "split_registry",
    }
)
PLANNER_SOURCE_NAMES = (
    "code/core/geometry_contract.py",
    "code/core/scientific_artifact.py",
    "code/experiments/proofs/plan_corpus_v4_accuracy_v2.py",
    "code/quality/verify_corpus_v4_fem_v2_production_archive.py",
)
EXECUTION_SOURCE_NAMES = (
    "code/core/geometry_contract.py",
    "code/core/pcb_graph.py",
    "code/core/planar_to_graph.py",
    "code/core/scientific_artifact.py",
    "code/core/trace_peec.py",
    "code/data/corpus_v4_accuracy_dataset_v2.py",
    "code/env.sh",
    "code/experiments/proofs/build_corpus_v4_accuracy_execution_lock_v2.py",
    "code/experiments/proofs/corpus_v4_accuracy_contract_v2.py",
    "code/experiments/proofs/finalize_corpus_v4_accuracy_v2.py",
    "code/experiments/proofs/plan_corpus_v4_accuracy_v2.py",
    "code/experiments/proofs/plan_corpus_v4_accuracy_resume_v2.py",
    "code/experiments/proofs/run_corpus_v4_accuracy_task_v2.py",
    "code/inference/safe_npz_bundle.py",
    "code/jobs/slurm_job_env.sh",
    "code/jobs/submit_corpus_v4_accuracy_v2.sh",
    "code/jobs/submit_finalize_corpus_v4_accuracy_v2.sh",
    "code/models/gnn/gnn_baseline.py",
    "code/quality/verify_corpus_v4_accuracy_archive_v2.py",
    "code/quality/verify_corpus_v4_fem_v2_production_archive.py",
    "requirements-proof.txt",
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
SCIENTIFIC_THREAD_ENV_NAMES = (
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
)


def require_plain_int(value: Any, label: str, *, minimum: int = 0) -> int:
    """Reject bools and integer-like floats at trust boundaries."""
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def require_repo_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{label} is not a canonical repository-relative path")
    return value


def resolve_repo_path(value: Any, label: str = "path") -> Path:
    relative = require_repo_relative_path(value, label)
    candidate = ROOT
    for component in PurePosixPath(relative).parts:
        candidate /= component
        if candidate.is_symlink():
            raise ValueError(f"{label} traverses a symlink")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the repository") from exc
    return resolved


def resolve_descendant_path(directory: Path, value: Any, label: str = "path") -> Path:
    """Resolve a canonical relative path without following a symlink component."""
    relative = require_repo_relative_path(value, label)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"{label} root must be a regular directory")
    base = directory.resolve()
    candidate = directory
    for component in PurePosixPath(relative).parts:
        candidate /= component
        if candidate.is_symlink():
            raise ValueError(f"{label} traverses a symlink")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes its artifact directory") from exc
    return resolved


def _require_exact_json(actual: Any, expected: Any, label: str) -> None:
    """Compare JSON values without Python's bool/int equality coercion."""
    try:
        matches = canonical_json_bytes(actual) == canonical_json_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not finite JSON data") from exc
    if not matches:
        raise ValueError(f"{label} differs from the frozen protocol")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, member in pairs:
        if name in value:
            raise ValueError(f"duplicate JSON object key is forbidden: {name}")
        value[name] = member
    return value


def _strict_json_loads(text: str, label: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid strict JSON in {label}: {exc}") from exc


def load_json(path: Path) -> dict[str, Any]:
    payload = _strict_json_loads(path.read_text(encoding="utf-8"), str(path))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def validate_protocol(path: Path, expected_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("accuracy protocol must be a regular non-symlink file")
    if expected_sha256 is not None:
        require_file_sha256(path, expected_sha256, "accuracy protocol")
    protocol = load_json(path)
    observed = sha256_file(path)
    if set(protocol) != {
        "checkpoint",
        "determinism",
        "evaluation",
        "forbidden_actions",
        "inputs",
        "model",
        "optimization",
        "protocol_name",
        "resources",
        "runtime",
        "schema",
        "seeds",
        "splits",
        "targets",
        "upstream_archive_git_commit",
        "validation_fidelity",
    } or protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("unexpected Corpus V4 accuracy protocol schema")
    expected_sections = {
        "checkpoint": {
            "accept_before_test_inference": True,
            "bundle_format": "numpy_npz_allow_pickle_false",
            "designated_downstream_task_id": 12,
            "maximum_bundle_bytes": 67108864,
            "maximum_uncompressed_bytes": 134217728,
            "save_every_task": True,
            "smoke_examples": 5,
        },
        "determinism": {
            "cpu_only": True,
            "fixed_epoch_no_early_stopping": True,
            "python_hash_seed": 0,
            "torch_deterministic_algorithms": True,
        },
        "evaluation": {
            "descriptive_seed_grid_interval": {
                "label": "crossed-axis seed-grid resampling interval",
                "percentiles": [2.5, 97.5],
                "resamples": 10000,
                "seed": 20260819,
                "statistical_semantics": (
                    "descriptive sensitivity interval, not a population confidence interval"
                ),
            },
            "metric_quantile_method": "Hyndman-Fan type 7",
            "passivity_relative_tolerance": 1e-9,
            "prediction_passivity_is_integrity_gate": False,
            "r3_test_scope": "all layouts in the frozen test families",
            "r4_test_scope": "the 39 preselected R4 layouts in the frozen test families",
            "relative_error_denominator": "absolute reference value",
            "report_nonpositive_prediction_count": True,
        },
        "forbidden_actions": {
            "accuracy_threshold_as_integrity_gate": True,
            "global_r3_to_r4_correction": True,
            "legacy_cps_as_training_target": True,
            "random_or_regenerated_split": True,
            "r4_in_checkpoint_selection": True,
            "r4_in_hyperparameter_selection": True,
            "r4_in_normalization": True,
            "r4_in_optimization": True,
            "test_or_r4_selected_checkpoint": True,
        },
        "model": {
            "architecture": "PCBParasiticGNN",
            "edge_dim": 7,
            "hidden": 96,
            "n_layers": 4,
            "n_targets": 4,
            "node_dim": 9,
            "parameterization": "pure PyTorch message-passing network",
        },
        "optimization": {
            "batch_size": 32,
            "epochs": 200,
            "gradient_clip_norm": 5.0,
            "learning_rate": 0.002,
            "loss": "SmoothL1 on train-standardized log1p targets",
            "lr_schedule": "CosineAnnealingLR over exactly 200 epochs",
            "model_selection": "fixed final epoch; validation is diagnostic only",
            "normalization": (
                "node, edge, and target statistics fitted on training layouts only"
            ),
            "optimizer": "AdamW",
            "weight_decay": 0.00001,
        },
        "resources": {
            "finalizer": {
                "allocated_cpus_may_exceed_request": True,
                "cpus_per_task": 2,
                "memory_gib": 16,
                "partition": "nextgen",
                "scientific_threads": 2,
                "time_limit": "00:30:00",
            },
            "training": {
                "allocated_cpus_may_exceed_request": True,
                "array": "0-24%5",
                "cpus_per_task": 8,
                "memory_gib": 48,
                "partition": "nextgen",
                "scientific_threads": 8,
                "time_limit": "04:00:00",
            },
        },
        "runtime": {
            "numpy_distribution": "2.0.2",
            "python": "3.9.21",
            "torch_distribution": "2.8.0",
        },
        "seeds": {
            "init": list(SEEDS),
            "mapping": "row-major: task_id = split_index * 5 + init_index",
            "split": list(SEEDS),
            "tasks": 25,
        },
        "splits": {
            "families": {"test": 13, "train": 46, "validation": 7},
            "family_key": "swap-closed unordered turn-count pair",
            "r4_test_layouts_per_split": 39,
            "source": "frozen split_registry.json; never regenerated",
        },
        "targets": [
            {
                "fidelity_id": "cps_fem_r3_p16_t1_v2",
                "name": "Cps_pF",
                "role": "training and bulk-test numerical target",
                "source": "admitted deterministic one-thread FEM-v2 observations",
                "units": "pF",
            },
            *[
                {
                    "fidelity_id": "fasthenry_100khz_active_leg",
                    "name": name,
                    "role": "training and test numerical target",
                    "source": "finalized Corpus V3 FastHenry labels",
                    "units": "nH",
                }
                for name in TARGETS[1:]
            ],
        ],
        "validation_fidelity": {
            "fidelity_id": "cps_fem_r4_p16_t1_v2",
            "role": "evaluation-only higher-resolution comparator",
            "units": "pF",
        },
    }
    if protocol.get("protocol_name") != "corpus-v4-fem-v2-family-crossed-accuracy-v2":
        raise ValueError("accuracy protocol name differs from the frozen v2 identity")
    if protocol.get("upstream_archive_git_commit") != (
        "d512cf242a5b2b8faf60de9c6bba0a814f867ec6"
    ):
        raise ValueError("accuracy protocol does not bind the admitted archive commit")
    for name, expected in expected_sections.items():
        _require_exact_json(protocol.get(name), expected, f"protocol {name}")
    inputs = protocol.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != EXPECTED_INPUT_NAMES:
        raise ValueError("protocol input closure is not exact")
    for name, record in inputs.items():
        if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
            raise ValueError(f"protocol input {name} must contain only path and sha256")
        require_repo_relative_path(record.get("path"), f"protocol input {name}")
        if not isinstance(record.get("sha256"), str) or not SHA256_RE.fullmatch(
            record["sha256"]
        ):
            raise ValueError(f"protocol input {name} has an invalid SHA-256")
    return protocol, observed


def canonical_task_row(task_id: int) -> dict[str, int | bool]:
    task_id = require_plain_int(task_id, "task_id")
    if task_id >= 25:
        raise ValueError("task_id must be in 0..24")
    split_index, init_index = divmod(task_id, 5)
    return {
        "task_id": task_id,
        "split_seed": SEEDS[split_index],
        "init_seed": SEEDS[init_index],
        "designated_downstream_checkpoint": task_id == 12,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"blank JSONL line {line_number}: {path}")
            value = _strict_json_loads(line, f"{path}:{line_number}")
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row {line_number} is not an object")
            rows.append(value)
    return rows


def _planner_value_sha256(value: Any) -> str:
    """Match the planner's newline-terminated canonical JSON convention."""
    payload = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return sha256_bytes(payload)


def runtime_identity() -> dict[str, str]:
    """Return the distribution-level runtime identity frozen by the protocol."""
    try:
        numpy_version = importlib.metadata.version("numpy")
        torch_version = importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"required runtime distribution is unavailable: {exc.name}") from exc
    return {
        "numpy_distribution": numpy_version,
        "python": platform.python_version(),
        "torch_distribution": torch_version,
    }


def validate_plan(
    plan_path: Path,
    task_manifest_path: Path,
    *,
    expected_plan_sha256: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str, str]:
    if plan_path.is_symlink() or not plan_path.is_file():
        raise ValueError("accuracy plan must be a regular non-symlink file")
    if task_manifest_path.is_symlink() or not task_manifest_path.is_file():
        raise ValueError("task-row manifest must be a regular non-symlink file")
    if expected_plan_sha256 is not None:
        require_file_sha256(plan_path, expected_plan_sha256, "accuracy plan")
    if expected_manifest_sha256 is not None:
        require_file_sha256(task_manifest_path, expected_manifest_sha256, "task manifest")
    plan = load_json(plan_path)
    rows = load_jsonl(task_manifest_path)
    plan_sha = sha256_file(plan_path)
    manifest_sha = sha256_file(task_manifest_path)
    if plan.get("schema") != PLAN_SCHEMA or len(rows) != 25:
        raise ValueError("accuracy plan is not the canonical 25-task plan")
    artifacts = plan.get("artifact_sha256")
    if (
        not isinstance(artifacts, dict)
        or set(artifacts) != {"evaluation_dataset.jsonl", "task_manifest.jsonl"}
        or artifacts.get("task_manifest.jsonl") != manifest_sha
        or any(
            not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
            for digest in artifacts.values()
        )
    ):
        raise ValueError("plan does not bind the exact task manifest")
    expected_row_fields = {
        "designated_downstream_checkpoint",
        "evaluation_dataset_sha256",
        "init_seed",
        "partition_counts",
        "partition_family_counts",
        "partition_family_ids_sha256",
        "partition_layout_ids_sha256",
        "partitions",
        "protocol_sha256",
        "r4_test_geometry_sha256",
        "r4_test_layout_count",
        "r4_test_layout_ids",
        "r4_test_layout_ids_sha256",
        "schema",
        "split_seed",
        "task_id",
    }
    for task_id, row in enumerate(rows):
        expected = canonical_task_row(task_id)
        if set(row) != expected_row_fields or row.get("schema") != TASK_ROW_SCHEMA:
            raise ValueError(f"task row {task_id} schema mismatch")
        if any(row.get(name) != value for name, value in expected.items()):
            raise ValueError(f"task row {task_id} identity mismatch")
        counts = row.get("partition_counts", {})
        families = row.get("partition_family_counts", {})
        partitions = row.get("partitions")
        if (
            not isinstance(partitions, dict)
            or set(partitions) != {"test", "train", "validation"}
            or not isinstance(counts, dict)
            or not isinstance(families, dict)
            or sum(
                counts.get(name, -1) for name in ("train", "validation", "test")
            )
            != 1500
            or families != {"test": 13, "train": 46, "validation": 7}
            or row.get("r4_test_layout_count") != 39
        ):
            raise ValueError(f"task row {task_id} partition contract mismatch")
        observed_layout_hashes: dict[str, str] = {}
        observed_family_hashes: dict[str, str] = {}
        for name in ("train", "validation", "test"):
            partition = partitions[name]
            if (
                not isinstance(partition, dict)
                or set(partition)
                != {"family_ids", "layout_ids", "n_families", "n_layouts", "n_r4_layouts"}
                or partition.get("n_layouts") != counts.get(name)
                or partition.get("n_families") != families.get(name)
                or not isinstance(partition.get("layout_ids"), list)
                or not isinstance(partition.get("family_ids"), list)
                or any(type(value) is not int for value in partition["layout_ids"])
                or any(not isinstance(value, str) for value in partition["family_ids"])
                or partition["layout_ids"] != sorted(set(partition["layout_ids"]))
                or partition["family_ids"] != sorted(set(partition["family_ids"]))
            ):
                raise ValueError(f"task row {task_id} {name} partition is malformed")
            observed_layout_hashes[name] = _planner_value_sha256(
                partition["layout_ids"]
            )
            observed_family_hashes[name] = _planner_value_sha256(
                partition["family_ids"]
            )
        r4_ids = row.get("r4_test_layout_ids")
        r4_geometries = row.get("r4_test_geometry_sha256")
        if (
            row.get("partition_layout_ids_sha256") != observed_layout_hashes
            or row.get("partition_family_ids_sha256") != observed_family_hashes
            or not isinstance(r4_ids, list)
            or any(type(value) is not int for value in r4_ids)
            or r4_ids != sorted(set(r4_ids))
            or len(r4_ids) != 39
            or row.get("r4_test_layout_ids_sha256")
            != _planner_value_sha256(r4_ids)
            or not isinstance(r4_geometries, list)
            or len(r4_geometries) != 39
            or any(
                not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None
                for digest in r4_geometries
            )
            or not isinstance(row.get("protocol_sha256"), str)
            or SHA256_RE.fullmatch(row["protocol_sha256"]) is None
            or not isinstance(row.get("evaluation_dataset_sha256"), str)
            or SHA256_RE.fullmatch(row["evaluation_dataset_sha256"]) is None
        ):
            raise ValueError(f"task row {task_id} hash closure is malformed")
    return plan, rows, plan_sha, manifest_sha


def validate_root_closure(
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    plan: Mapping[str, Any],
    plan_path: Path,
    task_rows: Sequence[Mapping[str, Any]],
    task_manifest_sha256: str,
    lock: Mapping[str, Any] | None = None,
    lock_sha256: str | None = None,
) -> str:
    """Bind protocol, generated artifacts, task rows, sources, and optional lock."""
    if not isinstance(protocol_sha256, str) or SHA256_RE.fullmatch(protocol_sha256) is None:
        raise ValueError("protocol root SHA-256 is malformed")
    if (
        not isinstance(task_manifest_sha256, str)
        or SHA256_RE.fullmatch(task_manifest_sha256) is None
    ):
        raise ValueError("task-manifest root SHA-256 is malformed")
    expected_inputs = {
        name: protocol["inputs"][name]["sha256"] for name in sorted(EXPECTED_INPUT_NAMES)
    }
    for name in sorted(EXPECTED_INPUT_NAMES):
        record = protocol["inputs"][name]
        source_path = ROOT / require_repo_relative_path(
            record["path"], f"protocol input {name}"
        )
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError(f"protocol input must be a regular non-symlink file: {name}")
        resolved_source = resolve_repo_path(record["path"], f"protocol input {name}")
        require_file_sha256(resolved_source, record["sha256"], f"protocol input {name}")
    if plan.get("protocol_sha256") != protocol_sha256:
        raise ValueError("plan does not bind the supplied protocol root")
    if plan.get("input_sha256") != expected_inputs:
        raise ValueError("plan input hashes differ from the supplied protocol")
    artifacts = plan.get("artifact_sha256", {})
    evaluation_sha256 = artifacts.get("evaluation_dataset.jsonl")
    if artifacts.get("task_manifest.jsonl") != task_manifest_sha256:
        raise ValueError("plan task-manifest root differs from the supplied rows")
    evaluation_path = plan_path.parent / "evaluation_dataset.jsonl"
    if evaluation_path.is_symlink() or not evaluation_path.is_file():
        raise ValueError("evaluation dataset must be a regular non-symlink file")
    if (
        not isinstance(evaluation_sha256, str)
        or SHA256_RE.fullmatch(evaluation_sha256) is None
    ):
        raise ValueError("evaluation dataset SHA-256 is malformed")
    require_file_sha256(evaluation_path, evaluation_sha256, "evaluation dataset")

    planner_sources = plan.get("planner_source_sha256")
    if not isinstance(planner_sources, dict) or set(planner_sources) != set(
        PLANNER_SOURCE_NAMES
    ):
        raise ValueError("plan planner-source closure is not exact")
    for name in PLANNER_SOURCE_NAMES:
        digest = planner_sources[name]
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"plan planner-source hash is malformed: {name}")
        require_file_sha256(resolve_repo_path(name, "planner source"), digest, name)

    if len(task_rows) != 25:
        raise ValueError("root closure requires exactly 25 task rows")
    for task_id, row in enumerate(task_rows):
        if row.get("protocol_sha256") != protocol_sha256:
            raise ValueError(f"task row {task_id} does not bind the protocol root")
        if row.get("evaluation_dataset_sha256") != evaluation_sha256:
            raise ValueError(f"task row {task_id} does not bind the evaluation dataset")

    if (lock is None) != (lock_sha256 is None):
        raise ValueError("execution lock and its external SHA-256 must be supplied together")
    if lock is not None and lock_sha256 is not None:
        if SHA256_RE.fullmatch(lock_sha256) is None:
            raise ValueError("execution-lock root SHA-256 is malformed")
        expected_lock_roots = {
            "plan_sha256": sha256_file(plan_path),
            "protocol_sha256": protocol_sha256,
            "task_manifest_sha256": task_manifest_sha256,
            "upstream_archive_sha256": protocol["inputs"]["archive_manifest"][
                "sha256"
            ],
            "upstream_dataset_admission_sha256": protocol["inputs"][
                "dataset_admission"
            ]["sha256"],
        }
        if any(lock.get(name) != digest for name, digest in expected_lock_roots.items()):
            raise ValueError("execution lock does not bind the supplied frozen roots")
    return evaluation_sha256


def validate_pending_set(
    path: Path,
    expected_sha256: str,
    bindings: Mapping[str, str],
) -> tuple[dict[str, Any], list[int], str]:
    """Validate a retry allowlist against external bytes and all frozen roots."""
    binding_names = {
        "execution_lock_sha256",
        "plan_sha256",
        "protocol_sha256",
        "task_manifest_sha256",
    }
    if set(bindings) != binding_names:
        raise ValueError("pending-set root binding names are not exact")
    for name in sorted(binding_names):
        digest = bindings[name]
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"pending-set expected binding is malformed: {name}")
    if not isinstance(expected_sha256, str) or SHA256_RE.fullmatch(expected_sha256) is None:
        raise ValueError("pending-set external SHA-256 is malformed")
    if path.is_symlink() or not path.is_file():
        raise ValueError("pending set must be a regular non-symlink file")
    require_file_sha256(path, expected_sha256, "pending set")
    payload = load_json(path)
    if not isinstance(payload, dict) or set(payload) != binding_names | {
        "n_pending",
        "pending",
        "schema",
    }:
        raise ValueError("pending-set fields are not exact")
    if payload.get("schema") != PENDING_SCHEMA:
        raise ValueError("unexpected pending-set schema")
    if any(payload.get(name) != bindings[name] for name in binding_names):
        raise ValueError("pending set does not bind the supplied frozen roots")
    pending = payload.get("pending")
    if not isinstance(pending, list) or not pending:
        raise ValueError("pending set must contain at least one canonical task")
    if require_plain_int(payload.get("n_pending"), "n_pending", minimum=1) != len(pending):
        raise ValueError("pending-set count differs from its task rows")
    task_ids: list[int] = []
    for index, row in enumerate(pending):
        if not isinstance(row, dict):
            raise ValueError(f"pending task row {index} is not an object")
        task_id = require_plain_int(row.get("task_id"), f"pending task row {index} id")
        _require_exact_json(row, canonical_task_row(task_id), f"pending task row {index}")
        task_ids.append(task_id)
    if task_ids != sorted(set(task_ids)):
        raise ValueError("pending task IDs must be unique and strictly increasing")
    return payload, task_ids, sha256_file(path)


def build_file_manifest(directory: Path, names: Iterable[str]) -> dict[str, Any]:
    records: dict[str, str] = {}
    for name in sorted(set(names)):
        relative = require_repo_relative_path(name, "artifact name")
        path = resolve_descendant_path(directory, relative, "artifact name")
        if not path.is_file():
            raise FileNotFoundError(path)
        records[relative] = sha256_file(path)
    return {"files_sha256": records, "schema": TASK_MANIFEST_SCHEMA}


def validate_file_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("task manifest must be a regular non-symlink file")
    manifest = load_json(path)
    if manifest.get("schema") != TASK_MANIFEST_SCHEMA:
        raise ValueError("unexpected task-manifest schema")
    records = manifest.get("files_sha256")
    if not isinstance(records, dict) or not records:
        raise ValueError("task manifest has no files")
    for name, digest in records.items():
        require_repo_relative_path(name, "task artifact")
        if not SHA256_RE.fullmatch(str(digest)):
            raise ValueError("task manifest contains an invalid SHA-256")
        artifact = resolve_descendant_path(path.parent, name, "task artifact")
        if not artifact.is_file():
            raise ValueError(f"task artifact must be a regular non-symlink file: {name}")
        require_file_sha256(artifact, digest, name)
    return manifest


def validate_execution_lock(path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("execution lock must be a regular non-symlink file")
    require_file_sha256(path, expected_sha256, "execution lock")
    lock = load_json(path)
    if set(lock) != {
        "decision",
        "plan_sha256",
        "protocol_sha256",
        "schema",
        "source_sha256",
        "task_manifest_sha256",
        "upstream_archive_sha256",
        "upstream_dataset_admission_sha256",
    } or lock.get("schema") != LOCK_SCHEMA:
        raise ValueError("unexpected accuracy execution-lock schema")
    if lock.get("decision") != {
        "claim_eligible": False,
        "held_out_inference_may_start": False,
        "plan_frozen": True,
        "protocol_frozen": True,
        "speed_claim_eligible": False,
        "training_may_start": True,
    }:
        raise ValueError("accuracy execution lock is not the frozen training admission")
    source = lock.get("source_sha256")
    if not isinstance(source, dict) or set(source) != set(EXECUTION_SOURCE_NAMES):
        raise ValueError("execution lock source closure is not exact")
    for name in EXECUTION_SOURCE_NAMES:
        expected = source[name]
        if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
            raise ValueError(f"execution lock has invalid source SHA-256: {name}")
        source_path = resolve_repo_path(name, "execution source")
        require_file_sha256(source_path, expected, name)
    for name in (
        "plan_sha256",
        "protocol_sha256",
        "task_manifest_sha256",
        "upstream_archive_sha256",
        "upstream_dataset_admission_sha256",
    ):
        if not isinstance(lock.get(name), str) or not SHA256_RE.fullmatch(lock[name]):
            raise ValueError(f"execution lock has invalid {name}")
    return lock, sha256_file(path)


def parse_tres(value: Any) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in str(value or "").split(","):
        key, separator, member = item.partition("=")
        if separator and key:
            parsed[key] = member
    return parsed


def canonical_tres(value: Any) -> str:
    """Canonicalize a complete TRES map without weakening value or unit checks."""
    if not isinstance(value, str) or not value:
        raise ValueError("TRES must be a non-empty string")
    items = value.split(",")
    if any(
        not item
        or "=" not in item
        or not item.partition("=")[0]
        or not item.partition("=")[2]
        or item.partition("=")[0] != item.partition("=")[0].strip()
        or item.partition("=")[2] != item.partition("=")[2].strip()
        for item in items
    ):
        raise ValueError("TRES contains a malformed field")
    parsed = parse_tres(value)
    if len(parsed) != len(items):
        raise ValueError("TRES contains a duplicate field")
    return ",".join(f"{name}={parsed[name]}" for name in sorted(parsed))


def tres_equivalent(left: Any, right: Any) -> bool:
    """Compare TRES maps by field while rejecting malformed representations."""
    try:
        return canonical_tres(left) == canonical_tres(right)
    except ValueError:
        return False


def parse_scontrol_records(output: str) -> list[dict[str, str]]:
    return [
        {token.split("=", 1)[0]: token.split("=", 1)[1] for token in line.split() if "=" in token}
        for line in output.splitlines()
        if line.strip()
    ]


def _resource_contract(
    fields: Mapping[str, str], profile: Mapping[str, Any]
) -> dict[str, int] | None:
    requested_cpu = require_plain_int(profile.get("cpus_per_task"), "cpus_per_task", minimum=1)
    requested_mem = require_plain_int(profile.get("memory_gib"), "memory_gib", minimum=1)
    scientific_threads = require_plain_int(
        profile.get("scientific_threads"), "scientific_threads", minimum=1
    )
    environment_cpu = int(os.environ.get("SLURM_CPUS_PER_TASK", "0"))
    requested = parse_tres(fields.get("ReqTRES"))
    per_task = parse_tres(fields.get("TresPerTask"))
    allocated = parse_tres(fields.get("AllocTRES"))
    allocated_cpu = int(allocated.get("cpu", "0"))
    cpu_allocation_valid = (
        allocated_cpu >= requested_cpu
        if profile.get("allocated_cpus_may_exceed_request") is True
        else allocated_cpu == requested_cpu
    )
    valid = (
        environment_cpu == allocated_cpu
        and all(
            os.environ.get(name) == str(scientific_threads)
            for name in SCIENTIFIC_THREAD_ENV_NAMES
        )
        and cpu_allocation_valid
        and int(os.environ.get("SLURM_MEM_PER_NODE", "0")) == requested_mem * 1024
        and int(fields.get("NumCPUs", "0")) == allocated_cpu
        and int(fields.get("NumTasks", "0")) == 1
        and int(fields.get("CPUs/Task", "0")) == allocated_cpu
        and requested.get("cpu") == str(requested_cpu)
        and requested.get("mem") == f"{requested_mem}G"
        and per_task.get("cpu") == str(requested_cpu)
        and allocated.get("mem") == f"{requested_mem}G"
        and fields.get("MinMemoryNode") == f"{requested_mem}G"
    )
    if not valid:
        return None
    return {
        "allocated_cpus_per_task": allocated_cpu,
        "environment_cpus_per_task": environment_cpu,
        "requested_cpus_per_task": requested_cpu,
        "requested_memory_gib": requested_mem,
        "scientific_threads": scientific_threads,
    }


def validate_slurm_allocation(
    protocol: Mapping[str, Any],
    *,
    stage: str,
    allowed_training_task_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    if stage not in {"training", "finalizer"}:
        raise ValueError("unknown scheduler stage")
    required = [
        "SLURM_JOB_ID",
        "SLURM_CPUS_PER_TASK",
        "SLURM_MEM_PER_NODE",
        "SLURM_JOB_PARTITION",
        *SCIENTIFIC_THREAD_ENV_NAMES,
    ]
    if stage == "training":
        required.extend(
            [
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
    if stage == "training":
        task_id = require_plain_int(int(os.environ["SLURM_ARRAY_TASK_ID"]), "array task")
        component = f"{os.environ['SLURM_ARRAY_JOB_ID']}_{task_id}"
    else:
        task_id = None
        component = os.environ["SLURM_JOB_ID"]
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", component],
        capture_output=True,
        check=False,
        text=True,
    )
    records = parse_scontrol_records(query.stdout)
    matches = [record for record in records if record.get("JobId") == os.environ["SLURM_JOB_ID"]]
    if query.returncode != 0 or len(matches) != 1:
        raise SystemExit("active SLURM component is missing or ambiguous")
    fields = matches[0]
    expected_time = profile["time_limit"]
    resources = _resource_contract(fields, profile)
    valid = (
        fields.get("JobState") in {"RUNNING", "COMPLETING"}
        and fields.get("Partition") == profile["partition"] == os.environ["SLURM_JOB_PARTITION"]
        and fields.get("TimeLimit") == expected_time
        and resources is not None
    )
    if stage == "training":
        valid = valid and (
            task_id is not None
            and fields.get("ArrayJobId") == os.environ["SLURM_ARRAY_JOB_ID"]
            and fields.get("ArrayTaskId") == str(task_id)
            and int(fields.get("ArrayTaskThrottle", "-1")) == 5
        )
        observed_min = int(os.environ["SLURM_ARRAY_TASK_MIN"])
        observed_max = int(os.environ["SLURM_ARRAY_TASK_MAX"])
        observed_count = int(os.environ["SLURM_ARRAY_TASK_COUNT"])
        if allowed_training_task_ids is None:
            valid = valid and task_id is not None and 0 <= task_id < 25 and observed_min == 0 and observed_max == 24 and observed_count == 25
        else:
            allowed = sorted(set(allowed_training_task_ids))
            valid = valid and (
                bool(allowed)
                and all(type(value) is int and 0 <= value < 25 for value in allowed)
                and task_id in allowed
                and observed_min == allowed[0]
                and observed_max == allowed[-1]
                and observed_count == len(allowed)
            )
    if not valid:
        raise SystemExit(f"SLURM allocation differs from the frozen {stage} protocol")
    assert resources is not None
    return {
        **resources,
        "array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "array_task_id": task_id,
        "job_id": os.environ["SLURM_JOB_ID"],
        "scheduler_record": {
            name: fields[name]
            for name in SCHEDULER_RECORD_ALLOWLIST
            if name in fields
        },
    }


def metric_set(
    prediction: Sequence[float],
    reference: Sequence[float],
    family_ids: Sequence[str],
) -> dict[str, Any]:
    """Reconstruct one target's metrics from unmodified physical-unit values."""
    pred = np.asarray(prediction, dtype=np.float64)
    ref = np.asarray(reference, dtype=np.float64)
    families = np.asarray(family_ids, dtype=str)
    if pred.ndim != 1 or ref.shape != pred.shape or families.shape != pred.shape or not len(pred):
        raise ValueError("metric vectors must be non-empty, one-dimensional, and aligned")
    if not np.all(np.isfinite(ref)) or np.any(ref <= 0.0):
        raise ValueError("metric references must be finite and strictly positive")
    finite = np.isfinite(pred)
    if not np.all(finite):
        raise ValueError("non-finite predictions fail the task integrity contract")
    residual = pred - ref
    ape = np.abs(residual) / np.abs(ref) * 100.0
    unique_families = sorted(set(families.tolist()))
    family_means = [float(np.mean(ape[families == family])) for family in unique_families]
    denominator = float(np.sum((ref - np.mean(ref)) ** 2))
    return {
        "family_macro_mape_pct": float(np.mean(family_means)),
        "mae_physical_units": float(np.mean(np.abs(residual))),
        "mean_ape_pct": float(np.mean(ape)),
        "median_ape_pct": float(np.median(ape)),
        "n_families": len(unique_families),
        "n_nonfinite_predictions": int(np.count_nonzero(~finite)),
        "n_nonpositive_predictions": int(np.count_nonzero(pred <= 0.0)),
        "n_samples": int(len(pred)),
        "nonpositive_prediction_rate_pct": float(
            100.0 * np.count_nonzero(pred <= 0.0) / len(pred)
        ),
        "p95_ape_pct": float(np.quantile(ape, 0.95, method="linear")),
        "r2": float(1.0 - np.sum(residual**2) / denominator) if denominator > 0.0 else None,
        "signed_bias_physical_units": float(np.mean(residual)),
    }


def assert_finite_json(value: Any, label: str = "artifact") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite value in {label}")
    if isinstance(value, dict):
        for child in value.values():
            assert_finite_json(child, label)
    elif isinstance(value, list):
        for child in value:
            assert_finite_json(child, label)


def write_execution_lock(
    output: Path,
    *,
    protocol_path: Path,
    plan_path: Path,
    task_manifest_path: Path,
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    protocol, protocol_sha256 = validate_protocol(protocol_path)
    plan, task_rows, plan_sha256, task_manifest_sha256 = validate_plan(
        plan_path, task_manifest_path
    )
    validate_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha256,
        plan=plan,
        plan_path=plan_path,
        task_rows=task_rows,
        task_manifest_sha256=task_manifest_sha256,
    )
    payload = {
        "decision": {
            "claim_eligible": False,
            "held_out_inference_may_start": False,
            "plan_frozen": True,
            "protocol_frozen": True,
            "speed_claim_eligible": False,
            "training_may_start": True,
        },
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "schema": LOCK_SCHEMA,
        "source_sha256": {
            name: sha256_file(resolve_repo_path(name, "execution source"))
            for name in EXECUTION_SOURCE_NAMES
        },
        "task_manifest_sha256": task_manifest_sha256,
        "upstream_archive_sha256": protocol["inputs"]["archive_manifest"]["sha256"],
        "upstream_dataset_admission_sha256": protocol["inputs"]["dataset_admission"][
            "sha256"
        ],
    }
    atomic_write_json(output, payload)
    return payload
