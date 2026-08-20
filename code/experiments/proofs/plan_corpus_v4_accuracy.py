#!/usr/bin/env python3
"""Build the static, family-disjoint Corpus V4 accuracy execution plan.

The planner is intentionally login-safe.  It performs geometry, identity,
fidelity, family, and split validation, but it never trains a model or invokes
a field solver.  All joins use ``(layout_id, geometry_sha256)`` rather than file
position.  The historical Corpus V3 capacitance column is never copied into the
derived evaluation dataset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))
sys.path.insert(0, str(ROOT / "code/quality"))

from geometry_contract import (  # noqa: E402
    geometry_sha256,
    validate_layout,
    validate_passive_labels,
)
from verify_corpus_v4_discrepancy_archive import verify_analysis_archive  # noqa: E402


PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-accuracy-protocol.v1"
PLAN_SCHEMA = "pcb-gnn.corpus-v4-accuracy-plan.v1"
DATASET_ROW_SCHEMA = "pcb-gnn.corpus-v4-accuracy-evaluation-row.v1"
TASK_SCHEMA = "pcb-gnn.corpus-v4-accuracy-task-row.v1"
DEFAULT_PROTOCOL = ROOT / "protocols/corpus_v4_accuracy_v1.json"
DEFAULT_OUT = ROOT / "results/corpus_v4/accuracy/plan/v1"
ARTIFACT_NAMES = (
    "evaluation_dataset.jsonl",
    "task_manifest.jsonl",
    "plan.json",
)
EXPECTED_INPUT_NAMES = {
    "archive_manifest",
    "discrepancy_analysis_manifest",
    "final_observations",
    "geometry_families",
    "hf_selection_registry",
    "inductance_labels",
    "layouts",
    "source_corpus_summary",
    "split_registry",
}
EXPECTED_SEEDS = (40, 41, 42, 43, 44)
EXPECTED_LAYOUT_COUNTS = {
    40: {"train": 1039, "validation": 170, "test": 291},
    41: {"train": 1066, "validation": 152, "test": 282},
    42: {"train": 1012, "validation": 182, "test": 306},
    43: {"train": 1076, "validation": 125, "test": 299},
    44: {"train": 1055, "validation": 153, "test": 292},
}
EXPECTED_FAMILY_COUNTS = {"train": 46, "validation": 7, "test": 13}
EXPECTED_R4_COUNTS = {"train": 138, "validation": 21, "test": 39}
TARGET_NAMES = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
FIDELITY_IDS = {
    "Cps_pF": "cps_fem_r3_p16",
    "L_pri_nH": "fasthenry_100khz_active_leg",
    "L_sec_nH": "fasthenry_100khz_active_leg",
    "L_mut_nH": "fasthenry_100khz_active_leg",
}
TARGET_UNITS = {
    "Cps_pF": "pF",
    "L_pri_nH": "nH",
    "L_sec_nH": "nH",
    "L_mut_nH": "nH",
}


class AccuracyPlanError(ValueError):
    """Raised when a frozen input or derived plan violates the contract."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def canonical_jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


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
        raise AccuracyPlanError(f"invalid strict JSON in {label}: {exc}") from exc


def load_json(path: Path) -> dict[str, Any]:
    payload = _strict_json_loads(path.read_text(encoding="utf-8"), str(path))
    if not isinstance(payload, dict):
        raise AccuracyPlanError(f"expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            raise AccuracyPlanError(f"blank JSONL row at {path}:{line_number}")
        row = _strict_json_loads(line, f"{path}:{line_number}")
        if not isinstance(row, dict):
            raise AccuracyPlanError(f"non-object JSONL row at {path}:{line_number}")
        rows.append(row)
    return rows


def resolve_repo_file(root: Path, record: dict[str, Any], label: str) -> Path:
    if set(record) != {"path", "sha256"}:
        raise AccuracyPlanError(f"{label} pin must contain only path and sha256")
    relative = record.get("path")
    expected = record.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
        raise AccuracyPlanError(f"malformed {label} pin")
    relative_path = PurePosixPath(relative)
    if (
        not relative
        or relative_path.is_absolute()
        or ".." in relative_path.parts
        or relative_path.as_posix() != relative
    ):
        raise AccuracyPlanError(f"{label} path is not canonical repository-relative")
    candidate = root
    for component in relative_path.parts:
        candidate /= component
        if candidate.is_symlink():
            raise AccuracyPlanError(f"{label} traverses a symlink")
    if not candidate.is_file():
        raise AccuracyPlanError(f"{label} is missing or is a symlink")
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise AccuracyPlanError(f"{label} escapes repository root") from exc
    if sha256_file(candidate) != expected:
        raise AccuracyPlanError(f"{label} hash mismatch")
    return candidate


def validate_protocol(protocol: dict[str, Any]) -> None:
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise AccuracyPlanError("unexpected accuracy protocol schema")
    seeds = protocol.get("seeds", {})
    if (
        tuple(seeds.get("split", ())) != EXPECTED_SEEDS
        or tuple(seeds.get("init", ())) != EXPECTED_SEEDS
        or seeds.get("tasks") != 25
        or seeds.get("mapping") != "row-major: task_id = split_index * 5 + init_index"
    ):
        raise AccuracyPlanError("accuracy seed grid is not the frozen 5x5 design")
    splits = protocol.get("splits", {})
    if (
        splits.get("families") != EXPECTED_FAMILY_COUNTS
        or splits.get("r4_test_layouts_per_split") != 39
        or splits.get("source")
        != "frozen split_registry.json; never regenerated"
    ):
        raise AccuracyPlanError("family split contract differs from the frozen design")
    if protocol.get("checkpoint", {}).get("designated_downstream_task_id") != 12:
        raise AccuracyPlanError("downstream checkpoint task must be predeclared as task 12")
    if protocol.get("resources", {}).get("training", {}).get("array") != "0-24%5":
        raise AccuracyPlanError("training array must be exactly 0-24%5")
    if protocol.get("runtime") != {
        "numpy_distribution": "2.0.2",
        "python": "3.9.21",
        "torch_distribution": "2.8.0",
    }:
        raise AccuracyPlanError("accuracy runtime differs from the frozen proof environment")
    if set(protocol.get("inputs", {})) != EXPECTED_INPUT_NAMES:
        raise AccuracyPlanError("accuracy protocol input set is not exact")
    if [row.get("name") for row in protocol.get("targets", [])] != list(TARGET_NAMES):
        raise AccuracyPlanError("accuracy target order is not frozen")
    if [row.get("fidelity_id") for row in protocol["targets"]] != [
        FIDELITY_IDS[name] for name in TARGET_NAMES
    ]:
        raise AccuracyPlanError("accuracy training fidelities are not frozen")
    if protocol.get("validation_fidelity") != {
        "fidelity_id": "cps_fem_r4_p16",
        "role": "evaluation-only higher-resolution comparator",
        "units": "pF",
    }:
        raise AccuracyPlanError("R4 must remain an evaluation-only comparator")
    forbidden = protocol.get("forbidden_actions", {})
    if not forbidden or any(value is not True for value in forbidden.values()):
        raise AccuracyPlanError("all frozen leakage and overclaim prohibitions must be enabled")


def require_pinned_inputs(
    root: Path, protocol: dict[str, Any]
) -> dict[str, Path]:
    return {
        name: resolve_repo_file(root, protocol["inputs"][name], name)
        for name in sorted(EXPECTED_INPUT_NAMES)
    }


def validate_archive_links(
    protocol: dict[str, Any], paths: dict[str, Path]
) -> None:
    archive = load_json(paths["archive_manifest"])
    if archive.get("schema") != "pcb-gnn.cps-multifidelity-archive.v1":
        raise AccuracyPlanError("unexpected upstream archive schema")
    links = (
        (archive["source_corpus"]["summary"], protocol["inputs"]["source_corpus_summary"]),
        (archive["source_corpus"]["layouts"], protocol["inputs"]["layouts"]),
        (archive["source_corpus"]["labels"], protocol["inputs"]["inductance_labels"]),
        (archive["final"]["observations"], protocol["inputs"]["final_observations"]),
    )
    for actual, expected in links:
        if actual["path"] != expected["path"] or actual["sha256"] != expected["sha256"]:
            raise AccuracyPlanError("accuracy inputs do not descend from the upstream archive")
    if (
        archive["source_corpus"].get("expected_geometries") != 1500
        or archive["final"]["observations"].get("expected_rows") != 1698
    ):
        raise AccuracyPlanError("upstream archive cardinality is not frozen")
    discrepancy = load_json(paths["discrepancy_analysis_manifest"])
    upstream = discrepancy.get("files", {}).get("upstream_archive")
    if upstream != protocol["inputs"]["archive_manifest"]:
        raise AccuracyPlanError("discrepancy analysis does not reference the pinned archive")


def index_unique(
    rows: Iterable[dict[str, Any]], key_name: str, label: str
) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for row in rows:
        key = row.get(key_name)
        if not isinstance(key, int) or isinstance(key, bool) or key in indexed:
            raise AccuracyPlanError(f"{label} contains invalid or duplicate {key_name}")
        indexed[key] = row
    return indexed


def expected_family_id(layout: dict[str, Any]) -> str:
    primary = sum(trace.get("net") == "pri" for trace in layout["traces"])
    secondary = sum(trace.get("net") == "sec" for trace in layout["traces"])
    lower, upper = sorted((primary, secondary))
    return f"turns-{lower:02d}-{upper:02d}"


def validate_geometry_and_inductance(
    paths: dict[str, Path],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    summary = load_json(paths["source_corpus_summary"])
    if (
        summary.get("schema") != "pcb-gnn.corpus-v3-final.v1"
        or summary.get("gates", {}).get("n_layouts") != 1500
        or summary["gates"].get("n_unique_geometry_hashes") != 1500
        or summary["gates"].get("geometry_valid") is not True
        or summary["gates"].get("all_labels_passive") is not True
        or summary["gates"].get("all_array_tasks_clean_and_source_identical") is not True
        or summary.get("artifacts_sha256", {}).get("layouts.jsonl")
        != sha256_file(paths["layouts"])
        or summary.get("artifacts_sha256", {}).get("labels.jsonl")
        != sha256_file(paths["inductance_labels"])
    ):
        raise AccuracyPlanError("source corpus summary does not close the frozen corpus")
    layouts = index_unique(load_jsonl(paths["layouts"]), "layout_id", "layouts")
    labels = index_unique(
        load_jsonl(paths["inductance_labels"]), "layout_id", "inductance labels"
    )
    exact_ids = set(range(1500))
    if set(layouts) != exact_ids or set(labels) != exact_ids:
        raise AccuracyPlanError("source layouts and inductance labels are not dense 0..1499")
    seen_hashes: set[str] = set()
    for layout_id in range(1500):
        layout_row = layouts[layout_id]
        label_row = labels[layout_id]
        geometry_hash = layout_row.get("geometry_sha256")
        if (
            not isinstance(geometry_hash, str)
            or len(geometry_hash) != 64
            or geometry_hash in seen_hashes
            or label_row.get("geometry_sha256") != geometry_hash
        ):
            raise AccuracyPlanError("layout/inductance geometry identity mismatch")
        validate_layout(layout_row["layout"])
        if geometry_sha256(layout_row["layout"]) != geometry_hash:
            raise AccuracyPlanError("recomputed layout geometry hash mismatch")
        seen_hashes.add(geometry_hash)
    return layouts, labels


def validate_family_registry(
    path: Path, layouts: dict[int, dict[str, Any]]
) -> tuple[dict[str, set[int]], dict[int, str]]:
    rows = load_jsonl(path)
    if len(rows) != 66:
        raise AccuracyPlanError("geometry family registry must contain 66 families")
    family_members: dict[str, set[int]] = {}
    family_by_layout: dict[int, str] = {}
    for row in rows:
        family_id = row.get("family_id")
        member_ids = row.get("member_layout_ids")
        member_hashes = row.get("member_geometry_sha256")
        if (
            row.get("schema") != "pcb-gnn.geometry-family-registry.v1"
            or not isinstance(family_id, str)
            or family_id in family_members
            or not isinstance(member_ids, list)
            or not isinstance(member_hashes, list)
            or len(member_ids) != len(member_hashes)
            or row.get("n_members") != len(member_ids)
            or member_ids != sorted(member_ids)
        ):
            raise AccuracyPlanError("malformed geometry family registry row")
        members: set[int] = set()
        for layout_id, geometry_hash in zip(member_ids, member_hashes):
            if (
                not isinstance(layout_id, int)
                or layout_id in family_by_layout
                or layout_id not in layouts
                or layouts[layout_id]["geometry_sha256"] != geometry_hash
                or expected_family_id(layouts[layout_id]["layout"]) != family_id
            ):
                raise AccuracyPlanError("family membership disagrees with frozen geometry")
            members.add(layout_id)
            family_by_layout[layout_id] = family_id
        if len(members) != len(member_ids):
            raise AccuracyPlanError("duplicate layout inside a family")
        family_members[family_id] = members
    if set(family_by_layout) != set(range(1500)):
        raise AccuracyPlanError("family registry does not cover exactly 1,500 layouts")
    return family_members, family_by_layout


def validate_selection_registry(
    path: Path,
    layouts: dict[int, dict[str, Any]],
    family_by_layout: dict[int, str],
) -> set[int]:
    selection = load_json(path)
    rows = selection.get("rows")
    if (
        selection.get("schema") != "pcb-gnn.hf-selection-registry.v1"
        or not isinstance(rows, list)
        or len(rows) != 198
    ):
        raise AccuracyPlanError("unexpected high-fidelity selection registry")
    selected: set[int] = set()
    family_counts: Counter[str] = Counter()
    family_ranks: dict[str, set[int]] = {}
    anchors = 0
    for row in rows:
        layout_id = row.get("layout_id")
        family_id = row.get("family_id")
        if (
            not isinstance(layout_id, int)
            or layout_id in selected
            or layout_id not in layouts
            or row.get("geometry_sha256") != layouts[layout_id]["geometry_sha256"]
            or family_by_layout[layout_id] != family_id
            or not isinstance(row.get("is_mandatory_anchor"), bool)
        ):
            raise AccuracyPlanError("selection registry identity mismatch")
        selected.add(layout_id)
        family_counts[family_id] += 1
        family_ranks.setdefault(family_id, set()).add(row.get("selection_rank_within_family"))
        anchors += int(row["is_mandatory_anchor"])
    if (
        len(family_counts) != 66
        or set(family_counts.values()) != {3}
        or any(ranks != {0, 1, 2} for ranks in family_ranks.values())
        or anchors != 9
    ):
        raise AccuracyPlanError("selection registry is not three-per-family with nine anchors")
    return selected


def validate_observations(
    path: Path,
    layouts: dict[int, dict[str, Any]],
    selected: set[int],
) -> tuple[dict[int, float], dict[int, float]]:
    rows = load_jsonl(path)
    if len(rows) != 1698:
        raise AccuracyPlanError("final observations must contain exactly 1,698 rows")
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        layout_id = row.get("layout_id")
        fidelity_id = row.get("fidelity_id")
        key = (layout_id, fidelity_id)
        if (
            not isinstance(layout_id, int)
            or layout_id not in layouts
            or fidelity_id not in {"cps_fem_r3_p16", "cps_fem_r4_p16"}
            or key in by_key
            or row.get("geometry_sha256") != layouts[layout_id]["geometry_sha256"]
            or row.get("units") != "pF"
        ):
            raise AccuracyPlanError("final observation identity or fidelity mismatch")
        value = row.get("cps_pf")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise AccuracyPlanError("capacitance observations must be finite and positive")
        by_key[key] = row
    r3 = {
        layout_id: float(by_key[(layout_id, "cps_fem_r3_p16")]["cps_pf"])
        for layout_id in range(1500)
        if (layout_id, "cps_fem_r3_p16") in by_key
    }
    r4 = {
        layout_id: float(by_key[(layout_id, "cps_fem_r4_p16")]["cps_pf"])
        for layout_id in selected
        if (layout_id, "cps_fem_r4_p16") in by_key
    }
    if set(r3) != set(range(1500)) or set(r4) != selected or len(by_key) != 1698:
        raise AccuracyPlanError("R3/R4 observation coverage is not exact")
    return r3, r4


def validate_split_registry(
    registry: dict[str, Any],
    family_members: dict[str, set[int]],
    selected: set[int],
    protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = registry.get("rows")
    if (
        registry.get("schema") != "pcb-gnn.swap-closed-split-registry.v1"
        or not isinstance(rows, list)
        or [row.get("split_seed") for row in rows] != list(EXPECTED_SEEDS)
        or tuple(protocol["seeds"]["split"]) != EXPECTED_SEEDS
    ):
        raise AccuracyPlanError("split registry is not the frozen five-row design")
    all_families = set(family_members)
    exact_layouts = set(range(1500))
    validated: list[dict[str, Any]] = []
    for row in rows:
        seed = row["split_seed"]
        partitions = row.get("partitions")
        if not isinstance(partitions, dict) or set(partitions) != set(EXPECTED_FAMILY_COUNTS):
            raise AccuracyPlanError("split partition set is not exact")
        family_sets: dict[str, set[str]] = {}
        layout_sets: dict[str, set[int]] = {}
        frozen_partitions: dict[str, dict[str, Any]] = {}
        for name in ("train", "validation", "test"):
            partition = partitions[name]
            family_ids = partition.get("family_ids")
            layout_ids = partition.get("layout_ids")
            if (
                not isinstance(family_ids, list)
                or not isinstance(layout_ids, list)
                or family_ids != sorted(family_ids)
                or layout_ids != sorted(layout_ids)
                or len(family_ids) != EXPECTED_FAMILY_COUNTS[name]
                or len(layout_ids) != EXPECTED_LAYOUT_COUNTS[seed][name]
                or partition.get("n_families") != len(family_ids)
                or partition.get("n_layouts") != len(layout_ids)
            ):
                raise AccuracyPlanError("split partition counts or ordering differ")
            family_set = set(family_ids)
            expected_ids = {
                layout_id
                for family_id in family_set
                for layout_id in family_members.get(family_id, set())
            }
            layout_set = set(layout_ids)
            if expected_ids != layout_set or len(layout_set) != len(layout_ids):
                raise AccuracyPlanError("split layout membership disagrees with family registry")
            r4_ids = sorted(layout_set & selected)
            if len(r4_ids) != EXPECTED_R4_COUNTS[name]:
                raise AccuracyPlanError("split R4 coverage differs from three-per-family design")
            family_sets[name] = family_set
            layout_sets[name] = layout_set
            frozen_partitions[name] = {
                "family_ids": family_ids,
                "layout_ids": layout_ids,
                "n_families": len(family_ids),
                "n_layouts": len(layout_ids),
                "n_r4_layouts": len(r4_ids),
            }
        if (
            set.union(*family_sets.values()) != all_families
            or sum(len(value) for value in family_sets.values()) != len(all_families)
            or set.union(*layout_sets.values()) != exact_layouts
            or sum(len(value) for value in layout_sets.values()) != 1500
        ):
            raise AccuracyPlanError("split partitions are not disjoint and exhaustive")
        validated.append(
            {
                "partitions": frozen_partitions,
                "r4_test_layout_ids": sorted(layout_sets["test"] & selected),
                "split_seed": seed,
            }
        )
    return validated


def build_evaluation_rows(
    layouts: dict[int, dict[str, Any]],
    inductance: dict[int, dict[str, Any]],
    family_by_layout: dict[int, str],
    r3: dict[int, float],
    r4: dict[int, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for layout_id in range(1500):
        label = inductance[layout_id]
        target_values = {
            "Cps_pF": r3[layout_id],
            "L_pri_nH": float(label["L_pri_nH"]),
            "L_sec_nH": float(label["L_sec_nH"]),
            "L_mut_nH": float(label["L_mut_nH"]),
        }
        if any(not math.isfinite(value) or value <= 0 for value in target_values.values()):
            raise AccuracyPlanError("log1p training targets must be finite and positive")
        validate_passive_labels(target_values)
        training_reference = {
            name: {
                "fidelity_id": FIDELITY_IDS[name],
                "units": TARGET_UNITS[name],
                "value": target_values[name],
            }
            for name in TARGET_NAMES
        }
        r4_reference = None
        if layout_id in r4:
            r4_reference = {
                "fidelity_id": "cps_fem_r4_p16",
                "units": "pF",
                "value": r4[layout_id],
            }
        rows.append(
            {
                "evaluation_only_r4_cps": r4_reference,
                "family_id": family_by_layout[layout_id],
                "geometry_sha256": layouts[layout_id]["geometry_sha256"],
                "layout_id": layout_id,
                "schema": DATASET_ROW_SCHEMA,
                "training_reference": training_reference,
            }
        )
    return rows


def build_task_rows(
    protocol: dict[str, Any],
    protocol_sha256: str,
    evaluation_sha256: str,
    split_rows: list[dict[str, Any]],
    layouts: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    designated = protocol["checkpoint"]["designated_downstream_task_id"]
    split_by_seed = {row["split_seed"]: row for row in split_rows}
    for split_index, split_seed in enumerate(EXPECTED_SEEDS):
        split = split_by_seed[split_seed]
        for init_index, init_seed in enumerate(EXPECTED_SEEDS):
            task_id = split_index * 5 + init_index
            r4_test_ids = split["r4_test_layout_ids"]
            partition_counts = {
                name: split["partitions"][name]["n_layouts"]
                for name in ("train", "validation", "test")
            }
            partition_family_counts = {
                name: split["partitions"][name]["n_families"]
                for name in ("train", "validation", "test")
            }
            partition_layout_ids_sha256 = {
                name: sha256_bytes(
                    canonical_json_bytes(split["partitions"][name]["layout_ids"])
                )
                for name in ("train", "validation", "test")
            }
            partition_family_ids_sha256 = {
                name: sha256_bytes(
                    canonical_json_bytes(split["partitions"][name]["family_ids"])
                )
                for name in ("train", "validation", "test")
            }
            tasks.append(
                {
                    "designated_downstream_checkpoint": task_id == designated,
                    "evaluation_dataset_sha256": evaluation_sha256,
                    "init_seed": init_seed,
                    "partition_counts": partition_counts,
                    "partition_family_counts": partition_family_counts,
                    "partition_family_ids_sha256": partition_family_ids_sha256,
                    "partition_layout_ids_sha256": partition_layout_ids_sha256,
                    "partitions": split["partitions"],
                    "protocol_sha256": protocol_sha256,
                    "r4_test_geometry_sha256": [
                        layouts[layout_id]["geometry_sha256"] for layout_id in r4_test_ids
                    ],
                    "r4_test_layout_count": len(r4_test_ids),
                    "r4_test_layout_ids": r4_test_ids,
                    "r4_test_layout_ids_sha256": sha256_bytes(
                        canonical_json_bytes(r4_test_ids)
                    ),
                    "schema": TASK_SCHEMA,
                    "split_seed": split_seed,
                    "task_id": task_id,
                }
            )
    if [row["task_id"] for row in tasks] != list(range(25)):
        raise AccuracyPlanError("task IDs are not dense row-major 0..24")
    if [(row["split_seed"], row["init_seed"]) for row in tasks][12] != (42, 42):
        raise AccuracyPlanError("task 12 is not the predeclared split42/init42 arm")
    if sum(row["designated_downstream_checkpoint"] for row in tasks) != 1:
        raise AccuracyPlanError("exactly one downstream checkpoint must be designated")
    return tasks


def build_artifacts(
    *, root: Path = ROOT, protocol_path: Path = DEFAULT_PROTOCOL
) -> dict[str, bytes]:
    root = root.resolve()
    protocol_path = protocol_path.resolve()
    protocol = load_json(protocol_path)
    validate_protocol(protocol)
    protocol_sha256 = sha256_file(protocol_path)
    paths = require_pinned_inputs(root, protocol)
    verify_analysis_archive(
        root,
        paths["discrepancy_analysis_manifest"],
        require_git_tracked=True,
    )
    validate_archive_links(protocol, paths)
    layouts, inductance = validate_geometry_and_inductance(paths)
    family_members, family_by_layout = validate_family_registry(
        paths["geometry_families"], layouts
    )
    selected = validate_selection_registry(
        paths["hf_selection_registry"], layouts, family_by_layout
    )
    r3, r4 = validate_observations(paths["final_observations"], layouts, selected)
    split_rows = validate_split_registry(
        load_json(paths["split_registry"]), family_members, selected, protocol
    )
    evaluation_rows = build_evaluation_rows(
        layouts, inductance, family_by_layout, r3, r4
    )
    evaluation_bytes = canonical_jsonl_bytes(evaluation_rows)
    task_rows = build_task_rows(
        protocol,
        protocol_sha256,
        sha256_bytes(evaluation_bytes),
        split_rows,
        layouts,
    )
    task_bytes = canonical_jsonl_bytes(task_rows)
    test_memberships = [
        layout_id for row in split_rows for layout_id in row["r4_test_layout_ids"]
    ]
    test_families = {
        family_by_layout[layout_id] for layout_id in test_memberships
    }
    plan = {
        "artifact_sha256": {
            "evaluation_dataset.jsonl": sha256_bytes(evaluation_bytes),
            "task_manifest.jsonl": sha256_bytes(task_bytes),
        },
        "counts": {
            "designated_downstream_tasks": 1,
            "evaluation_rows": 1500,
            "families": 66,
            "r3_observations": 1500,
            "r4_observations": 198,
            "split_rows": 5,
            "tasks": 25,
        },
        "designated_downstream": {
            "init_seed": 42,
            "split_seed": 42,
            "task_id": 12,
        },
        "input_sha256": {
            name: protocol["inputs"][name]["sha256"]
            for name in sorted(EXPECTED_INPUT_NAMES)
        },
        "partition_summary": [
            {
                "layout_counts": {
                    name: row["partitions"][name]["n_layouts"]
                    for name in ("train", "validation", "test")
                },
                "r4_counts": {
                    name: row["partitions"][name]["n_r4_layouts"]
                    for name in ("train", "validation", "test")
                },
                "split_seed": row["split_seed"],
            }
            for row in split_rows
        ],
        "planner_source_sha256": {
            "code/core/geometry_contract.py": sha256_file(
                root / "code/core/geometry_contract.py"
            ),
            "code/core/scientific_artifact.py": sha256_file(
                root / "code/core/scientific_artifact.py"
            ),
            "code/experiments/proofs/plan_corpus_v4_accuracy.py": sha256_file(
                Path(__file__).resolve()
            ),
            "code/experiments/proofs/audit_corpus_v4_cps_fidelity_discrepancy.py": sha256_file(
                root
                / "code/experiments/proofs/audit_corpus_v4_cps_fidelity_discrepancy.py"
            ),
            "code/quality/verify_corpus_v4_archive.py": sha256_file(
                root / "code/quality/verify_corpus_v4_archive.py"
            ),
            "code/quality/verify_corpus_v4_discrepancy_archive.py": sha256_file(
                root / "code/quality/verify_corpus_v4_discrepancy_archive.py"
            ),
        },
        "protocol_sha256": protocol_sha256,
        "r4_test_overlap": {
            "panel_memberships": len(test_memberships),
            "unique_families": len(test_families),
            "unique_layouts": len(set(test_memberships)),
        },
        "schema": PLAN_SCHEMA,
        "scientific_scope": {
            "legacy_cps_used": False,
            "random_split_used": False,
            "r4_role": "evaluation-only on each split's 39 selected test layouts",
            "test_panels_are_independent": False,
        },
        "seeds": {
            "init": list(EXPECTED_SEEDS),
            "mapping": "row-major: task_id = split_index * 5 + init_index",
            "split": list(EXPECTED_SEEDS),
        },
    }
    return {
        "evaluation_dataset.jsonl": evaluation_bytes,
        "task_manifest.jsonl": task_bytes,
        "plan.json": canonical_json_bytes(plan),
    }


def materialize_plan(
    out: Path, artifacts: dict[str, bytes], *, check: bool = False
) -> None:
    if set(artifacts) != set(ARTIFACT_NAMES):
        raise AccuracyPlanError("planner artifact set is not exact")
    if check:
        if not out.is_dir() or out.is_symlink():
            raise AccuracyPlanError("plan directory is missing or is a symlink")
        entries = list(out.iterdir())
        if {entry.name for entry in entries} != set(ARTIFACT_NAMES):
            raise AccuracyPlanError("plan directory inventory is not exact")
        for name in ARTIFACT_NAMES:
            path = out / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != artifacts[name]:
                raise AccuracyPlanError(
                    f"plan artifact differs from deterministic rebuild: {name}"
                )
        return
    if out.exists():
        raise AccuracyPlanError("refusing to overwrite an existing plan path")
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp.", dir=out.parent))
    try:
        for name in ARTIFACT_NAMES:
            with (temporary / name).open("xb") as handle:
                handle.write(artifacts[name])
        os.replace(temporary, out)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in memory and byte-compare the exact existing plan inventory",
    )
    args = parser.parse_args()
    try:
        artifacts = build_artifacts(protocol_path=args.protocol)
        materialize_plan(args.out, artifacts, check=args.check)
    except (AccuracyPlanError, KeyError, TypeError, ValueError) as exc:
        print(f"Corpus V4 accuracy plan: FAIL: {exc}", file=sys.stderr)
        return 1
    action = "CHECK" if args.check else "WRITE"
    print(f"Corpus V4 accuracy plan: {action} PASS (25 tasks, 1,500 rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
