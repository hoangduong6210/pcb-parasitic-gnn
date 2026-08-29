#!/usr/bin/env python3
"""Verify the tracked one-thread FEM-v2 production closure without solving.

The verifier is deliberately scheduler independent.  It authenticates the
postterminal receipts already captured by the SLURM finalizers, every accepted
solver result referenced by the joint observation table, the frozen roots, and
the exact closure inventory.  It never invokes FEM, FastHenry, or model code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = (
    ROOT
    / "results/corpus_v4/cps_reference_v2/production/v1/ARCHIVE_MANIFEST.json"
)
ARCHIVE_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-archive.v1"
WAVE_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-wave-admission.v1"
DATASET_ADMISSION_SCHEMA = (
    "pcb-gnn.corpus-v4-fem-v2-production-dataset-admission.v1"
)
DATASET_MANIFEST_SCHEMA = (
    "pcb-gnn.corpus-v4-fem-v2-production-dataset-final-manifest.v1"
)
TASK_SCHEMA = "pcb-gnn.corpus-v4-fem-v2-production-task.v1"
R3_FIDELITY = "cps_fem_r3_p16_t1_v2"
R4_FIDELITY = "cps_fem_r4_p16_t1_v2"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
OBSERVATION_KEYS = {
    "artifact_result_path",
    "artifact_result_sha256",
    "cps_pf",
    "fidelity_id",
    "geometry_sha256",
    "layout_id",
    "mesh_nodes",
    "mesh_tetrahedra",
    "relative_residual",
    "system_sha256",
    "units",
}
EXPECTED_WAVE_ADMISSIONS = (
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_000/admission/source_set_3297d44ec30f70499082aa1bb9094ae8c56b4c59ba595e7e746203e30c9caec4/finalizer_job_6963562/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_001/admission/source_set_c941ecfc612668d5f8f63c181946f51b2ca900c68ab7fcd7103dfe638793fa49/finalizer_job_7004762/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_002/admission/source_set_045bb74c31f4d3a6fd44162457105341b604a5a70be6c278da88bf8db9b7487a/finalizer_job_7022706/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_003/admission/source_set_828a87e4831bc6eb22ef9352f6116a59ded59ea0adeac08618fb04d338d18e8d/finalizer_job_7057803/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r3/wave_004/admission/source_set_5e6e28ff339fed5501c89e62caddad748c8d5137ecbf6f8599bbf5d7d528a1c1/finalizer_job_7064646/FINAL_ADMISSION.json",
    "results/corpus_v4/cps_reference_v2/production/v1/waves/r4/wave_000/admission/source_set_75ce1fe7bf7bd5b4ec5c77b9e691badcf54faf1543af93a6c85807fee38b6c17/finalizer_job_6963560/FINAL_ADMISSION.json",
)
ACCEPTED_ENTRY_KEYS = {
    "array_task_id",
    "artifact_manifest_path",
    "artifact_manifest_sha256",
    "artifact_result_path",
    "artifact_result_sha256",
    "fidelity_id",
    "geometry_sha256",
    "layout_id",
    "source_array_job_id",
    "task_index",
}


class ArchiveVerificationError(ValueError):
    """Raised when any byte, identity, or scientific boundary is invalid."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ArchiveVerificationError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_nonfinite(token: str) -> None:
    raise ArchiveVerificationError(f"non-finite JSON number: {token}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveVerificationError(f"cannot read strict JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArchiveVerificationError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ArchiveVerificationError(f"cannot read JSONL {path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line:
            raise ArchiveVerificationError(f"blank JSONL row at {path}:{line_number}")
        try:
            row = json.loads(
                line,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonfinite,
            )
        except json.JSONDecodeError as exc:
            raise ArchiveVerificationError(
                f"invalid JSONL row at {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise ArchiveVerificationError(
                f"non-object JSONL row at {path}:{line_number}"
            )
        rows.append(row)
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ArchiveVerificationError(f"{label} path is not a string")
    relative = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.as_posix() != value
    ):
        raise ArchiveVerificationError(f"{label} path is unsafe: {value!r}")
    return relative


def _resolve_record(record: Any, label: str) -> Path:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise ArchiveVerificationError(f"{label} record is not exact")
    relative = _safe_relative_path(record["path"], label)
    expected = record["sha256"]
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        raise ArchiveVerificationError(f"{label} SHA-256 is malformed")
    path = ROOT.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ArchiveVerificationError(f"{label} file is missing or a symlink")
    if _sha256_file(path) != expected:
        raise ArchiveVerificationError(f"{label} SHA-256 mismatch")
    return path


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ArchiveVerificationError("closure path escapes repository") from exc


def _require_git_tracked(paths: Iterable[Path]) -> None:
    relative = sorted({_repo_relative(path) for path in paths})
    for offset in range(0, len(relative), 200):
        chunk = relative[offset : offset + 200]
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", *chunk],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
        if tracked.returncode != 0:
            raise ArchiveVerificationError("closure contains an untracked path")
        status = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all", "--", *chunk],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
        if status.stdout.strip():
            raise ArchiveVerificationError("closure contains modified bytes")


def _positive_number(value: Any, label: str) -> float:
    if type(value) not in {int, float}:
        raise ArchiveVerificationError(f"{label} is not numeric")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise ArchiveVerificationError(f"{label} is not positive and finite")
    return converted


def _verify_source_commit(source_commit: str, source_sha256: dict[str, Any]) -> None:
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ArchiveVerificationError("source commit is malformed")
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if exists.returncode != 0 or ancestor.returncode != 0:
        raise ArchiveVerificationError("production source commit is absent or not an ancestor")
    if not isinstance(source_sha256, dict) or not source_sha256:
        raise ArchiveVerificationError("production source inventory is empty")
    for relative, expected in sorted(source_sha256.items()):
        _safe_relative_path(relative, "production source")
        if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
            raise ArchiveVerificationError("production source hash is malformed")
        current = ROOT / relative
        if current.is_symlink() or not current.is_file() or _sha256_file(current) != expected:
            raise ArchiveVerificationError(f"production source bytes changed: {relative}")
        blob = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if blob.returncode != 0 or hashlib.sha256(blob.stdout).hexdigest() != expected:
            raise ArchiveVerificationError(
                f"production source is not bound to its Git blob: {relative}"
            )


def _accepted_rows_from_receipt(
    receipt: dict[str, Any], *, expected_fidelity: str, expected_count: int
) -> tuple[set[tuple[str, int, str, str, str]], Path]:
    files = receipt.get("preterminal_files", {})
    path = _resolve_record(
        {
            "path": files.get("accepted_set_path"),
            "sha256": files.get("accepted_set_sha256"),
        },
        f"{expected_fidelity} accepted set",
    )
    payload = _load_json(path)
    entries = payload.get("entries")
    if (
        payload.get("schema")
        != "pcb-gnn.corpus-v4-fem-v2-production-accepted-set.v1"
        or payload.get("fidelity_id") != expected_fidelity
        or not isinstance(entries, list)
        or len(entries) != expected_count
    ):
        raise ArchiveVerificationError("final accepted-set header is invalid")
    identities: set[tuple[str, int, str, str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != ACCEPTED_ENTRY_KEYS:
            raise ArchiveVerificationError(f"accepted-set entry {index} is not exact")
        fidelity = entry.get("fidelity_id")
        layout_id = entry.get("layout_id")
        geometry = entry.get("geometry_sha256")
        result_path = entry.get("artifact_result_path")
        result_sha = entry.get("artifact_result_sha256")
        if (
            fidelity != expected_fidelity
            or type(layout_id) is not int
            or not isinstance(geometry, str)
            or SHA256_RE.fullmatch(geometry) is None
            or not isinstance(result_sha, str)
            or SHA256_RE.fullmatch(result_sha) is None
        ):
            raise ArchiveVerificationError(f"accepted-set entry {index} is malformed")
        _safe_relative_path(result_path, f"accepted-set entry {index}")
        identity = (fidelity, layout_id, geometry, result_path, result_sha)
        if identity in identities:
            raise ArchiveVerificationError("accepted set contains a duplicate entry")
        identities.add(identity)
    return identities, path


def _validate_wave_admission(
    path: Path,
    *,
    fidelity_id: str,
    accepted: int,
    roots: dict[str, str],
) -> tuple[dict[str, Any], set[Path]]:
    receipt = _load_json(path)
    if (
        receipt.get("schema") != WAVE_SCHEMA
        or receipt.get("fidelity_id") != fidelity_id
        or receipt.get("admission_eligible") is not True
        or receipt.get("counts")
        != {
            "accepted": accepted,
            "expected": accepted,
            "pending": 0,
            "terminal_negative": 0,
        }
        or receipt.get("decision")
        != {
            "coverage_complete": True,
            "dataset_finalize_may_start": True,
            "retry_may_start": False,
            "scientific_outcome": "POSITIVE",
            "terminal_negative": False,
        }
    ):
        raise ArchiveVerificationError(f"wave admission is not positive: {path}")
    accounting_row = receipt.get("finalizer_terminal_accounting", {}).get("row", {})
    if (
        accounting_row.get("State") != "COMPLETED"
        or accounting_row.get("ExitCode") != "0:0"
        or not str(accounting_row.get("JobID", "")).isdigit()
    ):
        raise ArchiveVerificationError("wave finalizer accounting is not terminal-clean")
    observed_roots = receipt.get("roots", {})
    for name, expected in roots.items():
        if observed_roots.get(f"{name}_sha256") != expected:
            raise ArchiveVerificationError(f"wave admission root mismatch: {name}")

    closure = {path}
    files = receipt.get("preterminal_files")
    if not isinstance(files, dict):
        raise ArchiveVerificationError("wave admission lacks preterminal files")
    path_keys = sorted(key for key in files if key.endswith("_path"))
    if len(path_keys) != 5:
        raise ArchiveVerificationError("wave preterminal inventory is not exact")
    for path_key in path_keys:
        sha_key = path_key[:-5] + "_sha256"
        artifact = _resolve_record(
            {"path": files[path_key], "sha256": files.get(sha_key)},
            f"wave {fidelity_id} {path_key}",
        )
        closure.add(artifact)
    return receipt, closure


def _validate_result(row: dict[str, Any], path: Path) -> None:
    result = _load_json(path)
    fidelity = row["fidelity_id"]
    expected_dir = "r3" if fidelity == R3_FIDELITY else "r4"
    expected_refine = 3 if fidelity == R3_FIDELITY else 4
    expected_coverage = 1500 if fidelity == R3_FIDELITY else 198
    expected_role = (
        "bulk_low_fidelity" if fidelity == R3_FIDELITY else "higher_fidelity_validation"
    )
    relative = _repo_relative(path)
    prefix = (
        "results/corpus_v4/cps_reference_v2/production/v1/attempts/"
        f"{expected_dir}/job_"
    )
    if not relative.startswith(prefix) or not relative.endswith("/result.json"):
        raise ArchiveVerificationError("accepted result path is outside its fidelity tree")
    if (
        result.get("schema") != TASK_SCHEMA
        or result.get("task_pass") is not True
        or result.get("package_admission_eligible") is not False
        or result.get("training_may_start") is not False
        or result.get("claim_eligible") is not False
        or result.get("speed_claim_eligible") is not False
        or result.get("fresh_production_solve") is not True
        or result.get("fidelity")
        != {
            "coverage": expected_coverage,
            "fidelity_id": fidelity,
            "pad_mm": 16.0,
            "refine": expected_refine,
            "role": expected_role,
        }
        or result.get("geometry")
        != {
            "geometry_sha256": row["geometry_sha256"],
            "layout_id": row["layout_id"],
        }
    ):
        raise ArchiveVerificationError(f"accepted result contract mismatch: {relative}")
    worker = result.get("worker_result", {})
    comparisons = {
        "cps_pf": row["cps_pf"],
        "mesh_nodes": row["mesh_nodes"],
        "mesh_tetrahedra": row["mesh_tetrahedra"],
        "relative_residual": row["relative_residual"],
        "system_sha256": row["system_sha256"],
    }
    if any(worker.get(name) != expected for name, expected in comparisons.items()):
        raise ArchiveVerificationError(f"accepted result payload mismatch: {relative}")
    execution = result.get("execution", {})
    gates = result.get("gates", {})
    numerical = gates.get("numerical_resource", {})
    if (
        execution.get("returncode") != 0
        or execution.get("signal") is not None
        or execution.get("timed_out") is not False
        or execution.get("worker_result_count") != 1
        or not isinstance(execution.get("stages"), list)
        or not execution["stages"]
        or gates.get("source_stable") is not True
        or gates.get("gmsh_thread", {}).get("pass") is not True
        or gates.get("gmsh_thread", {}).get("observed_gmsh_threads") != 1
        or numerical.get("pass") is not True
        or any(value is not True for value in numerical.get("checks", {}).values())
        or worker.get("input_system_sha256") != worker.get("system_sha256")
        or worker.get("refine") != expected_refine
        or worker.get("pad_mm") != 16.0
        or worker.get("rtol") != 1.0e-10
        or worker.get("maxiter") != 500
        or worker.get("solver_info") != 0
        or worker.get("linear_solver") != "pyamg_smoothed_aggregation_cg"
        or type(worker.get("iterations")) is not int
        or not (0 < worker["iterations"] <= worker["maxiter"])
    ):
        raise ArchiveVerificationError(f"accepted solver contract mismatch: {relative}")


def verify_archive(
    archive_path: Path = DEFAULT_ARCHIVE, *, require_git_tracked: bool = False
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    archive = _load_json(archive_path)
    if archive.get("schema") != ARCHIVE_SCHEMA:
        raise ArchiveVerificationError("unexpected production archive schema")
    if archive.get("source_commit") != "c01b97bc90cbe3d1f2094e9441eb2e18219e4eb1":
        raise ArchiveVerificationError("unexpected FEM-v2 production source commit")
    if archive.get("forbidden_claims") != [
        "ground_truth",
        "mesh_converged",
        "physical_accuracy_validated",
        "speed_claim_from_dataset_generation",
    ]:
        raise ArchiveVerificationError("scientific boundary is not frozen")
    if archive.get("accepted_artifacts") != {
        "expected_result_files": 1698,
        "inventory_source": "dataset observation rows",
    }:
        raise ArchiveVerificationError("accepted-artifact inventory is not frozen")

    closure: set[Path] = {archive_path}
    root_hashes: dict[str, str] = {}
    for name in ("protocol", "plan", "execution_lock"):
        record = archive.get("frozen_roots", {}).get(name)
        closure.add(_resolve_record(record, f"frozen {name}"))
        root_hashes[name] = record["sha256"]
    for name, record in archive.get("source_corpus", {}).items():
        closure.add(_resolve_record(record, f"source corpus {name}"))

    wave_admissions: dict[str, dict[str, Any]] = {}
    for name, fidelity, expected in (
        ("r3", R3_FIDELITY, 1500),
        ("r4", R4_FIDELITY, 198),
    ):
        record = archive.get("wave_admissions", {}).get(name)
        if (
            not isinstance(record, dict)
            or record.get("fidelity_id") != fidelity
            or record.get("accepted") != expected
        ):
            raise ArchiveVerificationError(f"archive wave record is invalid: {name}")
        admission_path = _resolve_record(
            {"path": record.get("path"), "sha256": record.get("sha256")},
            f"{name} admission",
        )
        receipt, wave_closure = _validate_wave_admission(
            admission_path,
            fidelity_id=fidelity,
            accepted=expected,
            roots=root_hashes,
        )
        wave_admissions[name] = receipt
        closure.update(wave_closure)
    reference_roots = wave_admissions["r3"].get("roots", {})
    if reference_roots.get("source_git_head") != archive["source_commit"]:
        raise ArchiveVerificationError("wave source commit differs from archive")
    _verify_source_commit(
        archive["source_commit"], reference_roots.get("source_sha256", {})
    )
    admitted_result_rows: set[tuple[str, int, str, str, str]] = set()
    for name, fidelity, expected in (
        ("r3", R3_FIDELITY, 1500),
        ("r4", R4_FIDELITY, 198),
    ):
        accepted_rows, accepted_path = _accepted_rows_from_receipt(
            wave_admissions[name],
            expected_fidelity=fidelity,
            expected_count=expected,
        )
        if admitted_result_rows & accepted_rows:
            raise ArchiveVerificationError("R3/R4 accepted sets overlap")
        admitted_result_rows.update(accepted_rows)
        closure.add(accepted_path)

    dataset = archive.get("dataset", {})
    expected_counts = {
        "geometries": 1500,
        "r3_observations": 1500,
        "r4_observations": 198,
        "total_observations": 1698,
    }
    if dataset.get("counts") != expected_counts:
        raise ArchiveVerificationError("dataset archive counts are not frozen")
    admission_path = _resolve_record(dataset.get("admission"), "dataset admission")
    final_manifest_path = _resolve_record(
        dataset.get("final_manifest"), "dataset final manifest"
    )
    observations_path = _resolve_record(dataset.get("observations"), "observations")
    summary_path = _resolve_record(dataset.get("summary"), "dataset summary")
    closure.update(
        {admission_path, final_manifest_path, observations_path, summary_path}
    )

    admission = _load_json(admission_path)
    if (
        admission.get("schema") != DATASET_ADMISSION_SCHEMA
        or admission.get("source_set_sha256") != dataset.get("source_set_sha256")
        or admission.get("admission_eligible") is not True
        or admission.get("counts") != expected_counts
        or admission.get("decision")
        != {
            "accuracy_protocol_may_be_frozen": True,
            "dataset_generation_admitted": True,
            "training_may_start": False,
        }
        or admission.get("training_may_start") is not False
        or admission.get("claim_eligible") is not False
        or admission.get("speed_claim_eligible") is not False
    ):
        raise ArchiveVerificationError("dataset admission boundary is invalid")
    dataset_accounting = admission.get("finalizer_terminal_accounting", {}).get(
        "row", {}
    )
    if (
        dataset_accounting.get("State") != "COMPLETED"
        or dataset_accounting.get("ExitCode") != "0:0"
        or not str(dataset_accounting.get("JobID", "")).isdigit()
    ):
        raise ArchiveVerificationError("dataset finalizer accounting is not terminal-clean")
    admission_roots = admission.get("roots", {})
    for name, expected in root_hashes.items():
        if admission_roots.get(f"{name}_sha256") != expected:
            raise ArchiveVerificationError(f"dataset admission root mismatch: {name}")
    if admission_roots.get("source_git_head") != archive["source_commit"]:
        raise ArchiveVerificationError("dataset source commit mismatch")
    preterminal = admission.get("preterminal_files", {})
    for name, record_name in (
        ("final_manifest", "final_manifest"),
        ("label_observations", "observations"),
        ("summary", "summary"),
    ):
        record = dataset[record_name]
        if (
            preterminal.get(f"{name}_path") != record["path"]
            or preterminal.get(f"{name}_sha256") != record["sha256"]
        ):
            raise ArchiveVerificationError(f"dataset receipt does not bind {name}")

    final_manifest = _load_json(final_manifest_path)
    if (
        final_manifest.get("schema") != DATASET_MANIFEST_SCHEMA
        or final_manifest.get("source_set_sha256") != dataset["source_set_sha256"]
        or final_manifest.get("files_sha256")
        != {
            "label_observations.jsonl": dataset["observations"]["sha256"],
            "summary.json": dataset["summary"]["sha256"],
        }
    ):
        raise ArchiveVerificationError("dataset final manifest is inconsistent")
    summary = _load_json(summary_path)
    if (
        summary.get("counts") != expected_counts
        or summary.get("decision")
        != {"dataset_generation_pass": True, "training_may_start": False}
        or summary.get("fidelity_semantics", {}).get("multifidelity_only") is not True
        or summary.get("fidelity_semantics", {}).get("ground_truth") is not False
        or summary.get("fidelity_semantics", {}).get("mesh_converged") is not False
    ):
        raise ArchiveVerificationError("dataset summary scientific boundary is invalid")

    layout_rows = _load_jsonl(_resolve_record(archive["source_corpus"]["layouts"], "layouts"))
    layout_geometry = {
        row.get("layout_id"): row.get("geometry_sha256") for row in layout_rows
    }
    if set(layout_geometry) != set(range(1500)) or len(layout_rows) != 1500:
        raise ArchiveVerificationError("layout registry is not dense 0..1499")
    selection = _load_json(
        _resolve_record(
            archive["source_corpus"]["hf_selection_registry"], "HF registry"
        )
    )
    expected_r4 = {row.get("layout_id") for row in selection.get("rows", [])}
    if len(expected_r4) != 198 or None in expected_r4:
        raise ArchiveVerificationError("higher-fidelity selection is not exactly 198")

    observations = _load_jsonl(observations_path)
    if len(observations) != 1698:
        raise ArchiveVerificationError("observation table does not contain 1698 rows")
    identities: set[tuple[str, int]] = set()
    observation_result_rows: set[tuple[str, int, str, str, str]] = set()
    result_paths: set[Path] = set()
    fidelity_counts: Counter[str] = Counter()
    for row_number, row in enumerate(observations, 1):
        if set(row) != OBSERVATION_KEYS:
            raise ArchiveVerificationError(f"observation row {row_number} is not exact")
        fidelity = row.get("fidelity_id")
        layout_id = row.get("layout_id")
        geometry = row.get("geometry_sha256")
        if fidelity not in {R3_FIDELITY, R4_FIDELITY}:
            raise ArchiveVerificationError(f"unknown fidelity at row {row_number}")
        if type(layout_id) is not int or layout_id not in layout_geometry:
            raise ArchiveVerificationError(f"invalid layout at row {row_number}")
        if geometry != layout_geometry[layout_id]:
            raise ArchiveVerificationError(f"geometry mismatch at row {row_number}")
        identity = (fidelity, layout_id)
        if identity in identities:
            raise ArchiveVerificationError(f"duplicate observation: {identity}")
        identities.add(identity)
        if row.get("units") != "pF":
            raise ArchiveVerificationError(f"unexpected units at row {row_number}")
        _positive_number(row.get("cps_pf"), f"row {row_number} capacitance")
        _positive_number(row.get("mesh_nodes"), f"row {row_number} mesh nodes")
        _positive_number(
            row.get("mesh_tetrahedra"), f"row {row_number} mesh tetrahedra"
        )
        residual = _positive_number(
            row.get("relative_residual"), f"row {row_number} residual"
        )
        if residual > 1.0e-8:
            raise ArchiveVerificationError(f"residual gate failed at row {row_number}")
        if not isinstance(row.get("system_sha256"), str) or SHA256_RE.fullmatch(
            row["system_sha256"]
        ) is None:
            raise ArchiveVerificationError(f"invalid system hash at row {row_number}")
        result_path = _resolve_record(
            {
                "path": row.get("artifact_result_path"),
                "sha256": row.get("artifact_result_sha256"),
            },
            f"accepted result row {row_number}",
        )
        if result_path in result_paths:
            raise ArchiveVerificationError("accepted result path is reused")
        _validate_result(row, result_path)
        result_paths.add(result_path)
        observation_result_rows.add(
            (
                fidelity,
                layout_id,
                geometry,
                row["artifact_result_path"],
                row["artifact_result_sha256"],
            )
        )
        fidelity_counts[fidelity] += 1
    if fidelity_counts != Counter({R3_FIDELITY: 1500, R4_FIDELITY: 198}):
        raise ArchiveVerificationError("observation fidelity coverage is incomplete")
    if {layout_id for fidelity, layout_id in identities if fidelity == R3_FIDELITY} != set(
        range(1500)
    ):
        raise ArchiveVerificationError("R3 coverage is not dense 0..1499")
    if {layout_id for fidelity, layout_id in identities if fidelity == R4_FIDELITY} != expected_r4:
        raise ArchiveVerificationError("R4 coverage differs from the frozen registry")
    if observation_result_rows != admitted_result_rows:
        raise ArchiveVerificationError(
            "dataset observations differ from the final admitted result union"
        )
    closure.update(result_paths)

    production = archive_path.parent
    attempts_root = production / "attempts"
    waves_root = production / "waves"
    dataset_root = production / "dataset"

    # Intermediate receipts are retained because they explain the cumulative
    # accepted set and the one infrastructure-only retry.  Their scientific
    # decisions may be incomplete by design, but every receipt must share the
    # frozen roots and authenticate its exact five-file preterminal package.
    observed_wave_receipts = {
        _repo_relative(path) for path in waves_root.rglob("FINAL_ADMISSION.json")
    }
    if observed_wave_receipts != set(EXPECTED_WAVE_ADMISSIONS):
        raise ArchiveVerificationError("wave receipt inventory is not exactly six")
    for relative in EXPECTED_WAVE_ADMISSIONS:
        receipt_path = ROOT / relative
        if receipt_path in closure:
            continue
        receipt = _load_json(receipt_path)
        if receipt.get("schema") != WAVE_SCHEMA:
            raise ArchiveVerificationError("unexpected intermediate wave schema")
        accounting_row = receipt.get("finalizer_terminal_accounting", {}).get(
            "row", {}
        )
        if (
            accounting_row.get("State") != "COMPLETED"
            or accounting_row.get("ExitCode") != "0:0"
            or not str(accounting_row.get("JobID", "")).isdigit()
        ):
            raise ArchiveVerificationError(
                "intermediate wave finalizer accounting is not terminal-clean"
            )
        receipt_roots = receipt.get("roots", {})
        for name, expected in root_hashes.items():
            if receipt_roots.get(f"{name}_sha256") != expected:
                raise ArchiveVerificationError(
                    f"intermediate wave root mismatch: {name}"
                )
        files = receipt.get("preterminal_files")
        if not isinstance(files, dict):
            raise ArchiveVerificationError("intermediate wave lacks file inventory")
        path_keys = sorted(key for key in files if key.endswith("_path"))
        if len(path_keys) != 5:
            raise ArchiveVerificationError(
                "intermediate wave preterminal inventory is not exact"
            )
        closure.add(receipt_path)
        for path_key in path_keys:
            sha_key = path_key[:-5] + "_sha256"
            closure.add(
                _resolve_record(
                    {"path": files[path_key], "sha256": files.get(sha_key)},
                    f"intermediate wave {path_key}",
                )
            )

    actual_attempt_files = {path for path in attempts_root.rglob("*") if path.is_file()}
    actual_wave_files = {path for path in waves_root.rglob("*") if path.is_file()}
    actual_dataset_files = {path for path in dataset_root.rglob("*") if path.is_file()}
    expected_wave_files = {
        path for path in closure if waves_root.resolve() in path.resolve().parents
    }
    expected_dataset_files = {
        path for path in closure if dataset_root.resolve() in path.resolve().parents
    }
    if actual_attempt_files != result_paths:
        raise ArchiveVerificationError("accepted-attempt inventory is not exact")
    if actual_wave_files != expected_wave_files:
        raise ArchiveVerificationError("wave-closure inventory is not exact")
    if actual_dataset_files != expected_dataset_files:
        raise ArchiveVerificationError("dataset-closure inventory is not exact")

    if require_git_tracked:
        _require_git_tracked(closure)
    return {
        "archive_sha256": _sha256_file(archive_path),
        "dataset_admission_sha256": dataset["admission"]["sha256"],
        "fidelity_counts": dict(sorted(fidelity_counts.items())),
        "result_files_verified": len(result_paths),
        "source_commit": archive["source_commit"],
        "status": "PASS",
        "training_may_start": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--require-git-tracked", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_archive(
            args.archive, require_git_tracked=args.require_git_tracked
        )
    except (ArchiveVerificationError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc), "status": "FAIL"}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
