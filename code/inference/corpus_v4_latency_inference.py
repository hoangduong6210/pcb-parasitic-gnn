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
from run_corpus_v4_accuracy_task import (
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


def predict_raw_record(
    model: PCBParasiticGNN,
    normalizer: Any,
    raw_layout: bytes,
) -> np.ndarray:
    """Run the complete resident raw-record-to-four-output timing boundary."""
    layout = parse_canonical_layout(raw_layout)
    graph = build_graph_from_planar_layout(layout)
    node, edge, edge_index = graph.to_feature_matrices()
    if node.shape[1] != 9 or edge.shape[1] != 7 or edge_index.shape[0] != 2:
        raise ValueError("graph features differ from the checkpoint architecture")
    sample = {
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
    with torch.no_grad():
        standardized = model(collate([sample])).cpu().numpy()
    output = np.ascontiguousarray(normalizer.inverse(standardized)[0], dtype=np.float64)
    if output.shape != (4,) or any(not math.isfinite(float(value)) for value in output):
        raise ValueError("checkpoint emitted a non-finite or malformed prediction")
    return output


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
