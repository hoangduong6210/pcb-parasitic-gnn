#!/usr/bin/env python3
"""Freeze geometry families, high-fidelity selection, splits, and task manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    load_json,
    require_file_sha256,
    sha256_file,
    sha256_json,
)
from verified_geometry_corpus import load_verified_geometry_corpus  # noqa: E402


PLAN_SCHEMA = "pcb-gnn.cps-multifidelity-plan.v1"
FAMILY_SCHEMA = "pcb-gnn.geometry-family-registry.v1"
SELECTION_SCHEMA = "pcb-gnn.hf-selection-registry.v1"
SPLIT_SCHEMA = "pcb-gnn.swap-closed-split-registry.v1"
MANIFEST_SCHEMA = "pcb-gnn.cps-multifidelity-task-manifest.v1"
PLANNER_SOURCE_NAMES = (
    "code/core/geometry_contract.py",
    "code/core/scientific_artifact.py",
    "code/data/verified_geometry_corpus.py",
    "code/experiments/proofs/plan_corpus_v4_cps_multifidelity.py",
)


def family_identity(layout: dict[str, Any]) -> tuple[str, int, int, int, int]:
    n_primary = sum(trace["net"] == "pri" for trace in layout["traces"])
    n_secondary = sum(trace["net"] == "sec" for trace in layout["traces"])
    lower, upper = sorted((n_primary, n_secondary))
    return f"turns-{lower:02d}-{upper:02d}", lower, upper, n_primary, n_secondary


def _stats(values: Iterable[float]) -> tuple[float, float]:
    vector = np.asarray(list(values), dtype=np.float64)
    return float(vector.mean()), float(vector.std())


def geometry_descriptor(layout: dict[str, Any]) -> list[float]:
    """Return a label-blind fixed-width descriptor used only for HF selection."""
    traces = layout["traces"]
    by_net = {
        net: [trace for trace in traces if trace["net"] == net]
        for net in ("pri", "sec")
    }
    descriptor: list[float] = [
        float(len(by_net["pri"])),
        float(len(by_net["sec"])),
        float(layout["n_layers"]),
    ]
    centroids: dict[str, tuple[float, float]] = {}
    for net in ("pri", "sec"):
        group = by_net[net]
        length_mean, length_std = _stats(float(t["length_mm"]) for t in group)
        width_mean, width_std = _stats(float(t["width_mm"]) for t in group)
        x_mean, x_std = _stats(
            float(t["x0"]) + float(t["length_mm"]) / 2.0 for t in group
        )
        y_mean, y_std = _stats(
            float(t["y0"]) + float(t["width_mm"]) / 2.0 for t in group
        )
        layer_mean, layer_std = _stats(float(t["layer"]) for t in group)
        centroids[net] = (x_mean, y_mean)
        descriptor.extend(
            [
                length_mean,
                length_std,
                width_mean,
                width_std,
                x_mean,
                x_std,
                y_mean,
                y_std,
                layer_mean,
                layer_std,
            ]
        )
    descriptor.extend(
        [
            abs(centroids["pri"][0] - centroids["sec"][0]),
            abs(centroids["pri"][1] - centroids["sec"][1]),
        ]
    )
    if not all(math.isfinite(value) for value in descriptor):
        raise ValueError("non-finite geometry descriptor")
    return descriptor


def _salted_rank(salt: str, geometry_sha256: str) -> str:
    return hashlib.sha256(f"{salt}:{geometry_sha256}".encode("utf-8")).hexdigest()


def select_family_rows(
    rows: list[dict[str, Any]],
    *,
    count: int,
    mandatory_hashes: set[str],
    salt: str,
) -> list[dict[str, Any]]:
    if len(rows) < count:
        raise ValueError("family contains fewer designs than requested HF coverage")
    ordered = sorted(rows, key=lambda row: _salted_rank(salt, row["geometry_sha256"]))
    mandatory = [row for row in ordered if row["geometry_sha256"] in mandatory_hashes]
    if len(mandatory) > count:
        raise ValueError("mandatory anchors exceed per-family HF allocation")
    selected = list(mandatory)
    if not selected:
        selected.append(ordered[0])

    matrix = np.asarray([geometry_descriptor(row["layout"]) for row in ordered])
    scale = matrix.std(axis=0)
    scale[scale == 0.0] = 1.0
    normalized = (matrix - matrix.mean(axis=0)) / scale
    index_by_hash = {
        row["geometry_sha256"]: index for index, row in enumerate(ordered)
    }
    while len(selected) < count:
        selected_indices = [index_by_hash[row["geometry_sha256"]] for row in selected]
        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for index, row in enumerate(ordered):
            if row in selected:
                continue
            min_distance = min(
                float(np.linalg.norm(normalized[index] - normalized[chosen]))
                for chosen in selected_indices
            )
            candidates.append(
                (min_distance, _salted_rank(salt, row["geometry_sha256"]), row)
            )
        candidates.sort(key=lambda item: (-item[0], item[1]))
        selected.append(candidates[0][2])
    return selected


def solver_contract_id(protocol: dict[str, Any], fidelity_id: str) -> str:
    fidelity = protocol["fidelities"][fidelity_id]
    payload = {
        "computational_sources": protocol["computational_sources"],
        "fidelity": {
            "pad_mm": fidelity["pad_mm"],
            "refine": fidelity["refine"],
        },
        "linear_solver": protocol["linear_solver"],
        "physics": protocol["physics"],
        "runtime": protocol["runtime"],
    }
    return sha256_json(payload)


def build_registries(
    records: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[str, Any]:
    selection_spec = protocol["validation_selection"]
    split_spec = protocol["split_registry"]
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    family_metadata: dict[str, tuple[int, int]] = {}
    for record in records:
        family_id, lower, upper, n_primary, n_secondary = family_identity(record["layout"])
        enriched = {
            **record,
            "family_id": family_id,
            "n_primary": n_primary,
            "n_secondary": n_secondary,
        }
        families[family_id].append(enriched)
        family_metadata[family_id] = (lower, upper)
    if len(families) != int(selection_spec["n_families"]):
        raise ValueError("swap-closed family count differs from protocol")

    mandatory_hashes = set(selection_spec["mandatory_geometry_sha256"])
    observed_hashes = {record["geometry_sha256"] for record in records}
    if not mandatory_hashes <= observed_hashes:
        raise ValueError("one or more mandatory anchors are absent")

    family_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    for family_id in sorted(families):
        members = sorted(families[family_id], key=lambda row: row["layout_id"])
        lower, upper = family_metadata[family_id]
        family_rows.append(
            {
                "family_id": family_id,
                "lower_turn_count": lower,
                "member_geometry_sha256": [row["geometry_sha256"] for row in members],
                "member_layout_ids": [row["layout_id"] for row in members],
                "n_members": len(members),
                "schema": FAMILY_SCHEMA,
                "upper_turn_count": upper,
            }
        )
        chosen = select_family_rows(
            members,
            count=int(selection_spec["n_per_family"]),
            mandatory_hashes=mandatory_hashes,
            salt=selection_spec["selection_salt"],
        )
        for rank, row in enumerate(chosen):
            selected_rows.append(
                {
                    "family_expansion_weight": len(members) / len(chosen),
                    "family_id": family_id,
                    "family_coverage_fraction": len(chosen) / len(members),
                    "geometry_sha256": row["geometry_sha256"],
                    "is_mandatory_anchor": row["geometry_sha256"] in mandatory_hashes,
                    "layout_id": row["layout_id"],
                    "selection_rank_within_family": rank,
                }
            )
    if len(selected_rows) != int(selection_spec["n_total"]):
        raise ValueError("HF selection cardinality differs from protocol")

    membership = {
        row["family_id"]: set(row["member_layout_ids"]) for row in family_rows
    }
    family_ids = np.asarray(sorted(families), dtype=object)
    split_rows: list[dict[str, Any]] = []
    for seed in split_spec["split_seeds"]:
        shuffled = np.random.default_rng(int(seed)).permutation(family_ids).tolist()
        n_test = int(split_spec["n_test_families"])
        n_validation = int(split_spec["n_validation_families"])
        if split_spec["partition_assignment"] != "test_13_validation_7_train_remaining_v1":
            raise ValueError("unsupported split partition assignment")
        partitions = {
            "test": shuffled[:n_test],
            "validation": shuffled[n_test : n_test + n_validation],
            "train": shuffled[n_test + n_validation :],
        }
        if len(partitions["train"]) != int(split_spec["n_train_families"]):
            raise ValueError("split family cardinality differs from protocol")
        split_rows.append(
            {
                "partitions": {
                    name: {
                        "family_ids": sorted(ids),
                        "layout_ids": sorted(
                            layout_id for family_id in ids for layout_id in membership[family_id]
                        ),
                        "n_families": len(ids),
                        "n_layouts": sum(len(membership[family_id]) for family_id in ids),
                    }
                    for name, ids in partitions.items()
                },
                "split_seed": int(seed),
            }
        )
    return {
        "family_rows": family_rows,
        "selected_rows": sorted(selected_rows, key=lambda row: row["layout_id"]),
        "split_rows": split_rows,
    }


def validate_protocol(protocol: dict[str, Any]) -> None:
    if protocol.get("schema") != "pcb-gnn.cps-multifidelity-protocol.v1":
        raise ValueError("unexpected protocol schema")
    if protocol["fidelities"]["cps_fem_r3_p16"] != {
        "coverage": 1500,
        "pad_mm": 16.0,
        "refine": 3,
        "role": "bulk_low_fidelity",
    }:
        raise ValueError("R3P16 fidelity is not frozen")
    if protocol["fidelities"]["cps_fem_r4_p16"]["coverage"] != 198:
        raise ValueError("R4P16 coverage must be 198")
    if protocol["scientific_semantics"]["r3_converged_to_r4"] is not False:
        raise ValueError("protocol may not claim R3 convergence")
    for relative, expected in protocol["computational_sources"].items():
        require_file_sha256(ROOT / relative, expected, relative)


def task_manifest(
    records: list[dict[str, Any]],
    fidelity_id: str,
    protocol: dict[str, Any],
    protocol_sha256: str,
) -> list[dict[str, Any]]:
    contract_id = solver_contract_id(protocol, fidelity_id)
    return [
        {
            "fidelity_id": fidelity_id,
            "geometry_sha256": row["geometry_sha256"],
            "layout_id": row["layout_id"],
            "protocol_sha256": protocol_sha256,
            "schema": MANIFEST_SCHEMA,
            "solver_contract_id": contract_id,
            "task_index": index,
        }
        for index, row in enumerate(sorted(records, key=lambda item: item["layout_id"]))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    protocol = load_json(args.protocol)
    validate_protocol(protocol)
    protocol_sha256 = sha256_file(args.protocol)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "protocol_sha256": protocol_sha256,
                    "schema": protocol["schema"],
                    "status": "validation-ok",
                },
                sort_keys=True,
            )
        )
        return
    if args.corpus is None or args.out is None:
        raise SystemExit("--corpus and --out are required unless --validate-only is used")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("refusing to overwrite a non-empty plan directory")

    records, summary = load_verified_geometry_corpus(
        args.corpus, protocol["input_geometry_corpus"]
    )
    registries = build_registries(records, protocol)
    selected_hashes = {row["geometry_sha256"] for row in registries["selected_rows"]}
    r4_records = [row for row in records if row["geometry_sha256"] in selected_hashes]
    manifests = {
        "r3_manifest.jsonl": task_manifest(
            records, "cps_fem_r3_p16", protocol, protocol_sha256
        ),
        "r4_manifest.jsonl": task_manifest(
            r4_records, "cps_fem_r4_p16", protocol, protocol_sha256
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    family_path = args.out / "geometry_families.jsonl"
    selection_path = args.out / "hf_selection_registry.json"
    split_path = args.out / "split_registry.json"
    atomic_write_jsonl(family_path, registries["family_rows"])
    atomic_write_json(
        selection_path,
        {
            "algorithm": protocol["validation_selection"],
            "rows": registries["selected_rows"],
            "schema": SELECTION_SCHEMA,
        },
    )
    atomic_write_json(
        split_path,
        {
            "init_seeds": protocol["split_registry"]["init_seeds"],
            "rows": registries["split_rows"],
            "schema": SPLIT_SCHEMA,
        },
    )
    for name, rows in manifests.items():
        atomic_write_jsonl(args.out / name, rows)

    generated_names = [
        "geometry_families.jsonl",
        "hf_selection_registry.json",
        "split_registry.json",
        *manifests.keys(),
    ]
    plan = {
        "artifact_sha256": {
            name: sha256_file(args.out / name) for name in sorted(generated_names)
        },
        "corpus_summary_sha256": sha256_file(args.corpus / "summary.json"),
        "counts": {
            "families": len(registries["family_rows"]),
            "geometries": len(records),
            "r3_tasks": len(manifests["r3_manifest.jsonl"]),
            "r4_tasks": len(manifests["r4_manifest.jsonl"]),
        },
        "protocol_sha256": protocol_sha256,
        "planner_environment": {
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "planner_source_sha256": {
            name: sha256_file(ROOT / name) for name in PLANNER_SOURCE_NAMES
        },
        "schema": PLAN_SCHEMA,
        "source_corpus_schema": summary["schema"],
        "solver_contract_ids": {
            fidelity_id: solver_contract_id(protocol, fidelity_id)
            for fidelity_id in sorted(protocol["fidelities"])
        },
    }
    atomic_write_json(args.out / "plan.json", plan)
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
