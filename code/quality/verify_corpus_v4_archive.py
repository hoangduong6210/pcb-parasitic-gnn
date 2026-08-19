#!/usr/bin/env python3
"""Verify the tracked Corpus v4 archive without executing a field solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    REPO
    / "results/corpus_v4/cps_multifidelity/ARCHIVE_MANIFEST.json"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
TASK_FILE_RE = re.compile(r"task_[0-9]{4}\.json")
ARCHIVE_SCHEMA = "pcb-gnn.cps-multifidelity-archive.v1"
ACCEPTED_SET_SCHEMA = "pcb-gnn.cps-multifidelity-accepted-artifact-set.v1"
CANDIDATE_INDEX_SCHEMA = "pcb-gnn.cps-multifidelity-candidate-index.v1"
FINAL_SCHEMA = "pcb-gnn.cps-multifidelity-final.v1"
TASK_SCHEMA = "pcb-gnn.cps-multifidelity-task.v1"
OBSERVATION_FIELDS = {
    "artifact_sha256",
    "cps_pf",
    "fidelity_id",
    "geometry_sha256",
    "layout_id",
    "mesh_nodes",
    "mesh_tetrahedra",
    "relative_residual",
    "units",
}


class ArchiveValidationError(ValueError):
    """Raised when the tracked archive is incomplete or internally inconsistent."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ArchiveValidationError(f"non-finite JSON number: {token}")


def require_nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ArchiveValidationError(f"{label} must be a non-negative integer")
    return value


def _require_finite_tree(value: Any, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ArchiveValidationError(f"non-finite numeric value in {label}")
    if isinstance(value, dict):
        for child in value.values():
            _require_finite_tree(child, label)
    elif isinstance(value, list):
        for child in value:
            _require_finite_tree(child, label)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveValidationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArchiveValidationError(f"expected JSON object: {path}")
    _require_finite_tree(payload, str(path))
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ArchiveValidationError(
                        f"blank JSONL row at {path}:{line_number}"
                    )
                row = json.loads(
                    line,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_nonfinite,
                )
                if not isinstance(row, dict):
                    raise ArchiveValidationError(
                        f"expected JSON object at {path}:{line_number}"
                    )
                _require_finite_tree(row, f"{path}:{line_number}")
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveValidationError(f"cannot load JSONL {path}: {exc}") from exc
    return rows


def resolve_repo_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if "\\" in relative or candidate.is_absolute() or ".." in candidate.parts:
        raise ArchiveValidationError(f"archive path is not repository-relative: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ArchiveValidationError(f"archive path escapes repository: {relative}") from exc
    return resolved


def require_pinned_file(root: Path, record: dict[str, Any], label: str) -> Path:
    relative = record.get("path")
    expected = record.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ArchiveValidationError(f"{label} must declare path and sha256")
    if SHA256_RE.fullmatch(expected) is None:
        raise ArchiveValidationError(f"{label} has invalid SHA-256: {expected!r}")
    path = resolve_repo_path(root, relative)
    if not path.is_file():
        raise ArchiveValidationError(f"missing {label}: {relative}")
    observed = sha256_file(path)
    if observed != expected:
        raise ArchiveValidationError(
            f"{label} SHA-256 mismatch: expected {expected}, observed {observed}"
        )
    return path


def require_dense_entries(entries: list[dict[str, Any]], expected: int, label: str) -> None:
    task_indices = [entry.get("task_index") for entry in entries]
    if task_indices != list(range(expected)):
        raise ArchiveValidationError(f"{label} does not have exact dense task coverage")
    paths = [entry.get("path") for entry in entries]
    if len(set(paths)) != expected:
        raise ArchiveValidationError(f"{label} contains duplicate artifact paths")
    geometries = [entry.get("geometry_sha256") for entry in entries]
    if len(set(geometries)) != expected:
        raise ArchiveValidationError(f"{label} contains duplicate geometries")


def _record_map(entries: Iterable[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        path = entry.get("path")
        digest = entry.get("sha256", entry.get("artifact_sha256"))
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ArchiveValidationError("candidate or accepted entry lacks path/hash")
        if path in result:
            raise ArchiveValidationError(f"duplicate candidate path: {path}")
        result[path] = digest
    return result


def _safe_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def recompute_numerical_resource_gate(
    execution: dict[str, Any], protocol: dict[str, Any], fidelity_id: str
) -> dict[str, Any]:
    """Rebuild the task gate from raw telemetry and the frozen protocol."""
    result = execution.get("worker_result") or {}
    solver = protocol["linear_solver"]
    limits = protocol["resource_profiles"][fidelity_id]["fail_fast"]
    fidelity = protocol["fidelities"][fidelity_id]

    rss_kib = [
        value
        for stage in execution.get("stages", [])
        if (value := _safe_float(stage.get("max_rss_kb"))) is not None
    ]
    peak_rss = max(rss_kib) if rss_kib else None
    observed = {
        "cps_pf": _safe_float(result.get("cps_pf")),
        "eps_r": _safe_float(result.get("eps_r")),
        "iterations": _safe_int(result.get("iterations")),
        "maxiter": _safe_int(result.get("maxiter")),
        "mesh_nodes": _safe_int(result.get("mesh_nodes")),
        "mesh_tetrahedra": _safe_int(result.get("mesh_tetrahedra")),
        "operator_complexity": _safe_float(result.get("operator_complexity")),
        "pad_mm": _safe_float(result.get("pad_mm")),
        "refine": _safe_int(result.get("refine")),
        "relative_residual": _safe_float(result.get("relative_residual")),
        "rtol": _safe_float(result.get("rtol")),
        "solver_info": _safe_int(result.get("solver_info")),
        "wall_s": _safe_float(execution.get("wall_s")),
        "worker_peak_rss_gib": (
            None if peak_rss is None else peak_rss / 1048576.0
        ),
    }

    def positive_finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and value > 0.0

    def valid_hash(value: Any) -> bool:
        return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None

    input_hash = result.get("input_system_sha256")
    system_hash = result.get("system_sha256")
    checks = {
        "cps_positive_finite": positive_finite(observed["cps_pf"]),
        "fidelity": (
            observed["refine"] == int(fidelity["refine"])
            and observed["pad_mm"] == float(fidelity["pad_mm"])
            and observed["eps_r"] == float(protocol["physics"]["eps_r"])
        ),
        "iterations": positive_finite(observed["iterations"])
        and observed["iterations"] <= int(solver["iterations_max"]),
        "mesh_nodes": positive_finite(observed["mesh_nodes"])
        and observed["mesh_nodes"] <= int(limits["mesh_nodes_max"]),
        "mesh_tetrahedra": positive_finite(observed["mesh_tetrahedra"])
        and observed["mesh_tetrahedra"]
        <= int(limits["mesh_tetrahedra_max"]),
        "operator_complexity": positive_finite(observed["operator_complexity"])
        and observed["operator_complexity"]
        <= float(limits["operator_complexity_max"]),
        "relative_residual": observed["relative_residual"] is not None
        and 0.0
        <= observed["relative_residual"]
        <= float(solver["residual_max"]),
        "resource_rss": positive_finite(observed["worker_peak_rss_gib"])
        and observed["worker_peak_rss_gib"]
        <= float(limits["worker_peak_rss_gib_max"]),
        "resource_wall": positive_finite(observed["wall_s"])
        and observed["wall_s"] <= float(limits["wall_s_max"]),
        "solver_contract": (
            result.get("linear_solver") == solver["reported"]
            and observed["maxiter"] == int(solver["maxiter"])
            and observed["rtol"] == float(solver["rtol"])
            and observed["solver_info"] == int(solver["solver_info"])
        ),
        "system_fingerprint": valid_hash(input_hash)
        and valid_hash(system_hash)
        and input_hash == system_hash,
        "worker_execution": (
            execution.get("returncode") == 0
            and execution.get("worker_result_count") == 1
            and not execution.get("timed_out")
            and not execution.get("telemetry_parse_errors")
        ),
    }
    return {
        "checks": checks,
        "limits": limits,
        "observed": observed,
        "pass": all(checks.values()),
    }


def _validate_source_corpus(
    root: Path, archive: dict[str, Any]
) -> tuple[set[str], dict[str, str]]:
    source = archive["source_corpus"]
    expected = require_nonnegative_int(
        source["expected_geometries"], "source expected_geometries"
    )
    summary_path = require_pinned_file(root, source["summary"], "source summary")
    layouts_path = require_pinned_file(root, source["layouts"], "source layouts")
    labels_path = require_pinned_file(root, source["labels"], "source labels")
    summary = load_json(summary_path)
    gates = summary.get("gates", {})
    if (
        summary.get("schema") != "pcb-gnn.corpus-v3-final.v1"
        or gates.get("n_layouts") != expected
        or gates.get("n_unique_geometry_hashes") != expected
        or gates.get("geometry_valid") is not True
        or gates.get("all_labels_passive") is not True
        or gates.get("all_array_tasks_clean_and_source_identical") is not True
    ):
        raise ArchiveValidationError("source corpus closure gates are not satisfied")
    source_hashes = {
        "layouts.jsonl": source["layouts"]["sha256"],
        "labels.jsonl": source["labels"]["sha256"],
    }
    if summary.get("artifacts_sha256") != source_hashes:
        raise ArchiveValidationError("source summary artifact hashes do not match archive")
    layouts = load_jsonl(layouts_path)
    labels = load_jsonl(labels_path)
    if len(layouts) != expected or len(labels) != expected:
        raise ArchiveValidationError("source layouts/labels cardinality mismatch")
    layout_pairs = [(row.get("layout_id"), row.get("geometry_sha256")) for row in layouts]
    label_pairs = [(row.get("layout_id"), row.get("geometry_sha256")) for row in labels]
    if layout_pairs != label_pairs:
        raise ArchiveValidationError("source layouts and labels have different identities")
    if [pair[0] for pair in layout_pairs] != list(range(expected)):
        raise ArchiveValidationError("source corpus layout IDs are not dense")
    for row in layouts:
        canonical = json.dumps(
            row.get("layout"), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if hashlib.sha256(canonical).hexdigest() != row.get("geometry_sha256"):
            raise ArchiveValidationError(
                f"source geometry hash mismatch at layout {row.get('layout_id')}"
            )
    geometries = {pair[1] for pair in layout_pairs}
    if len(geometries) != expected or not all(isinstance(item, str) for item in geometries):
        raise ArchiveValidationError("source corpus geometry hashes are not unique")
    return geometries, source_hashes


def _validate_fidelity(
    root: Path,
    config: dict[str, Any],
    protocol: dict[str, Any],
    frozen_hashes: dict[str, str],
    source_commit: str,
    source_file_hashes: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[tuple[int, str], dict[str, Any]]]:
    fidelity_id = config["fidelity_id"]
    expected = require_nonnegative_int(
        config["expected_observations"], f"{fidelity_id} expected_observations"
    )
    manifest_path = require_pinned_file(root, config["manifest"], f"{fidelity_id} manifest")
    index_path = require_pinned_file(
        root, config["candidate_index"], f"{fidelity_id} candidate index"
    )
    accepted_path = require_pinned_file(
        root, config["accepted_set"], f"{fidelity_id} accepted set"
    )
    manifest_rows = load_jsonl(manifest_path)
    index = load_json(index_path)
    accepted = load_json(accepted_path)
    if len(manifest_rows) != expected:
        raise ArchiveValidationError(f"{fidelity_id} manifest cardinality mismatch")
    if (
        index.get("schema") != CANDIDATE_INDEX_SCHEMA
        or index.get("n_entries") != expected
        or len(index.get("entries", [])) != expected
    ):
        raise ArchiveValidationError(f"{fidelity_id} candidate index is incomplete")
    if (
        accepted.get("schema") != ACCEPTED_SET_SCHEMA
        or accepted.get("fidelity_id") != fidelity_id
        or accepted.get("n_expected") != expected
        or accepted.get("n_accepted") != expected
        or accepted.get("rejected_candidates") != []
        or accepted.get("plan_sha256") != frozen_hashes["plan"]
        or accepted.get("protocol_sha256") != frozen_hashes["protocol"]
        or accepted.get("execution_lock_sha256") != frozen_hashes["execution_lock"]
        or accepted.get("manifest_sha256") != config["manifest"]["sha256"]
        or accepted.get("candidate_index_sha256")
        != [{"path": config["candidate_index"]["path"], "sha256": config["candidate_index"]["sha256"]}]
    ):
        raise ArchiveValidationError(f"{fidelity_id} accepted-set closure mismatch")
    entries = accepted.get("entries", [])
    if not isinstance(entries, list) or len(entries) != expected:
        raise ArchiveValidationError(f"{fidelity_id} accepted entries are incomplete")
    require_dense_entries(entries, expected, fidelity_id)
    if _record_map(index["entries"]) != _record_map(entries):
        raise ArchiveValidationError(f"{fidelity_id} index and accepted set differ")

    observations: dict[tuple[int, str], dict[str, Any]] = {}
    for task_index, (entry, manifest_row) in enumerate(zip(entries, manifest_rows)):
        expected_identity = {
            "task_index": task_index,
            "layout_id": manifest_row.get("layout_id"),
            "geometry_sha256": manifest_row.get("geometry_sha256"),
            "fidelity_id": fidelity_id,
        }
        observed_identity = {
            "task_index": entry.get("task_index"),
            "layout_id": entry.get("layout_id"),
            "geometry_sha256": entry.get("geometry_sha256"),
            "fidelity_id": entry.get("fidelity_id"),
        }
        if observed_identity != expected_identity:
            raise ArchiveValidationError(f"{fidelity_id} manifest identity mismatch at {task_index}")
        artifact_path = require_pinned_file(
            root,
            {"path": entry["path"], "sha256": entry["artifact_sha256"]},
            f"{fidelity_id} task {task_index}",
        )
        artifact = load_json(artifact_path)
        gate = artifact.get("numerical_resource_gate", {})
        recomputed_gate = recompute_numerical_resource_gate(
            artifact.get("execution", {}), protocol, fidelity_id
        )
        checks = gate.get("checks", {})
        provenance = artifact.get("provenance", {})
        if (
            artifact.get("schema") != TASK_SCHEMA
            or artifact.get("task_index") != task_index
            or artifact.get("task_pass") is not True
            or artifact.get("fidelity", {}).get("fidelity_id") != fidelity_id
            or artifact.get("geometry", {}).get("layout_id") != entry["layout_id"]
            or artifact.get("geometry", {}).get("geometry_sha256") != entry["geometry_sha256"]
            or gate.get("pass") is not True
            or not checks
            or not all(value is True for value in checks.values())
            or gate != recomputed_gate
            or provenance.get("git_head") != source_commit
            or provenance.get("final_git_head") != source_commit
            or provenance.get("plan_sha256") != frozen_hashes["plan"]
            or provenance.get("final_plan_sha256") != frozen_hashes["plan"]
            or provenance.get("protocol_sha256") != frozen_hashes["protocol"]
            or provenance.get("execution_lock_sha256")
            != frozen_hashes["execution_lock"]
            or provenance.get("manifest_sha256") != config["manifest"]["sha256"]
            or provenance.get("final_manifest_sha256")
            != config["manifest"]["sha256"]
            or provenance.get("source_file_sha256") != source_file_hashes
            or provenance.get("final_source_file_sha256") != source_file_hashes
            or provenance.get("git_dirty_paths") != []
            or provenance.get("final_git_dirty_paths") != []
            or provenance.get("untracked_code") != []
            or provenance.get("final_untracked_code") != []
        ):
            raise ArchiveValidationError(f"{fidelity_id} task artifact failed at {task_index}")
        worker = artifact.get("execution", {}).get("worker_result", {})
        key = (entry["layout_id"], fidelity_id)
        observations[key] = {
            "artifact_sha256": entry["artifact_sha256"],
            "cps_pf": worker.get("cps_pf"),
            "fidelity_id": fidelity_id,
            "geometry_sha256": entry["geometry_sha256"],
            "layout_id": entry["layout_id"],
            "mesh_nodes": worker.get("mesh_nodes"),
            "mesh_tetrahedra": worker.get("mesh_tetrahedra"),
            "relative_residual": worker.get("relative_residual"),
            "units": "pF",
        }
    return entries, observations


def _validate_final(
    root: Path,
    archive: dict[str, Any],
    frozen_hashes: dict[str, str],
    source_hashes: dict[str, str],
    accepted_hashes: dict[str, str],
    expected_observations: dict[tuple[int, str], dict[str, Any]],
) -> int:
    final = archive["final"]
    summary_path = require_pinned_file(root, final["summary"], "final summary")
    observations_path = require_pinned_file(
        root, final["observations"], "final observations"
    )
    summary = load_json(summary_path)
    observations = load_jsonl(observations_path)
    expected_rows = require_nonnegative_int(
        final["observations"]["expected_rows"], "final expected_rows"
    )
    counts = summary.get("counts", {})
    semantics = summary.get("fidelity_semantics", {})
    if (
        summary.get("schema") != FINAL_SCHEMA
        or counts.get("geometries") != archive["source_corpus"]["expected_geometries"]
        or counts.get("r3_observations")
        != archive["fidelities"]["r3"]["expected_observations"]
        or counts.get("r4_observations")
        != archive["fidelities"]["r4"]["expected_observations"]
        or summary.get("plan_sha256") != frozen_hashes["plan"]
        or summary.get("protocol_sha256") != frozen_hashes["protocol"]
        or summary.get("execution_lock_sha256") != frozen_hashes["execution_lock"]
        or summary.get("source_corpus_artifacts_sha256") != source_hashes
        or summary.get("input_artifact_set_sha256") != accepted_hashes
        or summary.get("artifacts_sha256", {}).get("label_observations.jsonl")
        != final["observations"]["sha256"]
        or semantics.get("forbidden_claims") != final["forbidden_claims"]
        or semantics.get("r3_converged_to_r4") is not False
        or semantics.get("r4_continuum_converged") is not False
        or summary.get("provenance", {}).get("git_head") != archive["source_commit"]
        or summary.get("provenance", {}).get("final_git_head") != archive["source_commit"]
    ):
        raise ArchiveValidationError("final summary closure mismatch")
    if len(observations) != expected_rows or len(expected_observations) != expected_rows:
        raise ArchiveValidationError("final observation cardinality mismatch")
    if observations != sorted(
        observations, key=lambda row: (row.get("layout_id"), row.get("fidelity_id"))
    ):
        raise ArchiveValidationError("final observations are not canonically sorted")
    observed_map: dict[tuple[int, str], dict[str, Any]] = {}
    for row in observations:
        if set(row) != OBSERVATION_FIELDS:
            raise ArchiveValidationError("final observation schema mismatch")
        key = (row["layout_id"], row["fidelity_id"])
        if key in observed_map:
            raise ArchiveValidationError(f"duplicate final observation: {key}")
        observed_map[key] = row
    if observed_map != expected_observations:
        raise ArchiveValidationError("final observations differ from accepted tasks")
    return expected_rows


def _require_tracked(root: Path, paths: Iterable[Path]) -> None:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    )
    tracked = {item.decode() for item in result.stdout.split(b"\0") if item}
    missing = sorted(
        path.resolve().relative_to(root.resolve()).as_posix()
        for path in paths
        if path.resolve().relative_to(root.resolve()).as_posix() not in tracked
    )
    if missing:
        preview = ", ".join(missing[:5])
        raise ArchiveValidationError(f"archive files are not Git-tracked: {preview}")


def _validate_plan_artifacts(
    root: Path,
    archive: dict[str, Any],
    source_file_hashes: dict[str, str],
) -> tuple[list[Path], list[tuple[int, str]]]:
    plan_record = archive["frozen_inputs"]["plan"]
    plan_path = resolve_repo_path(root, plan_record["path"])
    plan = load_json(plan_path)
    expected_names = {
        "geometry_families.jsonl",
        "hf_selection_registry.json",
        "r3_manifest.jsonl",
        "r4_manifest.jsonl",
        "split_registry.json",
    }
    artifact_hashes = plan.get("artifact_sha256", {})
    if (
        plan.get("schema") != "pcb-gnn.cps-multifidelity-plan.v1"
        or plan.get("protocol_sha256")
        != archive["frozen_inputs"]["protocol"]["sha256"]
        or plan.get("corpus_summary_sha256")
        != archive["source_corpus"]["summary"]["sha256"]
        or plan.get("counts")
        != {"families": 66, "geometries": 1500, "r3_tasks": 1500, "r4_tasks": 198}
        or set(artifact_hashes) != expected_names
        or any(
            source_file_hashes.get(name) != digest
            for name, digest in plan.get("planner_source_sha256", {}).items()
        )
    ):
        raise ArchiveValidationError("frozen plan closure mismatch")
    descendants: list[Path] = []
    for name in sorted(expected_names):
        path = require_pinned_file(
            root,
            {
                "path": (Path(plan_record["path"]).parent / name).as_posix(),
                "sha256": artifact_hashes[name],
            },
            f"plan artifact {name}",
        )
        descendants.append(path)
    hf_registry = load_json(plan_path.parent / "hf_selection_registry.json")
    hf_rows = hf_registry.get("rows", [])
    family_counts = Counter(row.get("family_id") for row in hf_rows)
    algorithm = hf_registry.get("algorithm", {})
    if (
        hf_registry.get("schema") != "pcb-gnn.hf-selection-registry.v1"
        or len(hf_rows) != 198
        or len(family_counts) != 66
        or set(family_counts.values()) != {3}
        or algorithm.get("n_families") != 66
        or algorithm.get("n_per_family") != 3
        or algorithm.get("n_total") != 198
        or algorithm.get("label_inputs_forbidden") is not True
    ):
        raise ArchiveValidationError("higher-fidelity selection registry mismatch")
    return descendants, [
        (row.get("layout_id"), row.get("geometry_sha256")) for row in hf_rows
    ]


def _validate_source_commit(
    root: Path, source_commit: str, source_hashes: dict[str, str]
) -> None:
    commit_check = subprocess.run(
        ["git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if commit_check.returncode != 0:
        raise ArchiveValidationError(
            f"source commit {source_commit} is unavailable; use a full Git clone"
        )
    for relative, expected in source_hashes.items():
        content = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if content.returncode != 0:
            raise ArchiveValidationError(
                f"source file is unavailable at {source_commit}: {relative}"
            )
        observed = hashlib.sha256(content.stdout).hexdigest()
        if observed != expected:
            raise ArchiveValidationError(
                f"source commit hash mismatch for {relative}: {observed}"
            )


def validate_archive(
    root: Path = REPO,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_git_tracked: bool = False,
) -> dict[str, int]:
    root = root.resolve()
    archive = load_json(manifest_path)
    if archive.get("schema") != ARCHIVE_SCHEMA:
        raise ArchiveValidationError("unsupported archive manifest schema")
    source_commit = str(archive.get("source_commit", ""))
    if GIT_COMMIT_RE.fullmatch(source_commit) is None:
        raise ArchiveValidationError("archive source commit is not a 40/64-hex identity")

    source_geometries, source_hashes = _validate_source_corpus(root, archive)
    frozen_hashes: dict[str, str] = {}
    tracked_paths = [manifest_path]
    for name, record in archive["frozen_inputs"].items():
        tracked_paths.append(require_pinned_file(root, record, name))
        frozen_hashes[name] = record["sha256"]
    protocol = load_json(
        resolve_repo_path(root, archive["frozen_inputs"]["protocol"]["path"])
    )
    execution_lock = load_json(
        resolve_repo_path(root, archive["frozen_inputs"]["execution_lock"]["path"])
    )
    source_file_hashes = execution_lock.get("source_sha256")
    if not isinstance(source_file_hashes, dict) or not source_file_hashes:
        raise ArchiveValidationError("execution lock lacks its source hash map")
    _validate_source_commit(root, source_commit, source_file_hashes)
    plan_descendants, hf_identities = _validate_plan_artifacts(
        root, archive, source_file_hashes
    )
    tracked_paths.extend(plan_descendants)

    accepted_hashes: dict[str, str] = {}
    accepted_by_fidelity: dict[str, list[dict[str, Any]]] = {}
    expected_observations: dict[tuple[int, str], dict[str, Any]] = {}
    accepted_task_paths: set[str] = set()
    for short_name in ("r3", "r4"):
        config = archive["fidelities"][short_name]
        entries, observations = _validate_fidelity(
            root,
            config,
            protocol,
            frozen_hashes,
            source_commit,
            source_file_hashes,
        )
        accepted_by_fidelity[short_name] = entries
        expected_observations.update(observations)
        accepted_hashes[short_name] = config["accepted_set"]["sha256"]
        for record_name in ("manifest", "candidate_index", "accepted_set"):
            tracked_paths.append(resolve_repo_path(root, config[record_name]["path"]))
        tracked_paths.extend(resolve_repo_path(root, entry["path"]) for entry in entries)
        accepted_task_paths.update(entry["path"] for entry in entries)

    r3_geometries = {entry["geometry_sha256"] for entry in accepted_by_fidelity["r3"]}
    r4_geometries = {entry["geometry_sha256"] for entry in accepted_by_fidelity["r4"]}
    if r3_geometries != source_geometries or not r4_geometries < r3_geometries:
        raise ArchiveValidationError("accepted fidelity geometry coverage is inconsistent")
    if [
        (entry["layout_id"], entry["geometry_sha256"])
        for entry in accepted_by_fidelity["r4"]
    ] != hf_identities:
        raise ArchiveValidationError("R4 accepted set differs from frozen HF selection")

    row_count = _validate_final(
        root,
        archive,
        frozen_hashes,
        source_hashes,
        accepted_hashes,
        expected_observations,
    )
    tracked_paths.extend(
        resolve_repo_path(root, archive["final"][name]["path"])
        for name in ("summary", "observations")
    )
    tracked_paths.extend(
        resolve_repo_path(root, archive["source_corpus"][name]["path"])
        for name in ("summary", "layouts", "labels")
    )

    task_root = root / "results/corpus_v4/cps_multifidelity"
    archived_task_files = [
        path
        for path in task_root.glob("r[34]/attempts/job_*/*.json")
        if TASK_FILE_RE.fullmatch(path.name)
    ]
    expected_task_count = sum(
        require_nonnegative_int(
            config["expected_observations"], "fidelity expected_observations"
        )
        for config in archive["fidelities"].values()
    )
    if len(archived_task_files) != expected_task_count:
        raise ArchiveValidationError("archive contains missing or extra task result files")
    archived_task_paths = {
        path.relative_to(root).as_posix() for path in archived_task_files
    }
    if archived_task_paths != accepted_task_paths:
        raise ArchiveValidationError("task-file inventory differs from accepted sets")
    if list(task_root.glob("r[34]/attempts/job_*/*.started.json")):
        raise ArchiveValidationError("archive contains redundant started-task snapshots")
    if require_git_tracked:
        _require_tracked(root, tracked_paths)

    fidelity_counts = Counter(
        row["fidelity_id"] for row in expected_observations.values()
    )
    return {
        "geometries": len(source_geometries),
        "r3_observations": fidelity_counts[
            archive["fidelities"]["r3"]["fidelity_id"]
        ],
        "r4_observations": fidelity_counts[
            archive["fidelities"]["r4"]["fidelity_id"]
        ],
        "rows": row_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    try:
        counts = validate_archive(
            args.root,
            args.manifest,
            require_git_tracked=args.require_git_tracked,
        )
    except (ArchiveValidationError, KeyError, TypeError) as exc:
        print(f"corpus-v4 archive check: FAIL: {exc}")
        return 1
    print(
        "corpus-v4 archive check: PASS "
        f"({counts['geometries']} geometries, "
        f"{counts['r3_observations']} R3, {counts['r4_observations']} R4, "
        f"{counts['rows']} rows)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
