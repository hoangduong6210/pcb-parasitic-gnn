"""Read-only contracts for the tracked Corpus v4 scientific archive."""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "code/quality"
sys.path.insert(0, str(QUALITY))

from verify_corpus_v4_archive import (  # noqa: E402
    ARCHIVE_SCHEMA,
    DEFAULT_MANIFEST,
    ArchiveValidationError,
    _record_map,
    load_jsonl,
    recompute_numerical_resource_gate,
    require_dense_entries,
    require_pinned_file,
    resolve_repo_path,
    validate_archive,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _dense_entries(count: int) -> list[dict[str, object]]:
    return [
        {
            "geometry_sha256": f"{index + 1:064x}",
            "path": f"results/tasks/task_{index:04d}.json",
            "task_index": index,
        }
        for index in range(count)
    ]


def test_tracked_archive_validates_end_to_end_without_a_solver() -> None:
    assert DEFAULT_MANIFEST == (
        ROOT / "results/corpus_v4/cps_multifidelity/ARCHIVE_MANIFEST.json"
    )
    assert validate_archive(ROOT, DEFAULT_MANIFEST) == {
        "geometries": 1500,
        "r3_observations": 1500,
        "r4_observations": 198,
        "rows": 1698,
    }


@pytest.mark.parametrize(
    ("relative", "fidelity_id"),
    (
        (
            "results/corpus_v4/cps_multifidelity/r3/attempts/"
            "job_6846403/task_0000.json",
            "cps_fem_r3_p16",
        ),
        (
            "results/corpus_v4/cps_multifidelity/r4/attempts/"
            "job_6891382/task_0197.json",
            "cps_fem_r4_p16",
        ),
    ),
)
def test_numerical_resource_gate_is_independently_reproducible(
    relative: str, fidelity_id: str
) -> None:
    artifact = json.loads((ROOT / relative).read_text())
    protocol = json.loads(
        (ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json").read_text()
    )
    recomputed = recompute_numerical_resource_gate(
        artifact["execution"], protocol, fidelity_id
    )
    assert recomputed == artifact["numerical_resource_gate"]

    tampered = deepcopy(artifact["execution"])
    tampered["worker_result"]["relative_residual"] = 1.0
    failed = recompute_numerical_resource_gate(tampered, protocol, fidelity_id)
    assert failed["pass"] is False
    assert failed["checks"]["relative_residual"] is False


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ({"schema": "unexpected"}, "unsupported archive manifest schema"),
        (
            {"schema": ARCHIVE_SCHEMA, "source_commit": "not-a-commit"},
            "archive source commit is not a 40/64-hex identity",
        ),
    ),
)
def test_manifest_rejects_schema_and_source_identity_before_loading_artifacts(
    tmp_path: Path, payload: dict[str, str], message: str
) -> None:
    manifest = tmp_path / "ARCHIVE_MANIFEST.json"
    _write_json(manifest, payload)
    with pytest.raises(ArchiveValidationError, match=message):
        validate_archive(tmp_path, manifest)


def test_pinned_file_accepts_exact_bytes_and_rejects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b'{"value":1}\n')
    record = {"path": "artifact.json", "sha256": _sha256(artifact)}
    assert require_pinned_file(tmp_path, record, "fixture") == artifact

    artifact.write_bytes(b'{"value":2}\n')
    with pytest.raises(ArchiveValidationError, match="fixture SHA-256 mismatch"):
        require_pinned_file(tmp_path, record, "fixture")


def test_pinned_file_rejects_missing_file_and_malformed_digest(tmp_path: Path) -> None:
    missing = {"path": "missing.json", "sha256": "0" * 64}
    with pytest.raises(ArchiveValidationError, match="missing fixture"):
        require_pinned_file(tmp_path, missing, "fixture")

    malformed = {"path": "missing.json", "sha256": "A" * 64}
    with pytest.raises(ArchiveValidationError, match="invalid SHA-256"):
        require_pinned_file(tmp_path, malformed, "fixture")


@pytest.mark.parametrize("relative", ("../escape.json", "/tmp/escape.json"))
def test_archive_paths_must_be_repository_relative(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(ArchiveValidationError, match="repository-relative"):
        resolve_repo_path(tmp_path, relative)


def test_archive_path_cannot_escape_through_a_symlink(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArchiveValidationError, match="escapes repository"):
        resolve_repo_path(tmp_path, "link/artifact.json")


def test_dense_entries_reject_missing_duplicate_and_reordered_tasks() -> None:
    require_dense_entries(_dense_entries(3), 3, "fixture")

    missing = _dense_entries(2)
    with pytest.raises(ArchiveValidationError, match="exact dense task coverage"):
        require_dense_entries(missing, 3, "fixture")

    duplicate_path = _dense_entries(3)
    duplicate_path[2]["path"] = duplicate_path[1]["path"]
    with pytest.raises(ArchiveValidationError, match="duplicate artifact paths"):
        require_dense_entries(duplicate_path, 3, "fixture")

    duplicate_geometry = _dense_entries(3)
    duplicate_geometry[2]["geometry_sha256"] = duplicate_geometry[1][
        "geometry_sha256"
    ]
    with pytest.raises(ArchiveValidationError, match="duplicate geometries"):
        require_dense_entries(duplicate_geometry, 3, "fixture")

    reordered = list(reversed(_dense_entries(3)))
    with pytest.raises(ArchiveValidationError, match="exact dense task coverage"):
        require_dense_entries(reordered, 3, "fixture")


def test_candidate_map_rejects_duplicate_paths() -> None:
    entries = [
        {"path": "task.json", "sha256": "a" * 64},
        {"path": "task.json", "sha256": "b" * 64},
    ]
    with pytest.raises(ArchiveValidationError, match="duplicate candidate path"):
        _record_map(entries)


def test_jsonl_loader_rejects_blank_and_non_object_rows(tmp_path: Path) -> None:
    blank = tmp_path / "blank.jsonl"
    blank.write_text('{"row":1}\n\n')
    with pytest.raises(ArchiveValidationError, match="blank JSONL row"):
        load_jsonl(blank)

    scalar = tmp_path / "scalar.jsonl"
    scalar.write_text("[]\n")
    with pytest.raises(ArchiveValidationError, match="expected JSON object"):
        load_jsonl(scalar)
