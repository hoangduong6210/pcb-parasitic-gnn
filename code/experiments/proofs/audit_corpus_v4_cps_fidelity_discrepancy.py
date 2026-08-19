#!/usr/bin/env python3
"""Audit matched Corpus v4 FEM-R3P16 and FEM-R4P16 observations."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))
sys.path.insert(0, str(ROOT / "code/quality"))

from scientific_artifact import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from verify_corpus_v4_archive import validate_archive  # noqa: E402


PROTOCOL_SCHEMA = "pcb-gnn.cps-fidelity-discrepancy-protocol.v1"
SUMMARY_SCHEMA = "pcb-gnn.cps-fidelity-discrepancy-summary.v1"
PAIR_SCHEMA = "pcb-gnn.cps-fidelity-discrepancy-pair.v1"
FAMILY_SCHEMA = "pcb-gnn.cps-fidelity-discrepancy-family.v1"
DEFAULT_PROTOCOL = ROOT / "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json"
DEFAULT_OUTPUT = (
    ROOT
    / "results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1"
)
JOB_OUTPUT_RE = re.compile(r"job_[0-9]+")


class DiscrepancyAuditError(ValueError):
    """Raised when the frozen audit contract or its inputs are inconsistent."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DiscrepancyAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise DiscrepancyAuditError(f"non-finite JSON number: {token}")


def _finite_tree(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise DiscrepancyAuditError(f"non-finite number in {label}")
    if isinstance(value, dict):
        for child in value.values():
            _finite_tree(child, label)
    elif isinstance(value, list):
        for child in value:
            _finite_tree(child, label)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscrepancyAuditError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DiscrepancyAuditError(f"expected JSON object: {path}")
    _finite_tree(value, str(path))
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise DiscrepancyAuditError(
                        f"blank JSONL row at {path}:{line_number}"
                    )
                value = json.loads(
                    line,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_nonfinite,
                )
                if not isinstance(value, dict):
                    raise DiscrepancyAuditError(
                        f"expected JSON object at {path}:{line_number}"
                    )
                _finite_tree(value, f"{path}:{line_number}")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscrepancyAuditError(f"cannot load JSONL {path}: {exc}") from exc
    return rows


def resolve_repo_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if "\\" in relative or candidate.is_absolute() or ".." in candidate.parts:
        raise DiscrepancyAuditError(f"unsafe repository-relative path: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise DiscrepancyAuditError(f"path escapes repository: {relative}") from exc
    return resolved


def require_pinned_input(
    root: Path, record: dict[str, Any], label: str
) -> Path:
    relative = record.get("path")
    expected = record.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise DiscrepancyAuditError(f"{label} must define path and SHA-256")
    path = resolve_repo_path(root, relative)
    if not path.is_file():
        raise DiscrepancyAuditError(f"missing {label}: {relative}")
    observed = sha256_file(path)
    if observed != expected:
        raise DiscrepancyAuditError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return path


def quantile_type7(values: Sequence[float], probability: float) -> float:
    """Return the Hyndman-Fan type-7 quantile used by the frozen protocol."""
    if not values:
        raise DiscrepancyAuditError("cannot summarize an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise DiscrepancyAuditError("quantile probability must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def summarize(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        raise DiscrepancyAuditError("cannot summarize an empty sequence")
    finite = [float(value) for value in values]
    if not all(math.isfinite(value) for value in finite):
        raise DiscrepancyAuditError("summary input contains a non-finite number")
    return {
        "count": len(finite),
        "max": max(finite),
        "mean": math.fsum(finite) / len(finite),
        "median": quantile_type7(finite, 0.50),
        "min": min(finite),
        "q25": quantile_type7(finite, 0.25),
        "q75": quantile_type7(finite, 0.75),
        "q90": quantile_type7(finite, 0.90),
        "q95": quantile_type7(finite, 0.95),
    }


def _canonical_jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def _load_protocol_inputs(
    root: Path, protocol_path: Path
) -> tuple[dict[str, Any], dict[str, Path], str]:
    protocol = load_json(protocol_path)
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise DiscrepancyAuditError("unsupported discrepancy-audit protocol schema")
    expected_protocol_path = resolve_repo_path(
        root, "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json"
    )
    if protocol_path.resolve() != expected_protocol_path:
        raise DiscrepancyAuditError("audit protocol must use its canonical repository path")
    inputs = {
        name: require_pinned_input(root, record, name)
        for name, record in protocol.get("inputs", {}).items()
    }
    expected_inputs = {
        "archive_manifest",
        "final_observations",
        "final_summary",
        "geometry_families",
        "hf_selection_registry",
        "multifidelity_protocol",
        "plan",
        "split_registry",
    }
    if set(inputs) != expected_inputs:
        raise DiscrepancyAuditError("protocol input set is incomplete or unexpected")
    require_pinned_input(root, protocol["implementation"], "implementation")
    return protocol, inputs, sha256_file(protocol_path)


def _validate_archive_linkage(
    archive: dict[str, Any], protocol: dict[str, Any]
) -> None:
    final = archive.get("final", {})
    final_record = final.get("observations", {})
    protocol_record = protocol["inputs"]["final_observations"]
    final_summary = final.get("summary", {})
    protocol_summary = protocol["inputs"]["final_summary"]
    frozen_inputs = archive.get("frozen_inputs", {})
    if (
        archive.get("schema") != "pcb-gnn.cps-multifidelity-archive.v1"
        or final_record.get("path") != protocol_record.get("path")
        or final_record.get("sha256") != protocol_record.get("sha256")
        or final_record.get("expected_rows") != 1698
        or final_summary.get("path") != protocol_summary.get("path")
        or final_summary.get("sha256") != protocol_summary.get("sha256")
        or frozen_inputs.get("plan") != protocol["inputs"]["plan"]
        or frozen_inputs.get("protocol")
        != protocol["inputs"]["multifidelity_protocol"]
    ):
        raise DiscrepancyAuditError("archive does not pin the audited observation table")


def _validate_families(
    rows: list[dict[str, Any]], expected_families: int
) -> tuple[dict[str, dict[str, Any]], dict[int, str], dict[int, str]]:
    if len(rows) != expected_families:
        raise DiscrepancyAuditError("geometry-family count mismatch")
    by_family: dict[str, dict[str, Any]] = {}
    layout_to_family: dict[int, str] = {}
    layout_to_geometry: dict[int, str] = {}
    for row in rows:
        family_id = row.get("family_id")
        members = row.get("member_layout_ids")
        geometries = row.get("member_geometry_sha256")
        if (
            row.get("schema") != "pcb-gnn.geometry-family-registry.v1"
            or not isinstance(family_id, str)
            or family_id in by_family
            or not isinstance(members, list)
            or not isinstance(geometries, list)
            or len(members) != len(geometries)
            or row.get("n_members") != len(members)
        ):
            raise DiscrepancyAuditError("invalid geometry-family registry row")
        by_family[family_id] = row
        for layout_id, geometry in zip(members, geometries):
            if (
                type(layout_id) is not int
                or layout_id in layout_to_family
                or not isinstance(geometry, str)
                or len(geometry) != 64
                or any(character not in "0123456789abcdef" for character in geometry)
                or geometry in layout_to_geometry.values()
            ):
                raise DiscrepancyAuditError("family membership is not disjoint")
            layout_to_family[layout_id] = family_id
            layout_to_geometry[layout_id] = geometry
    if sorted(layout_to_family) != list(range(1500)):
        raise DiscrepancyAuditError("family registry is not exhaustive over layouts")
    return by_family, layout_to_family, layout_to_geometry


def _validate_selection(
    registry: dict[str, Any],
    family_by_id: dict[str, dict[str, Any]],
    layout_to_family: dict[int, str],
    layout_to_geometry: dict[int, str],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = registry.get("rows")
    expected_layouts = int(contract["matched_layouts"])
    expected_per_family = int(contract["selected_per_family"])
    if (
        registry.get("schema") != "pcb-gnn.hf-selection-registry.v1"
        or not isinstance(rows, list)
        or len(rows) != expected_layouts
        or registry.get("algorithm", {}).get("label_inputs_forbidden") is not True
    ):
        raise DiscrepancyAuditError("high-fidelity selection registry is invalid")
    family_counts: Counter[str] = Counter()
    seen_layouts: set[int] = set()
    seen_geometries: set[str] = set()
    ranks: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        layout_id = row.get("layout_id")
        geometry = row.get("geometry_sha256")
        family_id = row.get("family_id")
        rank = row.get("selection_rank_within_family")
        if (
            type(layout_id) is not int
            or not isinstance(geometry, str)
            or not isinstance(family_id, str)
            or type(rank) is not int
            or layout_id in seen_layouts
            or geometry in seen_geometries
            or layout_to_family.get(layout_id) != family_id
            or family_id not in family_by_id
            or layout_to_geometry.get(layout_id) != geometry
            or type(row.get("is_mandatory_anchor")) is not bool
        ):
            raise DiscrepancyAuditError("selection identity is invalid or duplicated")
        seen_layouts.add(layout_id)
        seen_geometries.add(geometry)
        family_counts[family_id] += 1
        ranks[family_id].add(rank)
    expected_ranks = set(range(expected_per_family))
    if (
        set(family_counts) != set(family_by_id)
        or set(family_counts.values()) != {expected_per_family}
        or any(value != expected_ranks for value in ranks.values())
    ):
        raise DiscrepancyAuditError("selection is not exact and balanced by family")
    mandatory = set(registry.get("algorithm", {}).get("mandatory_geometry_sha256", []))
    observed_mandatory = {
        row["geometry_sha256"] for row in rows if row["is_mandatory_anchor"]
    }
    if observed_mandatory != mandatory or len(mandatory) != 9:
        raise DiscrepancyAuditError("mandatory-anchor identities are not exact")
    return sorted(rows, key=lambda row: row["layout_id"])


def _validate_splits(
    registry: dict[str, Any],
    family_by_id: dict[str, dict[str, Any]],
    selected_layouts: set[int],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = registry.get("rows")
    seeds = contract["split_seeds"]
    if (
        registry.get("schema") != "pcb-gnn.swap-closed-split-registry.v1"
        or not isinstance(rows, list)
        or sorted(row.get("split_seed") for row in rows) != sorted(seeds)
    ):
        raise DiscrepancyAuditError("split registry does not match frozen seeds")
    all_layouts = set(range(1500))
    expected_test_families = int(contract["test_families_per_split"])
    expected_selected_test = expected_test_families * int(
        contract["selected_per_family"]
    )
    for row in rows:
        partitions = row.get("partitions", {})
        sets = {
            name: set(partitions.get(name, {}).get("layout_ids", []))
            for name in ("train", "validation", "test")
        }
        if (
            sets["train"] & sets["validation"]
            or sets["train"] & sets["test"]
            or sets["validation"] & sets["test"]
            or set().union(*sets.values()) != all_layouts
        ):
            raise DiscrepancyAuditError("split partitions are not disjoint and exhaustive")
        partition_families = {
            name: set(partitions.get(name, {}).get("family_ids", []))
            for name in ("train", "validation", "test")
        }
        if (
            partition_families["train"] & partition_families["validation"]
            or partition_families["train"] & partition_families["test"]
            or partition_families["validation"] & partition_families["test"]
            or set().union(*partition_families.values()) != set(family_by_id)
        ):
            raise DiscrepancyAuditError("split families are not disjoint and exhaustive")
        for name, family_ids in partition_families.items():
            expected_layouts = {
                layout_id
                for family_id in family_ids
                for layout_id in family_by_id[family_id]["member_layout_ids"]
            }
            if sets[name] != expected_layouts:
                raise DiscrepancyAuditError(
                    f"{name} split is not closed over declared families"
                )
        test_families = partition_families["test"]
        if (
            len(test_families) != expected_test_families
            or len(selected_layouts & sets["test"]) != expected_selected_test
        ):
            raise DiscrepancyAuditError("test split is not family-closed as declared")
    return sorted(rows, key=lambda row: row["split_seed"])


def _observation_map(
    rows: list[dict[str, Any]], protocol: dict[str, Any]
) -> dict[tuple[int, str], dict[str, Any]]:
    expected = protocol["pairing"]
    allowed = {expected["r3_fidelity_id"], expected["r4_fidelity_id"]}
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        layout_id = row.get("layout_id")
        fidelity_id = row.get("fidelity_id")
        cps = row.get("cps_pf")
        artifact_sha256 = row.get("artifact_sha256")
        key = (layout_id, fidelity_id)
        if (
            type(layout_id) is not int
            or fidelity_id not in allowed
            or row.get("units") != "pF"
            or not isinstance(artifact_sha256, str)
            or len(artifact_sha256) != 64
            or any(character not in "0123456789abcdef" for character in artifact_sha256)
            or type(cps) not in {int, float}
            or not math.isfinite(float(cps))
            or float(cps) <= 0.0
            or key in by_key
        ):
            raise DiscrepancyAuditError("observation table has an invalid or duplicate row")
        by_key[key] = row
    r3_count = sum(key[1] == expected["r3_fidelity_id"] for key in by_key)
    r4_count = sum(key[1] == expected["r4_fidelity_id"] for key in by_key)
    if r3_count != 1500 or r4_count != int(protocol["design"]["matched_layouts"]):
        raise DiscrepancyAuditError("observation fidelity counts are incomplete")
    return by_key


def _build_pairs(
    selection: list[dict[str, Any]],
    observations: dict[tuple[int, str], dict[str, Any]],
    protocol: dict[str, Any],
) -> list[dict[str, Any]]:
    pairing = protocol["pairing"]
    rows: list[dict[str, Any]] = []
    for selected in selection:
        layout_id = selected["layout_id"]
        r3 = observations.get((layout_id, pairing["r3_fidelity_id"]))
        r4 = observations.get((layout_id, pairing["r4_fidelity_id"]))
        if r3 is None or r4 is None:
            raise DiscrepancyAuditError(f"missing matched observation for layout {layout_id}")
        geometry = selected["geometry_sha256"]
        if r3.get("geometry_sha256") != geometry or r4.get("geometry_sha256") != geometry:
            raise DiscrepancyAuditError(f"geometry mismatch for layout {layout_id}")
        r3_cps = float(r3["cps_pf"])
        r4_cps = float(r4["cps_pf"])
        signed_percent = 100.0 * (r3_cps - r4_cps) / abs(r4_cps)
        rows.append(
            {
                "absolute_delta_percent": abs(signed_percent),
                "absolute_delta_pf": abs(r3_cps - r4_cps),
                "family_id": selected["family_id"],
                "geometry_sha256": geometry,
                "is_mandatory_anchor": selected["is_mandatory_anchor"],
                "layout_id": layout_id,
                "log_r3_to_r4_ratio": math.log(r3_cps / r4_cps),
                "r3_cps_pf": r3_cps,
                "r3_task_artifact_sha256": r3["artifact_sha256"],
                "r3_to_r4_ratio": r3_cps / r4_cps,
                "r4_cps_pf": r4_cps,
                "r4_task_artifact_sha256": r4["artifact_sha256"],
                "schema": PAIR_SCHEMA,
                "selection_rank_within_family": selected[
                    "selection_rank_within_family"
                ],
                "signed_delta_percent": signed_percent,
            }
        )
    return rows


def _metric_block(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    absolute = [row["absolute_delta_percent"] for row in rows]
    signed = [row["signed_delta_percent"] for row in rows]
    ratio = [row["r3_to_r4_ratio"] for row in rows]
    log_ratio = [row["log_r3_to_r4_ratio"] for row in rows]
    tolerance = 1e-15
    return {
        "absolute_delta_percent": summarize(absolute),
        "direction_counts": {
            "r3_equal_r4_within_1e_15_percent": sum(
                abs(value) <= tolerance for value in signed
            ),
            "r3_greater_than_r4": sum(value > tolerance for value in signed),
            "r3_less_than_r4": sum(value < -tolerance for value in signed),
        },
        "log_r3_to_r4_ratio": summarize(log_ratio),
        "r3_to_r4_ratio": summarize(ratio),
        "signed_delta_percent": summarize(signed),
    }


def _build_family_rows(
    pairs: list[dict[str, Any]], family_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pairs:
        grouped[row["family_id"]].append(row)
    output: list[dict[str, Any]] = []
    for family_id in sorted(grouped):
        members = sorted(grouped[family_id], key=lambda row: row["layout_id"])
        family = family_by_id[family_id]
        output.append(
            {
                "absolute_delta_percent": summarize(
                    [row["absolute_delta_percent"] for row in members]
                ),
                "family_id": family_id,
                "lower_turn_count": family["lower_turn_count"],
                "n_family_members": family["n_members"],
                "n_selected": len(members),
                "schema": FAMILY_SCHEMA,
                "selected_layout_ids": [row["layout_id"] for row in members],
                "signed_delta_percent": summarize(
                    [row["signed_delta_percent"] for row in members]
                ),
                "upper_turn_count": family["upper_turn_count"],
            }
        )
    return output


def build_audit(
    root: Path = ROOT, protocol_path: Path = DEFAULT_PROTOCOL
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    root = root.resolve()
    protocol_path = protocol_path.resolve()
    protocol, paths, protocol_sha256 = _load_protocol_inputs(root, protocol_path)
    archive = load_json(paths["archive_manifest"])
    validate_archive(root, paths["archive_manifest"], require_git_tracked=True)
    _validate_archive_linkage(archive, protocol)
    families, layout_to_family, layout_to_geometry = _validate_families(
        load_jsonl(paths["geometry_families"]),
        int(protocol["design"]["families"]),
    )
    selection = _validate_selection(
        load_json(paths["hf_selection_registry"]),
        families,
        layout_to_family,
        layout_to_geometry,
        protocol["design"],
    )
    selected_layouts = {row["layout_id"] for row in selection}
    splits = _validate_splits(
        load_json(paths["split_registry"]),
        families,
        selected_layouts,
        protocol["design"],
    )
    observations = _observation_map(
        load_jsonl(paths["final_observations"]), protocol
    )
    pairs = _build_pairs(selection, observations, protocol)
    family_rows = _build_family_rows(pairs, families)
    if len(pairs) != 198 or len(family_rows) != 66:
        raise DiscrepancyAuditError("audit output coverage is incomplete")

    anchors = [row for row in pairs if row["is_mandatory_anchor"]]
    nonanchors = [row for row in pairs if not row["is_mandatory_anchor"]]
    split_test: list[dict[str, Any]] = []
    for split in splits:
        test_ids = set(split["partitions"]["test"]["layout_ids"])
        selected_test = [row for row in pairs if row["layout_id"] in test_ids]
        split_test.append(
            {
                "families": len(split["partitions"]["test"]["family_ids"]),
                "metrics": _metric_block(selected_test),
                "pairs": len(selected_test),
                "split_seed": split["split_seed"],
            }
        )

    pair_bytes = _canonical_jsonl_bytes(pairs)
    family_bytes = _canonical_jsonl_bytes(family_rows)
    family_medians = [
        row["absolute_delta_percent"]["median"] for row in family_rows
    ]
    family_maxima = [row["absolute_delta_percent"]["max"] for row in family_rows]
    maximum_pair = max(pairs, key=lambda row: row["absolute_delta_percent"])
    summary = {
        "counts": {
            "families": len(family_rows),
            "mandatory_anchors": len(anchors),
            "matched_pairs": len(pairs),
            "non_anchor_selections": len(nonanchors),
            "split_test_pairs_per_seed": sorted(
                {row["pairs"] for row in split_test}
            ),
        },
        "definitions": protocol["definitions"],
        "design": protocol["design"],
        "input_sha256": {
            name: protocol["inputs"][name]["sha256"]
            for name in sorted(protocol["inputs"])
        },
        "metrics": {
            "extrema": {
                "maximum_absolute_delta_percent": {
                    "absolute_delta_percent": maximum_pair[
                        "absolute_delta_percent"
                    ],
                    "family_id": maximum_pair["family_id"],
                    "layout_id": maximum_pair["layout_id"],
                    "signed_delta_percent": maximum_pair[
                        "signed_delta_percent"
                    ],
                }
            },
            "family_maximum_absolute_delta_percent": summarize(family_maxima),
            "family_median_absolute_delta_percent": summarize(family_medians),
            "mandatory_anchors": _metric_block(anchors),
            "non_anchor_selections": _metric_block(nonanchors),
            "selected_set": _metric_block(pairs),
            "split_test_sets": split_test,
        },
        "output_sha256": {
            "family_summaries.jsonl": sha256_bytes(family_bytes),
            "matched_pairs.jsonl": sha256_bytes(pair_bytes),
        },
        "protocol_sha256": protocol_sha256,
        "schema": SUMMARY_SCHEMA,
        "scientific_semantics": protocol["scientific_semantics"],
    }
    return summary, pairs, family_rows


def _expected_output_bytes(
    summary: dict[str, Any],
    pairs: list[dict[str, Any]],
    families: list[dict[str, Any]],
) -> dict[str, bytes]:
    pretty_summary = (
        json.dumps(
            summary,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return {
        "family_summaries.jsonl": _canonical_jsonl_bytes(families),
        "matched_pairs.jsonl": _canonical_jsonl_bytes(pairs),
        "summary.json": pretty_summary,
    }


def _validate_output_path(output: Path, *, writing: bool) -> Path:
    root = ROOT.resolve()
    lexical_base = DEFAULT_OUTPUT.absolute()
    current = ROOT.absolute()
    for part in lexical_base.relative_to(current).parts:
        current = current / part
        if current.is_symlink():
            raise DiscrepancyAuditError("canonical audit output path contains a symlink")
    base = lexical_base.resolve()
    try:
        base.relative_to(root)
    except ValueError as exc:
        raise DiscrepancyAuditError("canonical audit output path escapes repository") from exc
    resolved_parent = output.parent.resolve()
    if (
        resolved_parent != base
        or JOB_OUTPUT_RE.fullmatch(output.name) is None
        or (output.exists() and output.is_symlink())
    ):
        raise DiscrepancyAuditError(
            "output must be a non-symlink job directory under the canonical audit root"
        )
    if writing and output.name != f"job_{os.environ.get('SLURM_JOB_ID', '')}":
        raise DiscrepancyAuditError("output job directory does not match SLURM_JOB_ID")
    return output


def _scheduler_snapshot() -> dict[str, Any]:
    job_id = os.environ.get("SLURM_JOB_ID")
    executed_batch = Path(os.environ.get("PCB_GNN_EXECUTED_BATCH_SCRIPT", ""))
    if not job_id or not executed_batch.is_file():
        raise DiscrepancyAuditError("--write requires an executed SLURM batch script")
    query = subprocess.run(
        ["scontrol", "show", "job", "-o", job_id],
        capture_output=True,
        check=False,
        text=True,
    )
    fields = {
        token.split("=", 1)[0]: token.split("=", 1)[1]
        for token in query.stdout.split()
        if "=" in token
    }
    if (
        query.returncode != 0
        or fields.get("JobState") not in {"RUNNING", "COMPLETING"}
        or fields.get("Partition") != "nextgen"
        or fields.get("TimeLimit") != "00:15:00"
        or int(os.environ.get("SLURM_CPUS_PER_TASK", "0")) != 2
        or int(os.environ.get("SLURM_MEM_PER_NODE", "0")) != 8192
    ):
        raise DiscrepancyAuditError("SLURM allocation differs from the audit contract")
    return {
        "allocated_cpus_per_task": int(os.environ["SLURM_CPUS_PER_TASK"]),
        "allocated_memory_mib": int(os.environ["SLURM_MEM_PER_NODE"]),
        "executed_batch_path": executed_batch,
        "job_id": job_id,
        "job_name": fields.get("JobName"),
        "partition": fields.get("Partition"),
        "state_at_capture": fields.get("JobState"),
        "time_limit": fields.get("TimeLimit"),
    }


def _execution_receipt(
    root: Path,
    protocol: dict[str, Any],
    protocol_sha256: str,
    output_bytes: dict[str, bytes],
) -> dict[str, Any]:
    scheduler = _scheduler_snapshot()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_source = subprocess.run(
        [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
        ],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    if dirty or untracked_source:
        raise DiscrepancyAuditError("audit execution source is not clean")
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    executed_batch = scheduler.pop("executed_batch_path")
    executed_batch_sha256 = sha256_file(executed_batch)
    if executed_batch_sha256 != protocol["batch_script"]["sha256"]:
        raise DiscrepancyAuditError("executed batch differs from the frozen batch script")
    return {
        "executed_batch_sha256": executed_batch_sha256,
        "implementation_sha256": protocol["implementation"]["sha256"],
        "job_id": scheduler.pop("job_id"),
        "output_sha256": {
            name: sha256_bytes(content) for name, content in sorted(output_bytes.items())
        },
        "protocol_sha256": protocol_sha256,
        "scheduler": scheduler,
        "schema": "pcb-gnn.cps-fidelity-discrepancy-execution.v1",
        "source_git_commit": git_head,
        "source_tree_clean": True,
        "upstream_archive_sha256": protocol["inputs"]["archive_manifest"][
            "sha256"
        ],
    }


def _require_stable_execution_source(
    root: Path, protocol: dict[str, Any], receipt: dict[str, Any]
) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    untracked_source = subprocess.run(
        [
            "git",
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
        ],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    if (
        head != receipt["source_git_commit"]
        or dirty
        or untracked_source
        or sha256_file(root / protocol["implementation"]["path"])
        != receipt["implementation_sha256"]
        or sha256_file(root / protocol["batch_script"]["path"])
        != receipt["executed_batch_sha256"]
        or sha256_file(DEFAULT_PROTOCOL) != receipt["protocol_sha256"]
    ):
        raise DiscrepancyAuditError("audit execution source changed during the job")


def write_outputs(
    output: Path,
    protocol: dict[str, Any],
    protocol_sha256: str,
    summary: dict[str, Any],
    pairs: list[dict[str, Any]],
    families: list[dict[str, Any]],
) -> None:
    output = _validate_output_path(output, writing=True)
    expected = _expected_output_bytes(summary, pairs, families)
    receipt = _execution_receipt(ROOT, protocol, protocol_sha256, expected)
    output.mkdir(parents=True, exist_ok=True)
    allowed = {
        "execution_receipt.json",
        "family_summaries.jsonl",
        "matched_pairs.jsonl",
        "summary.json",
    }
    entries = list(output.iterdir())
    existing = {path.name for path in entries}
    if existing:
        if existing - allowed or any(
            path.is_symlink() or not path.is_file() for path in entries
        ):
            raise DiscrepancyAuditError("output directory contains unmanaged files")
        raise DiscrepancyAuditError(
            "refusing to overwrite an existing versioned audit artifact"
        )
    atomic_write_jsonl(output / "matched_pairs.jsonl", pairs)
    atomic_write_jsonl(output / "family_summaries.jsonl", families)
    atomic_write_json(output / "summary.json", summary)
    _require_stable_execution_source(ROOT, protocol, receipt)
    atomic_write_json(output / "execution_receipt.json", receipt)


def check_outputs(
    output: Path,
    protocol: dict[str, Any],
    summary: dict[str, Any],
    pairs: list[dict[str, Any]],
    families: list[dict[str, Any]],
) -> None:
    output = _validate_output_path(output, writing=False)
    expected_bytes = _expected_output_bytes(summary, pairs, families)
    expected_inventory = set(expected_bytes) | {"execution_receipt.json"}
    entries = list(output.iterdir()) if output.is_dir() else []
    observed_inventory = {path.name for path in entries}
    if observed_inventory != expected_inventory or any(
        path.is_symlink() or not path.is_file() for path in entries
    ):
        raise DiscrepancyAuditError("tracked audit output inventory is not exact")
    for name, expected in expected_bytes.items():
        path = output / name
        if not path.is_file() or path.read_bytes() != expected:
            raise DiscrepancyAuditError(f"tracked audit output differs: {path}")
    receipt = load_json(output / "execution_receipt.json")
    expected_hashes = {
        name: sha256_bytes(content) for name, content in sorted(expected_bytes.items())
    }
    if (
        receipt.get("schema")
        != "pcb-gnn.cps-fidelity-discrepancy-execution.v1"
        or receipt.get("output_sha256") != expected_hashes
        or receipt.get("protocol_sha256") != summary["protocol_sha256"]
        or receipt.get("implementation_sha256")
        != protocol["implementation"]["sha256"]
        or receipt.get("executed_batch_sha256")
        != protocol["batch_script"]["sha256"]
        or receipt.get("upstream_archive_sha256")
        != summary["input_sha256"]["archive_manifest"]
        or receipt.get("source_tree_clean") is not True
        or str(receipt.get("job_id")) != output.name.removeprefix("job_")
    ):
        raise DiscrepancyAuditError("execution receipt does not close the audit outputs")
    source_commit = receipt.get("source_git_commit")
    scheduler = receipt.get("scheduler", {})
    expected_scheduler = {
        "allocated_cpus_per_task": 2,
        "allocated_memory_mib": 8192,
        "job_name": "pcb-v4-cps-audit",
        "partition": "nextgen",
        "time_limit": "00:15:00",
    }
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40,64}", source_commit) is None
        or scheduler.get("state_at_capture") not in {"RUNNING", "COMPLETING"}
        or {key: scheduler.get(key) for key in expected_scheduler}
        != expected_scheduler
        or set(scheduler) != set(expected_scheduler) | {"state_at_capture"}
    ):
        raise DiscrepancyAuditError("execution receipt scheduler/source contract is invalid")
    for relative, expected_hash in (
        (protocol["implementation"]["path"], protocol["implementation"]["sha256"]),
        (protocol["batch_script"]["path"], protocol["batch_script"]["sha256"]),
        (
            "protocols/corpus_v4_cps_fidelity_discrepancy_v1.json",
            summary["protocol_sha256"],
        ),
    ):
        content = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if content.returncode != 0 or hashlib.sha256(content.stdout).hexdigest() != expected_hash:
            raise DiscrepancyAuditError(
                f"execution source blob is unavailable or changed: {relative}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        summary, pairs, families = build_audit(ROOT, args.protocol)
        protocol = load_json(args.protocol)
        if args.write:
            write_outputs(
                args.output,
                protocol,
                summary["protocol_sha256"],
                summary,
                pairs,
                families,
            )
            action_name = "WROTE"
        else:
            check_outputs(args.output, protocol, summary, pairs, families)
            action_name = "PASS"
    except (DiscrepancyAuditError, KeyError, TypeError) as exc:
        print(f"Cps fidelity discrepancy audit: FAIL: {exc}")
        return 1
    print(
        f"Cps fidelity discrepancy audit: {action_name} "
        f"({len(pairs)} pairs, {len(families)} families)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
