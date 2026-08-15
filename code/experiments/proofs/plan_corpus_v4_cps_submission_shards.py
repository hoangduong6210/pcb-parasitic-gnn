#!/usr/bin/env python3
"""Create deterministic, hashable dense dispatch shards for a frozen manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    load_json,
    require_file_sha256,
    sha256_file,
)
from run_corpus_v4_cps_multifidelity_task import (  # noqa: E402
    validate_execution_lock,
    validate_frozen_inputs,
)


TASK_SET_SCHEMA = "pcb-gnn.cps-multifidelity-pending-task-set.v1"
SUMMARY_SCHEMA = "pcb-gnn.cps-multifidelity-submission-shards.v1"


def build_shards(
    rows: list[dict[str, Any]],
    *,
    plan_sha256: str,
    manifest_sha256: str,
    execution_lock_sha256: str,
    max_array_size: int,
) -> list[dict[str, Any]]:
    """Partition canonical tasks into dense local arrays without renumbering them."""
    if max_array_size < 1:
        raise ValueError("max array size must be positive")
    shards: list[dict[str, Any]] = []
    for start in range(0, len(rows), max_array_size):
        selected = rows[start : start + max_array_size]
        pending = [
            {
                "geometry_sha256": row["geometry_sha256"],
                "layout_id": row["layout_id"],
                "task_index": row["task_index"],
            }
            for row in selected
        ]
        shards.append(
            {
                "execution_lock_sha256": execution_lock_sha256,
                "fidelity_id": selected[0]["fidelity_id"],
                "manifest_sha256": manifest_sha256,
                "pending": pending,
                "plan_sha256": plan_sha256,
                "schema": TASK_SET_SCHEMA,
            }
        )
    expected_indices = [row["task_index"] for row in rows]
    flattened = [entry["task_index"] for shard in shards for entry in shard["pending"]]
    if (
        expected_indices != sorted(expected_indices)
        or len(set(expected_indices)) != len(expected_indices)
        or flattened != expected_indices
    ):
        raise RuntimeError("submission shards do not exactly cover the selected tasks")
    return shards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--execution-lock", type=Path, required=True)
    parser.add_argument("--expected-execution-lock-sha256", required=True)
    parser.add_argument("--task-set", type=Path)
    parser.add_argument("--expected-task-set-sha256")
    parser.add_argument("--max-array-size", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    _, _, manifest_rows, _, manifest_sha256 = validate_frozen_inputs(
        args.protocol,
        args.plan,
        args.expected_plan_sha256,
        args.manifest,
    )
    _, lock_sha256 = validate_execution_lock(
        args.execution_lock, args.expected_execution_lock_sha256
    )
    if (args.task_set is None) != (args.expected_task_set_sha256 is None):
        raise ValueError("task set and its externally pinned SHA-256 are both required")
    rows = manifest_rows
    source_task_set_sha256 = None
    if args.task_set is not None:
        require_file_sha256(
            args.task_set, args.expected_task_set_sha256, "source task set"
        )
        task_set = load_json(args.task_set)
        if (
            task_set.get("schema") != TASK_SET_SCHEMA
            or task_set.get("plan_sha256") != args.expected_plan_sha256
            or task_set.get("manifest_sha256") != manifest_sha256
            or task_set.get("execution_lock_sha256") != lock_sha256
            or task_set.get("fidelity_id") != manifest_rows[0]["fidelity_id"]
        ):
            raise ValueError("source task set does not bind the frozen execution roots")
        expected_by_index = {row["task_index"]: row for row in manifest_rows}
        selected_rows: list[dict[str, Any]] = []
        for entry in task_set.get("pending", []):
            task_index = int(entry.get("task_index", -1))
            expected = expected_by_index.get(task_index)
            if expected is None or (
                entry.get("layout_id") != expected["layout_id"]
                or entry.get("geometry_sha256") != expected["geometry_sha256"]
            ):
                raise ValueError("source task-set identity differs from the manifest")
            selected_rows.append(expected)
        if not selected_rows:
            raise ValueError("source task set is empty")
        rows = selected_rows
        source_task_set_sha256 = args.expected_task_set_sha256
    shards = build_shards(
        rows,
        plan_sha256=args.expected_plan_sha256,
        manifest_sha256=manifest_sha256,
        execution_lock_sha256=lock_sha256,
        max_array_size=args.max_array_size,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    expected_paths = [args.out / f"dispatch_shard_{index:03d}.json" for index in range(len(shards))]
    summary_path = args.out / "submission_shards.json"
    if summary_path.exists() or any(path.exists() for path in expected_paths):
        raise SystemExit("refusing to overwrite an existing submission-shard artifact")
    for path, shard in zip(expected_paths, shards):
        atomic_write_json(path, shard)
    summary = {
        "algorithm": "contiguous_canonical_indices_v1",
        "execution_lock_sha256": lock_sha256,
        "fidelity_id": rows[0]["fidelity_id"],
        "manifest_sha256": manifest_sha256,
        "max_array_size": args.max_array_size,
        "n_dispatched_tasks": len(rows),
        "n_manifest_tasks": len(manifest_rows),
        "n_shards": len(shards),
        "plan_sha256": args.expected_plan_sha256,
        "schema": SUMMARY_SCHEMA,
        "source_task_set_sha256": source_task_set_sha256,
        "shards": [
            {
                "canonical_task_max": shard["pending"][-1]["task_index"],
                "canonical_task_min": shard["pending"][0]["task_index"],
                "local_array_max": len(shard["pending"]) - 1,
                "n_tasks": len(shard["pending"]),
                "path": path.name,
                "sha256": sha256_file(path),
            }
            for path, shard in zip(expected_paths, shards)
        ],
    }
    atomic_write_json(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
