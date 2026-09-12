"""Authenticated batch-one inference boundary for Corpus V4 latency evidence."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from geometry_contract import validate_layout
from gnn_baseline import PCBParasiticGNN, collate
from planar_to_graph import build_graph_from_planar_layout
from run_corpus_v4_accuracy_task_v3 import (
    _model_from_arrays,
    _normalizer_from_arrays,
    _smoke_hook,
    expected_bundle_payload,
    expected_bundle_specs,
)
from safe_npz_bundle import BundleLimits, load_safe_npz_bundle


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate raw-layout JSON key: {key}")
        value[key] = child
    return value


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite raw-layout JSON constant: {token}")


def canonical_layout_bytes(layout: Mapping[str, Any]) -> bytes:
    """Produce the exact resident-byte boundary frozen by the protocol."""
    return json.dumps(
        dict(layout),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def parse_canonical_layout(raw_layout: bytes) -> dict[str, Any]:
    if not isinstance(raw_layout, bytes) or not raw_layout:
        raise ValueError("raw layout must be non-empty bytes")
    try:
        layout = json.loads(
            raw_layout,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid raw-layout JSON: {exc}") from exc
    if not isinstance(layout, dict) or canonical_layout_bytes(layout) != raw_layout:
        raise ValueError("raw layout is not canonical JSON bytes")
    validate_layout(layout)
    return layout


def load_designated_model(
    *,
    bundle_dir: Path,
    smoke_rows: Sequence[dict[str, Any]],
    smoke_input_sha256: str,
    metadata_sha256: str,
    expected_archive_sha256: str,
    checkpoint_task: Mapping[str, Any],
    accuracy_bindings: Mapping[str, str],
    max_archive_bytes: int,
    max_uncompressed_bytes: int,
) -> tuple[PCBParasiticGNN, Any, dict[str, Any]]:
    """Authenticate, smoke-test, and materialize the predesignated checkpoint."""
    started_ns = time.perf_counter_ns()
    loaded = load_safe_npz_bundle(
        bundle_dir,
        expected_metadata_sha256=metadata_sha256,
        expected_specs=expected_bundle_specs(),
        expected_payload=expected_bundle_payload(checkpoint_task, accuracy_bindings),
        smoke_hook=_smoke_hook(smoke_rows),
        expected_smoke_input_sha256=smoke_input_sha256,
        require_smoke=True,
        limits=BundleLimits(
            max_archive_bytes=max_archive_bytes,
            max_expanded_bytes=max_uncompressed_bytes,
            max_member_expanded_bytes=max_uncompressed_bytes,
        ),
    )
    if loaded.archive_sha256 != expected_archive_sha256:
        raise ValueError("checkpoint archive differs from the externally pinned digest")
    model = _model_from_arrays(loaded.arrays)
    normalizer = _normalizer_from_arrays(loaded.arrays)
    model.eval()
    stop_ns = time.perf_counter_ns()
    if stop_ns <= started_ns:
        raise RuntimeError("checkpoint load timer did not advance monotonically")
    return model, normalizer, {
        "archive_sha256": loaded.archive_sha256,
        "elapsed_ms": (stop_ns - started_ns) / 1e6,
        "metadata_sha256": loaded.metadata_sha256,
        "start_ns": started_ns,
        "stop_ns": stop_ns,
    }


def _normalized_sample(layout: Mapping[str, Any], normalizer: Any) -> dict[str, Any]:
    """Construct the exact normalized sample consumed by the frozen checkpoint."""
    graph = build_graph_from_planar_layout(layout)
    node, edge, edge_index = graph.to_feature_matrices()
    if node.shape[1] != 9 or edge.shape[1] != 7 or edge_index.shape[0] != 2:
        raise ValueError("graph features differ from the checkpoint architecture")
    return {
        "edge_dim": 7,
        "edge_feat": (
            (edge.astype(np.float64) - normalizer.edge_mean) / normalizer.edge_scale
        ).astype(np.float32),
        "edge_index": np.ascontiguousarray(edge_index, dtype=np.int64),
        "node_feat": (
            (node.astype(np.float64) - normalizer.node_mean) / normalizer.node_scale
        ).astype(np.float32),
        "y": np.zeros(4, dtype=np.float32),
    }


def predict_raw_record(
    model: PCBParasiticGNN,
    normalizer: Any,
    raw_layout: bytes,
) -> np.ndarray:
    """Run the complete resident raw-record-to-four-output timing boundary."""
    layout = parse_canonical_layout(raw_layout)
    sample = _normalized_sample(layout, normalizer)
    with torch.no_grad():
        standardized = model(collate([sample])).cpu().numpy()
    output = np.ascontiguousarray(normalizer.inverse(standardized)[0], dtype=np.float64)
    if output.shape != (4,) or any(not math.isfinite(float(value)) for value in output):
        raise ValueError("checkpoint emitted a non-finite or malformed prediction")
    return output


def prepare_model_only_batch(normalizer: Any, raw_layout: bytes) -> Any:
    """Prepare normalized batch-one tensors outside the model-only timer."""
    layout = parse_canonical_layout(raw_layout)
    return collate([_normalized_sample(layout, normalizer)])


def measure_model_only_inference(
    model: PCBParasiticGNN,
    normalizer: Any,
    batch: Any,
    *,
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    """Measure only forward calls from resident graph tensors to resident output."""
    if type(warmups) is not int or warmups < 0:
        raise ValueError("model-only warmups must be a nonnegative integer")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("model-only repetitions must be a positive integer")
    with torch.no_grad():
        for _ in range(warmups):
            model(batch)
        timings_ms: list[float] = []
        standardized_predictions: list[np.ndarray] = []
        for _ in range(repetitions):
            start_ns = time.perf_counter_ns()
            standardized = model(batch)
            stop_ns = time.perf_counter_ns()
            if stop_ns <= start_ns:
                raise RuntimeError("model-only timer did not advance monotonically")
            elapsed_ms = (stop_ns - start_ns) / 1e6
            if not math.isfinite(elapsed_ms) or elapsed_ms <= 0.0:
                raise RuntimeError("model-only latency is not positive and finite")
            timings_ms.append(elapsed_ms)
            standardized_predictions.append(
                np.ascontiguousarray(standardized.cpu().numpy()[0], dtype=np.float64)
            )
    reference = standardized_predictions[0]
    if reference.shape != (4,) or any(
        not np.array_equal(reference, value)
        for value in standardized_predictions[1:]
    ):
        raise RuntimeError("repeated model-only inference changed its prediction")
    physical = np.ascontiguousarray(
        normalizer.inverse(reference.reshape(1, 4))[0], dtype=np.float64
    )
    return {
        "median": float(np.median(np.asarray(timings_ms, dtype=np.float64))),
        "physical_prediction": physical.tolist(),
        "repetitions": timings_ms,
        "timed_repetitions": repetitions,
        "warmups": warmups,
    }


def measure_raw_record_inference(
    model: PCBParasiticGNN,
    normalizer: Any,
    raw_layout: bytes,
    *,
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    if type(warmups) is not int or warmups < 0:
        raise ValueError("warmups must be a nonnegative integer")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    for _ in range(warmups):
        predict_raw_record(model, normalizer, raw_layout)

    timings_ms: list[float] = []
    predictions: list[np.ndarray] = []
    for _ in range(repetitions):
        start_ns = time.perf_counter_ns()
        prediction = predict_raw_record(model, normalizer, raw_layout)
        stop_ns = time.perf_counter_ns()
        if stop_ns <= start_ns:
            raise RuntimeError("inference timer did not advance monotonically")
        elapsed_ms = (stop_ns - start_ns) / 1e6
        if not math.isfinite(elapsed_ms) or elapsed_ms <= 0.0:
            raise RuntimeError("inference latency is not positive and finite")
        timings_ms.append(elapsed_ms)
        predictions.append(prediction)

    reference = predictions[0]
    if any(not np.array_equal(reference, value) for value in predictions[1:]):
        raise RuntimeError("repeated deterministic inference changed its prediction")
    median_ms = float(np.median(np.asarray(timings_ms, dtype=np.float64)))
    return {
        "median_ms": median_ms,
        "prediction": reference.tolist(),
        "repetitions_ms": timings_ms,
        "warmup_repetitions": warmups,
    }


def combine_raw_record_blocks(
    pre_solver: Mapping[str, Any],
    post_solver: Mapping[str, Any],
    *,
    expected_repetitions: int,
    expected_warmups: int,
    block_median_ratio_max: float,
) -> dict[str, Any]:
    """Validate and combine the frozen pre/post raw-record timing blocks."""
    if type(expected_repetitions) is not int or expected_repetitions < 2:
        raise ValueError("expected repetitions must be an integer of at least two")
    if expected_repetitions % 2:
        raise ValueError("expected repetitions must divide equally across two blocks")
    if type(expected_warmups) is not int or expected_warmups < 0:
        raise ValueError("expected warmups must be a nonnegative integer")
    if (
        type(block_median_ratio_max) not in {int, float}
        or not math.isfinite(float(block_median_ratio_max))
        or float(block_median_ratio_max) < 1.0
    ):
        raise ValueError("block-median ratio gate must be finite and at least one")
    expected_fields = {
        "median_ms",
        "prediction",
        "repetitions_ms",
        "warmup_repetitions",
    }
    if set(pre_solver) != expected_fields or set(post_solver) != expected_fields:
        raise ValueError("raw-record timing block fields are not exact")
    if (
        pre_solver["warmup_repetitions"] != expected_warmups
        or post_solver["warmup_repetitions"] != 0
    ):
        raise ValueError("raw-record timing block warmups differ from the protocol")
    if pre_solver["prediction"] != post_solver["prediction"]:
        raise RuntimeError("pre/post solver GNN predictions differ")

    block_size = expected_repetitions // 2
    pre = np.asarray(pre_solver["repetitions_ms"], dtype=np.float64)
    post = np.asarray(post_solver["repetitions_ms"], dtype=np.float64)
    if pre.shape != (block_size,) or post.shape != (block_size,):
        raise ValueError("raw-record timing block counts differ from the protocol")
    if not np.all(np.isfinite(pre)) or not np.all(np.isfinite(post)):
        raise ValueError("raw-record timing blocks contain non-finite values")
    if np.any(pre <= 0.0) or np.any(post <= 0.0):
        raise ValueError("raw-record timing blocks must be strictly positive")

    pre_median = float(np.median(pre))
    post_median = float(np.median(post))
    block_ratio = max(pre_median, post_median) / min(pre_median, post_median)
    if block_ratio > float(block_median_ratio_max):
        raise RuntimeError(
            "GNN pre/post block-median drift exceeds the frozen protocol gate"
        )
    repetitions = np.concatenate((pre, post))
    return {
        "median": float(np.median(repetitions)),
        "post_solver_median": post_median,
        "post_solver_repetitions": post.tolist(),
        "pre_solver_median": pre_median,
        "pre_solver_repetitions": pre.tolist(),
        "repetitions": repetitions.tolist(),
        "timed_repetitions": expected_repetitions,
        "warmups": expected_warmups,
    }
