#!/usr/bin/env python3
"""Recompute and archive the complete 5x5 Corpus V4 accuracy evidence grid."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[3]
for _directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/inference",
    ROOT / "code/models/gnn",
    Path(__file__).resolve().parent,
):
    sys.path.insert(0, str(_directory))

from corpus_v4_accuracy_contract import (  # noqa: E402
    ACCEPTED_SCHEMA,
    FINAL_SCHEMA,
    TARGETS,
    canonical_task_row,
    load_jsonl,
    metric_set,
    resolve_repo_path,
    runtime_identity,
    validate_execution_lock,
    validate_file_manifest,
    validate_plan,
    validate_protocol,
    validate_root_closure,
    validate_slurm_allocation,
)
from corpus_v4_accuracy_dataset import load_corpus_v4_accuracy_dataset  # noqa: E402
from plan_corpus_v4_accuracy_resume import validate_attempt  # noqa: E402
from run_corpus_v4_accuracy_task import (  # noqa: E402
    NORMALIZATION_NAMES,
    TrainOnlyNormalizer,
    _graph_samples,
    _model_from_arrays,
    _predict,
    _smoke_hook,
    expected_bundle_payload,
    expected_bundle_specs,
)
from safe_npz_bundle import BundleLimits, load_safe_npz_bundle  # noqa: E402
from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    load_json,
    require_file_sha256,
    sha256_file,
)


PREDICTION_SCHEMA = "pcb-gnn.corpus-v4-accuracy-prediction.v1"
ANALYSIS_MANIFEST_SCHEMA = "pcb-gnn.corpus-v4-accuracy-analysis-manifest.v1"
MATRIX_METRICS = (
    "family_macro_mape_pct",
    "mae_physical_units",
    "mean_ape_pct",
    "median_ape_pct",
    "n_nonfinite_predictions",
    "n_nonpositive_predictions",
    "p95_ape_pct",
    "r2",
    "signed_bias_physical_units",
)


def _source_state() -> tuple[str, list[str], list[str]]:
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
        ["git", "status", "--short", "--untracked-files=all", "--", "code", "protocols", "requirements-proof.txt"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    return head, dirty, untracked


def _load_evaluation_dataset(plan_path: Path, plan: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    path = plan_path.parent / "evaluation_dataset.jsonl"
    expected = plan["artifact_sha256"]["evaluation_dataset.jsonl"]
    require_file_sha256(path, expected, "evaluation dataset")
    rows = load_jsonl(path)
    if len(rows) != 1500 or [row.get("layout_id") for row in rows] != list(range(1500)):
        raise ValueError("evaluation dataset is not dense layout IDs 0..1499")
    return {row["layout_id"]: row for row in rows}


def _validate_accepted_set(
    path: Path,
    payload: Mapping[str, Any],
    *,
    bindings: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Close accepted entries to the exact, hash-pinned candidate inventory."""
    if set(payload) != {
        "candidate_index",
        "entries",
        "execution_lock_sha256",
        "n_accepted",
        "n_expected",
        "protocol_sha256",
        "plan_sha256",
        "rejected_candidates",
        "schema",
        "task_manifest_sha256",
    }:
        raise ValueError("accepted-set fields are not exact")
    if payload.get("schema") != ACCEPTED_SCHEMA or any(
        payload.get(name) != value for name, value in bindings.items()
    ):
        raise ValueError("accepted set is bound to other frozen roots")
    candidate_record = payload.get("candidate_index")
    if not isinstance(candidate_record, dict) or set(candidate_record) != {"path", "sha256"}:
        raise ValueError("accepted set does not bind a canonical candidate index")
    candidate_path = resolve_repo_path(candidate_record["path"], "candidate index")
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise ValueError("candidate index must be a regular non-symlink file")
    require_file_sha256(candidate_path, candidate_record["sha256"], "candidate index")
    candidate = load_json(candidate_path)
    if set(candidate) != {"entries", "schema"} or candidate.get("schema") != "pcb-gnn.corpus-v4-accuracy-candidate-index.v1":
        raise ValueError("candidate-index fields or schema are invalid")
    candidate_triples: set[tuple[int, str, str]] = set()
    for index, entry in enumerate(candidate.get("entries", [])):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "task_id"}:
            raise ValueError(f"candidate entry {index} fields are not exact")
        task_id = entry["task_id"]
        if type(task_id) is not int or not 0 <= task_id < 25:
            raise ValueError("candidate task ID is invalid")
        candidate_path_value = resolve_repo_path(entry["path"], "candidate manifest")
        if candidate_path_value.is_symlink() or not candidate_path_value.is_file():
            raise ValueError("candidate manifest is missing or a symlink")
        if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64:
            raise ValueError("candidate manifest SHA-256 is malformed")
        require_file_sha256(
            candidate_path_value,
            entry["sha256"],
            f"candidate manifest {index}",
        )
        triple = (task_id, entry["path"], entry["sha256"])
        if triple in candidate_triples:
            raise ValueError("candidate index contains a duplicate entry")
        candidate_triples.add(triple)

    entries = payload.get("entries")
    if (
        payload.get("n_accepted") != 25
        or payload.get("n_expected") != 25
        or not isinstance(entries, list)
        or [entry.get("task_id") for entry in entries if isinstance(entry, dict)]
        != list(range(25))
    ):
        raise ValueError("accepted set is incomplete or reordered")
    for task_id, entry in enumerate(entries):
        if set(entry) != {
            "manifest_path",
            "manifest_sha256",
            "scheduler_completion",
            "task_id",
        }:
            raise ValueError("accepted entry fields are not exact")
        manifest_path = resolve_repo_path(entry["manifest_path"], "accepted task manifest")
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("accepted task manifest is missing or a symlink")
        require_file_sha256(manifest_path, entry["manifest_sha256"], "accepted task manifest")
        if (task_id, entry["manifest_path"], entry["manifest_sha256"]) not in candidate_triples:
            raise ValueError("accepted entry is absent from its candidate index")
        accounting = entry["scheduler_completion"]
        if (
            not isinstance(accounting, dict)
            or set(accounting)
            != {"AllocTRES", "ElapsedRaw", "ExitCode", "JobIDRaw", "ReqTRES", "State"}
            or accounting["State"] != "COMPLETED"
            or accounting["ExitCode"] != "0:0"
        ):
            raise ValueError("accepted entry lacks exact successful SLURM accounting")
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError("accepted set escapes the repository") from exc
    return entries


def _completed_accounting(result: Mapping[str, Any]) -> dict[str, str]:
    scheduler = result["provenance"]["scheduler"]
    component = f"{scheduler['array_job_id']}_{scheduler['array_task_id']}"
    query = subprocess.run(
        [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            component,
            "--format=JobIDRaw,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    records: list[dict[str, str]] = []
    fields = ("JobIDRaw", "State", "ExitCode", "ElapsedRaw", "ReqTRES", "AllocTRES")
    for line in query.stdout.splitlines():
        values = line.split("|")
        if len(values) >= len(fields):
            records.append(dict(zip(fields, values)))
    matches = [record for record in records if record["JobIDRaw"] == component]
    if (
        query.returncode != 0
        or len(matches) != 1
        or matches[0]["State"].split()[0].rstrip("+") != "COMPLETED"
        or matches[0]["ExitCode"] != "0:0"
    ):
        raise ValueError(f"task {component} lacks exact successful SLURM accounting")
    normalized = dict(matches[0])
    normalized["State"] = "COMPLETED"
    in_run = scheduler.get("scheduler_record", {})
    if any(
        normalized[name] != in_run.get(name)
        for name in ("ReqTRES", "AllocTRES")
    ):
        raise ValueError(
            f"task {component} terminal resources differ from its in-run receipt"
        )
    return normalized


def recompute_task_metrics(
    prediction_rows: Sequence[dict[str, Any]],
    task_row: Mapping[str, Any],
    evaluation: Mapping[int, dict[str, Any]],
) -> dict[str, Any]:
    expected_ids = task_row["partitions"]["test"]["layout_ids"]
    if [row.get("layout_id") for row in prediction_rows] != expected_ids:
        raise ValueError("prediction rows do not exactly follow frozen test membership")
    r4_ids = set(task_row["r4_test_layout_ids"])
    for row in prediction_rows:
        layout_id = row["layout_id"]
        frozen = evaluation[layout_id]
        reference = [frozen["training_reference"][target]["value"] for target in TARGETS]
        frozen_r4 = frozen["evaluation_only_r4_cps"]
        expected_r4 = None if frozen_r4 is None else frozen_r4["value"]
        prediction = row.get("prediction")
        if (
            row.get("schema") != PREDICTION_SCHEMA
            or row.get("target_order") != list(TARGETS)
            or row.get("geometry_sha256") != frozen["geometry_sha256"]
            or row.get("family_id") != frozen["family_id"]
            or row.get("reference_r3") != reference
            or row.get("reference_r4_cps_pf") != expected_r4
            or (layout_id in r4_ids) != (expected_r4 is not None)
            or not isinstance(prediction, list)
            or len(prediction) != 4
            or not np.all(np.isfinite(np.asarray(prediction, dtype=np.float64)))
        ):
            raise ValueError(f"prediction/reference identity mismatch at layout {layout_id}")
    family_ids = [row["family_id"] for row in prediction_rows]
    metrics: dict[str, Any] = {"r3_full_test": {}}
    for column, target in enumerate(TARGETS):
        metrics["r3_full_test"][target] = metric_set(
            [row["prediction"][column] for row in prediction_rows],
            [row["reference_r3"][column] for row in prediction_rows],
            family_ids,
        )
    panel = [row for row in prediction_rows if row["layout_id"] in r4_ids]
    if len(panel) != 39:
        raise ValueError("R4 panel cardinality is not 39")
    panel_families = [row["family_id"] for row in panel]
    metrics["r4_panel_r3"] = {
        "Cps_pF": metric_set(
            [row["prediction"][0] for row in panel],
            [row["reference_r3"][0] for row in panel],
            panel_families,
        )
    }
    metrics["r4_panel_r4"] = {
        "Cps_pF": metric_set(
            [row["prediction"][0] for row in panel],
            [row["reference_r4_cps_pf"] for row in panel],
            panel_families,
        )
    }
    return metrics


def evaluate_accepted_checkpoint(
    manifest_path: Path,
    *,
    task_row: Mapping[str, Any],
    result: Mapping[str, Any],
    protocol: Mapping[str, Any],
    bindings: Mapping[str, str],
    samples: Mapping[int, dict[str, Any]],
    evaluation: Mapping[int, dict[str, Any]],
    r4_evaluation: Mapping[int, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Open test/R4 references only after the accepted-set gate has passed."""
    checkpoint = result["checkpoint"]
    smoke_path = manifest_path.parent / "smoke_examples.jsonl"
    smoke_rows = load_jsonl(smoke_path)
    bundle = load_safe_npz_bundle(
        manifest_path.parent / "bundle",
        expected_metadata_sha256=checkpoint["metadata_sha256"],
        expected_specs=expected_bundle_specs(),
        expected_payload=expected_bundle_payload(result["task"], bindings),
        smoke_hook=_smoke_hook(smoke_rows),
        expected_smoke_input_sha256=checkpoint["smoke_examples_sha256"],
        require_smoke=True,
        limits=BundleLimits(
            max_archive_bytes=int(protocol["checkpoint"]["maximum_bundle_bytes"]),
            max_expanded_bytes=int(protocol["checkpoint"]["maximum_uncompressed_bytes"]),
        ),
    )
    train_ids = task_row["partitions"]["train"]["layout_ids"]
    normalizer = TrainOnlyNormalizer(samples, train_ids)
    expected_normalization = normalizer.arrays()
    for name in NORMALIZATION_NAMES:
        if not np.array_equal(bundle.arrays[name], expected_normalization[name]):
            raise ValueError(
                f"checkpoint normalization was not reconstructed from frozen train IDs: {name}"
            )
    model = _model_from_arrays(bundle.arrays)
    test_ids = task_row["partitions"]["test"]["layout_ids"]
    work = {
        layout_id: normalizer.transform(samples[layout_id]) for layout_id in test_ids
    }
    prediction = _predict(
        model,
        normalizer,
        work,
        test_ids,
        int(protocol["optimization"]["batch_size"]),
    )
    r4_ids = set(task_row["r4_test_layout_ids"])
    rows: list[dict[str, Any]] = []
    for index, layout_id in enumerate(test_ids):
        frozen = evaluation[layout_id]
        sample = samples[layout_id]
        r4_record = frozen["evaluation_only_r4_cps"]
        independently_loaded_r4 = r4_evaluation.get(layout_id)
        if (
            frozen["geometry_sha256"] != sample["geometry_sha256"]
            or frozen["family_id"] != sample["family_id"]
            or (r4_record is not None) != (layout_id in r4_ids)
            or (independently_loaded_r4 is not None) != (r4_record is not None)
        ):
            raise ValueError("evaluation identity differs from graph/sample identity")
        reference_r3 = [
            frozen["training_reference"][target]["value"] for target in TARGETS
        ]
        if not np.array_equal(
            np.asarray(reference_r3, dtype=np.float64), sample["reference_r3"]
        ):
            raise ValueError("evaluation R3 values differ from independently loaded targets")
        if r4_record is not None and (
            independently_loaded_r4.geometry_sha256 != sample["geometry_sha256"]
            or float(independently_loaded_r4.cps_r4_pf) != float(r4_record["value"])
        ):
            raise ValueError("evaluation R4 value differs from independently loaded observation")
        rows.append(
            {
                "family_id": sample["family_id"],
                "geometry_sha256": sample["geometry_sha256"],
                "layout_id": layout_id,
                "prediction": prediction[index].tolist(),
                "reference_r3": reference_r3,
                "reference_r4_cps_pf": None
                if r4_record is None
                else r4_record["value"],
                "schema": PREDICTION_SCHEMA,
                "target_order": list(TARGETS),
            }
        )
    return rows, recompute_task_metrics(rows, task_row, evaluation)


def crossed_seed_grid_summary(matrix: np.ndarray, protocol: Mapping[str, Any]) -> dict[str, Any]:
    if matrix.shape != (5, 5) or not np.all(np.isfinite(matrix)):
        raise ValueError("summary matrix must be finite and exactly 5x5")
    interval = protocol["evaluation"]["descriptive_seed_grid_interval"]
    rng = np.random.default_rng(int(interval["seed"]))
    resamples = int(interval["resamples"])
    draws = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        rows = rng.integers(0, 5, 5)
        columns = rng.integers(0, 5, 5)
        draws[index] = float(np.mean(matrix[np.ix_(rows, columns)]))
    low, high = interval["percentiles"]
    return {
        "descriptive_interval": [
            float(np.percentile(draws, low)),
            float(np.percentile(draws, high)),
        ],
        "interval_label": interval["label"],
        "interval_semantics": interval["statistical_semantics"],
        "matrix_rows_split_seeds_columns_init_seeds": matrix.tolist(),
        "max_across_25_cells": float(np.max(matrix)),
        "mean_across_25_cells": float(np.mean(matrix)),
        "min_across_25_cells": float(np.min(matrix)),
        "std_across_25_cells": float(np.std(matrix, ddof=1)),
    }


def build_matrices(results: Sequence[dict[str, Any]], protocol: Mapping[str, Any]) -> dict[str, Any]:
    if len(results) != 25:
        raise ValueError("matrix construction requires exactly 25 task results")
    matrices: dict[str, Any] = {}
    for view, targets in (
        ("r3_full_test", TARGETS),
        ("r4_panel_r3", ("Cps_pF",)),
        ("r4_panel_r4", ("Cps_pF",)),
    ):
        matrices[view] = {}
        for target in targets:
            matrices[view][target] = {}
            for metric in MATRIX_METRICS:
                matrix = np.asarray(
                    [
                        [results[row * 5 + column]["metrics"][view][target][metric] for column in range(5)]
                        for row in range(5)
                    ],
                    dtype=np.float64,
                )
                matrices[view][target][metric] = crossed_seed_grid_summary(matrix, protocol)
    return matrices


def main() -> None:
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
    parser.add_argument("--accepted-set", type=Path, required=True)
    parser.add_argument("--expected-accepted-set-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

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
    if args.accepted_set.is_symlink() or not args.accepted_set.is_file():
        raise ValueError("accepted set must be a regular non-symlink file")
    require_file_sha256(args.accepted_set, args.expected_accepted_set_sha256, "accepted set")
    accepted = load_json(args.accepted_set)
    bindings = {
        "execution_lock_sha256": lock_sha,
        "plan_sha256": plan_sha,
        "protocol_sha256": protocol_sha,
        "task_manifest_sha256": task_manifest_sha,
    }
    entries = _validate_accepted_set(args.accepted_set, accepted, bindings=bindings)

    scheduler = validate_slurm_allocation(protocol, stage="finalizer")
    initial_head, initial_dirty, initial_untracked = _source_state()
    if initial_dirty or initial_untracked:
        raise SystemExit("refusing finalization from dirty or untracked source")
    if initial_head != args.expected_source_git_head:
        raise SystemExit("source commit differs from the external trust root")
    if runtime_identity() != protocol["runtime"]:
        raise SystemExit("finalizer runtime differs from the frozen proof environment")
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(int(protocol["resources"]["finalizer"]["scientific_threads"]))
    torch.set_num_interop_threads(1)
    source_hashes = {name: sha256_file(ROOT / name) for name in lock["source_sha256"]}
    if source_hashes != lock["source_sha256"]:
        raise ValueError("finalizer source differs from execution lock")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    expected_batch_hash = lock["source_sha256"]["code/jobs/submit_finalize_corpus_v4_accuracy.sh"]
    if not executed_batch.is_file() or sha256_file(executed_batch) != expected_batch_hash:
        raise SystemExit("executed finalizer batch differs from tracked source")

    # Validate every accepted checkpoint before the first held-out inference.
    accepted_results: list[tuple[Path, dict[str, Any]]] = []
    common_software: set[str] = set()
    for task_id, (entry, task_row) in enumerate(zip(entries, task_rows)):
        manifest_path = resolve_repo_path(entry["manifest_path"], "accepted task manifest")
        result = validate_attempt(
            manifest_path,
            task_row=task_row,
            protocol_sha256=protocol_sha,
            plan_sha256=plan_sha,
            task_manifest_sha256=task_manifest_sha,
            lock=lock,
            lock_sha256=lock_sha,
            expected_source_git_head=args.expected_source_git_head,
        )
        if result.get("task") != canonical_task_row(task_id):
            raise ValueError("task result is not in canonical row-major order")
        if _completed_accounting(result) != entry["scheduler_completion"]:
            raise ValueError("accepted scheduler receipt changed before finalization")
        common_software.add(json.dumps(result["provenance"]["software"], sort_keys=True))
        accepted_results.append((manifest_path, result))
    if len(common_software) != 1:
        raise ValueError("accepted tasks mix software environments")
    task_software = json.loads(next(iter(common_software)))
    if task_software.get("torch_build") != torch.__version__:
        raise ValueError("finalizer Torch build differs from accepted training tasks")

    evaluation = _load_evaluation_dataset(args.plan, plan)
    dataset = load_corpus_v4_accuracy_dataset(ROOT, args.protocol)
    samples = _graph_samples(dataset)
    bundle_bindings = {
        **bindings,
        "evaluation_dataset_sha256": plan["artifact_sha256"]["evaluation_dataset.jsonl"],
    }
    output = args.output_root / f"job_{scheduler['job_id']}"
    temporary = args.output_root / f".job_{scheduler['job_id']}.tmp"
    if output.exists() or temporary.exists():
        raise SystemExit("refusing to overwrite a final accuracy archive")
    args.output_root.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    (temporary / "predictions").mkdir()
    try:
        metric_results: list[dict[str, Any]] = []
        task_index: list[dict[str, Any]] = []
        checkpoint_index: list[dict[str, Any]] = []
        for task_id, ((manifest_path, result), entry, task_row) in enumerate(
            zip(accepted_results, entries, task_rows)
        ):
            prediction_rows, metrics = evaluate_accepted_checkpoint(
                manifest_path,
                task_row=task_row,
                result=result,
                protocol=protocol,
                bindings=bundle_bindings,
                samples=samples,
                evaluation=evaluation,
                r4_evaluation=dataset.r4_evaluation,
            )
            prediction_name = f"predictions/task_{task_id:02d}.jsonl"
            atomic_write_jsonl(temporary / prediction_name, prediction_rows)
            metric_results.append({"metrics": metrics, "task": canonical_task_row(task_id)})
            task_index.append(
                {
                    "manifest_path": entry["manifest_path"],
                    "manifest_sha256": entry["manifest_sha256"],
                    "prediction_path": prediction_name,
                    "prediction_sha256": sha256_file(temporary / prediction_name),
                    "scheduler_completion": entry["scheduler_completion"],
                    "task_id": task_id,
                }
            )
            checkpoint_index.append(
                {
                    **canonical_task_row(task_id),
                    **result["checkpoint"],
                    "bundle_path": (manifest_path.parent / "bundle").relative_to(ROOT).as_posix(),
                }
            )
        matrices = build_matrices(metric_results, protocol)
        atomic_write_json(temporary / "matrices.json", {"schema": "pcb-gnn.corpus-v4-accuracy-matrices.v1", "views": matrices})
        atomic_write_json(temporary / "checkpoint_index.json", {"entries": checkpoint_index, "schema": "pcb-gnn.corpus-v4-accuracy-checkpoint-index.v1"})
        atomic_write_json(temporary / "task_index.json", {"entries": task_index, "schema": "pcb-gnn.corpus-v4-accuracy-task-index.v1"})

        split_rows = task_rows[::5]
        panel_memberships = [
            layout_id for row in split_rows for layout_id in row["r4_test_layout_ids"]
        ]
        unique_layouts = set(panel_memberships)
        unique_families = {evaluation[index]["family_id"] for index in unique_layouts}
        layout_appearances = Counter(panel_memberships)
        family_appearances = Counter(
            evaluation[index]["family_id"]
            for row in split_rows
            for index in row["r4_test_layout_ids"]
        )
        all_r4_layouts = {
            index for index, row in evaluation.items() if row["evaluation_only_r4_cps"] is not None
        }
        all_r4_families = {evaluation[index]["family_id"] for index in all_r4_layouts}
        summary = {
            "bindings": {
                **bindings,
                "accepted_set_sha256": args.expected_accepted_set_sha256,
                "expected_source_git_head": args.expected_source_git_head,
            },
            "counts": {
                "r4_panel_split_layout_memberships": len(panel_memberships),
                "r4_task_layout_evaluations": sum(len(row["r4_test_layout_ids"]) for row in task_rows),
                "r4_unique_families_across_split_panels": len(unique_families),
                "r4_unique_layouts_across_split_panels": len(unique_layouts),
                "r4_unseen_selected_families": len(all_r4_families - unique_families),
                "r4_unseen_selected_layouts": len(all_r4_layouts - unique_layouts),
                "r4_family_split_appearance_histogram": dict(sorted(Counter(family_appearances.values()).items())),
                "r4_layout_split_appearance_histogram": dict(sorted(Counter(layout_appearances.values()).items())),
                "tasks": 25,
            },
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "designated_downstream_checkpoint": checkpoint_index[12],
            "provenance": {
                "finalizer_runtime": {
                    **runtime_identity(),
                    "torch_build": torch.__version__,
                },
                "scheduler": scheduler,
                "source_file_sha256": source_hashes,
                "source_git_head": initial_head,
                "task_software": task_software,
            },
            "schema": FINAL_SCHEMA,
            "scientific_scope": {
                "checkpoint_gate": "all 25 checkpoints accepted before first held-out inference",
                "r3": "all held-out-family test layouts; FEM-R3P16 Cps plus FastHenry inductance references",
                "r4": "the same predictions on exactly 39 selected held-out-family layouts per split",
                "r4_is_truth": False,
                "r4_panels_independent": False,
                "validation_role": "diagnostic only; all checkpoints are fixed final epoch",
            },
        }
        atomic_write_json(temporary / "summary.json", summary)
        output_names = (
            "checkpoint_index.json",
            "matrices.json",
            "summary.json",
            "task_index.json",
            *(f"predictions/task_{task_id:02d}.jsonl" for task_id in range(25)),
        )
        analysis_files = {name: sha256_file(temporary / name) for name in output_names}
        accepted_relative = args.accepted_set.resolve().relative_to(ROOT.resolve()).as_posix()
        atomic_write_json(
            temporary / "ANALYSIS_MANIFEST.json",
            {
                "files": {
                    **{name: {"path": name, "sha256": digest} for name, digest in analysis_files.items()},
                    "accepted_set": {"path": accepted_relative, "sha256": args.expected_accepted_set_sha256},
                },
                "schema": ANALYSIS_MANIFEST_SCHEMA,
            },
        )
        final_head, final_dirty, final_untracked = _source_state()
        final_sources = {name: sha256_file(ROOT / name) for name in lock["source_sha256"]}
        if (
            final_head != initial_head
            or final_dirty
            or final_untracked
            or final_sources != source_hashes
            or sha256_file(executed_batch) != expected_batch_hash
            or sha256_file(args.accepted_set) != args.expected_accepted_set_sha256
        ):
            raise SystemExit("source or accepted evidence changed during finalization")
        temporary.replace(output)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    print(json.dumps({"analysis_manifest_sha256": sha256_file(output / "ANALYSIS_MANIFEST.json"), "status": "completed", "tasks": 25}, sort_keys=True))


if __name__ == "__main__":
    main()
