#!/usr/bin/env python3
"""Frozen FEM-v2 coordinate-update ablation with isolated training.

No solver is called. Training, held-out inference, admission replay and archive
replay are SLURM stages. ``validate`` and ``build-lock`` are hash-only stages.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[3]
for directory in ("code/core", "code/data", "code/inference", "code/models/gnn", "code/experiments/proofs"):
    sys.path.insert(0, str(ROOT / directory))

from scientific_artifact import atomic_write_json, atomic_write_jsonl, sha256_file
from corpus_v4_accuracy_contract_v3 import (
    TARGETS, EXECUTION_SOURCE_NAMES, TERMINAL_RECEIPT_KEYS, canonical_task_row,
    load_json, load_jsonl, metric_set, validate_scheduler_receipt,
    validate_slurm_allocation, validate_terminal_receipt,
)
from corpus_v4_accuracy_dataset_v3 import load_training_split_dataset_v3
from run_corpus_v4_accuracy_task_v3 import _graph_samples, _source_state, _validate_training_sandbox
from gnn_baseline import collate
from strict_e3_ablation_v1 import ARM_NAMES, ScalarDistanceModel, SymmetryNormalizer, make_arms, matched_width, parameter_count
from planar_to_graph import build_graph_from_planar_layout
from safe_npz_bundle import ArraySpec, BundleLimits, load_safe_npz_bundle, write_safe_npz_bundle

BASE = "results/corpus_v4/strict_e3_fem_v2"
PLAN = "results/corpus_v4/accuracy_v3/plan/v1"
GNN = "results/corpus_v4/accuracy_v3/final/job_7102842"
PROTOCOL = "protocols/corpus_v4_strict_e3_fem_v2_v1.json"
WRAPPER = "code/jobs/submit_corpus_v4_strict_e3_fem_v2_v1.sh"
FINAL_WRAPPER = "code/jobs/submit_finalize_corpus_v4_strict_e3_fem_v2_v1.sh"
ARMS = tuple(ARM_NAMES)
SOURCES = sorted(set(EXECUTION_SOURCE_NAMES) | {
    "code/models/gnn/strict_e3_ablation_v1.py",
    "code/experiments/proofs/corpus_v4_strict_e3_fem_v2_v1.py",
    WRAPPER, FINAL_WRAPPER, PROTOCOL,
})
NORMALIZATION_SPECS = {
    "norm.node_mean": ArraySpec("<f8", (6,)),
    "norm.node_scale": ArraySpec("<f8", (6,), strictly_positive=True),
    "norm.edge_mean": ArraySpec("<f8", (3,)),
    "norm.edge_scale": ArraySpec("<f8", (3,), strictly_positive=True),
    "norm.target_log1p_mean": ArraySpec("<f8", (4,)),
    "norm.target_log1p_scale": ArraySpec("<f8", (4,), strictly_positive=True),
    "norm.coordinate_scale": ArraySpec("<f8", (1,), strictly_positive=True),
}
ACCURACY_INPUT_PATHS = (
    "datasets/corpus_v3/labels.jsonl", "datasets/corpus_v3/layouts.jsonl", "datasets/corpus_v3/summary.json",
    "results/corpus_v4/cps_multifidelity/plan/v1/geometry_families.jsonl",
    "results/corpus_v4/cps_multifidelity/plan/v1/hf_selection_registry.json",
    "results/corpus_v4/cps_multifidelity/plan/v1/split_registry.json",
    "results/corpus_v4/cps_reference_v2/production/v1/ARCHIVE_MANIFEST.json",
    "results/corpus_v4/cps_reference_v2/production/v1/dataset/admission/source_set_f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b/finalizer_job_7084776/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/dataset/final/source_set_f5c5b99b47fb6e58ac4110e3ab4e564a805b015565833c91013d19c8d404cf3b/finalizer_job_7084776/label_observations.jsonl",
)
PLANNER_SOURCE_PATHS = (
    "code/core/geometry_contract.py", "code/core/scientific_artifact.py",
    "code/experiments/proofs/plan_corpus_v4_accuracy_v3.py",
    "code/quality/verify_corpus_v4_fem_v2_production_archive.py",
)
GNN_ANALYSIS_NAMES = (
    "checkpoint_index.json", "matrices.json", "reference_fidelity_gap.json", "summary.json",
    "task_index.json", "task_metrics.json", *(f"predictions/task_{task:02d}.jsonl" for task in range(25)),
)


def checked_path(name: str) -> Path:
    path = Path(name)
    if path.is_absolute() or not path.parts or any(part in ("..", ".") for part in path.parts):
        raise ValueError("expected canonical repository-relative path")
    result = ROOT / path
    if result.resolve() != result.absolute() or not result.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("artifact path escapes root or traverses a symlink")
    return result


def canonical_argument(path: Path) -> Path:
    path = path if path.is_absolute() else ROOT / path
    if path.absolute() != path.resolve():
        raise ValueError("argument traverses a symlink or noncanonical path")
    return checked_path(path.relative_to(ROOT).as_posix())


def pin(name: str) -> dict[str, str]:
    return {"path": name, "sha256": sha256_file(checked_path(name))}


def authenticate(record: Mapping[str, str]) -> Path:
    if set(record) != {"path", "sha256"}:
        raise ValueError("malformed artifact pin")
    path = checked_path(record["path"])
    if not path.is_file() or sha256_file(path) != record["sha256"]:
        raise ValueError(f"artifact hash mismatch: {record['path']}")
    return path


def runtime() -> dict[str, str]:
    return {"python": platform.python_version(), **{
        name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn", "torch")
    }}


def arm_spec(protocol: Mapping[str, Any], arm: str) -> dict[str, Any]:
    if arm not in ARMS:
        raise ValueError("unknown coordinate-ablation arm")
    record = protocol["arms"][arm]
    return {"hidden": int(record["hidden"]), "update_coordinates": bool(record["update_coordinates"]), "n_layers": int(record["layers"])}


def validate_protocol_config(protocol: dict[str, Any]) -> None:
    if protocol.get("schema") != "pcb-gnn.corpus-v4-strict-e3-protocol.v1":
        raise ValueError("unsupported strict-E(3) protocol schema")
    seeds = protocol.get("seeds", {})
    if seeds.get("split") != list(range(40, 45)) or seeds.get("initialization") != list(range(40, 45)) or seeds.get("tasks") != 25 or seeds.get("arms_per_task") != 3 or seeds.get("required_checkpoints") != 75:
        raise ValueError("unsupported split/initialization/arm grid")
    if set(protocol.get("arms", {})) != set(ARMS) or protocol.get("targets") != list(TARGETS):
        raise ValueError("arm or target contract differs")
    expected = {
        "strict96": (96, True, 301354, [0, 1, 2]),
        "fixed96": (96, False, 273127, []),
        "fixed_matched": (101, False, 301997, []),
    }
    for arm, (hidden, moving, count, layers) in expected.items():
        row = protocol["arms"][arm]
        if (row.get("hidden"), row.get("update_coordinates"), row.get("parameters"), row.get("coordinate_update_layers_zero_based"), row.get("layers")) != (hidden, moving, count, layers, 4):
            raise ValueError(f"frozen architecture differs for {arm}")
        if parameter_count(hidden, moving, 4) != count:
            raise ValueError("analytic parameter count differs from protocol")
    if matched_width(96, 4) != 101:
        raise ValueError("matched-width resolution differs")
    if protocol.get("features") != {
        "raw_node_dim": 9, "raw_edge_dim": 7, "coordinate_columns": [0, 1, 2],
        "node_scalar_columns": [3, 4, 5, 6, 7, 8], "edge_scalar_columns": [1, 5, 6],
        "forbidden_learned_inputs": ["raw_xyz_in_scalar_encoder", "raw_relative_vector", "stored_distance", "layout_id", "family_id", "geometry_sha256", "split_seed"],
    }:
        raise ValueError("feature contract differs from implementation")
    optimization = protocol.get("optimization", {})
    required_optimization = {"epochs": 200, "batch_size": 32, "optimizer": "AdamW", "learning_rate": 0.002,
        "weight_decay": 0.00001, "gradient_clip_norm": 5.0,
        "loss": "SmoothL1 on train-standardized log1p targets",
        "lr_schedule": "CosineAnnealingLR over exactly 200 epochs",
        "model_selection": "fixed final epoch; validation is diagnostic only",
        "hyperparameter_search_trials": 0, "refit_train_plus_validation": False,
        "same_batch_order_all_arms": True, "cpu_only": True, "torch_deterministic_algorithms": True}
    if optimization != required_optimization:
        raise ValueError("optimization contract differs from implementation")
    gate = protocol.get("trained_symmetry_gate", {})
    if gate.get("fixtures") != "lowest layout ID from each validation family" or gate.get("transforms_per_initialization_seed") != 40 or gate.get("transform_seed_offset") != 20260913 or gate.get("relative_tolerance") != 0.00002:
        raise ValueError("trained symmetry transform contract differs")
    if gate.get("required") != {"all_arms_scalar_invariant": True, "strict96_coordinates_equivariant": True, "fixed96_coordinates_unchanged": True, "fixed_matched_coordinates_unchanged": True}:
        raise ValueError("trained symmetry decision gate differs")
    resampling = protocol.get("evaluation", {}).get("resampling")
    if resampling != {"resamples": 10000, "seed": 20260913, "percentiles": [2.5, 97.5], "axes": ["split", "initialization"], "paired_draws": True, "semantics": "descriptive crossed-axis seed-grid sensitivity interval, not a population confidence interval"}:
        raise ValueError("crossed-axis resampling contract differs")
    evaluation = protocol["evaluation"]
    if evaluation.get("paired_differences") != ["strict96 minus fixed96", "strict96 minus fixed_matched"] or evaluation.get("heldout_inference_before_all_checkpoint_admission") is not False or evaluation.get("prediction_clipping") is not False or evaluation.get("repair_predictions") is not False or evaluation.get("passivity_relative_tolerance") != 1e-9:
        raise ValueError("evaluation boundary differs")
    checkpoint = protocol.get("checkpoint", {})
    if checkpoint != {"format": "three arm-specific numeric NPZ bundles; allow_pickle=False; no executable serialization",
            "max_archive_bytes_per_arm": 67108864, "max_expanded_bytes_per_arm": 134217728}:
        raise ValueError("checkpoint bounds differ")
    if protocol.get("target_fidelities") != ["cps_fem_r3_p16_t1_v2", "fasthenry_100khz_active_leg", "fasthenry_100khz_active_leg", "fasthenry_100khz_active_leg"]:
        raise ValueError("target fidelity contract differs")
    normalization = protocol.get("normalization", {})
    if normalization.get("fit_partition") != "train only" or normalization.get("moment_dtype") != "float64" or normalization.get("population_std_ddof") != 0 or normalization.get("scalar_scale_floor") != 1e-6 or normalization.get("target_scale_floor") != 1e-8 or normalization.get("coordinate_centering") is not False or normalization.get("coordinate_per_axis_scaling") is not False or normalization.get("shared_between_arms") is not True or normalization.get("coordinate_scale") != "max(sqrt(mean squared raw edge-relative Euclidean norm over training edges), 1e-6)":
        raise ValueError("train-only isotropic normalization contract differs")
    if evaluation.get("historical_gnn") != "contextual comparison only; not a controlled ablation arm and excluded from primary paired contrasts" or evaluation.get("r4") != "excluded" or evaluation.get("accuracy_threshold_is_integrity_gate") is not False or evaluation.get("equivalence_conclusion_authorized") is not False:
        raise ValueError("scientific interpretation boundary differs")
    if protocol.get("retry_policy") != "one fixed full array; preserve failures; any training retry requires a new protocol identity" or protocol.get("claim_eligible") is not False:
        raise ValueError("retry/claim decision differs")
    expected_resources = {
        "training": {"allocated_cpus_may_exceed_request": True, "array": "0-24%5", "cpus_per_task": 8,
            "memory_gib": 48, "partition": "nextgen", "scientific_threads": 8, "time_limit": "04:00:00"},
        "finalizer": {"allocated_cpus_may_exceed_request": True, "cpus_per_task": 2, "memory_gib": 16,
            "partition": "nextgen", "scientific_threads": 2, "time_limit": "00:30:00"}}
    if protocol.get("resources") != expected_resources:
        raise ValueError("scheduler resource contract differs")
    expected_sandbox = {"backend": "bubblewrap", "executable": "/usr/bin/bwrap",
        "executable_sha256": "9dba99a1fa3be3b0d3e5cb7d6d297742b56a3b1749465f520503c651b38d99aa",
        "required": True, "sandbox_root": "/workspace",
        "training_files": "selected split-scoped train and validation table plus this task's initially empty output directory only; no test, R4, other split, other task, prior GNN, baseline, accepted-set or finalizer bytes"}
    if protocol.get("sandbox") != expected_sandbox:
        raise ValueError("training sandbox contract differs")


def validate_qualification(protocol: Mapping[str, Any]) -> None:
    """Authenticate the initialized-model prerequisite semantically, not by hash alone."""
    qualification_protocol_path = ROOT / "protocols/strict_e3_model_qualification_v1.json"
    receipt_path = ROOT / "results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json"
    qualification_protocol = load_json(qualification_protocol_path)
    receipt = load_json(receipt_path)
    if sha256_file(qualification_protocol_path) != protocol["upstream"][qualification_protocol_path.relative_to(ROOT).as_posix()] or sha256_file(receipt_path) != protocol["upstream"][receipt_path.relative_to(ROOT).as_posix()]:
        raise ValueError("qualification prerequisite hash differs")
    if receipt.get("schema") != "pcb-gnn.strict-e3-model-qualification.v1" or receipt.get("protocol") != qualification_protocol:
        raise ValueError("qualification protocol binding differs")
    if receipt.get("passed") is not True or receipt.get("training_started") is not False or receipt.get("corpus_bytes_opened") is not False or receipt.get("claim_eligible") is not False:
        raise ValueError("qualification decision boundary was not satisfied")
    if receipt.get("runtime") != qualification_protocol["runtime"]:
        raise ValueError("qualification runtime differs")
    model_name = "code/models/gnn/strict_e3_ablation_v1.py"
    expected_source_names = {model_name, "code/models/gnn/gnn_baseline.py",
        "code/experiments/proofs/qualify_strict_e3_model_v1.py",
        "code/jobs/submit_qualify_strict_e3_model_v1.sh",
        "protocols/strict_e3_model_qualification_v1.json"}
    source_receipt = receipt.get("source_sha256", {})
    if set(source_receipt) != expected_source_names or source_receipt.get(model_name) != sha256_file(ROOT / model_name) or source_receipt.get("protocols/strict_e3_model_qualification_v1.json") != sha256_file(qualification_protocol_path):
        raise ValueError("qualified model bytes differ from predictive source")
    rows = receipt.get("results")
    expected_pairs = [(seed, arm) for seed in range(40, 45) for arm in ARMS]
    if not isinstance(rows, list) or [(row.get("seed"), row.get("arm")) for row in rows] != expected_pairs:
        raise ValueError("qualification does not cover the exact seed/arm grid")
    tolerance = qualification_protocol["relative_tolerance"]
    for row in rows:
        residuals = row.get("max_relative_residual", {})
        if row.get("passed") is not True or set(residuals) != {"scalar", "coordinate", "separate_batch"} or any(type(value) not in (int, float) or not np.isfinite(value) or value > tolerance for value in residuals.values()):
            raise ValueError("qualification row failed its frozen tolerance")
        if row.get("initialization", {}).get("seed") != row["seed"] or set(row["initialization"].get("arms", {})) != set(ARMS):
            raise ValueError("qualification initialization identity differs")


def expected_input_names() -> set[str]:
    names = {
        f"{PLAN}/plan.json", f"{PLAN}/task_manifest.jsonl", f"{PLAN}/evaluation_dataset.jsonl",
        "datasets/corpus_v3/layouts.jsonl", "results/corpus_v4/accuracy_v3/ARCHIVE_MANIFEST.json",
        f"{GNN}/ANALYSIS_MANIFEST.json", f"{GNN}/summary.json",
        "protocols/corpus_v4_accuracy_v3.json",
        "protocols/corpus_v4_strict_e3_fem_v2_design_v1.json",
        "protocols/strict_e3_model_qualification_v1.json",
        "results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json",
    }
    names.update(f"{PLAN}/training_split_{seed}.jsonl" for seed in range(40, 45))
    names.update(f"{GNN}/predictions/task_{task:02d}.jsonl" for task in range(25))
    names.update(ACCURACY_INPUT_PATHS)
    names.update(PLANNER_SOURCE_PATHS)
    names.update(f"{GNN}/{name}" for name in GNN_ANALYSIS_NAMES)
    return names


def build_lock(args: argparse.Namespace) -> None:
    protocol = load_json(args.protocol)
    if sha256_file(args.protocol) != args.expected_protocol_sha256:
        raise ValueError("protocol hash mismatch")
    validate_protocol_config(protocol)
    validate_qualification(protocol)
    for name, digest in protocol["upstream"].items():
        authenticate({"path": name, "sha256": digest})
    names = sorted(expected_input_names())
    upstream = load_json(ROOT / "protocols/corpus_v4_accuracy_v3.json")
    plan = load_json(ROOT / PLAN / "plan.json")
    if tuple(sorted(record["path"] for record in upstream["inputs"].values())) != tuple(sorted(ACCURACY_INPUT_PATHS)) or tuple(sorted(plan["planner_source_sha256"])) != tuple(sorted(PLANNER_SOURCE_PATHS)):
        raise ValueError("upstream input/source path closure differs from implementation")
    if plan["protocol_sha256"] != protocol["upstream"]["protocols/corpus_v4_accuracy_v3.json"]:
        raise ValueError("admitted plan protocol root mismatch")
    for name, digest in plan["artifact_sha256"].items():
        authenticate({"path": f"{PLAN}/{name}", "sha256": digest})
    for record in upstream["inputs"].values():
        authenticate(record)
    for name, digest in plan["planner_source_sha256"].items():
        authenticate({"path": name, "sha256": digest})
    archive = load_json(ROOT / "results/corpus_v4/accuracy_v3/ARCHIVE_MANIFEST.json")
    if tuple(sorted(archive["verified_analysis_files_sha256"])) != tuple(sorted(GNN_ANALYSIS_NAMES)):
        raise ValueError("contextual GNN analysis inventory differs")
    authenticate(archive["analysis_manifest"])
    for name, digest in archive["verified_analysis_files_sha256"].items():
        authenticate({"path": f"{GNN}/{name}", "sha256": digest})
    for task in range(25):
        name = f"predictions/task_{task:02d}.jsonl"
        if sha256_file(ROOT / GNN / name) != archive["verified_analysis_files_sha256"][name]:
            raise ValueError("contextual GNN predictions differ from admitted archive")
    if args.execution_lock.exists():
        raise ValueError("refusing execution-lock overwrite")
    atomic_write_json(args.execution_lock, {
        "schema": "pcb-gnn.corpus-v4-strict-e3-execution-lock.v1",
        "protocol_sha256": args.expected_protocol_sha256,
        "source_sha256": {name: sha256_file(checked_path(name)) for name in SOURCES},
        "inputs": {name: sha256_file(checked_path(name)) for name in sorted(set(names))},
        "runtime": protocol["runtime"],
        "qualification": {"protocol_sha256": protocol["upstream"]["protocols/strict_e3_model_qualification_v1.json"],
            "receipt_sha256": protocol["upstream"]["results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json"],
            "semantic_validation_passed": True},
    })


def context(args: argparse.Namespace, *, training: bool = False, full_inputs: bool = False) -> tuple[dict, dict, list]:
    if sha256_file(args.protocol) != args.expected_protocol_sha256 or sha256_file(args.execution_lock) != args.expected_execution_lock_sha256:
        raise ValueError("external protocol/lock hash mismatch")
    protocol, lock = load_json(args.protocol), load_json(args.execution_lock)
    validate_protocol_config(protocol)
    expected_qualification = {"protocol_sha256": protocol["upstream"]["protocols/strict_e3_model_qualification_v1.json"],
        "receipt_sha256": protocol["upstream"]["results/corpus_v4/strict_e3_fem_v2/qualification/job_7275182/result.json"],
        "semantic_validation_passed": True}
    if set(lock) != {"schema", "protocol_sha256", "source_sha256", "inputs", "runtime", "qualification"} or lock.get("schema") != "pcb-gnn.corpus-v4-strict-e3-execution-lock.v1" or lock.get("protocol_sha256") != args.expected_protocol_sha256 or set(lock.get("source_sha256", {})) != set(SOURCES) or set(lock.get("inputs", {})) != expected_input_names() or lock.get("qualification") != expected_qualification:
        raise ValueError("execution-lock closure differs")
    if not training:
        validate_qualification(protocol)
    for name, digest in lock["source_sha256"].items():
        if sha256_file(checked_path(name)) != digest:
            raise ValueError(f"source mismatch: {name}")
    if runtime() != protocol["runtime"] or lock.get("runtime") != protocol["runtime"]:
        raise ValueError("runtime mismatch")
    head, dirty, untracked = _source_state()
    if (head != args.expected_source_git_head and args.stage != "verify") or dirty or untracked:
        raise ValueError("execution requires externally pinned clean source")
    for name in (f"{PLAN}/plan.json", f"{PLAN}/task_manifest.jsonl"):
        if sha256_file(checked_path(name)) != lock["inputs"][name]:
            raise ValueError("upstream plan mismatch")
    rows = load_jsonl(ROOT / PLAN / "task_manifest.jsonl")
    if len(rows) != 25 or any(any(row[key] != value for key, value in canonical_task_row(task).items()) for task, row in enumerate(rows)):
        raise ValueError("task grid differs from the frozen upstream")
    if full_inputs:
        for name, digest in lock["inputs"].items():
            if sha256_file(checked_path(name)) != digest:
                raise ValueError(f"upstream input mismatch: {name}")
    return protocol, lock, rows


def execution(args: argparse.Namespace, protocol: dict, lock: dict, stage: str) -> dict:
    scheduler = validate_slurm_allocation(protocol, stage=stage,
        allowed_training_task_ids=[0] if stage == "training" and args.probe_only else None)
    wrapper = WRAPPER if stage == "training" else FINAL_WRAPPER
    actual = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected = lock["source_sha256"][wrapper]
    if not actual.is_file() or sha256_file(actual) != expected or os.environ.get("PCB_GNN_EXECUTED_BATCH_SHA256") != expected:
        raise ValueError("executed scheduler script differs from locked bytes")
    return scheduler


def bindings(args: argparse.Namespace) -> dict[str, str]:
    return {"protocol_sha256": args.expected_protocol_sha256,
        "execution_lock_sha256": args.expected_execution_lock_sha256,
        "source_git_head": args.expected_source_git_head}


def configure_torch(threads: int) -> None:
    torch.set_num_threads(int(threads))
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)


def _seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_verified_arms(seed: int) -> tuple[dict[str, ScalarDistanceModel], dict[str, Any]]:
    models, receipt = make_arms(seed)
    fixed_state, strict_state = models["fixed96"].state_dict(), models["strict96"].state_dict()
    if not fixed_state or any(key not in strict_state or not torch.equal(value, strict_state[key])
            for key, value in fixed_state.items()):
        raise ValueError("same-width shared initial tensors are not exactly paired")
    observed_hashes = {key: hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
        for key, value in sorted(fixed_state.items())}
    if receipt.get("shared_tensor_sha256") != observed_hashes:
        raise ValueError("shared initial tensor hash receipt differs")
    actual_parameters = {arm: sum(parameter.numel() for parameter in model.parameters()) for arm, model in models.items()}
    receipt = {**receipt, "shared_tensor_equality_verified": True,
        "shared_tensor_count": len(fixed_state), "actual_parameter_count": actual_parameters}
    return models, receipt


def _batch_loss(model: nn.Module, work: Mapping[int, dict], ids: Sequence[int], batch_size: int) -> float:
    model.eval()
    total, count = 0.0, 0
    loss_fn = nn.SmoothL1Loss()
    with torch.no_grad():
        for offset in range(0, len(ids), batch_size):
            selected = ids[offset:offset + batch_size]
            batch = collate([work[index] for index in selected])
            loss = loss_fn(model(batch), batch.y)
            total += float(loss.item()) * len(selected)
            count += len(selected)
    return total / count


def _predict(model: nn.Module, normalizer: SymmetryNormalizer, work: Mapping[int, dict], ids: Sequence[int], batch_size: int) -> np.ndarray:
    blocks = []
    model.eval()
    with torch.no_grad():
        for offset in range(0, len(ids), batch_size):
            selected = ids[offset:offset + batch_size]
            blocks.append(model(collate([work[index] for index in selected])).cpu().numpy())
    prediction = normalizer.inverse(np.concatenate(blocks))
    if prediction.shape != (len(ids), 4) or not np.isfinite(prediction).all():
        raise ValueError("model emitted nonfinite or incorrectly shaped predictions")
    return prediction


def batch_order_sha256(train_ids: Sequence[int], init_seed: int, epochs: int) -> str:
    rng = np.random.default_rng(init_seed)
    digest = hashlib.sha256()
    for epoch in range(1, epochs + 1):
        order = np.asarray(train_ids, dtype="<i8").copy()
        rng.shuffle(order)
        digest.update(epoch.to_bytes(4, "little"))
        digest.update(order.tobytes())
    return digest.hexdigest()


def train_arm(model: nn.Module, work: Mapping[int, dict], train_ids: Sequence[int], validation_ids: Sequence[int], init_seed: int, protocol: Mapping[str, Any]) -> tuple[list[dict], str]:
    """Train one arm with an independently reset stochastic state and order."""
    _seed(init_seed)
    optimization = protocol["optimization"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=optimization["learning_rate"], weight_decay=optimization["weight_decay"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=optimization["epochs"])
    loss_fn = nn.SmoothL1Loss()
    rng = np.random.default_rng(init_seed)
    order_digest = hashlib.sha256()
    curve = []
    for epoch in range(1, optimization["epochs"] + 1):
        model.train()
        order = np.asarray(train_ids, dtype="<i8").copy()
        rng.shuffle(order)
        order_digest.update(epoch.to_bytes(4, "little"))
        order_digest.update(order.tobytes())
        total, seen = 0.0, 0
        for offset in range(0, len(order), optimization["batch_size"]):
            ids = order[offset:offset + optimization["batch_size"]].tolist()
            batch = collate([work[index] for index in ids])
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(batch), batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), optimization["gradient_clip_norm"])
            optimizer.step()
            total += float(loss.item()) * len(ids)
            seen += len(ids)
        scheduler.step()
        curve.append({"epoch": epoch, "learning_rate": float(scheduler.get_last_lr()[0]),
            "train_loss": total / seen,
            "validation_loss_diagnostic_only": _batch_loss(model, work, validation_ids, optimization["batch_size"])})
    observed_digest = order_digest.hexdigest()
    if observed_digest != batch_order_sha256(train_ids, init_seed, optimization["epochs"]):
        raise ValueError("minibatch-order commitment is not reproducible")
    return curve, observed_digest


def state_arrays(model: nn.Module, normalizer: SymmetryNormalizer) -> dict[str, np.ndarray]:
    arrays = {name: np.ascontiguousarray(value) for name, value in normalizer.arrays().items()}
    arrays.update({f"state.{name}": np.ascontiguousarray(value.detach().cpu().numpy())
        for name, value in model.state_dict().items()})
    return arrays


def expected_arm_specs(protocol: Mapping[str, Any], arm: str) -> dict[str, ArraySpec]:
    model = ScalarDistanceModel(**arm_spec(protocol, arm))
    result = dict(NORMALIZATION_SPECS)
    result.update({f"state.{name}": ArraySpec(value.detach().cpu().numpy().dtype.str, tuple(value.shape))
        for name, value in model.state_dict().items()})
    return result


def bundle_payload(args: argparse.Namespace, protocol: Mapping[str, Any], task_id: int, arm: str, initialization: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": "pcb-gnn.corpus-v4-strict-e3-arm-bundle.v1", "arm": arm,
        "architecture": arm_spec(protocol, arm), "parameters": protocol["arms"][arm]["parameters"],
        "bindings": bindings(args), "task": canonical_task_row(task_id),
        "initialization": initialization, "target_order": list(TARGETS),
        "target_transform": "train-standardized log1p; inverse expm1 without clipping"}


def normalizer_from_arrays(arrays: Mapping[str, np.ndarray]) -> SymmetryNormalizer:
    normalizer = object.__new__(SymmetryNormalizer)
    normalizer.node_mean = arrays["norm.node_mean"]
    normalizer.node_scale = arrays["norm.node_scale"]
    normalizer.edge_mean = arrays["norm.edge_mean"]
    normalizer.edge_scale = arrays["norm.edge_scale"]
    normalizer.target_mean = arrays["norm.target_log1p_mean"]
    normalizer.target_scale = arrays["norm.target_log1p_scale"]
    normalizer.coordinate_scale = float(arrays["norm.coordinate_scale"][0])
    return normalizer


def model_from_arrays(protocol: Mapping[str, Any], arm: str, arrays: Mapping[str, np.ndarray]) -> ScalarDistanceModel:
    model = ScalarDistanceModel(**arm_spec(protocol, arm))
    expected = set(model.state_dict())
    observed = {name.removeprefix("state.") for name in arrays if name.startswith("state.")}
    if observed != expected:
        raise ValueError("checkpoint state keys differ from frozen arm architecture")
    state = {name: torch.from_numpy(np.asarray(arrays[f"state.{name}"]).copy()) for name in sorted(expected)}
    model.load_state_dict(state, strict=True)
    return model


def relative_residual(actual: np.ndarray, expected: np.ndarray) -> float:
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("symmetry states are nonfinite or shape-mismatched")
    return float(np.max(np.abs(actual - expected)) / max(1.0, float(np.max(np.abs(expected)))))


def symmetry_fixture_ids(samples: Mapping[int, Mapping[str, Any]], validation_ids: Sequence[int]) -> list[int]:
    families: dict[str, list[int]] = {}
    for layout_id in validation_ids:
        families.setdefault(str(samples[layout_id]["family_id"]), []).append(int(layout_id))
    if len(families) != 7:
        raise ValueError("trained symmetry gate requires exactly seven validation families")
    return [min(families[family]) for family in sorted(families)]


def trained_symmetry_gate(model: ScalarDistanceModel, normalizer: SymmetryNormalizer,
    samples: Mapping[int, Mapping[str, Any]], validation_ids: Sequence[int], *, arm: str,
    init_seed: int, protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Replay the frozen E(3)+permutation gate on trained validation fixtures."""
    ids = symmetry_fixture_ids(samples, validation_ids)
    normalized = [normalizer.transform(samples[index]) for index in ids]
    base_batch = collate(normalized)
    model.eval()
    with torch.no_grad():
        base_y, _base_h, base_x_tensor = model.forward_states(base_batch)
    base_y, base_x = base_y.cpu().numpy(), base_x_tensor.cpu().numpy()
    input_x = np.concatenate([row["node_feat"][:, :3] for row in normalized])
    maxima = {"scalar_invariance": 0.0, "coordinate_equivariance": 0.0,
        "coordinate_unchanged": relative_residual(base_x, input_x)}
    coordinate_scale = normalizer.coordinate_scale
    gate = protocol["trained_symmetry_gate"]
    rng = np.random.default_rng(init_seed + gate["transform_seed_offset"])
    for transform_index in range(gate["transforms_per_initialization_seed"]):
        q, _r = np.linalg.qr(rng.normal(size=(3, 3)))
        q[:, 0] *= (1 if transform_index % 2 == 0 else -1) * np.linalg.det(q)
        translation = rng.uniform(-2.0, 2.0, size=3)
        changed, expected_strict, expected_fixed = [], [], []
        offset = 0
        for layout_id in ids:
            sample = samples[layout_id]
            node = np.asarray(sample["node_feat"], dtype=np.float64).copy()
            edge = np.asarray(sample["edge_feat"], dtype=np.float64).copy()
            edge_index = np.asarray(sample["edge_index"], dtype=np.int64)
            count = len(node)
            permutation = rng.permutation(count)
            inverse = np.empty(count, dtype=np.int64)
            inverse[permutation] = np.arange(count, dtype=np.int64)
            node[:, :3] = node[:, :3] @ q.T + translation
            node = node[permutation]
            remapped_edges = inverse[edge_index]
            transformed = normalizer.transform({"node_feat": node, "edge_feat": edge,
                "edge_index": remapped_edges, "reference_r3": sample["reference_r3"]})
            changed.append(transformed)
            expected_strict.append(base_x[offset:offset + count][permutation] @ q.T + translation / coordinate_scale)
            expected_fixed.append(transformed["node_feat"][:, :3])
            offset += count
        with torch.no_grad():
            observed_y, _observed_h, observed_x = model.forward_states(collate(changed))
        observed_y, observed_x = observed_y.cpu().numpy(), observed_x.cpu().numpy()
        maxima["scalar_invariance"] = max(maxima["scalar_invariance"], relative_residual(observed_y, base_y))
        if arm == "strict96":
            maxima["coordinate_equivariance"] = max(maxima["coordinate_equivariance"],
                relative_residual(observed_x, np.concatenate(expected_strict)))
        else:
            maxima["coordinate_unchanged"] = max(maxima["coordinate_unchanged"],
                relative_residual(observed_x, np.concatenate(expected_fixed)))
    tolerance = float(gate["relative_tolerance"])
    required = [maxima["scalar_invariance"]]
    if arm == "strict96":
        required.append(maxima["coordinate_equivariance"])
    else:
        required.append(maxima["coordinate_unchanged"])
    return {"schema": "pcb-gnn.corpus-v4-strict-e3-trained-symmetry.v1", "arm": arm,
        "fixture_layout_ids": ids, "fixture_family_ids": [samples[index]["family_id"] for index in ids],
        "transform_count": gate["transforms_per_initialization_seed"], "includes_permutation": True,
        "relative_tolerance": tolerance, "max_relative_residual": maxima,
        "coordinate_mode": "equivariant_update" if arm == "strict96" else "unchanged_input_coordinates",
        "passed": all(value <= tolerance for value in required)}


def train(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args, training=True)
    scheduler = execution(args, protocol, lock, "training")
    configure_torch(protocol["resources"]["training"]["scientific_threads"])
    task_id = int(scheduler["array_task_id"])
    row = rows[task_id]
    sandbox = _validate_training_sandbox(protocol, row)
    training_name = f"{PLAN}/{row['training_dataset']['path']}"
    if lock["inputs"][training_name] != row["training_dataset"]["sha256"]:
        raise ValueError("training dataset pin differs from lock")
    dataset = load_training_split_dataset_v3(authenticate({"path": training_name, "sha256": lock["inputs"][training_name]}),
        expected_sha256=lock["inputs"][training_name], task_row=row)
    samples = _graph_samples(dataset)
    output = canonical_argument(args.output_root)
    if not output.is_dir() or any(output.iterdir()) or output.is_symlink():
        raise ValueError("task-private output must be an existing empty real directory")
    expected_output = ROOT / BASE / ("probes" if args.probe_only else "jobs") / f"job_{scheduler['array_job_id']}" / f"task_{task_id:02d}"
    if output != expected_output or list(expected_output.parent.iterdir()) != [expected_output]:
        raise ValueError("task-private output path/visibility differs from scheduler identity")
    forbidden = [ROOT / BASE / name for name in ("final", "resume", "ARCHIVE_MANIFEST.json")]
    forbidden += [ROOT / "results/corpus_v4/baseline_fem_v2", ROOT / GNN]
    if any(path.exists() for path in forbidden):
        raise ValueError("sandbox exposes prior-model, admission, or held-out artifacts")
    sandbox = {**sandbox, "task_private_output_only": True, "other_task_checkpoints_visible": False,
        "prior_model_artifacts_visible": False, "heldout_artifacts_visible": False}
    receipt: dict[str, Any] = {"schema": "pcb-gnn.corpus-v4-strict-e3-task.v1", "bindings": bindings(args),
        "task": canonical_task_row(task_id), "scheduler": scheduler, "sandbox": sandbox,
        "source_sha256": lock["source_sha256"], "runtime": runtime(),
        "training_dataset": {"path": training_name, "sha256": lock["inputs"][training_name]},
        "heldout_bytes_opened": False, "training_started": not args.probe_only}
    if args.probe_only:
        receipt["model_fitting_started"] = False
        atomic_write_json(output / "probe.json", receipt)
        print(output.resolve().as_posix())
        return
    train_ids, validation_ids = list(dataset.train_layout_ids), list(dataset.validation_layout_ids)
    normalizer = SymmetryNormalizer(samples, train_ids)
    work = {index: normalizer.transform(samples[index]) for index in train_ids + validation_ids}
    models, initialization = make_verified_arms(int(row["init_seed"]))
    expected_counts = {arm: protocol["arms"][arm]["parameters"] for arm in ARMS}
    if initialization["arms"] != {arm: {"hidden": protocol["arms"][arm]["hidden"], "parameters": expected_counts[arm]} for arm in ARMS} or initialization["actual_parameter_count"] != expected_counts:
        raise ValueError("initialized arm dimensions/counts differ from protocol")
    receipt["initialization"] = initialization
    receipt["arms"] = {}
    started_task = time.perf_counter()
    batch_hashes = set()
    for arm in ARMS:
        started_arm = time.perf_counter()
        curve, batch_hash = train_arm(models[arm], work, train_ids, validation_ids, int(row["init_seed"]), protocol)
        batch_hashes.add(batch_hash)
        prediction = _predict(models[arm], normalizer, work, validation_ids, protocol["optimization"]["batch_size"])
        reference = np.stack([samples[index]["reference_r3"] for index in validation_ids])
        families = [samples[index]["family_id"] for index in validation_ids]
        diagnostic = {target: metric_set(prediction[:, target_index], reference[:, target_index], families)
            for target_index, target in enumerate(TARGETS)}
        symmetry = trained_symmetry_gate(models[arm], normalizer, samples, validation_ids,
            arm=arm, init_seed=int(row["init_seed"]), protocol=protocol)
        if not symmetry["passed"]:
            raise ValueError(f"trained symmetry gate failed for {arm}")
        arrays = state_arrays(models[arm], normalizer)
        specs = expected_arm_specs(protocol, arm)
        if set(arrays) != set(specs):
            raise ValueError("arm state differs from frozen bundle schema")
        arm_dir = output / f"arm_{arm}"
        hashes = write_safe_npz_bundle(arm_dir, arrays=arrays, specs=specs,
            payload=bundle_payload(args, protocol, task_id, arm, initialization),
            limits=BundleLimits(max_archive_bytes=protocol["checkpoint"]["max_archive_bytes_per_arm"],
                max_expanded_bytes=protocol["checkpoint"]["max_expanded_bytes_per_arm"]))
        load_safe_npz_bundle(arm_dir, expected_metadata_sha256=hashes["metadata.json"], expected_specs=specs,
            expected_payload=bundle_payload(args, protocol, task_id, arm, initialization),
            limits=BundleLimits(max_archive_bytes=protocol["checkpoint"]["max_archive_bytes_per_arm"],
                max_expanded_bytes=protocol["checkpoint"]["max_expanded_bytes_per_arm"]))
        curve_name = f"learning_curve_{arm}.jsonl"
        atomic_write_jsonl(output / curve_name, curve)
        receipt["arms"][arm] = {"bundle_specs": {name: spec.to_json() for name, spec in specs.items()},
            "files": {f"arm_{arm}/metadata.json": hashes["metadata.json"],
                f"arm_{arm}/weights_and_norm.npz": hashes["weights_and_norm.npz"],
                curve_name: sha256_file(output / curve_name)},
            "batch_order_sha256": batch_hash, "epochs_completed": len(curve),
            "validation_diagnostic_only": diagnostic, "trained_symmetry": symmetry,
            "training_wall_s": time.perf_counter() - started_arm}
    if len(batch_hashes) != 1:
        raise ValueError("arms did not consume identical minibatch orders")
    final_head, final_dirty, final_untracked = _source_state()
    final_hashes = {name: sha256_file(checked_path(name)) for name in lock["source_sha256"]}
    if final_head != args.expected_source_git_head or final_dirty or final_untracked or final_hashes != lock["source_sha256"] or sha256_file(authenticate({"path": training_name, "sha256": lock["inputs"][training_name]})) != lock["inputs"][training_name]:
        raise ValueError("source or training input changed during execution")
    receipt["common_batch_order_sha256"] = next(iter(batch_hashes))
    receipt["training_wall_s"] = time.perf_counter() - started_task
    receipt["all_75_checkpoint_admission_pending"] = True
    atomic_write_json(output / "result.json", receipt)
    print(output.resolve().as_posix())


def terminal(scheduler: Mapping[str, Any], stage: str) -> dict[str, str]:
    fields = list(TERMINAL_RECEIPT_KEYS) + ["Restarts", "Partition", "Timelimit"]
    completed = subprocess.run(["sacct", "-X", "-n", "-P", "-j", str(scheduler["job_id"]),
        "--format=" + ",".join(fields)], check=True, capture_output=True, text=True).stdout
    rows = [dict(zip(fields, line.split("|"))) for line in completed.splitlines() if len(line.split("|")) == len(fields)]
    rows = [row for row in rows if row["JobIDRaw"] == str(scheduler["job_id"])]
    if len(rows) != 1:
        raise ValueError("terminal scheduler accounting is unavailable or ambiguous")
    row = rows[0]
    expected_limit = "04:00:00" if stage == "training" else "00:30:00"
    if row["Restarts"] != "0" or row["Partition"] != "nextgen" or row["Timelimit"] != expected_limit:
        raise ValueError("terminal restart/resource boundary differs")
    validate_terminal_receipt(scheduler, {key: row[key] for key in TERMINAL_RECEIPT_KEYS}, stage=stage)
    return row


def load_arm(args: argparse.Namespace, protocol: Mapping[str, Any], result_path: Path,
    result: Mapping[str, Any], arm: str) -> tuple[Mapping[str, np.ndarray], ScalarDistanceModel, SymmetryNormalizer]:
    record = result["arms"][arm]
    specs = expected_arm_specs(protocol, arm)
    if record.get("bundle_specs") != {name: spec.to_json() for name, spec in specs.items()}:
        raise ValueError("recorded bundle schema differs from frozen architecture")
    folder = result_path.parent / f"arm_{arm}"
    loaded = load_safe_npz_bundle(folder,
        expected_metadata_sha256=record["files"][f"arm_{arm}/metadata.json"], expected_specs=specs,
        expected_payload=bundle_payload(args, protocol, result["task"]["task_id"], arm, result["initialization"]),
        limits=BundleLimits(max_archive_bytes=protocol["checkpoint"]["max_archive_bytes_per_arm"],
            max_expanded_bytes=protocol["checkpoint"]["max_expanded_bytes_per_arm"]))
    model = model_from_arrays(protocol, arm, loaded.arrays)
    return loaded.arrays, model, normalizer_from_arrays(loaded.arrays)


def _validate_curve(rows: list[dict[str, Any]], protocol: Mapping[str, Any]) -> None:
    if len(rows) != protocol["optimization"]["epochs"]:
        raise ValueError("learning curve does not contain exactly 200 epochs")
    for index, row in enumerate(rows, start=1):
        if set(row) != {"epoch", "learning_rate", "train_loss", "validation_loss_diagnostic_only"} or row["epoch"] != index:
            raise ValueError("learning curve schema/order differs")
        if any(type(row[name]) not in (int, float) or not np.isfinite(row[name]) for name in ("learning_rate", "train_loss", "validation_loss_diagnostic_only")):
            raise ValueError("learning curve contains a nonfinite value")


def assert_finite_json(value: Any) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("nonfinite JSON numeric value")
        return
    if isinstance(value, list):
        for item in value:
            assert_finite_json(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            assert_finite_json(item)
        return
    raise ValueError("unsupported JSON value type")


def assert_json_close(actual: Any, expected: Any) -> None:
    if isinstance(actual, bool) or actual is None or isinstance(actual, str):
        if actual != expected:
            raise ValueError("JSON replay value differs")
    elif isinstance(actual, (int, float)) and not isinstance(actual, bool):
        if not isinstance(expected, (int, float)) or isinstance(expected, bool) or not np.isclose(actual, expected, rtol=1e-8, atol=1e-10):
            raise ValueError("JSON replay numeric value differs")
    elif isinstance(actual, list):
        if not isinstance(expected, list) or len(actual) != len(expected):
            raise ValueError("JSON replay list differs")
        for left, right in zip(actual, expected):
            assert_json_close(left, right)
    elif isinstance(actual, dict):
        if not isinstance(expected, dict) or set(actual) != set(expected):
            raise ValueError("JSON replay object differs")
        for key in actual:
            assert_json_close(actual[key], expected[key])
    else:
        raise ValueError("unsupported JSON replay type")


def check_task(args: argparse.Namespace, path: Path, task_id: int, protocol: Mapping[str, Any], lock: Mapping[str, Any], rows: list) -> dict:
    result = load_json(path)
    expected_top = {"schema", "bindings", "task", "scheduler", "sandbox", "source_sha256", "runtime",
        "training_dataset", "heldout_bytes_opened", "training_started", "initialization", "arms",
        "common_batch_order_sha256", "training_wall_s", "all_75_checkpoint_admission_pending"}
    if set(result) != expected_top or result.get("schema") != "pcb-gnn.corpus-v4-strict-e3-task.v1":
        raise ValueError("task receipt schema is not exact")
    if result["bindings"] != bindings(args) or result["task"] != canonical_task_row(task_id):
        raise ValueError("task identity or frozen bindings differ")
    validate_scheduler_receipt(result["scheduler"], stage="training", task_id=task_id)
    expected_dir = ROOT / BASE / "jobs" / f"job_{result['scheduler']['array_job_id']}" / f"task_{task_id:02d}"
    if path.parent.absolute() != expected_dir or path.name != "result.json":
        raise ValueError("task path differs from scheduler identity")
    if result["source_sha256"] != lock["source_sha256"] or result["runtime"] != lock["runtime"]:
        raise ValueError("task source/runtime differs")
    if result["heldout_bytes_opened"] is not False or result["training_started"] is not True or result["all_75_checkpoint_admission_pending"] is not True:
        raise ValueError("task evaluation boundary differs")
    sandbox = result["sandbox"]
    expected_sandbox = {"backend": "bubblewrap", "executable_sha256": protocol["sandbox"]["executable_sha256"],
        "filesystem_boundary_passed": True, "forbidden_roots_absent": True,
        "hidden_training_artifact_count": 4, "sandbox_root": "/workspace",
        "selected_training_artifact": rows[task_id]["training_dataset"]["path"],
        "task_private_output_only": True, "other_task_checkpoints_visible": False,
        "prior_model_artifacts_visible": False, "heldout_artifacts_visible": False}
    if sandbox != expected_sandbox:
        raise ValueError("task sandbox gate was not satisfied")
    training = rows[task_id]["training_dataset"]
    training_pin = {"path": f"{PLAN}/{training['path']}", "sha256": training["sha256"]}
    if result["training_dataset"] != training_pin or lock["inputs"].get(training_pin["path"]) != training_pin["sha256"]:
        raise ValueError("task training dataset differs")
    expected_models, expected_initialization = make_verified_arms(rows[task_id]["init_seed"])
    del expected_models
    if result["initialization"] != expected_initialization:
        raise ValueError("shared-width initialization receipt is not reproducible")
    if set(result["arms"]) != set(ARMS) or type(result["training_wall_s"]) not in (int, float) or not np.isfinite(result["training_wall_s"]) or result["training_wall_s"] <= 0:
        raise ValueError("task must contain exactly three arms")
    expected_files = {"result.json"}
    normalized_arrays: dict[str, np.ndarray] | None = None
    loaded_models: dict[str, tuple[ScalarDistanceModel, SymmetryNormalizer]] = {}
    for arm in ARMS:
        record = result["arms"][arm]
        if set(record) != {"bundle_specs", "files", "batch_order_sha256", "epochs_completed",
                "validation_diagnostic_only", "trained_symmetry", "training_wall_s"}:
            raise ValueError("arm receipt schema is not exact")
        expected_arm_files = {f"arm_{arm}/metadata.json", f"arm_{arm}/weights_and_norm.npz", f"learning_curve_{arm}.jsonl"}
        if set(record["files"]) != expected_arm_files:
            raise ValueError("arm artifact inventory differs")
        expected_files.update(expected_arm_files)
        for name, digest in record["files"].items():
            artifact = path.parent / name
            if not artifact.is_file() or artifact.is_symlink() or sha256_file(artifact) != digest:
                raise ValueError("arm artifact is missing, linked, or hash-mismatched")
        _validate_curve(load_jsonl(path.parent / f"learning_curve_{arm}.jsonl"), protocol)
        if record["epochs_completed"] != 200 or record["batch_order_sha256"] != result["common_batch_order_sha256"] or type(record["training_wall_s"]) not in (int, float) or not np.isfinite(record["training_wall_s"]) or record["training_wall_s"] <= 0:
            raise ValueError("arm training completion/order/timing differs")
        arrays, model, normalizer = load_arm(args, protocol, path, result, arm)
        normalization = np.concatenate([np.asarray(arrays[name]).ravel() for name in sorted(NORMALIZATION_SPECS)])
        if normalized_arrays is None:
            normalized_arrays = normalization
        elif not np.array_equal(normalized_arrays, normalization):
            raise ValueError("all arms must store identical train-only normalization")
        symmetry = record["trained_symmetry"]
        expected_symmetry_keys = {"schema", "arm", "fixture_layout_ids", "fixture_family_ids", "transform_count",
            "includes_permutation", "relative_tolerance", "max_relative_residual", "coordinate_mode", "passed"}
        expected_mode = "equivariant_update" if arm == "strict96" else "unchanged_input_coordinates"
        if set(symmetry) != expected_symmetry_keys or symmetry.get("schema") != "pcb-gnn.corpus-v4-strict-e3-trained-symmetry.v1" or symmetry.get("arm") != arm or symmetry.get("passed") is not True or symmetry.get("transform_count") != 40 or symmetry.get("includes_permutation") is not True or symmetry.get("coordinate_mode") != expected_mode or symmetry.get("relative_tolerance") != protocol["trained_symmetry_gate"]["relative_tolerance"]:
            raise ValueError("stored trained-symmetry receipt failed")
        residuals = symmetry.get("max_relative_residual", {})
        if set(residuals) != {"scalar_invariance", "coordinate_equivariance", "coordinate_unchanged"} or any(type(value) not in (int, float) or not np.isfinite(value) or value < 0 for value in residuals.values()):
            raise ValueError("stored trained-symmetry residual schema differs")
        required_residuals = [residuals["scalar_invariance"], residuals["coordinate_equivariance"] if arm == "strict96" else residuals["coordinate_unchanged"]]
        if any(value > symmetry["relative_tolerance"] for value in required_residuals):
            raise ValueError("stored trained-symmetry residual exceeds tolerance")
        diagnostics = record.get("validation_diagnostic_only", {})
        expected_metric_keys = set(metric_set([1.0], [1.0], ["fixture"]))
        if set(diagnostics) != set(TARGETS) or any(set(diagnostics[target]) != expected_metric_keys for target in TARGETS):
            raise ValueError("validation diagnostic target coverage differs")
        assert_finite_json(diagnostics)
        loaded_models[arm] = (model, normalizer)
    actual_files = {item.relative_to(path.parent).as_posix() for item in path.parent.rglob("*") if item.is_file()}
    if actual_files != expected_files or any(item.is_symlink() for item in path.parent.rglob("*")):
        raise ValueError("task directory contains unexpected files or symlinks")
    dataset = load_training_split_dataset_v3(authenticate(training_pin), expected_sha256=training_pin["sha256"], task_row=rows[task_id])
    samples = _graph_samples(dataset)
    expected_batch_hash = batch_order_sha256(list(dataset.train_layout_ids), rows[task_id]["init_seed"], protocol["optimization"]["epochs"])
    if result["common_batch_order_sha256"] != expected_batch_hash or any(result["arms"][arm]["batch_order_sha256"] != expected_batch_hash for arm in ARMS):
        raise ValueError("stored minibatch-order commitment differs from canonical replay")
    validation_ids = list(dataset.validation_layout_ids)
    for arm, (model, normalizer) in loaded_models.items():
        replay = trained_symmetry_gate(model, normalizer, samples, validation_ids,
            arm=arm, init_seed=rows[task_id]["init_seed"], protocol=protocol)
        stored = result["arms"][arm]["trained_symmetry"]
        nonnumeric = {key: value for key, value in replay.items() if key != "max_relative_residual"}
        stored_nonnumeric = {key: value for key, value in stored.items() if key != "max_relative_residual"}
        if replay["passed"] is not True or nonnumeric != stored_nonnumeric:
            raise ValueError("independent trained-symmetry replay failed")
        for name, value in replay["max_relative_residual"].items():
            if not np.isclose(value, stored["max_relative_residual"][name], rtol=1e-5, atol=1e-7):
                raise ValueError("stored trained-symmetry residual differs from replay")
        work = {index: normalizer.transform(samples[index]) for index in validation_ids}
        prediction = _predict(model, normalizer, work, validation_ids, protocol["optimization"]["batch_size"])
        reference = np.stack([samples[index]["reference_r3"] for index in validation_ids])
        families = [samples[index]["family_id"] for index in validation_ids]
        expected_diagnostic = {target: metric_set(prediction[:, target_index], reference[:, target_index], families)
            for target_index, target in enumerate(TARGETS)}
        assert_json_close(result["arms"][arm]["validation_diagnostic_only"], expected_diagnostic)
    return result


def admit(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args)
    execution(args, protocol, lock, "finalizer")
    configure_torch(protocol["resources"]["finalizer"]["scientific_threads"])
    root = canonical_argument(args.attempt_root)
    accepted_path = canonical_argument(args.accepted_set)
    if accepted_path != ROOT / BASE / "resume/round_00/accepted_artifact_set.json":
        raise ValueError("accepted-set task destination differs from frozen namespace")
    if not root.is_dir() or sorted(item.name for item in root.iterdir()) != [f"task_{task:02d}" for task in range(25)]:
        raise ValueError("admission requires exactly 25 task directories and no extras")
    accepted = []
    for task_id in range(25):
        path = root / f"task_{task_id:02d}" / "result.json"
        result = check_task(args, path, task_id, protocol, lock, rows)
        accepted.append({"task_id": task_id, "result": pin(path.relative_to(ROOT).as_posix()),
            "terminal": terminal(result["scheduler"], "training")})
    if len({load_json(authenticate(item["result"]))["scheduler"]["array_job_id"] for item in accepted}) != 1 or len({load_json(authenticate(item["result"]))["scheduler"]["job_id"] for item in accepted}) != 25:
        raise ValueError("all tasks must come from one complete no-retry array")
    array_id = load_json(authenticate(accepted[0]["result"]))["scheduler"]["array_job_id"]
    if root != ROOT / BASE / "jobs" / f"job_{array_id}":
        raise ValueError("attempt root differs from admitted array namespace")
    if accepted_path.exists():
        raise ValueError("refusing accepted-set overwrite")
    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(accepted_path, {"schema": "pcb-gnn.corpus-v4-strict-e3-accepted.v1",
        "bindings": bindings(args), "accepted": accepted, "task_count": 25, "checkpoint_count": 75,
        "trained_symmetry_receipt_count": 75, "heldout_inference_permitted": True, "claim_eligible": False})


def accepted_tasks(args: argparse.Namespace, protocol: Mapping[str, Any], lock: Mapping[str, Any], rows: list) -> list[tuple[Path, dict]]:
    accepted_path = canonical_argument(args.accepted_set)
    if accepted_path != ROOT / BASE / "resume/round_00/accepted_artifact_set.json":
        raise ValueError("accepted-set task path differs from frozen namespace")
    if sha256_file(accepted_path) != args.expected_accepted_set_sha256:
        raise ValueError("accepted set hash mismatch")
    accepted = load_json(accepted_path)
    if set(accepted) != {"schema", "bindings", "accepted", "task_count", "checkpoint_count", "trained_symmetry_receipt_count", "heldout_inference_permitted", "claim_eligible"} or accepted.get("schema") != "pcb-gnn.corpus-v4-strict-e3-accepted.v1" or accepted.get("bindings") != bindings(args) or accepted.get("task_count") != 25 or accepted.get("checkpoint_count") != 75 or accepted.get("trained_symmetry_receipt_count") != 75 or accepted.get("heldout_inference_permitted") is not True or accepted.get("claim_eligible") is not False:
        raise ValueError("accepted-set decision/schema differs")
    if [row.get("task_id") for row in accepted["accepted"]] != list(range(25)):
        raise ValueError("accepted set must cover exactly tasks 0 through 24")
    results = []
    for item in accepted["accepted"]:
        if set(item) != {"task_id", "result", "terminal"}:
            raise ValueError("accepted task row schema differs")
        path = authenticate(item["result"])
        result = check_task(args, path, item["task_id"], protocol, lock, rows)
        if terminal(result["scheduler"], "training") != item["terminal"]:
            raise ValueError("accepted terminal receipt changed")
        results.append((path, result))
    if len({result["scheduler"]["array_job_id"] for _path, result in results}) != 1 or len({result["scheduler"]["job_id"] for _path, result in results}) != 25:
        raise ValueError("accepted set is not one fixed complete array")
    return results


def summarize_trained_symmetry(accepted: Sequence[tuple[Path, Mapping[str, Any]]]) -> dict[str, Any]:
    receipts = [result["arms"][arm]["trained_symmetry"] for _path, result in accepted for arm in ARMS]
    if len(receipts) != 75 or any(receipt.get("passed") is not True for receipt in receipts):
        raise ValueError("trained symmetry receipt grid is incomplete or failed")
    scalar = {arm: max(receipt["max_relative_residual"]["scalar_invariance"]
        for receipt in receipts if receipt["arm"] == arm) for arm in ARMS}
    return {"checkpoint_receipts": 75, "validation_family_fixtures_per_checkpoint": 7,
        "transforms_per_checkpoint": 40, "arm_transform_batches": 3000,
        "graph_transform_evaluations": 21000, "includes_permutation": True,
        "relative_tolerance": receipts[0]["relative_tolerance"],
        "maximum_scalar_invariance_residual_by_arm": scalar,
        "maximum_strict96_coordinate_equivariance_residual": max(receipt["max_relative_residual"]["coordinate_equivariance"] for receipt in receipts if receipt["arm"] == "strict96"),
        "maximum_fixed_coordinate_unchanged_residual": {
            arm: max(receipt["max_relative_residual"]["coordinate_unchanged"] for receipt in receipts if receipt["arm"] == arm)
            for arm in ("fixed96", "fixed_matched")},
        "all_passed": True,
        "scope": "trained checkpoints on frozen validation-family encoded-graph fixtures; not raw-layout regeneration"}


def passivity_diagnostic(prediction: np.ndarray) -> dict[str, Any]:
    values = np.asarray(prediction, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 4 or not np.isfinite(values).all():
        raise ValueError("passivity diagnostic requires finite four-target rows")
    lp, ls, mutual = values[:, 1], values[:, 2], values[:, 3]
    tolerance = 1e-9
    invalid_diagonal = (lp < 0) | (ls < 0)
    determinant_bad = mutual ** 2 > np.maximum(lp * ls, 0.0) * (1.0 + tolerance)
    invalid = invalid_diagonal | determinant_bad
    return {"n_samples": len(values), "n_nonpositive_target_predictions": int((values <= 0).sum()),
        "n_inductance_psd_violations": int(invalid.sum()),
        "inductance_psd_violation_rate_pct": float(100.0 * invalid.mean()),
        "relative_tolerance": tolerance, "integrity_gate": False, "predictions_repaired": False}


def authenticate_evaluation_inputs(lock: Mapping[str, Any]) -> None:
    """Open held-out/context bytes only after accepted_tasks has returned."""
    required = {"datasets/corpus_v3/layouts.jsonl", f"{PLAN}/evaluation_dataset.jsonl",
        *(f"{GNN}/predictions/task_{task:02d}.jsonl" for task in range(25))}
    for name in sorted(required):
        authenticate({"path": name, "sha256": lock["inputs"][name]})


def inference_sample(normalizer: SymmetryNormalizer, sample: Mapping[str, Any]) -> dict[str, Any]:
    if "reference_r3" in sample:
        raise ValueError("held-out inference graph must not carry a reference target")
    transformed = normalizer.transform(sample)
    if transformed["y"].shape != (4,) or np.any(transformed["y"] != 0):
        raise ValueError("held-out inference graph must carry only a zero dummy target")
    return transformed


def evaluate(args: argparse.Namespace, protocol: Mapping[str, Any], lock: Mapping[str, Any], rows: list,
    accepted: list[tuple[Path, dict]] | None = None) -> tuple[list, list, list]:
    accepted = accepted if accepted is not None else accepted_tasks(args, protocol, lock, rows)
    authenticate_evaluation_inputs(lock)
    layouts = {row["layout_id"]: row for row in load_jsonl(ROOT / "datasets/corpus_v3/layouts.jsonl")}
    refs = {row["layout_id"]: row for row in load_jsonl(ROOT / PLAN / "evaluation_dataset.jsonl")}
    predictions, metrics, contrasts = [], [], []
    for task_id, (path, result) in enumerate(accepted):
        test_ids = rows[task_id]["partitions"]["test"]["layout_ids"]
        raw_samples: dict[int, dict[str, Any]] = {}
        reference = []
        families = []
        for layout_id in test_ids:
            layout, ref = layouts[layout_id], refs[layout_id]
            if layout["geometry_sha256"] != ref["geometry_sha256"]:
                raise ValueError("held-out geometry identity differs")
            node, edge, edge_index = build_graph_from_planar_layout(layout["layout"]).to_feature_matrices()
            values = np.asarray([ref["training_reference"][target]["value"] for target in TARGETS], dtype=np.float64)
            raw_samples[layout_id] = {"node_feat": node, "edge_feat": edge, "edge_index": edge_index,
                "family_id": ref["family_id"], "geometry_sha256": ref["geometry_sha256"]}
            reference.append(values)
            families.append(ref["family_id"])
        reference_array = np.stack(reference)
        gnn_rows = load_jsonl(ROOT / GNN / f"predictions/task_{task_id:02d}.jsonl")
        if [row["layout_id"] for row in gnn_rows] != test_ids:
            raise ValueError("contextual GNN membership differs")
        for index, row in enumerate(gnn_rows):
            if row["family_id"] != families[index] or row["geometry_sha256"] != refs[test_ids[index]]["geometry_sha256"] or row["reference_r3"] != reference_array[index].tolist():
                raise ValueError("contextual GNN pairing differs")
        gnn_prediction = np.asarray([row["prediction"] for row in gnn_rows], dtype=np.float64)
        gnn_metrics = {target: metric_set(gnn_prediction[:, target_index], reference_array[:, target_index], families)
            for target_index, target in enumerate(TARGETS)}
        task_metrics: dict[str, dict[str, dict[str, Any]]] = {}
        for arm in ARMS:
            _arrays, model, normalizer = load_arm(args, protocol, path, result, arm)
            work = {layout_id: inference_sample(normalizer, raw_samples[layout_id]) for layout_id in test_ids}
            prediction = _predict(model, normalizer, work, test_ids, protocol["optimization"]["batch_size"])
            diagnostic = passivity_diagnostic(prediction)
            task_metrics[arm] = {}
            for row_index, layout_id in enumerate(test_ids):
                predictions.append({"task_id": task_id, "split_seed": rows[task_id]["split_seed"],
                    "init_seed": rows[task_id]["init_seed"], "arm": arm, "layout_id": layout_id,
                    "family_id": families[row_index], "geometry_sha256": refs[layout_id]["geometry_sha256"],
                    "prediction": prediction[row_index].tolist(), "reference_r3": reference_array[row_index].tolist()})
            for target_index, target in enumerate(TARGETS):
                arm_metric = metric_set(prediction[:, target_index], reference_array[:, target_index], families)
                task_metrics[arm][target] = arm_metric
                metrics.append({"task_id": task_id, "split_seed": rows[task_id]["split_seed"],
                    "init_seed": rows[task_id]["init_seed"], "arm": arm, "target": target,
                    "metrics": arm_metric, "joint_prediction_diagnostic": diagnostic,
                    "contextual_gnn_metrics": gnn_metrics[target]})
        for control in ("fixed96", "fixed_matched"):
            for target in TARGETS:
                strict_value = task_metrics["strict96"][target]["family_macro_mape_pct"]
                fixed_value = task_metrics[control][target]["family_macro_mape_pct"]
                contrasts.append({"task_id": task_id, "split_seed": rows[task_id]["split_seed"],
                    "init_seed": rows[task_id]["init_seed"], "control": control, "target": target,
                    "strict96_family_macro_mape_pct": strict_value,
                    "control_family_macro_mape_pct": fixed_value,
                    "strict96_minus_control_pp": strict_value - fixed_value,
                    "positive_favors": "fixed-coordinate control"})
    if len(predictions) != 22050 or len(metrics) != 300 or len(contrasts) != 200:
        raise ValueError("held-out output cardinality differs from frozen 25-cell three-arm design")
    return predictions, metrics, contrasts


def summarize(metrics: list[dict[str, Any]], contrasts: list[dict[str, Any]]) -> dict[str, Any]:
    if len(metrics) != 300 or len(contrasts) != 200:
        raise ValueError("summary input cardinality differs from frozen design")
    assert_finite_json(metrics)
    assert_finite_json(contrasts)
    metric_lookup = {(row["task_id"], row["arm"], row["target"]): row["metrics"]["family_macro_mape_pct"] for row in metrics}
    if len(metric_lookup) != 300:
        raise ValueError("arm metric keys are not unique")
    rng = np.random.default_rng(20260913)
    split_draws = rng.integers(0, 5, size=(10000, 5))
    init_draws = rng.integers(0, 5, size=(10000, 5))
    arms: dict[str, Any] = {}
    for arm in ARMS:
        arms[arm] = {}
        for target in TARGETS:
            selected = sorted((row for row in metrics if row["arm"] == arm and row["target"] == target), key=lambda row: row["task_id"])
            if len(selected) != 25 or [row["task_id"] for row in selected] != list(range(25)):
                raise ValueError("arm metric grid is incomplete")
            for row in selected:
                expected_task = canonical_task_row(row["task_id"])
                if row["split_seed"] != expected_task["split_seed"] or row["init_seed"] != expected_task["init_seed"]:
                    raise ValueError("arm metric seed mapping differs from frozen grid")
            values = np.asarray([row["metrics"]["family_macro_mape_pct"] for row in selected])
            arms[arm][target] = {"mean_family_macro_mape_pct": float(values.mean()),
                "minimum_cell_family_macro_mape_pct": float(values.min()),
                "maximum_cell_family_macro_mape_pct": float(values.max()),
                "nonpositive_predictions_across_cells": int(sum(row["metrics"]["n_nonpositive_predictions"] for row in selected)),
                "inductance_psd_violations_across_cells": int(sum(row["joint_prediction_diagnostic"]["n_inductance_psd_violations"] for row in selected))}
    paired: dict[str, Any] = {}
    for control in ("fixed96", "fixed_matched"):
        paired[control] = {}
        for target in TARGETS:
            selected = sorted((row for row in contrasts if row["control"] == control and row["target"] == target), key=lambda row: row["task_id"])
            if len(selected) != 25 or [row["task_id"] for row in selected] != list(range(25)):
                raise ValueError("paired contrast grid is incomplete")
            for row in selected:
                expected_task = canonical_task_row(row["task_id"])
                if row["split_seed"] != expected_task["split_seed"] or row["init_seed"] != expected_task["init_seed"]:
                    raise ValueError("paired contrast seed mapping differs from frozen grid")
                if row.get("positive_favors") != "fixed-coordinate control" or row["strict96_family_macro_mape_pct"] != metric_lookup[(row["task_id"], "strict96", target)] or row["control_family_macro_mape_pct"] != metric_lookup[(row["task_id"], control, target)]:
                    raise ValueError("paired contrast does not link exactly to arm metrics")
            delta = np.asarray([row["strict96_minus_control_pp"] for row in selected], dtype=np.float64)
            for row in selected:
                if abs(row["strict96_minus_control_pp"] - (row["strict96_family_macro_mape_pct"] - row["control_family_macro_mape_pct"])) > 1e-12:
                    raise ValueError("paired contrast sign/value differs")
            resampled = delta.reshape(5, 5)[split_draws[:, :, None], init_draws[:, None, :]].mean(axis=(1, 2))
            paired[control][target] = {"mean_strict96_minus_control_pp": float(delta.mean()),
                "minimum_cell_difference_pp": float(delta.min()), "maximum_cell_difference_pp": float(delta.max()),
                "cells_strict96_lower_error": int((delta < 0).sum()), "cells_control_lower_error": int((delta > 0).sum()),
                "crossed_axis_95pct_interval_pp": np.quantile(resampled, [0.025, 0.975], method="linear").tolist()}
    contextual: dict[str, Any] = {}
    for target in TARGETS:
        selected = sorted((row for row in metrics if row["arm"] == "strict96" and row["target"] == target), key=lambda row: row["task_id"])
        contextual[target] = {"mean_family_macro_mape_pct": float(np.mean([row["contextual_gnn_metrics"]["family_macro_mape_pct"] for row in selected])),
            "role": "previously admitted GNN result shown as context only; not a controlled ablation contrast"}
    strict_count, matched_count = 301354, 301997
    return {"arms": arms, "paired_contrasts": paired, "contextual_original_gnn": contextual,
        "difference_sign": "strict96 minus fixed-coordinate control; positive means lower error for the fixed control",
        "scope": "post-hoc fixed-protocol coordinate-update ablation on the previously evaluated FEM-v2 benchmark",
        "mechanism_tested": "both moving- and fixed-coordinate arms have encoded-graph E(3)-invariant scalar outputs; the paired contrasts test coordinate updates, not the presence or benefit of equivariance",
        "interpretation_boundary": "does not establish raw-layout equivariance, blind generalization, equivalence, or universal coordinate-update benefit",
        "parameter_match": {"strict96": strict_count, "fixed_matched": matched_count,
            "fixed_matched_minus_strict96": matched_count - strict_count,
            "absolute_difference_relative_to_strict96_pct": 100.0 * (matched_count - strict_count) / strict_count},
        "counts": {"tasks": 25, "checkpoints": 75, "prediction_rows": 22050,
            "arm_target_metric_rows": 300, "paired_contrast_rows": 200},
        "resampling": {"resamples": 10000, "seed": 20260913, "axes": ["split", "initialization"],
            "pairing": "shared crossed-axis draws for both controls and all targets",
            "semantics": "descriptive crossed-axis seed-grid sensitivity interval, not a population confidence interval"},
        "inference_runtime_claim": False}


def finalize(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args)
    scheduler = execution(args, protocol, lock, "finalizer")
    configure_torch(protocol["resources"]["finalizer"]["scientific_threads"])
    accepted = accepted_tasks(args, protocol, lock, rows)
    output_root = canonical_argument(args.output_root)
    if output_root != ROOT / BASE / "final":
        raise ValueError("finalizer output root differs from frozen namespace")
    output = output_root / f"job_{scheduler['job_id']}"
    output.mkdir(parents=True, exist_ok=False)
    predictions, metrics, contrasts = evaluate(args, protocol, lock, rows, accepted)
    results = summarize(metrics, contrasts)
    results["trained_symmetry"] = summarize_trained_symmetry(accepted)
    summary = {"schema": "pcb-gnn.corpus-v4-strict-e3-analysis.v1", "bindings": bindings(args),
        "accepted_set_sha256": args.expected_accepted_set_sha256, "scheduler": scheduler,
        "results": results, "claim_eligible": False}
    atomic_write_jsonl(output / "predictions.jsonl", predictions)
    atomic_write_json(output / "metrics.json", {"arm_target_cells": metrics, "paired_contrasts": contrasts})
    atomic_write_json(output / "summary.json", summary)
    atomic_write_json(output / "ANALYSIS_MANIFEST.json", {"schema": "pcb-gnn.corpus-v4-strict-e3-analysis-manifest.v1",
        "bindings": bindings(args), "counts": summary["results"]["counts"],
        "files": {name: sha256_file(output / name) for name in ("predictions.jsonl", "metrics.json", "summary.json")}})
    print(output.resolve().as_posix())


def verify(args: argparse.Namespace) -> None:
    protocol, lock, rows = context(args)
    execution(args, protocol, lock, "finalizer")
    configure_torch(protocol["resources"]["finalizer"]["scientific_threads"])
    accepted = accepted_tasks(args, protocol, lock, rows)
    manifest_path = canonical_argument(args.analysis_manifest)
    if manifest_path.parent.parent != ROOT / BASE / "final" or manifest_path.name != "ANALYSIS_MANIFEST.json":
        raise ValueError("analysis manifest inventory path differs from frozen namespace")
    if sha256_file(manifest_path) != args.expected_analysis_manifest_sha256:
        raise ValueError("analysis manifest hash differs")
    manifest = load_json(manifest_path)
    expected_manifest_keys = {"schema", "bindings", "counts", "files"}
    if set(manifest) != expected_manifest_keys or manifest.get("schema") != "pcb-gnn.corpus-v4-strict-e3-analysis-manifest.v1" or manifest.get("bindings") != bindings(args) or set(manifest.get("files", {})) != {"predictions.jsonl", "metrics.json", "summary.json"}:
        raise ValueError("analysis manifest closure differs")
    folder = manifest_path.parent
    if {path.name for path in folder.iterdir()} != {"ANALYSIS_MANIFEST.json", "predictions.jsonl", "metrics.json", "summary.json"} or any(path.is_symlink() or not path.is_file() for path in folder.iterdir()):
        raise ValueError("analysis output inventory differs or contains symlinks")
    for name, digest in manifest["files"].items():
        if sha256_file(folder / name) != digest:
            raise ValueError("analysis artifact hash differs")
    summary = load_json(folder / "summary.json")
    if folder.name != f"job_{summary['scheduler']['job_id']}":
        raise ValueError("finalizer directory differs from scheduler identity")
    completion = terminal(summary["scheduler"], "finalizer")
    predictions, metrics, contrasts = evaluate(args, protocol, lock, rows, accepted)
    expected_results = summarize(metrics, contrasts)
    expected_results["trained_symmetry"] = summarize_trained_symmetry(accepted)
    if load_jsonl(folder / "predictions.jsonl") != predictions or load_json(folder / "metrics.json") != {"arm_target_cells": metrics, "paired_contrasts": contrasts} or summary.get("results") != expected_results:
        raise ValueError("independent numerical replay differs")
    if summary.get("bindings") != bindings(args) or summary.get("accepted_set_sha256") != args.expected_accepted_set_sha256 or summary.get("claim_eligible") is not False or manifest.get("counts") != summary["results"]["counts"]:
        raise ValueError("analysis decision/binding/count differs")
    out = canonical_argument(args.out)
    if out != ROOT / BASE / "ARCHIVE_MANIFEST.json":
        raise ValueError("archive output path differs from frozen namespace")
    receipt = {"schema": "pcb-gnn.corpus-v4-strict-e3-archive.v1", "bindings": bindings(args),
        "analysis_manifest": pin(manifest_path.relative_to(ROOT).as_posix()),
        "accepted_set": pin(canonical_argument(args.accepted_set).relative_to(ROOT).as_posix()),
        "finalizer_terminal": completion, "counts": summary["results"]["counts"],
        "numerical_reconstruction_passed": True, "claim_eligible": False}
    if args.check:
        if not out.is_file() or load_json(out) != receipt:
            raise ValueError("archive receipt replay differs")
    else:
        if out.exists():
            raise ValueError("refusing archive receipt overwrite")
        atomic_write_json(out, receipt)
    if args.require_git_tracked:
        names = set(lock["source_sha256"]) | set(lock["inputs"])
        names.update(path.relative_to(ROOT).as_posix() for path in folder.rglob("*") if path.is_file())
        names.update((canonical_argument(args.accepted_set).relative_to(ROOT).as_posix(), out.relative_to(ROOT).as_posix()))
        for item in load_json(canonical_argument(args.accepted_set))["accepted"]:
            task_path = authenticate(item["result"])
            names.update(path.relative_to(ROOT).as_posix() for path in task_path.parent.rglob("*") if path.is_file())
        subprocess.run(["git", "ls-files", "--error-unmatch", "--", *sorted(names)], cwd=ROOT, check=True, capture_output=True)
    print("strict-E(3) FEM-v2 archive replay passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build-lock", "validate", "train", "admit", "finalize", "verify"))
    parser.add_argument("--protocol", type=Path, default=ROOT / PROTOCOL)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256")
    parser.add_argument("--expected-source-git-head")
    parser.add_argument("--output-root", type=Path, default=ROOT / BASE / "jobs")
    parser.add_argument("--attempt-root", type=Path)
    parser.add_argument("--accepted-set", type=Path)
    parser.add_argument("--expected-accepted-set-sha256")
    parser.add_argument("--analysis-manifest", type=Path)
    parser.add_argument("--expected-analysis-manifest-sha256")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    if args.stage != "build-lock" and (not args.expected_execution_lock_sha256 or not args.expected_source_git_head):
        parser.error("execution lock SHA and source commit are required")
    if args.stage == "train" and args.output_root is None:
        parser.error("task-private output root is required")
    if args.stage == "admit" and (args.attempt_root is None or args.accepted_set is None):
        parser.error("attempt root and accepted-set output are required")
    if args.stage in ("finalize", "verify") and (args.accepted_set is None or not args.expected_accepted_set_sha256):
        parser.error("externally authenticated accepted set is required")
    if args.stage == "verify" and (args.analysis_manifest is None or not args.expected_analysis_manifest_sha256 or args.out is None):
        parser.error("analysis manifest hash and archive output are required")
    if args.stage == "validate":
        context(args, full_inputs=True)
        print("strict-E(3) FEM-v2 validation passed; no training or prediction")
    else:
        {"build-lock": build_lock, "train": train, "admit": admit,
            "finalize": finalize, "verify": verify}[args.stage](args)


if __name__ == "__main__":
    main()
