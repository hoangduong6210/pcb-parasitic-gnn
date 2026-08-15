#!/usr/bin/env python3
"""Build a byte-hashed candidate index from explicit job attempt directories."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code/core"))

from scientific_artifact import atomic_write_json, sha256_file  # noqa: E402


SCHEMA = "pcb-gnn.cps-multifidelity-candidate-index.v1"


def resolve_attempt_directory(path: Path, root: Path = ROOT) -> Path:
    resolved = path.resolve()
    if root.resolve() not in resolved.parents or not resolved.is_dir():
        raise ValueError("attempt directory must exist inside the repository")
    return resolved


def build_entries(attempt_directories: list[Path], root: Path = ROOT) -> list[dict[str, str]]:
    """Hash completed task artifacts from explicit, repository-local attempts."""
    entries: list[dict[str, str]] = []
    seen: set[Path] = set()
    for supplied in attempt_directories:
        attempt_dir = resolve_attempt_directory(supplied, root)
        for path in sorted(attempt_dir.glob("task_[0-9][0-9][0-9][0-9].json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            entries.append(
                {
                    "path": resolved.relative_to(root.resolve()).as_posix(),
                    "sha256": sha256_file(resolved),
                }
            )
    return sorted(entries, key=lambda entry: entry["path"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-dir", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite an existing candidate index")

    entries = build_entries(args.attempt_dir)
    payload = {
        "attempt_directories": [
            resolve_attempt_directory(path).relative_to(ROOT.resolve()).as_posix()
            for path in args.attempt_dir
        ],
        "entries": entries,
        "n_entries": len(entries),
        "schema": SCHEMA,
    }
    atomic_write_json(args.out, payload)
    print(json.dumps({"n_entries": len(entries), "output": str(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
