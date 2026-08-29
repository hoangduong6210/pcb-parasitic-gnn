#!/usr/bin/env python3
"""Train one frozen Corpus V4 split/init cell under a verified SLURM allocation."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import torch.nn as nn


ROOT = Path(__file__).resolve().parents[3]
for _directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/inference",
    ROOT / "code/models/gnn",
    Path(__file__).resolve().parent,
):
    sys.path.insert(0, str(_directory))

from corpus_v4_accuracy_dataset_v3 import load_training_split_dataset_v3  # noqa: E402
from corpus_v4_accuracy_contract_v3 import (  # noqa: E402
    TARGETS,
    TASK_RESULT_SCHEMA,
    build_file_manifest,
    canonical_task_row,
    runtime_identity,
    validate_execution_lock,
    validate_pending_set,
    validate_plan,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
    validate_training_root_closure,
)
from gnn_baseline import PCBParasiticGNN, collate  # noqa: E402
from planar_to_graph import build_graph_from_planar_layout  # noqa: E402
from safe_npz_bundle import (  # noqa: E402
    ArraySpec,
    BundleLimits,
    load_safe_npz_bundle,
    write_safe_npz_bundle,
)
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)


CURVE_SCHEMA = "pcb-gnn.corpus-v4-accuracy-learning-curve.v3"
SANDBOX_PROBE_SCHEMA = "pcb-gnn.corpus-v4-accuracy-sandbox-probe.v3"
MODEL_ARCHITECTURE = {
    "edge_dim": 7,
    "hidden": 96,
    "n_layers": 4,
    "n_targets": 4,
    "node_dim": 9,
}
NORMALIZATION_NAMES = (
    "norm.edge_mean",
    "norm.edge_scale",
    "norm.node_mean",
    "norm.node_scale",
    "norm.target_log1p_mean",
    "norm.target_log1p_scale",
)


class TrainOnlyNormalizer:
    """Train-fitted feature and log-target statistics with no split fallback."""

    def __init__(self, samples: Mapping[int, dict[str, Any]], train_ids: Sequence[int]):
        if not train_ids:
            raise ValueError("training partition is empty")
        targets = np.stack([samples[index]["reference_r3"] for index in train_ids]).astype(np.float64)
        if not np.all(np.isfinite(targets)) or np.any(targets <= 0.0):
            raise ValueError("training references must be finite and positive")
        nodes = np.concatenate([samples[index]["node_feat"] for index in train_ids], axis=0).astype(np.float64)
        edge_blocks = [samples[index]["edge_feat"] for index in train_ids if samples[index]["edge_feat"].shape[0]]
        if not edge_blocks:
            raise ValueError("training partition has no graph edges")
        edges = np.concatenate(edge_blocks, axis=0).astype(np.float64)
        logged = np.log1p(targets)
        self.target_mean = logged.mean(axis=0)
        self.target_scale = np.maximum(logged.std(axis=0), 1e-8)
        self.node_mean = nodes.mean(axis=0)
        self.node_scale = np.maximum(nodes.std(axis=0), 1e-6)
        self.edge_mean = edges.mean(axis=0)
        self.edge_scale = np.maximum(edges.std(axis=0), 1e-6)
        for scale in (self.target_scale, self.node_scale, self.edge_scale):
            if not np.all(np.isfinite(scale)) or np.any(scale <= 0.0):
                raise ValueError("training-only normalization contains a zero/nonfinite scale")

    def arrays(self) -> dict[str, np.ndarray]:
        return {
            "norm.edge_mean": np.ascontiguousarray(self.edge_mean, dtype=np.float64),
            "norm.edge_scale": np.ascontiguousarray(self.edge_scale, dtype=np.float64),
            "norm.node_mean": np.ascontiguousarray(self.node_mean, dtype=np.float64),
            "norm.node_scale": np.ascontiguousarray(self.node_scale, dtype=np.float64),
            "norm.target_log1p_mean": np.ascontiguousarray(self.target_mean, dtype=np.float64),
            "norm.target_log1p_scale": np.ascontiguousarray(self.target_scale, dtype=np.float64),
        }

    def transform(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "edge_dim": 7,
            "edge_feat": ((sample["edge_feat"].astype(np.float64) - self.edge_mean) / self.edge_scale).astype(np.float32),
            "edge_index": sample["edge_index"],
            "node_feat": ((sample["node_feat"].astype(np.float64) - self.node_mean) / self.node_scale).astype(np.float32),
            "y": ((np.log1p(sample["reference_r3"]) - self.target_mean) / self.target_scale).astype(np.float32),
        }

    def inverse(self, normalized: np.ndarray) -> np.ndarray:
        return np.expm1(normalized.astype(np.float64) * self.target_scale + self.target_mean)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--expected-task-manifest-sha256", required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--expected-source-git-head", required=True)
    parser.add_argument("--pending-set", type=Path)
    parser.add_argument("--expected-pending-set-sha256")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sandbox-probe-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _planner_membership_sha256(value: Any) -> str:
    """Match the planner's canonical JSON record convention, including newline."""
    return sha256_bytes(canonical_json_bytes(value) + b"\n")


def _source_state() -> tuple[str, list[str], list[str]]:
    isolated_head = os.environ.get("PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_COMMIT")
    if isolated_head is not None:
        if (
            len(isolated_head) != 40
            or any(character not in "0123456789abcdef" for character in isolated_head)
            or os.environ.get("PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_CLEAN") != "true"
        ):
            raise SystemExit("isolated host source receipt is malformed")
        return isolated_head, [], []
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    return head, dirty, untracked


def _graph_samples(dataset: Any) -> dict[int, dict[str, Any]]:
    """Build features only after SLURM and source/input validation have passed."""
    samples: dict[int, dict[str, Any]] = {}
    for record in dataset.samples:
        graph = build_graph_from_planar_layout(dict(record.layout))
        node_feat, edge_feat, edge_index = graph.to_feature_matrices()
        if node_feat.shape[1] != 9 or edge_feat.shape[1] != 7 or edge_index.shape[0] != 2:
            raise ValueError("graph feature dimensions differ from the frozen model")
        samples[record.layout_id] = {
            "edge_feat": np.ascontiguousarray(edge_feat, dtype=np.float32),
            "edge_index": np.ascontiguousarray(edge_index, dtype=np.int64),
            "family_id": record.family_id,
            "geometry_sha256": record.geometry_sha256,
            "layout": dict(record.layout),
            "layout_id": record.layout_id,
            "node_feat": np.ascontiguousarray(node_feat, dtype=np.float32),
            "reference_r3": np.asarray(record.training_target_values, dtype=np.float64),
        }
    if hasattr(dataset, "train_layout_ids") and hasattr(
        dataset, "validation_layout_ids"
    ):
        expected = set(dataset.train_layout_ids) | set(dataset.validation_layout_ids)
    else:
        expected = {record.layout_id for record in dataset.samples}
    if set(samples) != expected:
        raise ValueError("graph table differs from the split-scoped training membership")
    return samples


def _validate_training_sandbox(
    protocol: Mapping[str, Any], task_row: Mapping[str, Any]
) -> dict[str, Any]:
    """Prove the training process cannot see held-out repository bytes."""
    policy = protocol.get("sandbox", {})
    if policy.get("required") is not True or policy.get("backend") != "bubblewrap":
        raise SystemExit("the frozen training sandbox policy is not active")
    if os.environ.get("PCB_GNN_V4_ACCURACY_V3_SANDBOX_ACTIVE") != "true":
        raise SystemExit("training must execute inside the frozen filesystem sandbox")
    if ROOT.resolve().as_posix() != policy.get("sandbox_root"):
        raise SystemExit("training root differs from the frozen sandbox root")
    executable = Path(policy["executable"])
    if not executable.is_file() or sha256_file(executable) != policy["executable_sha256"]:
        raise SystemExit("bubblewrap executable differs from the frozen policy")
    selected = task_row["training_dataset"]["path"]
    selected_path = ROOT / "results/corpus_v4/accuracy_v3/plan/v1" / selected
    hidden_training = [
        ROOT / "results/corpus_v4/accuracy_v3/plan/v1" / f"training_split_{seed}.jsonl"
        for seed in (40, 41, 42, 43, 44)
        if seed != task_row["split_seed"]
    ]
    forbidden = [
        ROOT / ".git",
        ROOT / "datasets",
        ROOT / "results/corpus_v4/accuracy_v3/plan/v1/evaluation_dataset.jsonl",
        ROOT / "results/corpus_v4/accuracy_v3/final",
        Path("/users"),
    ]
    if not selected_path.is_file() or any(path.exists() for path in hidden_training):
        raise SystemExit("sandbox exposes the wrong split-scoped training inputs")
    if any(path.exists() for path in forbidden):
        raise SystemExit("sandbox exposes a forbidden held-out or host path")
    return {
        "backend": "bubblewrap",
        "executable_sha256": policy["executable_sha256"],
        "filesystem_boundary_passed": True,
        "forbidden_roots_absent": True,
        "hidden_training_artifact_count": len(hidden_training),
        "sandbox_root": policy["sandbox_root"],
        "selected_training_artifact": selected,
    }


def _batch_loss(
    model: PCBParasiticGNN,
    work: Mapping[int, dict[str, Any]],
    layout_ids: Sequence[int],
    loss_fn: nn.Module,
    batch_size: int,
) -> float:
    model.eval()
    total = 0.0
    count = 0
    with torch.no_grad():
        for offset in range(0, len(layout_ids), batch_size):
            ids = layout_ids[offset : offset + batch_size]
            batch = collate([work[index] for index in ids])
            loss = loss_fn(model(batch), batch.y)
            total += float(loss.item()) * len(ids)
            count += len(ids)
    return total / count


def _predict(
    model: PCBParasiticGNN,
    normalizer: TrainOnlyNormalizer,
    work: Mapping[int, dict[str, Any]],
    layout_ids: Sequence[int],
    batch_size: int,
) -> np.ndarray:
    blocks: list[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for offset in range(0, len(layout_ids), batch_size):
            ids = layout_ids[offset : offset + batch_size]
            blocks.append(model(collate([work[index] for index in ids])).cpu().numpy())
    prediction = normalizer.inverse(np.concatenate(blocks, axis=0))
    if prediction.shape != (len(layout_ids), 4) or not np.all(np.isfinite(prediction)):
        raise ValueError("model emitted a nonfinite or incorrectly shaped prediction table")
    return prediction


def _train(
    samples: Mapping[int, dict[str, Any]],
    train_ids: Sequence[int],
    validation_ids: Sequence[int],
    *,
    init_seed: int,
    protocol: Mapping[str, Any],
) -> tuple[PCBParasiticGNN, TrainOnlyNormalizer, list[dict[str, Any]], dict[int, dict[str, Any]]]:
    random.seed(init_seed)
    np.random.seed(init_seed)
    torch.manual_seed(init_seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(int(protocol["resources"]["training"]["scientific_threads"]))
    torch.set_num_interop_threads(1)
    normalizer = TrainOnlyNormalizer(samples, train_ids)
    admitted_ids = list(train_ids) + list(validation_ids)
    if len(set(admitted_ids)) != len(admitted_ids):
        raise ValueError("training and validation memberships overlap")
    work = {layout_id: normalizer.transform(samples[layout_id]) for layout_id in admitted_ids}
    model = PCBParasiticGNN(**MODEL_ARCHITECTURE)
    optimization = protocol["optimization"]
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(optimization["learning_rate"]),
        weight_decay=float(optimization["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=int(optimization["epochs"])
    )
    loss_fn = nn.SmoothL1Loss()
    batch_size = int(optimization["batch_size"])
    order_rng = np.random.default_rng(init_seed)
    curve: list[dict[str, Any]] = []
    for epoch in range(1, int(optimization["epochs"]) + 1):
        model.train()
        order = np.asarray(train_ids, dtype=np.int64).copy()
        order_rng.shuffle(order)
        total_loss = 0.0
        seen = 0
        for offset in range(0, len(order), batch_size):
            ids = order[offset : offset + batch_size].tolist()
            batch = collate([work[index] for index in ids])
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(batch), batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), float(optimization["gradient_clip_norm"]))
            optimizer.step()
            total_loss += float(loss.item()) * len(ids)
            seen += len(ids)
        scheduler.step()
        curve.append(
            {
                "epoch": epoch,
                "learning_rate": float(scheduler.get_last_lr()[0]),
                "schema": CURVE_SCHEMA,
                "train_loss": total_loss / seen,
                "validation_loss_diagnostic_only": _batch_loss(
                    model, work, validation_ids, loss_fn, batch_size
                ),
            }
        )
    return model, normalizer, curve, work


def _state_arrays(model: PCBParasiticGNN, normalizer: TrainOnlyNormalizer) -> dict[str, np.ndarray]:
    arrays = normalizer.arrays()
    arrays.update(
        {
            f"state.{name}": np.ascontiguousarray(tensor.detach().cpu().numpy())
            for name, tensor in model.state_dict().items()
        }
    )
    return arrays


def _array_specs(arrays: Mapping[str, np.ndarray]) -> dict[str, ArraySpec]:
    return {
        name: ArraySpec(
            dtype=array.dtype.str,
            shape=tuple(array.shape),
            strictly_positive=name.endswith("_scale"),
        )
        for name, array in arrays.items()
    }


def expected_bundle_specs() -> dict[str, ArraySpec]:
    """Return the architecture-derived allowlist without trusting bundle metadata."""
    model = PCBParasiticGNN(**MODEL_ARCHITECTURE)
    specs = {
        f"state.{name}": ArraySpec(tensor.detach().cpu().numpy().dtype.str, tuple(tensor.shape))
        for name, tensor in model.state_dict().items()
    }
    specs.update(
        {
            "norm.edge_mean": ArraySpec("<f8", (7,)),
            "norm.edge_scale": ArraySpec("<f8", (7,), strictly_positive=True),
            "norm.node_mean": ArraySpec("<f8", (9,)),
            "norm.node_scale": ArraySpec("<f8", (9,), strictly_positive=True),
            "norm.target_log1p_mean": ArraySpec("<f8", (4,)),
            "norm.target_log1p_scale": ArraySpec("<f8", (4,), strictly_positive=True),
        }
    )
    return specs


def expected_bundle_payload(
    task: Mapping[str, Any], bindings: Mapping[str, str]
) -> dict[str, Any]:
    return {
        "architecture": MODEL_ARCHITECTURE,
        "bindings": {
            name: bindings[name]
            for name in (
                "execution_lock_sha256",
                "heldout_commitment_sha256",
                "plan_sha256",
                "protocol_sha256",
                "task_manifest_sha256",
                "training_dataset_sha256",
            )
        },
        "designated_downstream_checkpoint": bool(task["designated_downstream_checkpoint"]),
        "init_seed": int(task["init_seed"]),
        "split_seed": int(task["split_seed"]),
        "target_order": list(TARGETS),
        "target_transform": "train-standardized log1p; inverse expm1",
        "task_id": int(task["task_id"]),
    }


def _normalizer_from_arrays(arrays: Mapping[str, np.ndarray]) -> Any:
    class FrozenNormalizer:
        node_mean = arrays["norm.node_mean"]
        node_scale = arrays["norm.node_scale"]
        edge_mean = arrays["norm.edge_mean"]
        edge_scale = arrays["norm.edge_scale"]
        target_mean = arrays["norm.target_log1p_mean"]
        target_scale = arrays["norm.target_log1p_scale"]

        @staticmethod
        def inverse(value: np.ndarray) -> np.ndarray:
            return np.expm1(value.astype(np.float64) * FrozenNormalizer.target_scale + FrozenNormalizer.target_mean)

    return FrozenNormalizer()


def _model_from_arrays(arrays: Mapping[str, np.ndarray]) -> PCBParasiticGNN:
    model = PCBParasiticGNN(**MODEL_ARCHITECTURE)
    expected_keys = set(model.state_dict())
    observed_keys = {
        name.removeprefix("state.") for name in arrays if name.startswith("state.")
    }
    if observed_keys != expected_keys:
        raise ValueError("checkpoint state keys differ from the frozen architecture")
    state = {
        name: torch.from_numpy(np.asarray(arrays[f"state.{name}"]).copy())
        for name in sorted(expected_keys)
    }
    model.load_state_dict(state, strict=True)
    return model


def _smoke_hook(layout_rows: Sequence[dict[str, Any]]):
    def run(arrays: Mapping[str, np.ndarray]) -> Mapping[str, np.ndarray]:
        model = _model_from_arrays(arrays)
        normalizer = _normalizer_from_arrays(arrays)
        work = []
        for row in layout_rows:
            graph = build_graph_from_planar_layout(row["layout"])
            node, edge, edge_index = graph.to_feature_matrices()
            work.append(
                {
                    "edge_dim": 7,
                    "edge_feat": ((edge.astype(np.float64) - normalizer.edge_mean) / normalizer.edge_scale).astype(np.float32),
                    "edge_index": edge_index.astype(np.int64),
                    "node_feat": ((node.astype(np.float64) - normalizer.node_mean) / normalizer.node_scale).astype(np.float32),
                    "y": np.zeros(4, dtype=np.float32),
                }
            )
        model.eval()
        with torch.no_grad():
            raw = model(collate(work)).numpy()
        return {"predictions": np.ascontiguousarray(normalizer.inverse(raw), dtype=np.float64)}

    return run


def main() -> None:
    args = parse_args()
    protocol, protocol_sha = validate_protocol(args.protocol, args.expected_protocol_sha256)
    plan, task_rows, plan_sha, task_manifest_sha = validate_plan(
        args.plan,
        args.task_manifest,
        expected_plan_sha256=args.expected_plan_sha256,
        expected_manifest_sha256=args.expected_task_manifest_sha256,
    )
    lock, lock_sha = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    if args.validate_only:
        validate_root_closure(
            protocol=protocol,
            protocol_sha256=protocol_sha,
            plan=plan,
            plan_path=args.plan,
            task_rows=task_rows,
            task_manifest_sha256=task_manifest_sha,
            lock=lock,
            lock_sha256=lock_sha,
        )
        head, dirty, untracked = _source_state()
        if head != args.expected_source_git_head or dirty or untracked:
            raise SystemExit("validation source is not the expected clean commit")
        if runtime_identity() != protocol["runtime"]:
            raise SystemExit("validation runtime differs from the frozen proof environment")
        if {name: sha256_file(ROOT / name) for name in lock["source_sha256"]} != lock[
            "source_sha256"
        ]:
            raise ValueError("validation source differs from the execution lock")
        print(json.dumps({"schema": TASK_RESULT_SCHEMA, "status": "validation-ok", "tasks": 25}, sort_keys=True))
        return

    retry_enabled = args.pending_set is not None or args.expected_pending_set_sha256 is not None
    if retry_enabled and (args.pending_set is None or args.expected_pending_set_sha256 is None):
        raise ValueError("retry pending set and its external SHA-256 are both required")
    if args.sandbox_probe_only and retry_enabled:
        raise ValueError("sandbox preflight cannot be combined with a retry set")
    allowed_task_ids = None
    pending_set_sha256 = None
    if retry_enabled:
        _, allowed_task_ids, pending_set_sha256 = validate_pending_set(
            args.pending_set,
            expected_sha256=args.expected_pending_set_sha256,
            bindings={
                "execution_lock_sha256": lock_sha,
                "plan_sha256": plan_sha,
                "protocol_sha256": protocol_sha,
                "task_manifest_sha256": task_manifest_sha,
            },
        )
        pending_set_path = args.pending_set.resolve().relative_to(ROOT.resolve()).as_posix()
    else:
        pending_set_path = None
    scheduler = validate_slurm_allocation(
        protocol,
        stage="training",
        allowed_training_task_ids=[0] if args.sandbox_probe_only else allowed_task_ids,
    )
    task_id = int(scheduler["array_task_id"])
    task = canonical_task_row(task_id)
    task_row = task_rows[task_id]
    if any(task_row.get(name) != value for name, value in task.items()):
        raise ValueError("scheduler task identity differs from the frozen task row")
    sandbox = _validate_training_sandbox(protocol, task_row)
    validate_training_root_closure(
        protocol=protocol,
        protocol_sha256=protocol_sha,
        plan=plan,
        plan_path=args.plan,
        task_row=task_row,
        task_manifest_sha256=task_manifest_sha,
        lock=lock,
        lock_sha256=lock_sha,
    )
    initial_head, initial_dirty, initial_untracked = _source_state()
    if initial_dirty or initial_untracked:
        raise SystemExit("refusing training from dirty or untracked source")
    if initial_head != args.expected_source_git_head:
        raise SystemExit("source commit differs from the external trust root")
    if runtime_identity() != protocol["runtime"]:
        raise SystemExit("runtime differs from the frozen proof environment")
    initial_source_hashes = {name: sha256_file(ROOT / name) for name in lock["source_sha256"]}
    if initial_source_hashes != lock["source_sha256"]:
        raise ValueError("execution source differs from the lock")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch_hash = lock["source_sha256"]["code/jobs/submit_corpus_v4_accuracy_v3.sh"]
    if not executed_batch.is_file() or sha256_file(executed_batch) != expected_batch_hash:
        raise SystemExit("executed batch bytes differ from tracked source")

    training_pin = task_row.get("training_dataset", {})
    if set(training_pin) != {"path", "sha256"}:
        raise ValueError("task training-dataset pin is malformed")
    training_path = args.plan.parent / training_pin["path"]
    dataset = load_training_split_dataset_v3(
        training_path,
        expected_sha256=training_pin["sha256"],
        task_row=task_row,
    )
    samples = _graph_samples(dataset)
    train_ids = list(dataset.train_layout_ids)
    validation_ids = list(dataset.validation_layout_ids)
    if task_row["partition_layout_ids_sha256"]["train"] != _planner_membership_sha256(
        train_ids
    ) or task_row["partition_layout_ids_sha256"]["validation"] != _planner_membership_sha256(
        validation_ids
    ):
        raise ValueError("loader train/validation membership differs from the frozen plan")

    if args.sandbox_probe_only:
        probe_root = args.output_root.parent / "sandbox_probes"
        probe_dir = probe_root / f"job_{scheduler['array_job_id']}"
        probe_path = probe_dir / f"task_{task_id:02d}.json"
        if probe_path.exists():
            raise SystemExit("refusing to overwrite an existing sandbox probe")
        probe_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            probe_path,
            {
                "bindings": {
                    "execution_lock_sha256": lock_sha,
                    "plan_sha256": plan_sha,
                    "protocol_sha256": protocol_sha,
                    "task_manifest_sha256": task_manifest_sha,
                    "training_dataset_sha256": training_pin["sha256"],
                },
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "dataset": {
                    "graph_count": len(samples),
                    "training_layout_count": len(train_ids),
                    "validation_layout_count": len(validation_ids),
                },
                "decision": {
                    "heldout_bytes_opened": False,
                    "sandbox_boundary_passed": True,
                    "training_started": False,
                },
                "provenance": {
                    "executed_batch_script_sha256": expected_batch_hash,
                    "sandbox": sandbox,
                    "scheduler": scheduler,
                    "source_file_sha256": initial_source_hashes,
                    "source_git_head": initial_head,
                },
                "schema": SANDBOX_PROBE_SCHEMA,
                "task": task,
            },
        )
        print(
            json.dumps(
                {
                    "probe_path": probe_path.as_posix(),
                    "schema": SANDBOX_PROBE_SCHEMA,
                    "status": "sandbox-probe-completed",
                },
                sort_keys=True,
            )
        )
        return

    job_root = args.output_root / f"job_{scheduler['array_job_id']}"
    final_dir = job_root / f"task_{task_id:02d}"
    temporary = job_root / f".task_{task_id:02d}.tmp-{scheduler['job_id']}"
    if final_dir.exists() or temporary.exists():
        raise SystemExit("refusing to overwrite an existing task attempt")
    job_root.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    started = time.perf_counter()
    try:
        model, normalizer, curve, work = _train(
            samples,
            train_ids,
            validation_ids,
            init_seed=int(task["init_seed"]),
            protocol=protocol,
        )
        atomic_write_jsonl(temporary / "learning_curve.jsonl", curve)

        # Only validation fixtures enter the pre-acceptance checkpoint.  The
        # SLURM finalizer is the first stage allowed to run test/R4 inference.
        smoke_ids = validation_ids[: int(protocol["checkpoint"]["smoke_examples"])]
        smoke_rows = [
            {
                "geometry_sha256": samples[index]["geometry_sha256"],
                "layout": samples[index]["layout"],
                "layout_id": index,
            }
            for index in smoke_ids
        ]
        atomic_write_jsonl(temporary / "smoke_examples.jsonl", smoke_rows)
        smoke_sha = sha256_file(temporary / "smoke_examples.jsonl")
        arrays = _state_arrays(model, normalizer)
        specs = _array_specs(arrays)
        root_bindings = {
            "execution_lock_sha256": lock_sha,
            "heldout_commitment_sha256": task_row["evaluation_dataset_sha256"],
            "plan_sha256": plan_sha,
            "protocol_sha256": protocol_sha,
            "task_manifest_sha256": task_manifest_sha,
            "training_dataset_sha256": training_pin["sha256"],
        }
        bundle_payload = expected_bundle_payload(task, root_bindings)
        bundle_hashes = write_safe_npz_bundle(
            temporary / "bundle",
            arrays=arrays,
            specs=specs,
            payload=bundle_payload,
            smoke_hook=_smoke_hook(smoke_rows),
            smoke_input_sha256=smoke_sha,
            limits=BundleLimits(
                max_archive_bytes=int(protocol["checkpoint"]["maximum_bundle_bytes"]),
                max_expanded_bytes=int(protocol["checkpoint"]["maximum_uncompressed_bytes"]),
            ),
        )
        load_safe_npz_bundle(
            temporary / "bundle",
            expected_metadata_sha256=bundle_hashes["metadata.json"],
            expected_specs=specs,
            expected_payload=bundle_payload,
            smoke_hook=_smoke_hook(smoke_rows),
            expected_smoke_input_sha256=smoke_sha,
            require_smoke=True,
            limits=BundleLimits(
                max_archive_bytes=int(protocol["checkpoint"]["maximum_bundle_bytes"]),
                max_expanded_bytes=int(protocol["checkpoint"]["maximum_uncompressed_bytes"]),
            ),
        )

        final_head, final_dirty, final_untracked = _source_state()
        final_source_hashes = {name: sha256_file(ROOT / name) for name in lock["source_sha256"]}
        integrity_passed = (
            final_head == initial_head
            and not final_dirty
            and not final_untracked
            and final_source_hashes == initial_source_hashes == lock["source_sha256"]
            and sha256_file(executed_batch) == expected_batch_hash
            and sha256_file(args.protocol) == protocol_sha
            and sha256_file(args.plan) == plan_sha
            and sha256_file(args.task_manifest) == task_manifest_sha
            and sha256_file(args.execution_lock) == lock_sha
            and sha256_file(training_path) == training_pin["sha256"]
            and (
                not retry_enabled
                or sha256_file(args.pending_set) == pending_set_sha256
            )
        )
        if not integrity_passed:
            raise SystemExit("source or frozen input changed during task execution")
        result = {
            "bindings": {
                "execution_lock_sha256": lock_sha,
                "expected_source_git_head": args.expected_source_git_head,
                "heldout_commitment_sha256": task_row["evaluation_dataset_sha256"],
                "plan_sha256": plan_sha,
                "protocol_sha256": protocol_sha,
                "retry_pending_set": None
                if pending_set_sha256 is None
                else {"path": pending_set_path, "sha256": pending_set_sha256},
                "task_manifest_sha256": task_manifest_sha,
                "training_dataset_sha256": training_pin["sha256"],
            },
            "checkpoint": {
                "archive_sha256": bundle_hashes["weights_and_norm.npz"],
                "metadata_sha256": bundle_hashes["metadata.json"],
                "smoke_examples_sha256": smoke_sha,
            },
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "integrity": {"passed": integrity_passed},
            "membership_sha256": {
                "partition_family_ids": task_row["partition_family_ids_sha256"],
                "partition_layout_ids": task_row["partition_layout_ids_sha256"],
                "r4_test_layout_ids": task_row["r4_test_layout_ids_sha256"],
            },
            "evaluation": {
                "heldout_bytes_opened": False,
                "heldout_used_for_normalization_optimization_or_acceptance": False,
                "test_predictions_emitted": False,
            },
            "provenance": {
                "executed_batch_script_sha256": expected_batch_hash,
                "final_git_dirty_paths": final_dirty,
                "final_git_head": final_head,
                "final_source_file_sha256": final_source_hashes,
                "final_untracked_source_paths": final_untracked,
                "git_dirty_paths": initial_dirty,
                "scheduler": scheduler,
                "sandbox": sandbox,
                "software": {
                    **runtime_identity(),
                    "scipy": _package_version("scipy"),
                    "torch_build": torch.__version__,
                },
                "source_file_sha256": initial_source_hashes,
                "source_git_head": initial_head,
                "untracked_source_paths": initial_untracked,
            },
            "schema": TASK_RESULT_SCHEMA,
            "task": task,
            "training": {
                "epochs_completed": len(curve),
                "final_epoch": len(curve),
                "model_selection": "fixed final epoch; validation diagnostic only",
                "wall_s": time.perf_counter() - started,
            },
        }
        atomic_write_json(temporary / "result.json", result)
        artifact_names = (
            "bundle/metadata.json",
            "bundle/weights_and_norm.npz",
            "learning_curve.jsonl",
            "result.json",
            "smoke_examples.jsonl",
        )
        atomic_write_json(temporary / "TASK_MANIFEST.json", build_file_manifest(temporary, artifact_names))
        temporary.replace(final_dir)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    print(json.dumps({"status": "completed", "task_id": task_id, "task_manifest_sha256": sha256_file(final_dir / "TASK_MANIFEST.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
