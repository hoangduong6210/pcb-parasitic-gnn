"""Fail-closed loader for the Corpus V4 family-crossed accuracy study.

The training table deliberately has no R4 field.  FEM-R3P16 is the only
capacitance target admitted to optimization, while the sparse FEM-R4P16
observations live in a separate evaluation-only mapping.  Inductance values
come from the finalized FastHenry label artifact; its historical capacitance
column is never read into a training target.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code/core"))

from geometry_contract import geometry_sha256, validate_layout  # noqa: E402


PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-accuracy-protocol.v1"
FAMILY_SCHEMA = "pcb-gnn.geometry-family-registry.v1"
SELECTION_SCHEMA = "pcb-gnn.hf-selection-registry.v1"
SPLIT_SCHEMA = "pcb-gnn.swap-closed-split-registry.v1"
DEFAULT_PROTOCOL = REPO / "protocols/corpus_v4_accuracy_v1.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
FAMILY_ID_RE = re.compile(r"turns-([0-9]{2})-([0-9]{2})")

TARGET_NAMES = ("Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH")
INDUCTANCE_NAMES = TARGET_NAMES[1:]
R3_FIDELITY_ID = "cps_fem_r3_p16"
R4_FIDELITY_ID = "cps_fem_r4_p16"
INDUCTANCE_FIDELITY_ID = "fasthenry_100khz_active_leg"
SPLIT_SEEDS = (40, 41, 42, 43, 44)
EXPECTED_LAYOUTS = 1500
EXPECTED_FAMILIES = 66
EXPECTED_R4 = 198
EXPECTED_SELECTED_PER_FAMILY = 3
EXPECTED_PARTITION_FAMILIES = {"train": 46, "validation": 7, "test": 13}
EXPECTED_PARTITION_LAYOUTS = {
    40: {"train": 1039, "validation": 170, "test": 291},
    41: {"train": 1066, "validation": 152, "test": 282},
    42: {"train": 1012, "validation": 182, "test": 306},
    43: {"train": 1076, "validation": 125, "test": 299},
    44: {"train": 1055, "validation": 153, "test": 292},
}
EXPECTED_R4_TEST_LAYOUTS = 39


class CorpusV4AccuracyDatasetError(ValueError):
    """Raised when a scientific input is incomplete or internally inconsistent."""


@dataclass(frozen=True)
class AccuracySample:
    """One optimization sample with explicit numerical-target fidelities."""

    layout_id: int
    geometry_sha256: str
    family_id: str
    layout: Mapping[str, Any]
    cps_r3_pf: float
    l_pri_nh: float
    l_sec_nh: float
    l_mut_nh: float
    r3_artifact_sha256: str

    @property
    def training_target_values(self) -> tuple[float, float, float, float]:
        """Return float64 Python values in the frozen model-target order."""
        return (self.cps_r3_pf, self.l_pri_nh, self.l_sec_nh, self.l_mut_nh)


@dataclass(frozen=True)
class R4EvaluationObservation:
    """Sparse higher-resolution comparator that is never part of a sample."""

    layout_id: int
    geometry_sha256: str
    cps_r4_pf: float
    artifact_sha256: str


@dataclass(frozen=True)
class FrozenPartition:
    family_ids: tuple[str, ...]
    layout_ids: tuple[int, ...]


@dataclass(frozen=True)
class FrozenSplit:
    split_seed: int
    train: FrozenPartition
    validation: FrozenPartition
    test: FrozenPartition
    r4_test_layout_ids: tuple[int, ...]


@dataclass(frozen=True)
class CorpusV4AccuracyDataset:
    """Immutable identities and reference values consumed by training tasks."""

    samples: tuple[AccuracySample, ...]
    r4_evaluation: Mapping[int, R4EvaluationObservation]
    splits: Mapping[int, FrozenSplit]
    input_sha256: Mapping[str, str]
    target_fidelity_ids: Mapping[str, str]

    def sample_by_layout_id(self) -> Mapping[int, AccuracySample]:
        return MappingProxyType({sample.layout_id: sample for sample in self.samples})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise CorpusV4AccuracyDatasetError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_nonfinite(token: str) -> None:
    raise CorpusV4AccuracyDatasetError(f"non-finite JSON number: {token}")


def _require_finite_tree(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CorpusV4AccuracyDatasetError(f"non-finite numeric value in {label}")
    if isinstance(value, dict):
        for child in value.values():
            _require_finite_tree(child, label)
    elif isinstance(value, list):
        for child in value:
            _require_finite_tree(child, label)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusV4AccuracyDatasetError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CorpusV4AccuracyDatasetError(f"expected JSON object: {path}")
    _require_finite_tree(value, str(path))
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    raise CorpusV4AccuracyDatasetError(
                        f"blank JSONL row at {path}:{line_number}"
                    )
                value = json.loads(
                    line,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_nonfinite,
                )
                if not isinstance(value, dict):
                    raise CorpusV4AccuracyDatasetError(
                        f"expected JSON object at {path}:{line_number}"
                    )
                _require_finite_tree(value, f"{path}:{line_number}")
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusV4AccuracyDatasetError(f"cannot load JSONL {path}: {exc}") from exc
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_input(root: Path, record: Any, label: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise CorpusV4AccuracyDatasetError(f"{label} input record is not exact")
    relative = record.get("path")
    expected = record.get("sha256")
    if (
        not isinstance(relative, str)
        or not isinstance(expected, str)
        or SHA256_RE.fullmatch(expected) is None
    ):
        raise CorpusV4AccuracyDatasetError(f"{label} input identity is malformed")
    candidate = Path(relative)
    if "\\" in relative or candidate.is_absolute() or ".." in candidate.parts:
        raise CorpusV4AccuracyDatasetError(f"unsafe repository-relative path: {relative}")
    resolved_root = root.resolve()
    path = (resolved_root / candidate).resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise CorpusV4AccuracyDatasetError(f"{label} path escapes repository") from exc
    if not path.is_file() or _sha256_file(path) != expected:
        raise CorpusV4AccuracyDatasetError(f"{label} file is missing or hash-mismatched")
    return path


def _positive_float(value: Any, label: str) -> float:
    if type(value) not in {int, float}:
        raise CorpusV4AccuracyDatasetError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise CorpusV4AccuracyDatasetError(f"{label} must be positive and finite")
    return converted


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise CorpusV4AccuracyDatasetError(f"{label} is not a lowercase SHA-256")
    return value


def _identity(row: Mapping[str, Any], label: str) -> tuple[int, str]:
    layout_id = row.get("layout_id")
    if type(layout_id) is not int or layout_id < 0:
        raise CorpusV4AccuracyDatasetError(f"{label} layout_id is invalid")
    geometry = _require_sha256(row.get("geometry_sha256"), f"{label} geometry")
    return layout_id, geometry


def _validate_protocol(protocol: dict[str, Any]) -> None:
    target_fidelities = {
        row.get("name"): row.get("fidelity_id")
        for row in protocol.get("targets", [])
        if isinstance(row, dict)
    }
    if (
        protocol.get("schema") != PROTOCOL_SCHEMA
        or protocol.get("seeds", {}).get("split") != list(SPLIT_SEEDS)
        or protocol.get("seeds", {}).get("init") != list(SPLIT_SEEDS)
        or protocol.get("seeds", {}).get("tasks") != 25
        or protocol.get("splits", {}).get("families")
        != EXPECTED_PARTITION_FAMILIES
        or protocol.get("splits", {}).get("r4_test_layouts_per_split")
        != EXPECTED_R4_TEST_LAYOUTS
        or target_fidelities
        != {
            "Cps_pF": R3_FIDELITY_ID,
            "L_pri_nH": INDUCTANCE_FIDELITY_ID,
            "L_sec_nH": INDUCTANCE_FIDELITY_ID,
            "L_mut_nH": INDUCTANCE_FIDELITY_ID,
        }
        or protocol.get("validation_fidelity", {}).get("fidelity_id")
        != R4_FIDELITY_ID
        or protocol.get("forbidden_actions", {}).get(
            "legacy_cps_as_training_target"
        )
        is not True
        or protocol.get("forbidden_actions", {}).get("r4_in_optimization")
        is not True
        or protocol.get("forbidden_actions", {}).get("random_or_regenerated_split")
        is not True
    ):
        raise CorpusV4AccuracyDatasetError("accuracy protocol contract is not frozen")
    expected_inputs = {
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
    if set(protocol.get("inputs", {})) != expected_inputs:
        raise CorpusV4AccuracyDatasetError("accuracy protocol input set is not exact")


def _validate_layout_rows(
    rows: Sequence[dict[str, Any]], expected_count: int = EXPECTED_LAYOUTS
) -> dict[tuple[int, str], dict[str, Any]]:
    if len(rows) != expected_count:
        raise CorpusV4AccuracyDatasetError("layout cardinality mismatch")
    by_identity: dict[tuple[int, str], dict[str, Any]] = {}
    layout_ids: set[int] = set()
    geometries: set[str] = set()
    for row in rows:
        key = _identity(row, "layout")
        layout = row.get("layout")
        if not isinstance(layout, dict):
            raise CorpusV4AccuracyDatasetError("layout payload is not an object")
        validate_layout(layout)
        if geometry_sha256(layout) != key[1]:
            raise CorpusV4AccuracyDatasetError("recomputed layout geometry mismatch")
        if key in by_identity or key[0] in layout_ids or key[1] in geometries:
            raise CorpusV4AccuracyDatasetError("duplicate layout ID or geometry")
        by_identity[key] = row
        layout_ids.add(key[0])
        geometries.add(key[1])
    if layout_ids != set(range(expected_count)):
        raise CorpusV4AccuracyDatasetError("layout IDs are not exact and dense")
    return by_identity


def _validate_inductance_rows(
    rows: Sequence[dict[str, Any]],
    layout_by_identity: Mapping[tuple[int, str], dict[str, Any]],
) -> dict[tuple[int, str], tuple[float, float, float]]:
    if len(rows) != len(layout_by_identity):
        raise CorpusV4AccuracyDatasetError("inductance-label cardinality mismatch")
    values: dict[tuple[int, str], tuple[float, float, float]] = {}
    for row in rows:
        key = _identity(row, "inductance label")
        if key not in layout_by_identity:
            raise CorpusV4AccuracyDatasetError("inductance label identity is not a layout")
        if key in values:
            raise CorpusV4AccuracyDatasetError("duplicate inductance label identity")
        lp = _positive_float(row.get("L_pri_nH"), "L_pri_nH")
        ls = _positive_float(row.get("L_sec_nH"), "L_sec_nH")
        mutual = _positive_float(row.get("L_mut_nH"), "L_mut_nH")
        if mutual > math.sqrt(lp * ls) * (1.0 + 1e-9):
            raise CorpusV4AccuracyDatasetError("inductance label violates passivity")
        # Deliberately do not read row["Cps_pF"]: that column is historical.
        values[key] = (lp, ls, mutual)
    if set(values) != set(layout_by_identity):
        raise CorpusV4AccuracyDatasetError("inductance labels are missing or extra")
    return values


def _validate_observation_rows(
    rows: Sequence[dict[str, Any]],
    layout_by_identity: Mapping[tuple[int, str], dict[str, Any]],
    *,
    expected_r3: int = EXPECTED_LAYOUTS,
    expected_r4: int = EXPECTED_R4,
) -> tuple[
    dict[tuple[int, str], tuple[float, str]],
    dict[tuple[int, str], tuple[float, str]],
]:
    if len(rows) != expected_r3 + expected_r4:
        raise CorpusV4AccuracyDatasetError("Cps observation cardinality mismatch")
    by_fidelity: dict[str, dict[tuple[int, str], tuple[float, str]]] = {
        R3_FIDELITY_ID: {},
        R4_FIDELITY_ID: {},
    }
    for row in rows:
        key = _identity(row, "Cps observation")
        fidelity = row.get("fidelity_id")
        if fidelity not in by_fidelity or row.get("units") != "pF":
            raise CorpusV4AccuracyDatasetError("Cps observation fidelity or unit is invalid")
        if key not in layout_by_identity:
            raise CorpusV4AccuracyDatasetError("Cps observation identity is not a layout")
        destination = by_fidelity[fidelity]
        if key in destination:
            raise CorpusV4AccuracyDatasetError("duplicate Cps observation identity")
        destination[key] = (
            _positive_float(row.get("cps_pf"), f"{fidelity} Cps"),
            _require_sha256(row.get("artifact_sha256"), "Cps artifact"),
        )
    r3, r4 = by_fidelity[R3_FIDELITY_ID], by_fidelity[R4_FIDELITY_ID]
    if len(r3) != expected_r3 or set(r3) != set(layout_by_identity):
        raise CorpusV4AccuracyDatasetError("R3 observations are not exact and exhaustive")
    if len(r4) != expected_r4 or not set(r4) < set(r3):
        raise CorpusV4AccuracyDatasetError("R4 observations are not the expected sparse set")
    return r3, r4


def _layout_family_id(layout: Mapping[str, Any]) -> str:
    traces = layout.get("traces")
    if not isinstance(traces, list):
        raise CorpusV4AccuracyDatasetError("layout traces are unavailable")
    primary = sum(trace.get("net") == "pri" for trace in traces)
    secondary = sum(trace.get("net") == "sec" for trace in traces)
    lower, upper = sorted((primary, secondary))
    return f"turns-{lower:02d}-{upper:02d}"


def _validate_family_rows(
    rows: Sequence[dict[str, Any]],
    layout_by_identity: Mapping[tuple[int, str], dict[str, Any]],
    *,
    expected_families: int = EXPECTED_FAMILIES,
) -> tuple[dict[str, tuple[int, ...]], dict[int, str]]:
    if len(rows) != expected_families:
        raise CorpusV4AccuracyDatasetError("family cardinality mismatch")
    identity_by_layout = {key[0]: key for key in layout_by_identity}
    members_by_family: dict[str, tuple[int, ...]] = {}
    family_by_layout: dict[int, str] = {}
    for row in rows:
        family_id = row.get("family_id")
        match = FAMILY_ID_RE.fullmatch(family_id) if isinstance(family_id, str) else None
        layout_ids = row.get("member_layout_ids")
        geometries = row.get("member_geometry_sha256")
        if (
            row.get("schema") != FAMILY_SCHEMA
            or match is None
            or family_id in members_by_family
            or not isinstance(layout_ids, list)
            or not isinstance(geometries, list)
            or any(type(layout_id) is not int for layout_id in layout_ids)
            or len(layout_ids) != len(set(layout_ids))
            or len(layout_ids) != len(geometries)
            or row.get("n_members") != len(layout_ids)
            or row.get("lower_turn_count") != int(match.group(1))
            or row.get("upper_turn_count") != int(match.group(2))
        ):
            raise CorpusV4AccuracyDatasetError("geometry-family row is invalid")
        for layout_id, geometry in zip(layout_ids, geometries):
            key = identity_by_layout.get(layout_id)
            if (
                key is None
                or geometry != key[1]
                or layout_id in family_by_layout
                or _layout_family_id(layout_by_identity[key]["layout"]) != family_id
            ):
                raise CorpusV4AccuracyDatasetError("family identity or membership mismatch")
            family_by_layout[layout_id] = family_id
        members_by_family[family_id] = tuple(layout_ids)
    if set(family_by_layout) != set(range(len(layout_by_identity))):
        raise CorpusV4AccuracyDatasetError("families are not exhaustive over layouts")
    return members_by_family, family_by_layout


def _validate_selection(
    registry: dict[str, Any],
    layout_by_identity: Mapping[tuple[int, str], dict[str, Any]],
    family_by_layout: Mapping[int, str],
    r4: Mapping[tuple[int, str], tuple[float, str]],
    *,
    expected_r4: int = EXPECTED_R4,
    expected_per_family: int = EXPECTED_SELECTED_PER_FAMILY,
) -> set[int]:
    rows = registry.get("rows")
    identity_by_layout = {key[0]: key for key in layout_by_identity}
    if (
        registry.get("schema") != SELECTION_SCHEMA
        or not isinstance(rows, list)
        or len(rows) != expected_r4
        or registry.get("algorithm", {}).get("label_inputs_forbidden") is not True
    ):
        raise CorpusV4AccuracyDatasetError("R4 selection registry is invalid")
    selected: set[int] = set()
    selected_geometries: set[str] = set()
    counts: Counter[str] = Counter()
    ranks: dict[str, set[int]] = {}
    for row in rows:
        key = _identity(row, "R4 selection")
        family_id = row.get("family_id")
        rank = row.get("selection_rank_within_family")
        if (
            key not in layout_by_identity
            or key not in r4
            or key[0] in selected
            or key[1] in selected_geometries
            or family_by_layout.get(key[0]) != family_id
            or type(rank) is not int
            or type(row.get("is_mandatory_anchor")) is not bool
        ):
            raise CorpusV4AccuracyDatasetError("R4 selection identity is invalid")
        selected.add(key[0])
        selected_geometries.add(key[1])
        counts[family_id] += 1
        ranks.setdefault(family_id, set()).add(rank)
    if (
        len(counts) * expected_per_family != expected_r4
        or set(counts.values()) != {expected_per_family}
        or any(value != set(range(expected_per_family)) for value in ranks.values())
        or {identity_by_layout[layout_id] for layout_id in selected} != set(r4)
    ):
        raise CorpusV4AccuracyDatasetError("R4 selection is not exact and balanced")
    return selected


def _validate_splits(
    registry: dict[str, Any],
    members_by_family: Mapping[str, tuple[int, ...]],
    selected_r4: set[int],
) -> dict[int, FrozenSplit]:
    rows = registry.get("rows")
    if (
        set(registry) != {"init_seeds", "rows", "schema"}
        or registry.get("schema") != SPLIT_SCHEMA
        or registry.get("init_seeds") != list(SPLIT_SEEDS)
        or not isinstance(rows, list)
        or len(rows) != len(SPLIT_SEEDS)
    ):
        raise CorpusV4AccuracyDatasetError("split registry header is invalid")
    all_layouts = set(range(EXPECTED_LAYOUTS))
    splits: dict[int, FrozenSplit] = {}
    for expected_seed, row in zip(SPLIT_SEEDS, rows):
        if (
            not isinstance(row, dict)
            or set(row) != {"partitions", "split_seed"}
            or row.get("split_seed") != expected_seed
            or not isinstance(row.get("partitions"), dict)
            or set(row["partitions"]) != set(EXPECTED_PARTITION_FAMILIES)
        ):
            raise CorpusV4AccuracyDatasetError("split row is invalid or reordered")
        partitions: dict[str, FrozenPartition] = {}
        observed_family_sets: list[set[str]] = []
        observed_layout_sets: list[set[int]] = []
        for name in ("train", "validation", "test"):
            part = row["partitions"][name]
            family_ids = part.get("family_ids") if isinstance(part, dict) else None
            layout_ids = part.get("layout_ids") if isinstance(part, dict) else None
            if (
                not isinstance(part, dict)
                or set(part) != {"family_ids", "layout_ids", "n_families", "n_layouts"}
                or not isinstance(family_ids, list)
                or not isinstance(layout_ids, list)
                or any(not isinstance(family_id, str) for family_id in family_ids)
                or any(type(layout_id) is not int for layout_id in layout_ids)
                or len(family_ids) != len(set(family_ids))
                or len(layout_ids) != len(set(layout_ids))
                or part.get("n_families") != len(family_ids)
                or part.get("n_layouts") != len(layout_ids)
                or len(family_ids) != EXPECTED_PARTITION_FAMILIES[name]
                or len(layout_ids) != EXPECTED_PARTITION_LAYOUTS[expected_seed][name]
                or any(family_id not in members_by_family for family_id in family_ids)
            ):
                raise CorpusV4AccuracyDatasetError("split partition count or type mismatch")
            expected_layout_ids = {
                layout_id
                for family_id in family_ids
                for layout_id in members_by_family[family_id]
            }
            if set(layout_ids) != expected_layout_ids:
                raise CorpusV4AccuracyDatasetError("split partition is not family closed")
            partitions[name] = FrozenPartition(tuple(family_ids), tuple(layout_ids))
            observed_family_sets.append(set(family_ids))
            observed_layout_sets.append(set(layout_ids))
        if (
            set().union(*observed_family_sets) != set(members_by_family)
            or sum(len(value) for value in observed_family_sets) != EXPECTED_FAMILIES
            or set().union(*observed_layout_sets) != all_layouts
            or sum(len(value) for value in observed_layout_sets) != EXPECTED_LAYOUTS
        ):
            raise CorpusV4AccuracyDatasetError("split is not disjoint and exhaustive")
        r4_test = tuple(sorted(selected_r4 & set(partitions["test"].layout_ids)))
        if len(r4_test) != EXPECTED_R4_TEST_LAYOUTS:
            raise CorpusV4AccuracyDatasetError("split does not contain exactly 39 R4 tests")
        splits[expected_seed] = FrozenSplit(
            split_seed=expected_seed,
            train=partitions["train"],
            validation=partitions["validation"],
            test=partitions["test"],
            r4_test_layout_ids=r4_test,
        )
    return splits


def load_corpus_v4_accuracy_dataset(
    root: Path = REPO, protocol_path: Path = DEFAULT_PROTOCOL
) -> CorpusV4AccuracyDataset:
    """Load and cross-check every input without constructing graphs or training."""
    root = root.resolve()
    protocol_path = protocol_path.resolve()
    expected_protocol_path = root / "protocols/corpus_v4_accuracy_v1.json"
    if protocol_path != expected_protocol_path.resolve():
        raise CorpusV4AccuracyDatasetError("accuracy protocol is not at its canonical path")
    protocol = _load_json(protocol_path)
    _validate_protocol(protocol)
    paths = {
        name: _resolve_input(root, record, name)
        for name, record in protocol["inputs"].items()
    }

    source_summary = _load_json(paths["source_corpus_summary"])
    if (
        source_summary.get("schema") != "pcb-gnn.corpus-v3-final.v1"
        or source_summary.get("gates", {}).get("geometry_valid") is not True
        or source_summary.get("gates", {}).get("all_labels_passive") is not True
        or source_summary.get("gates", {}).get("n_layouts") != EXPECTED_LAYOUTS
        or source_summary.get("artifacts_sha256", {}).get("layouts.jsonl")
        != protocol["inputs"]["layouts"]["sha256"]
        or source_summary.get("artifacts_sha256", {}).get("labels.jsonl")
        != protocol["inputs"]["inductance_labels"]["sha256"]
    ):
        raise CorpusV4AccuracyDatasetError("source corpus summary closure is invalid")

    layouts = _validate_layout_rows(_load_jsonl(paths["layouts"]))
    inductance = _validate_inductance_rows(
        _load_jsonl(paths["inductance_labels"]), layouts
    )
    r3, r4 = _validate_observation_rows(
        _load_jsonl(paths["final_observations"]), layouts
    )
    members_by_family, family_by_layout = _validate_family_rows(
        _load_jsonl(paths["geometry_families"]), layouts
    )
    selected_r4 = _validate_selection(
        _load_json(paths["hf_selection_registry"]),
        layouts,
        family_by_layout,
        r4,
    )
    splits = _validate_splits(
        _load_json(paths["split_registry"]), members_by_family, selected_r4
    )

    samples: list[AccuracySample] = []
    r4_evaluation: dict[int, R4EvaluationObservation] = {}
    for key in sorted(layouts, key=lambda item: item[0]):
        layout_id, geometry = key
        lp, ls, mutual = inductance[key]
        cps_r3, r3_artifact = r3[key]
        samples.append(
            AccuracySample(
                layout_id=layout_id,
                geometry_sha256=geometry,
                family_id=family_by_layout[layout_id],
                layout=MappingProxyType(layouts[key]["layout"]),
                cps_r3_pf=cps_r3,
                l_pri_nh=lp,
                l_sec_nh=ls,
                l_mut_nh=mutual,
                r3_artifact_sha256=r3_artifact,
            )
        )
        if key in r4:
            cps_r4, r4_artifact = r4[key]
            r4_evaluation[layout_id] = R4EvaluationObservation(
                layout_id=layout_id,
                geometry_sha256=geometry,
                cps_r4_pf=cps_r4,
                artifact_sha256=r4_artifact,
            )

    return CorpusV4AccuracyDataset(
        samples=tuple(samples),
        r4_evaluation=MappingProxyType(r4_evaluation),
        splits=MappingProxyType(splits),
        input_sha256=MappingProxyType(
            {name: protocol["inputs"][name]["sha256"] for name in sorted(paths)}
        ),
        target_fidelity_ids=MappingProxyType(
            {
                "Cps_pF": R3_FIDELITY_ID,
                "L_pri_nH": INDUCTANCE_FIDELITY_ID,
                "L_sec_nH": INDUCTANCE_FIDELITY_ID,
                "L_mut_nH": INDUCTANCE_FIDELITY_ID,
                "Cps_pF_evaluation_only": R4_FIDELITY_ID,
            }
        ),
    )


__all__ = [
    "AccuracySample",
    "CorpusV4AccuracyDataset",
    "CorpusV4AccuracyDatasetError",
    "FrozenPartition",
    "FrozenSplit",
    "R4EvaluationObservation",
    "TARGET_NAMES",
    "load_corpus_v4_accuracy_dataset",
]
