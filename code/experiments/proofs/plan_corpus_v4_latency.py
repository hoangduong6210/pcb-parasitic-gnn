#!/usr/bin/env python3
"""Build the solver-free plan for the Corpus V4 paired-latency study.

The panel is the complete, predesignated split-42 test partition of accuracy
task 12.  This planner authenticates that partition and serializes geometry
only; labels, predictions, solver outcomes, and timings cannot influence panel
membership or task order.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for _directory in (
    ROOT / "code/core",
    ROOT / "code/data",
    ROOT / "code/experiments/proofs",
):
    sys.path.insert(0, str(_directory))

from corpus_v4_accuracy_dataset import load_corpus_v4_accuracy_dataset  # noqa: E402
from corpus_v4_latency_contract import (  # noqa: E402
    DESIGNATED_INIT_SEED,
    DESIGNATED_SPLIT_SEED,
    DESIGNATED_TASK_ID,
    EXPECTED_FAMILIES,
    EXPECTED_INPUT_NAMES,
    EXPECTED_LAYOUTS,
    PANEL_ROW_SCHEMA,
    PLAN_SCHEMA,
    PLANNER_SOURCE_NAMES,
    TASK_ROW_SCHEMA,
    LatencyContractError,
    panel_row_sha256,
    resolve_protocol_inputs,
    validate_protocol,
    validate_upstream_closure,
)
from scientific_artifact import canonical_json_bytes, sha256_bytes, sha256_file  # noqa: E402


DEFAULT_PROTOCOL = ROOT / "protocols/corpus_v4_latency_v1.json"
DEFAULT_OUT = ROOT / "results/corpus_v4/latency/plan/v1"
ARTIFACT_NAMES = ("panel_records.jsonl", "task_manifest.jsonl", "plan.json")


class LatencyPlanError(ValueError):
    """Raised when the immutable latency panel cannot be reconstructed."""


def _canonical_jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(dict(row)) + b"\n" for row in rows)


def _checkpoint_identity(protocol: Mapping[str, Any]) -> dict[str, Any]:
    inputs = protocol["inputs"]
    return {
        "archive_sha256": inputs["checkpoint_archive"]["sha256"],
        "init_seed": DESIGNATED_INIT_SEED,
        "metadata_sha256": inputs["checkpoint_metadata"]["sha256"],
        "smoke_examples_sha256": inputs["checkpoint_smoke_examples"]["sha256"],
        "split_seed": DESIGNATED_SPLIT_SEED,
        "task_id": DESIGNATED_TASK_ID,
    }


def build_artifacts(
    *,
    root: Path = ROOT,
    protocol_path: Path = DEFAULT_PROTOCOL,
) -> dict[str, bytes]:
    """Reconstruct all plan bytes without training or invoking a solver."""
    root = root.resolve()
    if root != ROOT.resolve():
        raise LatencyPlanError("latency planning root is not the repository root")
    protocol_path = protocol_path.resolve()
    protocol, protocol_sha = validate_protocol(protocol_path)
    paths = resolve_protocol_inputs(protocol)
    designated_task, upstream_checkpoint = validate_upstream_closure(protocol, paths)
    dataset = load_corpus_v4_accuracy_dataset(
        root=root,
        protocol_path=paths["accuracy_protocol"],
    )

    frozen_layout_ids = designated_task.get("partitions", {}).get("test", {}).get(
        "layout_ids"
    )
    frozen_family_ids = designated_task.get("partitions", {}).get("test", {}).get(
        "family_ids"
    )
    if (
        not isinstance(frozen_layout_ids, list)
        or frozen_layout_ids != sorted(set(frozen_layout_ids))
        or len(frozen_layout_ids) != EXPECTED_LAYOUTS
        or not isinstance(frozen_family_ids, list)
        or len(frozen_family_ids) != EXPECTED_FAMILIES
        or len(set(frozen_family_ids)) != EXPECTED_FAMILIES
    ):
        raise LatencyPlanError("task-12 test membership is not canonical")
    split = dataset.splits[DESIGNATED_SPLIT_SEED].test
    if list(split.layout_ids) != frozen_layout_ids:
        raise LatencyPlanError("dataset split-42 layouts differ from accuracy task 12")
    if list(split.family_ids) != frozen_family_ids:
        raise LatencyPlanError("dataset split-42 families differ from accuracy task 12")

    by_layout_id = dataset.sample_by_layout_id()
    panel_rows: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    for task_id, layout_id in enumerate(frozen_layout_ids):
        sample = by_layout_id.get(layout_id)
        if sample is None:
            raise LatencyPlanError(f"panel layout is absent from the dataset: {layout_id}")
        panel_row = {
            "family_id": sample.family_id,
            "geometry_sha256": sample.geometry_sha256,
            "layout": dict(sample.layout),
            "layout_id": sample.layout_id,
            "schema": PANEL_ROW_SCHEMA,
        }
        task_row = {
            "family_id": sample.family_id,
            "geometry_sha256": sample.geometry_sha256,
            "layout_id": sample.layout_id,
            "panel_record_sha256": panel_row_sha256(panel_row),
            "protocol_sha256": protocol_sha,
            "schema": TASK_ROW_SCHEMA,
            "task_id": task_id,
        }
        panel_rows.append(panel_row)
        task_rows.append(task_row)
        family_counts[sample.family_id] += 1
    if set(family_counts) != set(frozen_family_ids):
        raise LatencyPlanError("panel family membership differs from task 12")

    panel_bytes = _canonical_jsonl_bytes(panel_rows)
    task_bytes = _canonical_jsonl_bytes(task_rows)
    checkpoint = _checkpoint_identity(protocol)
    if any(upstream_checkpoint.get(name) != value for name, value in checkpoint.items()):
        raise LatencyPlanError("checkpoint summary differs from latency identity")
    plan = {
        "artifact_sha256": {
            "panel_records.jsonl": sha256_bytes(panel_bytes),
            "task_manifest.jsonl": sha256_bytes(task_bytes),
        },
        "checkpoint": checkpoint,
        "counts": {
            "families": EXPECTED_FAMILIES,
            "layouts": EXPECTED_LAYOUTS,
            "tasks": EXPECTED_LAYOUTS,
        },
        "input_sha256": {
            name: protocol["inputs"][name]["sha256"]
            for name in sorted(EXPECTED_INPUT_NAMES)
        },
        "panel": {
            "family_layout_counts": {
                family_id: family_counts[family_id]
                for family_id in sorted(family_counts)
            },
            "layout_ids_sha256": sha256_bytes(canonical_json_bytes(frozen_layout_ids)),
            "task_order": "ascending layout_id",
        },
        "planner_source_sha256": {
            name: sha256_file(root / name) for name in PLANNER_SOURCE_NAMES
        },
        "protocol_sha256": protocol_sha,
        "schema": PLAN_SCHEMA,
        "scientific_scope": {
            "all_designated_test_layouts_included": True,
            "labels_predictions_or_timings_used_for_selection": False,
            "selection_seed": None,
        },
    }
    return {
        "panel_records.jsonl": panel_bytes,
        "task_manifest.jsonl": task_bytes,
        "plan.json": canonical_json_bytes(plan),
    }


def materialize_plan(
    out: Path,
    artifacts: Mapping[str, bytes],
    *,
    check: bool = False,
) -> None:
    """Write once atomically, or byte-check an existing immutable plan."""
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise LatencyPlanError("latency planner artifact inventory is not exact")
    if check:
        if out.is_symlink() or not out.is_dir():
            raise LatencyPlanError("latency plan directory is missing or is a symlink")
        if {entry.name for entry in out.iterdir()} != set(ARTIFACT_NAMES):
            raise LatencyPlanError("latency plan directory inventory is not exact")
        for name in ARTIFACT_NAMES:
            path = out / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != artifacts[name]:
                raise LatencyPlanError(
                    f"latency plan differs from deterministic rebuild: {name}"
                )
        return
    if out.exists() or out.is_symlink():
        raise LatencyPlanError("refusing to overwrite an existing latency plan")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp.", dir=out.parent))
    try:
        for name in ARTIFACT_NAMES:
            with (temporary / name).open("xb") as handle:
                handle.write(artifacts[name])
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, out)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        artifacts = build_artifacts(protocol_path=args.protocol)
        materialize_plan(args.out, artifacts, check=args.check)
    except (
        KeyError,
        LatencyContractError,
        LatencyPlanError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Corpus V4 latency plan: FAIL: {exc}", file=sys.stderr)
        return 1
    action = "CHECK" if args.check else "WRITE"
    print(f"Corpus V4 latency plan: {action} PASS (306 tasks, 13 families)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
