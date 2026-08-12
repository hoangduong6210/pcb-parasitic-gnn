#!/usr/bin/env python3
"""Rigorous SLURM-only strict-EGNN versus invariant-MPNN ablation.

The job regenerates one field-grade FastHenry+FEM corpus, then compares two
models using identical train/test splits, scalar preprocessing, optimizer,
epoch budget, and five random seeds:

* invariant MPNN: invariant node/edge scalars and graph topology only;
* strict EGNN: the same scalars plus coordinates, while every learned message
  depends on coordinates only through squared distance.

All target and feature statistics are fit on the active training subset. Raw
per-design predictions, solver outputs, timing repeats, and hierarchical
bootstrap samples are retained for claim traceability.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn as nn

from fasthenry_ref import FASTHENRY, fasthenry_totals
from gnn_baseline import (
    GraphBatch,
    _scatter_max,
    _scatter_mean,
    _scatter_sum,
    collate,
)
from runtime_paths import fem_cps_worker_path
from planar_to_graph import build_graph_from_planar_layout
from pipeline import TARGETS, load_dataset


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
DATA_ROOT = Path(os.environ.get("PCB_GNN_DATA_ROOT", ROOT / "datasets")).resolve()
SCHEMA = "research13.strict-egnn-ablation.v2"
# Distance is intentionally excluded: both models recompute ||x_i-x_j||^2
# from coordinates, so the invariant baseline and strict EGNN receive exactly
# one geometry channel and cannot exploit a duplicated, independently scaled
# distance feature. The retained columns are overlap and the two edge flags.
EDGE_COLUMNS = (1, 5, 6)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-candidates", type=int, default=346)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44, 45, 46])
    parser.add_argument("--caps", type=int, nargs="+", default=[25, 50, 100, 200, 0])
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--strict-hidden", type=int, default=96)
    parser.add_argument("--fem-refine", type=int, default=1)
    parser.add_argument("--fem-timeout-s", type=int, default=90)
    parser.add_argument("--bootstrap-resamples", type=int, default=10_000)
    parser.add_argument("--timing-repeats", type=int, default=100)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--equivalence-margin-pct", type=float, default=2.0)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_key(path: Path) -> str:
    """Return a portable provenance label without exposing checkout paths."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return "dataset/" + resolved.relative_to(DATA_ROOT).as_posix()
        except ValueError:
            return "external/" + resolved.name


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def count_params(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


def percentile_summary(values: list[float] | np.ndarray) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": int(array.size),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "std": float(array.std()),
        "p05": float(np.percentile(array, 5)),
        "p95": float(np.percentile(array, 95)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def timed_call(function: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter_ns()
    value = function()
    return value, (time.perf_counter_ns() - started) / 1e6


def safe_fem_cps(layout: dict[str, Any], refine: int, timeout_s: int) -> float | None:
    descriptor, json_path = tempfile.mkstemp(suffix=".json")
    os.close(descriptor)
    path = Path(json_path)
    try:
        path.write_text(json.dumps(layout))
        result = subprocess.run(
            [sys.executable, str(fem_cps_worker_path()), str(path), str(refine)],
            cwd=fem_cps_worker_path().parent,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        for line in result.stdout.splitlines():
            if line.startswith("CPS="):
                return float(line[4:])
        return None
    except (subprocess.TimeoutExpired, ValueError):
        return None
    finally:
        path.unlink(missing_ok=True)


def make_sample(
    layout_id: int | str | None,
    layout: dict[str, Any],
    cps_pf: float,
    fh: dict[str, float],
) -> dict[str, Any]:
    graph = build_graph_from_planar_layout(layout)
    node_feat, edge_feat, edge_index = graph.to_feature_matrices()
    return {
        "layout_id": layout_id,
        "layout": layout,
        "node_feat": node_feat.astype(np.float32),
        "edge_feat": edge_feat.astype(np.float32),
        "edge_index": edge_index.astype(np.int64),
        "edge_dim": 7,
        "y": np.asarray(
            [cps_pf, fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]],
            dtype=np.float32,
        ),
    }


class SymmetryPreservingNorm:
    """Train-only scalar normalization plus one isotropic coordinate scale."""

    def __init__(self, samples: list[dict[str, Any]], train_indices: list[int]) -> None:
        targets = np.stack([samples[index]["y"] for index in train_indices])
        target_log = np.sign(targets) * np.log1p(np.abs(targets))
        self.target_mean = target_log.mean(0)
        self.target_std = target_log.std(0) + 1e-8

        node_scalars = np.concatenate(
            [samples[index]["node_feat"][:, 3:] for index in train_indices], axis=0
        )
        self.node_mean = node_scalars.mean(0)
        self.node_std = node_scalars.std(0) + 1e-6

        edge_parts = [
            samples[index]["edge_feat"][:, EDGE_COLUMNS]
            for index in train_indices
            if samples[index]["edge_feat"].size
        ]
        edge_scalars = np.concatenate(edge_parts, axis=0) if edge_parts else np.zeros((1, 3))
        self.edge_mean = edge_scalars.mean(0)
        self.edge_std = edge_scalars.std(0) + 1e-6

        distances = np.concatenate(
            [
                samples[index]["edge_feat"][:, 0]
                for index in train_indices
                if samples[index]["edge_feat"].size
            ]
        )
        self.coordinate_scale = float(np.sqrt(np.mean(distances ** 2)) + 1e-6)

    def transform(self, sample: dict[str, Any]) -> dict[str, Any]:
        nodes = np.asarray(sample["node_feat"], dtype=np.float32)
        coordinates = nodes[:, :3] / self.coordinate_scale
        scalars = (nodes[:, 3:] - self.node_mean) / self.node_std
        edge_raw = np.asarray(sample["edge_feat"], dtype=np.float32)
        if edge_raw.size:
            edge_scalars = (edge_raw[:, EDGE_COLUMNS] - self.edge_mean) / self.edge_std
        else:
            edge_scalars = np.zeros((0, 3), dtype=np.float32)
        target = np.asarray(sample["y"], dtype=np.float32)
        target_log = np.sign(target) * np.log1p(np.abs(target))
        return {
            "node_feat": np.concatenate([coordinates, scalars], axis=1).astype(np.float32),
            "edge_feat": edge_scalars.astype(np.float32),
            "edge_index": np.asarray(sample["edge_index"], dtype=np.int64),
            "edge_dim": 3,
            "y": ((target_log - self.target_mean) / self.target_std).astype(np.float32),
        }

    def inverse_target(self, standardized: np.ndarray) -> np.ndarray:
        logged = standardized * self.target_std + self.target_mean
        return np.sign(logged) * np.expm1(np.abs(logged))

    def serializable(self) -> dict[str, Any]:
        return {
            "target_mean": self.target_mean.tolist(),
            "target_std": self.target_std.tolist(),
            "node_mean": self.node_mean.tolist(),
            "node_std": self.node_std.tolist(),
            "edge_mean": self.edge_mean.tolist(),
            "edge_std": self.edge_std.tolist(),
            "coordinate_scale": self.coordinate_scale,
        }


class DistanceMessageLayer(nn.Module):
    """Shared scalar-message layer used by both ablation arms.

    Every learned message consumes ``[h_i, h_j, ||x_i-x_j||^2, edge_meta]``.
    Consequently scalar states are invariant under all orthogonal transforms
    and translations. Only the strict arm enables the equivariant coordinate
    update; keeping the message and node-update paths identical isolates that
    architectural choice.
    """

    def __init__(self, hidden: int, edge_dim: int, update_coordinates: bool) -> None:
        super().__init__()
        self.update_coordinates = update_coordinates
        self.msg = nn.Sequential(
            nn.Linear(2 * hidden + 1 + edge_dim, hidden),
            nn.SiLU(),
            nn.Linear(hidden, hidden),
            nn.SiLU(),
        )
        self.coord = (
            nn.Sequential(
                nn.Linear(hidden, hidden), nn.SiLU(), nn.Linear(hidden, 1)
            )
            if update_coordinates
            else None
        )
        self.upd = nn.Sequential(
            nn.Linear(2 * hidden, hidden), nn.SiLU(), nn.Linear(hidden, hidden)
        )
        self.norm = nn.LayerNorm(hidden)

    def forward(
        self,
        hidden: torch.Tensor,
        coordinates: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if edge_index.shape[1] == 0:
            aggregate = torch.zeros_like(hidden)
        else:
            source, destination = edge_index[0], edge_index[1]
            relative = coordinates[source] - coordinates[destination]
            distance_squared = (relative * relative).sum(-1, keepdim=True)
            messages = self.msg(
                torch.cat(
                    [hidden[source], hidden[destination], distance_squared, edge_attr],
                    dim=-1,
                )
            )
            aggregate = _scatter_mean(messages, destination, hidden.shape[0])
            if self.coord is not None:
                # Bounded radial displacement; the scalar coefficient is
                # invariant, while the relative vector transforms equivariantly.
                weight = 0.1 * torch.tanh(self.coord(messages))
                bounded_relative = relative / (distance_squared.sqrt() + 1.0)
                coordinates = coordinates + _scatter_mean(
                    bounded_relative * weight, destination, hidden.shape[0]
                )
        hidden = hidden + self.upd(torch.cat([hidden, aggregate], dim=-1))
        return self.norm(hidden), coordinates


class ScalarDistanceGNN(nn.Module):
    """Common implementation for invariant and strict-EGNN ablation arms."""

    def __init__(
        self,
        hidden: int,
        update_coordinates: bool,
        n_layers: int = 4,
        n_targets: int = 4,
    ) -> None:
        super().__init__()
        self.update_coordinates = update_coordinates
        self.node_enc = nn.Sequential(
            nn.Linear(6, hidden), nn.SiLU(), nn.Linear(hidden, hidden)
        )
        self.edge_enc = nn.Sequential(
            nn.Linear(3, hidden), nn.SiLU(), nn.Linear(hidden, 3)
        )
        self.layers = nn.ModuleList(
            [DistanceMessageLayer(hidden, 3, update_coordinates) for _ in range(n_layers)]
        )
        self.head = nn.Sequential(
            nn.Linear(3 * hidden, hidden),
            nn.SiLU(),
            nn.Linear(hidden, hidden),
            nn.SiLU(),
            nn.Linear(hidden, n_targets),
        )

    def forward_states(
        self, batch: GraphBatch
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        coordinates = batch.node_feat[:, :3].clone()
        hidden = self.node_enc(batch.node_feat[:, 3:])
        edges = self.edge_enc(batch.edge_feat) if batch.edge_feat.shape[0] else batch.edge_feat
        for layer in self.layers:
            hidden, coordinates = layer(hidden, coordinates, batch.edge_index, edges)
        graph_mean = _scatter_mean(hidden, batch.batch_index, batch.n_graphs)
        graph_max = _scatter_max(hidden, batch.batch_index, batch.n_graphs)
        graph_sum = _scatter_sum(hidden, batch.batch_index, batch.n_graphs)
        graph_sum = torch.sign(graph_sum) * torch.log1p(graph_sum.abs())
        output = self.head(torch.cat([graph_mean, graph_max, graph_sum], dim=-1))
        return output, hidden, coordinates

    def forward(self, batch: GraphBatch) -> torch.Tensor:
        return self.forward_states(batch)[0]


class InvariantScalarMPNN(ScalarDistanceGNN):
    """Invariant baseline with fixed coordinates and scalar distance messages."""

    def __init__(self, hidden: int, n_layers: int = 4, n_targets: int = 4) -> None:
        super().__init__(hidden, False, n_layers, n_targets)


class StrictScalarEGNN(ScalarDistanceGNN):
    """Strict E(3)-equivariant coordinate updates with scalar messages only."""

    def __init__(self, hidden: int, n_layers: int = 4, n_targets: int = 4) -> None:
        super().__init__(hidden, True, n_layers, n_targets)


def matched_baseline_hidden(strict_hidden: int) -> tuple[int, dict[str, int | float]]:
    """Widen the baseline until its budget most closely matches strict EGNN."""
    strict_params = count_params(StrictScalarEGNN(strict_hidden))
    candidates = []
    for hidden in range(max(16, strict_hidden - 8), strict_hidden + 33):
        params = count_params(InvariantScalarMPNN(hidden))
        candidates.append((abs(params - strict_params), hidden, params))
    _, baseline_hidden, baseline_params = min(candidates)
    return baseline_hidden, {
        "strict_hidden": strict_hidden,
        "strict_params": strict_params,
        "matched_baseline_hidden": baseline_hidden,
        "matched_baseline_params": baseline_params,
        "matched_baseline_minus_strict_pct":
            (baseline_params - strict_params) / strict_params * 100,
        "same_width_baseline_hidden": strict_hidden,
        "same_width_baseline_params": count_params(InvariantScalarMPNN(strict_hidden)),
    }


def split_indices(n_samples: int, seed: int) -> tuple[list[int], list[int]]:
    rng = np.random.default_rng(seed)
    indices = np.arange(n_samples)
    rng.shuffle(indices)
    n_test = max(1, int(0.2 * n_samples))
    return list(map(int, indices[n_test:])), list(map(int, indices[:n_test]))


def train_model(
    model: nn.Module,
    work: list[dict[str, Any]],
    train_indices: list[int],
    seed: int,
    epochs: int,
    batch_size: int,
) -> tuple[nn.Module, float]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_function = nn.SmoothL1Loss()
    rng = np.random.default_rng(seed + 1009)
    started = time.perf_counter()
    for _ in range(epochs):
        model.train()
        order = np.asarray(train_indices, dtype=np.int64).copy()
        rng.shuffle(order)
        for offset in range(0, len(order), batch_size):
            batch = collate([work[int(index)] for index in order[offset:offset + batch_size]])
            optimizer.zero_grad()
            loss = loss_function(model(batch), batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        scheduler.step()
    model.eval()
    return model, time.perf_counter() - started


def evaluate(
    model: nn.Module,
    normalizer: SymmetryPreservingNorm,
    work: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    test_indices: list[int],
) -> tuple[dict[str, Any], list[dict[str, Any]], np.ndarray]:
    predictions = []
    references = []
    rows = []
    with torch.no_grad():
        for index in test_indices:
            standardized = model(collate([work[index]])).numpy()[0]
            prediction = normalizer.inverse_target(standardized)
            reference = np.asarray(samples[index]["y"], dtype=np.float32)
            predictions.append(prediction)
            references.append(reference)
            rows.append({
                "sample_index": index,
                "layout_id": samples[index]["layout_id"],
                "prediction": prediction.tolist(),
                "reference": reference.tolist(),
            })
    pred = np.stack(predictions)
    ref = np.stack(references)
    relative_pct = np.abs(pred - ref) / (np.abs(ref) + 1e-9) * 100
    log_error = np.abs(np.log1p(np.maximum(pred, 0.0)) - np.log1p(np.maximum(ref, 0.0)))
    metrics: dict[str, Any] = {
        "n_test": len(test_indices),
        "primary_mean_absolute_log_error": float(log_error.mean()),
        "macro_median_relative_error_pct": float(np.median(relative_pct)),
        "negative_prediction_rate": float(np.mean(pred < 0.0)),
    }
    for column, target in enumerate(TARGETS):
        residual = pred[:, column] - ref[:, column]
        denominator = np.sum((ref[:, column] - ref[:, column].mean()) ** 2) + 1e-12
        metrics[target] = {
            "r2": float(1.0 - np.sum(residual ** 2) / denominator),
            "mae": float(np.mean(np.abs(residual))),
            "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "median_relative_error_pct": float(np.median(relative_pct[:, column])),
            "mean_relative_error_pct": float(np.mean(relative_pct[:, column])),
            "p95_relative_error_pct": float(np.percentile(relative_pct[:, column], 95)),
        }
    return metrics, rows, log_error.mean(axis=1)


def benchmark(
    model: nn.Module,
    normalizer: SymmetryPreservingNorm,
    work: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    test_indices: list[int],
    repeats: int,
) -> dict[str, Any]:
    batch = collate([work[index] for index in test_indices])
    with torch.no_grad():
        for _ in range(10):
            model(batch)
        batch_ms = [timed_call(lambda: model(batch))[1] for _ in range(repeats)]
        single_ms = []
        for index in test_indices:
            one = collate([work[index]])
            for _ in range(2):
                model(one)
            single_ms.extend(timed_call(lambda one=one: model(one))[1] for _ in range(3))

        # End-to-end single-design timing starts from the raw planar layout and
        # includes graph construction, normalization, collation, forward pass,
        # and inverse target transform. Three passes/design limit job overhead;
        # the primary throughput benchmark above retains 100 raw repeats.
        end_to_end_ms = []
        for index in test_indices:
            sample = samples[index]

            def end_to_end() -> np.ndarray:
                raw = make_sample(
                    sample["layout_id"], sample["layout"], 0.0,
                    {"L_pri_nH": 0.0, "L_sec_nH": 0.0, "L_mut_nH": 0.0},
                )
                standardized = model(collate([normalizer.transform(raw)])).numpy()[0]
                return normalizer.inverse_target(standardized)

            end_to_end_ms.extend(timed_call(end_to_end)[1] for _ in range(3))
    return {
        "batch_size": len(test_indices),
        "precollated_batch_total_ms": percentile_summary(batch_ms),
        "precollated_batch_ms_per_design": percentile_summary(
            np.asarray(batch_ms) / len(test_indices)
        ),
        "single_forward_ms": percentile_summary(single_ms),
        "raw_layout_end_to_end_ms": percentile_summary(end_to_end_ms),
        "raw_ms": {
            "batch_total": batch_ms,
            "single_forward": single_ms,
            "raw_layout_end_to_end": end_to_end_ms,
        },
    }


def random_orthogonal(rng: np.random.Generator, determinant: int) -> np.ndarray:
    matrix = rng.standard_normal((3, 3))
    orthogonal, _ = np.linalg.qr(matrix)
    if np.linalg.det(orthogonal) * determinant < 0:
        orthogonal[:, 0] *= -1
    return orthogonal.astype(np.float32)


def symmetry_check(
    model: ScalarDistanceGNN,
    work: list[dict[str, Any]],
    test_indices: list[int],
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed + 7001)
    residuals = []
    model.eval()
    with torch.no_grad():
        for index in test_indices[:20]:
            base_sample = work[index]
            base_output, _, base_coordinates = model.forward_states(collate([base_sample]))
            for determinant in (+1, -1):
                orthogonal = random_orthogonal(rng, determinant)
                translation = rng.uniform(-2.0, 2.0, size=3).astype(np.float32)
                changed = dict(base_sample)
                nodes = np.asarray(base_sample["node_feat"], dtype=np.float32).copy()
                nodes[:, :3] = nodes[:, :3] @ orthogonal.T + translation
                changed["node_feat"] = nodes
                output, _, coordinates = model.forward_states(collate([changed]))
                expected = base_coordinates @ torch.as_tensor(orthogonal).T + torch.as_tensor(translation)
                residuals.append({
                    "sample_index": index,
                    "determinant": determinant,
                    "output_relative_residual": float(
                        (torch.linalg.vector_norm(output - base_output)
                         / torch.linalg.vector_norm(base_output).clamp_min(1e-12)).item()
                    ),
                    "coordinate_relative_residual": float(
                        (torch.linalg.vector_norm(coordinates - expected)
                         / torch.linalg.vector_norm(expected).clamp_min(1e-12)).item()
                    ),
                })
    output_values = [row["output_relative_residual"] for row in residuals]
    coordinate_values = [row["coordinate_relative_residual"] for row in residuals]
    tolerance = 2e-5
    return {
        "n_cases": len(residuals),
        "tolerance": tolerance,
        "output_relative_residual": percentile_summary(output_values),
        "coordinate_relative_residual": percentile_summary(coordinate_values),
        "strict_pass": max(output_values) <= tolerance and (
            not model.update_coordinates or max(coordinate_values) <= tolerance
        ),
        "cases": residuals,
    }


def hierarchical_paired_bootstrap(
    baseline_by_seed: list[np.ndarray],
    strict_by_seed: list[np.ndarray],
    resamples: int,
    seed: int,
    equivalence_margin_pct: float,
    baseline_label: str = "matched invariant baseline",
) -> dict[str, Any]:
    """Paired seed/design bootstrap with absolute and relative effects."""
    if len(baseline_by_seed) != len(strict_by_seed):
        raise ValueError("paired bootstrap requires equal seed counts")
    rng = np.random.default_rng(seed)
    observed_baseline = float(np.mean([values.mean() for values in baseline_by_seed]))
    observed_strict = float(np.mean([values.mean() for values in strict_by_seed]))
    observed_delta = observed_strict - observed_baseline
    observed_relative = observed_delta / observed_baseline * 100.0
    boot_absolute = np.empty(resamples, dtype=np.float64)
    boot_relative = np.empty(resamples, dtype=np.float64)
    for iteration in range(resamples):
        seed_choices = rng.integers(0, len(baseline_by_seed), len(baseline_by_seed))
        baseline_seed_means = []
        strict_seed_means = []
        for selected_seed in seed_choices:
            baseline = baseline_by_seed[int(selected_seed)]
            strict = strict_by_seed[int(selected_seed)]
            design_choices = rng.integers(0, len(baseline), len(baseline))
            baseline_seed_means.append(float(baseline[design_choices].mean()))
            strict_seed_means.append(float(strict[design_choices].mean()))
        baseline_mean = float(np.mean(baseline_seed_means))
        strict_mean = float(np.mean(strict_seed_means))
        boot_absolute[iteration] = strict_mean - baseline_mean
        boot_relative[iteration] = (strict_mean - baseline_mean) / baseline_mean * 100.0

    relative_ci_95 = [
        float(np.percentile(boot_relative, 2.5)),
        float(np.percentile(boot_relative, 97.5)),
    ]
    relative_ci_90 = [
        float(np.percentile(boot_relative, 5.0)),
        float(np.percentile(boot_relative, 95.0)),
    ]
    margin = float(equivalence_margin_pct)
    if relative_ci_95[1] < -margin:
        verdict = "strict_practical_improvement"
    elif relative_ci_95[0] > margin:
        verdict = "strict_practical_worsening"
    elif relative_ci_90[0] >= -margin and relative_ci_90[1] <= margin:
        verdict = "practically_equivalent_within_predeclared_margin"
    elif relative_ci_95[1] < 0.0:
        verdict = "strict_statistical_improvement_but_practical_margin_unresolved"
    elif relative_ci_95[0] > 0.0:
        verdict = "strict_statistical_worsening_but_practical_margin_unresolved"
    else:
        verdict = "inconclusive"
    return {
        "definition": f"strict minus {baseline_label} in per-design mean absolute log1p error; negative favors strict EGNN",
        "observed_baseline": observed_baseline,
        "observed_strict": observed_strict,
        "observed_absolute_delta": observed_delta,
        "absolute_delta_95pct_ci": [
            float(np.percentile(boot_absolute, 2.5)),
            float(np.percentile(boot_absolute, 97.5)),
        ],
        "observed_relative_delta_pct": observed_relative,
        "relative_delta_95pct_ci": relative_ci_95,
        "relative_delta_90pct_ci_for_equivalence": relative_ci_90,
        "predeclared_equivalence_margin_pct": [-margin, margin],
        "verdict": verdict,
        "probability_relative_delta_below_zero": float(np.mean(boot_relative < 0.0)),
        "resamples": resamples,
        "resampling_units": "seed, then design within seed",
        "raw_bootstrap_absolute_deltas": boot_absolute.tolist(),
        "raw_bootstrap_relative_deltas_pct": boot_relative.tolist(),
    }


def paired_seed_bootstrap(
    baseline: list[float], strict: list[float], resamples: int, seed: int
) -> dict[str, Any]:
    """Seed bootstrap for one scalar summary per seed (for normalized AULC)."""
    baseline_array = np.asarray(baseline, dtype=np.float64)
    strict_array = np.asarray(strict, dtype=np.float64)
    rng = np.random.default_rng(seed)
    boot = np.empty(resamples, dtype=np.float64)
    for iteration in range(resamples):
        choices = rng.integers(0, len(baseline_array), len(baseline_array))
        baseline_mean = float(baseline_array[choices].mean())
        strict_mean = float(strict_array[choices].mean())
        boot[iteration] = (strict_mean - baseline_mean) / baseline_mean * 100.0
    return {
        "definition": "strict minus matched invariant normalized area under learning curve; negative favors strict",
        "baseline_seed_values": baseline,
        "strict_seed_values": strict,
        "observed_relative_delta_pct": float(
            (strict_array.mean() - baseline_array.mean()) / baseline_array.mean() * 100.0
        ),
        "relative_delta_95pct_ci": [
            float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
        ],
        "resamples": resamples,
        "raw_bootstrap_relative_deltas_pct": boot.tolist(),
    }


def provenance(args: argparse.Namespace) -> dict[str, Any]:
    tracked = [
        Path(__file__), CODE / "models" / "gnn" / "gnn_baseline.py",
        CODE / "models" / "gnn" / "gnn_equivariant.py",
        CODE / "core" / "pcb_graph.py", CODE / "core" / "planar_to_graph.py",
        CODE / "solvers" / "fasthenry_ref.py", CODE / "solvers" / "fem_cps_worker.py",
        CODE / "solvers" / "fem_capacitance_3d.py",
        DATA_ROOT / "synth_v2" / "layouts.jsonl",
        DATA_ROOT / "synth_v2" / "labels.json",
        DATA_ROOT / "synth_v2" / "meta.json",
        Path(FASTHENRY),
    ]
    cpu = "unknown"
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.lower().startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
        "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
        "slurm_node_list": os.environ.get("SLURM_JOB_NODELIST"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_model": cpu,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "package_versions": {
            package: package_version(package)
            for package in ("scipy", "scikit-fem", "gmsh", "meshio")
        },
        "torch_num_threads": torch.get_num_threads(),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "git_head": git_output("rev-parse", "HEAD"),
        "git_dirty_paths": git_output(
            "status", "--short", "--untracked-files=no"
        ).splitlines(),
        "arguments": vars(args),
        "sha256": {artifact_key(path): sha256(path) for path in tracked},
    }


def main() -> None:
    args = parse_args()
    matched_hidden, parameter_match = matched_baseline_hidden(args.strict_hidden)
    if args.validate_only:
        print(json.dumps({
            "schema": SCHEMA, "status": "validation-ok",
            "parameter_match": parameter_match,
        }))
        return
    job_id = os.environ.get("SLURM_JOB_ID")
    if not job_id:
        raise SystemExit("Submit submit_strict_egnn_ablation.sh; no solves/training on login")

    output_dir = ROOT / "results" / "proof_updates" / "jobs" / "strict_e3" / f"job_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    field_path = output_dir / "field_grade_targets.jsonl"
    partial_path = output_dir / "partial_results.json"
    result_path = output_dir / "results_strict_egnn_ablation.json"

    layouts, _, _ = load_dataset(DATA_ROOT / "synth_v2")
    candidates = [
        record for record in layouts
        if any(trace["net"] == "pri" for trace in record["layout"]["traces"])
        and any(trace["net"] == "sec" for trace in record["layout"]["traces"])
        and len(record["layout"]["traces"]) <= 28
    ][:args.max_candidates]

    samples = []
    field_records = []
    solver_started = time.perf_counter()
    with field_path.open("w") as handle:
        for ordinal, record in enumerate(candidates):
            layout = record["layout"]
            fh, fh_ms = timed_call(lambda layout=layout: fasthenry_totals(layout, 1e5))
            cps, fem_ms = timed_call(
                lambda layout=layout: safe_fem_cps(
                    layout, args.fem_refine, args.fem_timeout_s
                )
            )
            valid = bool(fh and fh.get("L_mut_nH", 0.0) > 0 and cps and cps > 0)
            target = None
            if valid:
                sample = make_sample(record.get("id"), layout, float(cps), fh)
                samples.append(sample)
                target = sample["y"].tolist()
            field_record = {
                "ordinal": ordinal, "layout_id": record.get("id"),
                "fasthenry_ms": fh_ms, "fem_ms": fem_ms,
                "paired_solver_ms": fh_ms + fem_ms, "valid": valid,
                "target": target,
            }
            field_records.append(field_record)
            handle.write(json.dumps(field_record) + "\n")
            handle.flush()
            print(
                f"[solver {ordinal + 1:03d}/{len(candidates)}] "
                f"id={record.get('id')} FH={fh_ms:.1f}ms FEM={fem_ms:.1f}ms valid={valid}",
                flush=True,
            )
    solver_wall_s = time.perf_counter() - solver_started
    if len(samples) < 50:
        raise RuntimeError(f"Only {len(samples)} valid field-grade samples")

    caps = [None if cap == 0 else int(cap) for cap in args.caps]
    if caps[-1] is not None or any(cap is None for cap in caps[:-1]):
        raise ValueError("--caps must contain one terminal 0 representing full data")
    full_train, test_indices = split_indices(len(samples), args.split_seed)
    run_results = []
    paired_errors: dict[str, dict[str, list[np.ndarray]]] = {
        "full" if cap is None else str(cap): {
            "invariant_matched": [], "strict_egnn": []
        }
        for cap in caps
    }
    learning_curve: dict[str, dict[int, dict[str, tuple[int, float]]]] = {
        "invariant_matched": {}, "strict_egnn": {}
    }
    full_models: dict[str, list[dict[str, Any]]] = {
        "invariant_matched": [], "strict_egnn": [], "invariant_same_width": []
    }
    sensitivity_errors: dict[str, list[np.ndarray]] = {
        "invariant_same_width": [], "strict_egnn": []
    }
    for seed in args.seeds:
        learning_curve["invariant_matched"][seed] = {}
        learning_curve["strict_egnn"][seed] = {}
        for cap in caps:
            cap_key = "full" if cap is None else str(cap)
            active_train = full_train if cap is None else full_train[:min(cap, len(full_train))]
            normalizer = SymmetryPreservingNorm(samples, active_train)
            work = [normalizer.transform(sample) for sample in samples]
            model_outputs: dict[str, tuple[dict[str, Any], np.ndarray]] = {}
            model_names = ["invariant_matched", "strict_egnn"]
            if cap is None and matched_hidden != args.strict_hidden:
                model_names.append("invariant_same_width")
            for model_name in model_names:
                torch.manual_seed(seed)
                model: nn.Module
                if model_name == "strict_egnn":
                    model = StrictScalarEGNN(args.strict_hidden)
                elif model_name == "invariant_matched":
                    model = InvariantScalarMPNN(matched_hidden)
                else:
                    model = InvariantScalarMPNN(args.strict_hidden)
                model, train_s = train_model(
                    model, work, active_train, seed, args.epochs, args.batch_size
                )
                metrics, predictions, design_log_error = evaluate(
                    model, normalizer, work, samples, test_indices
                )
                record: dict[str, Any] = {
                    "seed": seed, "train_cap": cap_key, "model": model_name,
                    "n_train": len(active_train), "n_test": len(test_indices),
                    "train_indices": active_train, "test_indices": test_indices,
                    "params": count_params(model), "training_wall_s": train_s,
                    "metrics": metrics, "predictions": predictions,
                    "normalizer": normalizer.serializable(),
                }
                if cap is None:
                    # One fully traced timing run per architecture avoids using
                    # initialization noise as fake hardware replication.
                    if seed == args.seeds[0]:
                        record["timing"] = benchmark(
                            model, normalizer, work, samples, test_indices,
                            args.timing_repeats,
                        )
                    record["symmetry_check"] = symmetry_check(
                        model, work, test_indices, seed
                    )
                    if not record["symmetry_check"]["strict_pass"]:
                        raise RuntimeError(
                            f"Symmetry check failed for {model_name} at seed {seed}"
                        )
                    full_models[model_name].append({
                        "seed": seed,
                        "state_dict": model.state_dict(),
                        "normalizer": normalizer.serializable(),
                    })
                run_results.append(record)
                model_outputs[model_name] = (metrics, design_log_error)
                if model_name in learning_curve:
                    learning_curve[model_name][seed][cap_key] = (
                        len(active_train), metrics["primary_mean_absolute_log_error"]
                    )
                print(
                    f"[train] seed={seed} cap={cap_key} model={model_name} "
                    f"MALE={metrics['primary_mean_absolute_log_error']:.6f} "
                    f"macroMdRE={metrics['macro_median_relative_error_pct']:.3f}% "
                    f"wall={train_s:.1f}s",
                    flush=True,
                )
            paired_errors[cap_key]["invariant_matched"].append(
                model_outputs["invariant_matched"][1]
            )
            paired_errors[cap_key]["strict_egnn"].append(
                model_outputs["strict_egnn"][1]
            )
            if cap is None and "invariant_same_width" in model_outputs:
                sensitivity_errors["invariant_same_width"].append(
                    model_outputs["invariant_same_width"][1]
                )
                sensitivity_errors["strict_egnn"].append(
                    model_outputs["strict_egnn"][1]
                )
            partial_path.write_text(json.dumps({
                "schema": SCHEMA, "job_id": job_id,
                "completed_runs": run_results,
            }, indent=2) + "\n")

    paired_analysis = {
        cap_key: hierarchical_paired_bootstrap(
            values["invariant_matched"], values["strict_egnn"],
            args.bootstrap_resamples, seed=20260812 + offset,
            equivalence_margin_pct=args.equivalence_margin_pct,
        )
        for offset, (cap_key, values) in enumerate(paired_errors.items())
    }
    sensitivity_analysis = (
        hierarchical_paired_bootstrap(
            sensitivity_errors["invariant_same_width"],
            sensitivity_errors["strict_egnn"],
            args.bootstrap_resamples,
            seed=20260901,
            equivalence_margin_pct=args.equivalence_margin_pct,
            baseline_label="same-width invariant baseline",
        )
        if sensitivity_errors["invariant_same_width"]
        else {"not_run": "matched baseline and strict EGNN have identical width"}
    )

    aulc_by_model: dict[str, list[float]] = {
        "invariant_matched": [], "strict_egnn": []
    }
    aulc_rows = []
    for seed in args.seeds:
        for model_name in ("invariant_matched", "strict_egnn"):
            ordered = [learning_curve[model_name][seed]["full" if cap is None else str(cap)] for cap in caps]
            n_train = np.asarray([row[0] for row in ordered], dtype=np.float64)
            errors = np.asarray([row[1] for row in ordered], dtype=np.float64)
            x = np.log2(n_train)
            normalized_area = float(np.trapezoid(errors, x=x) / (x[-1] - x[0]))
            aulc_by_model[model_name].append(normalized_area)
            aulc_rows.append({
                "seed": seed, "model": model_name,
                "n_train": n_train.astype(int).tolist(),
                "primary_errors": errors.tolist(),
                "normalized_log2_n_area": normalized_area,
            })
    sample_efficiency = {
        "definition": "normalized trapezoidal area of primary error versus log2(n_train); lower is better",
        "curves": aulc_rows,
        "paired_analysis": paired_seed_bootstrap(
            aulc_by_model["invariant_matched"],
            aulc_by_model["strict_egnn"],
            args.bootstrap_resamples,
            seed=20260902,
        ),
    }

    verdict = paired_analysis["full"]["verdict"]

    valid_solver_ms = [row["paired_solver_ms"] for row in field_records if row["valid"]]
    results = {
        "provenance": provenance(args),
        "protocol": {
            "models": {
                "invariant_matched": "node scalars [w,l,t,log_sigma,eps_r,layer], edge metadata [overlap,kind flags], and squared distance recomputed from fixed coordinates; no coordinate update",
                "strict_egnn": "identical scalar/message/update path; learned messages depend on coordinates only through squared distance; coordinate updates use invariant weights times relative vectors",
                "invariant_same_width": "full-data sensitivity arm with the strict model's hidden width; omitted only if already parameter matched",
            },
            "parameter_match": parameter_match,
            "seeds": args.seeds,
            "train_caps": ["full" if cap is None else cap for cap in caps],
            "epochs": args.epochs,
            "split_seed": args.split_seed,
            "split": "one fixed random 80/20 split shared across all initialization seeds and models; caps are nested prefixes of the fixed full training split",
            "normalization": "all target/node/edge statistics fit on active training subset; coordinates divided by one train-derived invariant scalar",
            "primary_metric": "per-design mean absolute log1p error averaged across four targets",
            "primary_inference": "paired hierarchical bootstrap over initialization seed, then fixed test design",
            "equivalence_test": f"two one-sided 90% bootstrap CI within predeclared relative margin +/-{args.equivalence_margin_pct}%",
            "scope_of_symmetry_claim": "strict E(3) equivariance/invariance on the already encoded graph with stored overlap and edge-kind scalars held fixed; the axis-aligned planar-layout-to-graph builder is outside this claim",
        },
        "corpus": {
            "n_candidates": len(candidates), "n_valid": len(samples),
            "n_failed": len(candidates) - len(samples),
            "solver_wall_s": solver_wall_s,
            "paired_solver_ms": percentile_summary(valid_solver_ms),
            "field_targets_artifact": str(field_path.relative_to(ROOT)),
            "field_targets_sha256": sha256(field_path),
        },
        "runs": run_results,
        "paired_analysis": paired_analysis,
        "same_width_sensitivity": sensitivity_analysis,
        "sample_efficiency": sample_efficiency,
        "verdict": {
            "full_data_primary": verdict,
            "benchmark_specific_no_practical_gain_supported": verdict in {
                "practically_equivalent_within_predeclared_margin",
                "strict_practical_worsening",
                "strict_statistical_worsening_but_practical_margin_unresolved",
            },
            "benchmark_specific_practical_improvement_supported":
                verdict == "strict_practical_improvement",
            "universal_claim_allowed": False,
            "inconclusive": verdict == "inconclusive",
        },
    }
    torch.save(
        {
            "schema": SCHEMA, "job_id": job_id,
            "parameter_match": parameter_match, "full_models": full_models,
        },
        output_dir / "full_models.pt",
    )
    result_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"STRICT_EGNN_ABLATION_RESULT={result_path}", flush=True)
    print(json.dumps({
        "parameter_match": parameter_match,
        "paired_analysis": {
            key: {
                field: value for field, value in analysis.items()
                if not field.startswith("raw_bootstrap")
            }
            for key, analysis in paired_analysis.items()
        },
        "sample_efficiency": {
            field: value for field, value in sample_efficiency["paired_analysis"].items()
            if not field.startswith("raw_bootstrap")
        },
        "verdict": results["verdict"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
