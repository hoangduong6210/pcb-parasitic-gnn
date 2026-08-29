"""Protect the archived accuracy-v1 package while accuracy-v2 is developed."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "d512cf242a5b2b8faf60de9c6bba0a814f867ec6"


def _git_bytes(spec: str) -> bytes:
    return subprocess.run(
        ["git", "show", spec],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout


def test_accuracy_v1_tree_is_identical_to_the_admitted_upstream_commit() -> None:
    def tree(spec: str) -> str:
        return subprocess.run(
            ["git", "rev-parse", spec],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()

    assert tree("HEAD:results/corpus_v4/accuracy") == tree(
        f"{UPSTREAM_COMMIT}:results/corpus_v4/accuracy"
    )


def test_accuracy_v1_protocol_lock_and_sources_are_byte_identical() -> None:
    protected = {
        "protocols/corpus_v4_accuracy_v1.json",
        "protocols/corpus_v4_accuracy_execution_lock_v1.json",
    }
    lock = json.loads(
        (ROOT / "protocols/corpus_v4_accuracy_execution_lock_v1.json").read_text(
            encoding="utf-8"
        )
    )
    protected.update(lock["source_sha256"])
    for relative in sorted(protected):
        current = (ROOT / relative).read_bytes()
        assert current == _git_bytes(f"{UPSTREAM_COMMIT}:{relative}"), (
            f"accuracy-v1 byte drift: {relative}"
        )
        if relative in lock["source_sha256"]:
            assert hashlib.sha256(current).hexdigest() == lock["source_sha256"][relative]
