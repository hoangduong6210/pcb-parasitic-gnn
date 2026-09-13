"""Authenticate analysis-only recovery without rewriting the timing execution root."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from corpus_v4_latency_contract_v2 import (
    EXECUTION_SOURCE_NAMES,
    load_json,
    resolve_repo_path,
    validate_execution_lock,
)
from scientific_artifact import atomic_write_json, sha256_file

ROOT = Path(__file__).resolve().parents[3]
FINALIZER_LOCK_SCHEMA = "corpus-v4-latency-fem-v2-finalizer-execution-lock.v1"
FINALIZER_SOURCE_NAMES = tuple(sorted(set(EXECUTION_SOURCE_NAMES) | {
    "code/experiments/proofs/corpus_v4_latency_finalizer_contract_v3.py",
    "code/experiments/proofs/build_corpus_v4_latency_finalizer_lock_v3.py",
    "code/experiments/proofs/finalize_corpus_v4_latency_v3.py",
    "code/jobs/submit_finalize_corpus_v4_latency_v3.sh",
    "code/quality/verify_corpus_v4_latency_archive_v3.py",
}))


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"invalid {label} SHA-256")


def validate_finalizer_execution_lock(
    path: Path,
    expected_sha256: str,
    *,
    task_lock: Mapping[str, Any],
    task_lock_sha256: str,
    accepted_set_sha256: str,
    expected_task_source_git_head: str,
) -> tuple[dict[str, Any], str]:
    """Validate a second trust root while preserving every original timing source."""
    _digest(expected_sha256, "finalizer lock")
    _digest(task_lock_sha256, "task lock")
    _digest(accepted_set_sha256, "accepted set")
    if re.fullmatch(r"[0-9a-f]{40}", expected_task_source_git_head or "") is None:
        raise ValueError("invalid original task Git commit")
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected_sha256:
        raise ValueError("finalizer lock is missing or hash-mismatched")
    lock = load_json(path)
    if set(lock) != {
        "schema", "task_execution_lock_sha256", "expected_task_source_git_head",
        "accepted_set_sha256", "source_sha256",
    } or lock.get("schema") != FINALIZER_LOCK_SCHEMA:
        raise ValueError("unexpected finalizer execution-lock schema")
    if (
        lock["task_execution_lock_sha256"] != task_lock_sha256
        or lock["expected_task_source_git_head"] != expected_task_source_git_head
        or lock["accepted_set_sha256"] != accepted_set_sha256
    ):
        raise ValueError("finalizer lock does not bind the immutable timing evidence")
    sources = lock["source_sha256"]
    if not isinstance(sources, dict) or set(sources) != set(FINALIZER_SOURCE_NAMES):
        raise ValueError("finalizer source closure is not exact")
    if {name: sources[name] for name in EXECUTION_SOURCE_NAMES} != task_lock.get("source_sha256"):
        raise ValueError("finalizer source closure changes original timing source bytes")
    for name, digest in sources.items():
        _digest(digest, name)
        source = resolve_repo_path(name, "finalizer source")
        if source.is_symlink() or not source.is_file() or sha256_file(source) != digest:
            raise ValueError(f"finalizer source hash differs: {name}")
    return lock, expected_sha256


def validate_finalizer_source(lock: Mapping[str, Any], expected_source_git_head: str) -> dict[str, str]:
    """Require a clean committed analysis checkout distinct from historical task HEAD."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              check=True, text=True).stdout.strip()

    sources = {name: sha256_file(resolve_repo_path(name, "finalizer source"))
               for name in FINALIZER_SOURCE_NAMES}
    if (
        git("rev-parse", "HEAD") != expected_source_git_head
        or git("status", "--short", "--untracked-files=no")
        or git("status", "--short", "--untracked-files=all", "--", "code", "protocols", "requirements-proof.txt")
        or sources != lock.get("source_sha256")
    ):
        raise SystemExit("latency recovery finalizer requires the exact clean source commit")
    return sources


def write_finalizer_execution_lock(
    output: Path, *, task_lock_path: Path, expected_task_lock_sha256: str,
    accepted_set_path: Path, expected_accepted_set_sha256: str,
    expected_task_source_git_head: str,
) -> dict[str, Any]:
    """Write a solver-free lock; validate old sources and externally pinned evidence first."""
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    task_payload = load_json(task_lock_path)
    task_lock, task_sha = validate_execution_lock(
        task_lock_path, expected_task_lock_sha256,
        **{name: task_payload[name] for name in (
            "protocol_sha256", "plan_sha256", "task_manifest_sha256", "panel_records_sha256")},
    )
    _digest(expected_accepted_set_sha256, "accepted set")
    if (accepted_set_path.is_symlink() or not accepted_set_path.is_file()
            or sha256_file(accepted_set_path) != expected_accepted_set_sha256):
        raise ValueError("accepted set is missing or hash-mismatched")
    accepted = load_json(accepted_set_path)
    if accepted.get("execution_lock_sha256") != task_sha:
        raise ValueError("accepted set does not bind original task lock")
    payload = {
        "schema": FINALIZER_LOCK_SCHEMA,
        "task_execution_lock_sha256": task_sha,
        "expected_task_source_git_head": expected_task_source_git_head,
        "accepted_set_sha256": expected_accepted_set_sha256,
        "source_sha256": {name: sha256_file(resolve_repo_path(name, "finalizer source"))
                          for name in FINALIZER_SOURCE_NAMES},
    }
    if re.fullmatch(r"[0-9a-f]{40}", expected_task_source_git_head or "") is None:
        raise ValueError("invalid original task Git commit")
    if {name: payload["source_sha256"][name] for name in EXECUTION_SOURCE_NAMES} != task_lock["source_sha256"]:
        raise ValueError("original timing source bytes changed")
    atomic_write_json(output, payload)
    return payload
