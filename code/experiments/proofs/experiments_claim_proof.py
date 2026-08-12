#!/usr/bin/env python3
"""SLURM-only proof for the solver-time and speedup claims.

The experiment intentionally measures every quantity used by the speed claim in
one process on one compute node:

1. Generate the complete field-grade corpus with FastHenry + electrostatic FEM,
   retaining per-layout wall times and failures.
2. Retrain the published GNN on the successful layouts and report held-out
   accuracy on the identical legacy seed-42 split.
3. Measure pre-collated batch throughput, single-design forward latency, and
   graph-build-to-prediction latency for that exact trained model.

No field solver may be called by a login-node smoke test.  The script refuses to
run unless SLURM_JOB_ID is present, except for ``--validate-only``.
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

from experiments_v5 import mk
from fasthenry_ref import FASTHENRY, fasthenry_totals
from gnn_baseline import PCBParasiticGNN, collate
from planar_to_graph import build_graph_from_planar_layout
from pipeline import TARGETS, load_dataset
from runtime_paths import fem_cps_worker_path


ROOT = Path(__file__).resolve().parents[3]
CODE = ROOT / "code"
DATA_ROOT = Path(os.environ.get("PCB_GNN_DATA_ROOT", ROOT / "datasets")).resolve()
PROOF_SCHEMA = "research13.claim-proof.v1"


class TrainOnlyNorm:
    """The published transform with all statistics fitted on training data only."""

    def __init__(self, samples: list[dict[str, Any]], train_idx: list[int]) -> None:
        targets = np.stack([samples[index]["y"] for index in train_idx])
        logged = np.sign(targets) * np.log1p(np.abs(targets))
        self.ym, self.ys = logged.mean(0), logged.std(0) + 1e-8
        nodes = np.concatenate([samples[index]["node_feat"] for index in train_idx], 0)
        self.nfm, self.nfs = nodes.mean(0), nodes.std(0) + 1e-6
        edge_parts = [
            samples[index]["edge_feat"] for index in train_idx
            if samples[index]["edge_feat"].size
        ]
        edges = np.concatenate(edge_parts, 0) if edge_parts else np.zeros((1, 7))
        self.efm, self.efs = edges.mean(0), edges.std(0) + 1e-6

    def node(self, values: np.ndarray) -> np.ndarray:
        return ((np.asarray(values, np.float32) - self.nfm) / self.nfs).astype(np.float32)

    def edge(self, values: np.ndarray) -> np.ndarray:
        array = np.asarray(values, np.float32)
        return ((array - self.efm) / self.efs).astype(np.float32) if array.size else array

    def y(self, values: np.ndarray) -> np.ndarray:
        logged = np.sign(values) * np.log1p(np.abs(values))
        return ((logged - self.ym) / self.ys).astype(np.float32)

    def inv(self, values: np.ndarray) -> np.ndarray:
        logged = values * self.ys + self.ym
        return np.sign(logged) * np.expm1(np.abs(logged))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-candidates", type=int, default=346)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fem-refine", type=int, default=1)
    parser.add_argument("--fem-timeout-s", type=int, default=90)
    parser.add_argument("--timing-repeats", type=int, default=100)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
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


def percentile_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "p05": None,
                "p95": None, "min": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": int(array.size),
        "mean": round(float(array.mean()), 6),
        "median": round(float(np.median(array)), 6),
        "p05": round(float(np.percentile(array, 5)), 6),
        "p95": round(float(np.percentile(array, 95)), 6),
        "min": round(float(array.min()), 6),
        "max": round(float(array.max()), 6),
    }


def timed_call(function: Callable[[], Any]) -> tuple[Any, float]:
    start = time.perf_counter_ns()
    value = function()
    elapsed_ms = (time.perf_counter_ns() - start) / 1e6
    return value, elapsed_ms


def safe_fem_cps(layout: dict[str, Any], refine: int, timeout_s: int) -> float | None:
    """Run one FEM solve in an isolated process and expose failures explicitly."""
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


def provenance(args: argparse.Namespace) -> dict[str, Any]:
    tracked = [
        Path(__file__),
        CODE / "models" / "gnn" / "gnn_baseline.py",
        CODE / "core" / "pcb_graph.py",
        CODE / "core" / "planar_to_graph.py",
        CODE / "solvers" / "fasthenry_ref.py",
        CODE / "solvers" / "fem_capacitance_3d.py",
        CODE / "solvers" / "fem_cps_worker.py",
        CODE / "core" / "experiments_v5.py",
        DATA_ROOT / "synth_v2" / "layouts.jsonl",
        DATA_ROOT / "synth_v2" / "labels.json",
        DATA_ROOT / "synth_v2" / "meta.json",
        Path(FASTHENRY),
    ]
    cpu_model = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "schema": PROOF_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
        "slurm_cluster_name": os.environ.get("SLURM_CLUSTER_NAME"),
        "slurm_node_list": os.environ.get("SLURM_JOB_NODELIST"),
        "slurm_cpus_on_node": os.environ.get("SLURM_CPUS_ON_NODE"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "cpu_model": cpu_model,
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
        "file_sha256": {artifact_key(path): sha256(path) for path in tracked},
    }


def make_sample(layout: dict[str, Any], cps_pf: float, fh: dict[str, float]) -> dict[str, Any]:
    graph = build_graph_from_planar_layout(layout)
    node_feat, edge_feat, edge_index = graph.to_feature_matrices()
    target = np.asarray(
        [cps_pf, fh["L_pri_nH"], fh["L_sec_nH"], fh["L_mut_nH"]],
        dtype=np.float32,
    )
    return {
        "node_feat": node_feat.astype(np.float32),
        "edge_feat": edge_feat.astype(np.float32),
        "edge_index": edge_index.astype(np.int64),
        "edge_dim": 7,
        "y": target,
    }


def train_model(
    samples: list[dict[str, Any]], seed: int, epochs: int
) -> tuple[PCBParasiticGNN, TrainOnlyNorm, list[dict[str, Any]], list[int], list[int], float]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    permutation = np.random.permutation(len(samples))
    cut = int(0.8 * len(samples))
    train_indices = list(map(int, permutation[:cut]))
    test_indices = list(map(int, permutation[cut:]))
    normalizer = TrainOnlyNorm(samples, train_indices)
    work = [mk(sample, normalizer) for sample in samples]
    model = PCBParasiticGNN(
        node_dim=samples[0]["node_feat"].shape[1], edge_dim=7,
        hidden=96, n_layers=4, n_targets=4,
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_function = nn.SmoothL1Loss()
    order = list(train_indices)
    started = time.perf_counter()
    for _ in range(epochs):
        model.train()
        np.random.shuffle(order)
        for offset in range(0, len(order), 32):
            batch = collate([work[index] for index in order[offset:offset + 32]])
            optimizer.zero_grad()
            loss_function(model(batch), batch.y).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
        scheduler.step()
    training_s = time.perf_counter() - started
    model.eval()
    return model, normalizer, work, train_indices, test_indices, training_s


def accuracy_metrics(
    model: PCBParasiticGNN,
    normalizer: TrainOnlyNorm,
    work: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    test_indices: list[int],
) -> dict[str, Any]:
    predictions: list[np.ndarray] = []
    references: list[np.ndarray] = []
    with torch.no_grad():
        for index in test_indices:
            output = model(collate([work[index]])).numpy()[0]
            predictions.append(normalizer.inv(output))
            references.append(samples[index]["y"])
    pred = np.stack(predictions)
    ref = np.stack(references)
    output: dict[str, Any] = {"n_test": len(test_indices)}
    for column, target in enumerate(TARGETS):
        residual = pred[:, column] - ref[:, column]
        denominator = np.sum((ref[:, column] - ref[:, column].mean()) ** 2) + 1e-12
        relative = np.abs(residual) / (np.abs(ref[:, column]) + 1e-9) * 100
        output[target] = {
            "r2": round(float(1.0 - np.sum(residual ** 2) / denominator), 6),
            "median_relative_error_pct": round(float(np.median(relative)), 6),
            "mean_relative_error_pct": round(float(np.mean(relative)), 6),
            "p95_relative_error_pct": round(float(np.percentile(relative, 95)), 6),
        }
    return output


def benchmark_model(
    model: PCBParasiticGNN,
    normalizer: TrainOnlyNorm,
    work: list[dict[str, Any]],
    successful_layouts: list[dict[str, Any]],
    test_indices: list[int],
    repeats: int,
) -> dict[str, Any]:
    batch = collate([work[index] for index in test_indices])
    with torch.no_grad():
        for _ in range(20):
            model(batch)
        batch_times_ms = []
        for _ in range(repeats):
            _, elapsed = timed_call(lambda: model(batch))
            batch_times_ms.append(elapsed)

        single_times_ms = []
        single_by_design_ms = []
        for index in test_indices:
            one = collate([work[index]])
            for _ in range(3):
                model(one)
            design_times = []
            for _ in range(10):
                _, elapsed = timed_call(lambda one=one: model(one))
                single_times_ms.append(elapsed)
                design_times.append(elapsed)
            single_by_design_ms.append(float(np.median(design_times)))

        end_to_end_times_ms = []
        end_to_end_by_design_ms = []
        for index in test_indices:
            layout = successful_layouts[index]
            reference_y = work[index]["y"]

            def graph_to_prediction() -> np.ndarray:
                graph = build_graph_from_planar_layout(layout)
                node_feat, edge_feat, edge_index = graph.to_feature_matrices()
                raw = {
                    "node_feat": node_feat.astype(np.float32),
                    "edge_feat": edge_feat.astype(np.float32),
                    "edge_index": edge_index.astype(np.int64),
                    "edge_dim": 7,
                    "y": np.zeros_like(reference_y, dtype=np.float32),
                }
                normalized = mk(raw, normalizer)
                standardized = model(collate([normalized])).numpy()[0]
                return normalizer.inv(standardized)

            for _ in range(2):
                graph_to_prediction()
            design_times = []
            for _ in range(5):
                _, elapsed = timed_call(graph_to_prediction)
                end_to_end_times_ms.append(elapsed)
                design_times.append(elapsed)
            end_to_end_by_design_ms.append(float(np.median(design_times)))

    per_sample_batch = [elapsed / len(test_indices) for elapsed in batch_times_ms]
    return {
        "precollated_batch_size": len(test_indices),
        "precollated_batch_total_ms": percentile_summary(batch_times_ms),
        "precollated_batch_ms_per_design": percentile_summary(per_sample_batch),
        "single_design_forward_ms": percentile_summary(single_times_ms),
        "graph_build_normalize_collate_forward_ms": percentile_summary(end_to_end_times_ms),
        "raw_ms": {
            "precollated_batch_total": batch_times_ms,
            "precollated_batch_per_design": per_sample_batch,
            "single_forward_all_repeats": single_times_ms,
            "single_forward_by_design_median": single_by_design_ms,
            "end_to_end_all_repeats": end_to_end_times_ms,
            "end_to_end_by_design_median": end_to_end_by_design_ms,
        },
        "warmup_batch_repeats": 20,
        "measured_batch_repeats": repeats,
        "single_repeats_per_design": 10,
        "end_to_end_repeats_per_design": 5,
    }


def main() -> None:
    args = parse_args()
    if args.validate_only:
        print(json.dumps({"schema": PROOF_SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Refusing field solves outside SLURM; submit submit_claim_proof.sh")

    job_id = os.environ["SLURM_JOB_ID"]
    output_dir = ROOT / "results" / "proof_updates" / "jobs" / "claim_proof" / f"job_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "results_claim_proof.json"
    raw_path = output_dir / "raw_solver_timings.jsonl"

    layouts, _, _ = load_dataset(DATA_ROOT / "synth_v2")
    candidates = [
        record for record in layouts
        if any(trace["net"] == "pri" for trace in record["layout"]["traces"])
        and any(trace["net"] == "sec" for trace in record["layout"]["traces"])
        and len(record["layout"]["traces"]) <= 28
    ][:args.max_candidates]

    records: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    successful_layouts: list[dict[str, Any]] = []
    solver_stage_started = time.perf_counter()
    with raw_path.open("w") as raw_handle:
        for ordinal, record in enumerate(candidates):
            layout = record["layout"]
            fh, fh_ms = timed_call(lambda layout=layout: fasthenry_totals(layout, 1e5))
            cps, fem_ms = timed_call(
                lambda layout=layout: safe_fem_cps(
                    layout, refine=args.fem_refine, timeout_s=args.fem_timeout_s
                )
            )
            valid = bool(fh and fh.get("L_mut_nH", 0.0) > 0 and cps and cps > 0)
            timing_record = {
                "ordinal": ordinal,
                "layout_id": record.get("id"),
                "n_traces": len(layout["traces"]),
                "fasthenry_ms": round(fh_ms, 6),
                "fem_ms": round(fem_ms, 6),
                "paired_solver_ms": round(fh_ms + fem_ms, 6),
                "valid": valid,
            }
            records.append(timing_record)
            raw_handle.write(json.dumps(timing_record) + "\n")
            raw_handle.flush()
            if valid:
                samples.append(make_sample(layout, float(cps), fh))
                successful_layouts.append(layout)
            print(
                f"[solver {ordinal + 1:03d}/{len(candidates)}] id={record.get('id')} "
                f"FH={fh_ms:.1f}ms FEM={fem_ms:.1f}ms valid={valid}",
                flush=True,
            )
    solver_stage_wall_s = time.perf_counter() - solver_stage_started
    if len(samples) < 50:
        raise RuntimeError(f"Only {len(samples)} valid paired-solver samples")

    model, normalizer, work, train_indices, test_indices, training_s = train_model(
        samples, seed=args.seed, epochs=args.epochs
    )
    accuracy = accuracy_metrics(model, normalizer, work, samples, test_indices)
    inference = benchmark_model(
        model, normalizer, work, successful_layouts, test_indices, args.timing_repeats
    )

    valid_records = [record for record in records if record["valid"]]
    paired_ms = [float(record["paired_solver_ms"]) for record in valid_records]
    fh_ms = [float(record["fasthenry_ms"]) for record in valid_records]
    fem_ms = [float(record["fem_ms"]) for record in valid_records]
    solver_median = float(np.median(paired_ms))
    batch_median = float(inference["precollated_batch_ms_per_design"]["median"])
    single_median = float(inference["single_design_forward_ms"]["median"])
    end_to_end_median = float(
        inference["graph_build_normalize_collate_forward_ms"]["median"]
    )
    test_solver_ms = np.asarray(
        [float(valid_records[index]["paired_solver_ms"]) for index in test_indices],
        dtype=np.float64,
    )
    test_e2e_ms = np.asarray(
        inference["raw_ms"]["end_to_end_by_design_median"], dtype=np.float64
    )
    paired_speedups = test_solver_ms / test_e2e_ms
    bootstrap_rng = np.random.default_rng(args.seed + 991)
    bootstrap_medians = np.empty(10_000, dtype=np.float64)
    for iteration in range(10_000):
        chosen = bootstrap_rng.integers(0, len(paired_speedups), len(paired_speedups))
        bootstrap_medians[iteration] = np.median(paired_speedups[chosen])

    results = {
        "provenance": provenance(args),
        "corpus": {
            "n_candidates": len(candidates),
            "n_valid": len(samples),
            "n_failed": len(candidates) - len(samples),
            "n_train": len(train_indices),
            "n_test": len(test_indices),
            "candidate_rule": "first synth_v2 layouts with pri+sec and <=28 traces",
        },
        "solver_timing_ms": {
            "fasthenry_valid_designs": percentile_summary(fh_ms),
            "fem_valid_designs": percentile_summary(fem_ms),
            "paired_valid_designs": percentile_summary(paired_ms),
            "solver_stage_wall_s_all_attempts": round(solver_stage_wall_s, 6),
            "solver_stage_wall_ms_per_attempt": round(
                solver_stage_wall_s * 1000 / len(candidates), 6
            ),
            "raw_timings": str(raw_path.relative_to(ROOT)),
        },
        "training": {"epochs": args.epochs, "wall_s": round(training_s, 6)},
        "normalization": "all node, edge, and target statistics fitted on training indices only",
        "held_out_accuracy": accuracy,
        "gnn_timing": inference,
        "derived_claims": {
            "speedup_solver_median_vs_batch_throughput_x": round(
                solver_median / batch_median, 6
            ),
            "speedup_solver_median_vs_single_forward_x": round(
                solver_median / single_median, 6
            ),
            "speedup_solver_median_vs_end_to_end_gnn_x": round(
                solver_median / end_to_end_median, 6
            ),
            "paired_speedup_solver_vs_end_to_end_gnn": {
                "n_designs": len(paired_speedups),
                "median_x": round(float(np.median(paired_speedups)), 6),
                "p05_x": round(float(np.percentile(paired_speedups, 5)), 6),
                "p95_x": round(float(np.percentile(paired_speedups, 95)), 6),
                "bootstrap_95pct_ci_median_x": [
                    round(float(np.percentile(bootstrap_medians, 2.5)), 6),
                    round(float(np.percentile(bootstrap_medians, 97.5)), 6),
                ],
                "bootstrap_cluster": "design",
                "bootstrap_resamples": 10_000,
            },
            "projected_one_thousand_designs_solver_hours_from_median": round(
                solver_median * 1000 / 1000 / 3600, 6
            ),
            "projected_one_thousand_designs_gnn_seconds_from_batch_throughput": round(
                batch_median * 1000 / 1000, 6
            ),
            "formula_note": "all ratios use paired-solver median from valid layouts",
        },
    }
    torch.save(
        {
            "state_dict": model.state_dict(),
            "normalizer": {
                "ym": normalizer.ym,
                "ys": normalizer.ys,
                "nfm": normalizer.nfm,
                "nfs": normalizer.nfs,
                "efm": normalizer.efm,
                "efs": normalizer.efs,
            },
            "test_indices": test_indices,
            "provenance": results["provenance"],
        },
        output_dir / "field_grade_checkpoint.pt",
    )
    result_path.write_text(json.dumps(results, indent=2))
    print("CLAIM_PROOF_RESULT=" + str(result_path), flush=True)
    print(json.dumps(results["derived_claims"], indent=2), flush=True)


if __name__ == "__main__":
    main()
