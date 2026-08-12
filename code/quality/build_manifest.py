#!/usr/bin/env python3
"""Build or verify the deterministic manifest of repository-tracked files."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "MANIFEST.json"


def tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        check=True,
        capture_output=True,
    )
    paths = [Path(item.decode()) for item in result.stdout.split(b"\0") if item]
    return sorted(path for path in paths if path.as_posix() != "MANIFEST.json")


def build_manifest() -> dict[str, object]:
    files: list[dict[str, object]] = []
    sections: Counter[str] = Counter()
    total_bytes = 0
    for relative in tracked_paths():
        absolute = REPO / relative
        payload = absolute.read_bytes()
        size = len(payload)
        top_level = relative.parts[0] if len(relative.parts) > 1 else "root"
        sections[top_level] += 1
        total_bytes += size
        files.append(
            {
                "path": relative.as_posix(),
                "bytes": size,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return {
        "schema": "pcb-parasitic-gnn-manifest-v2",
        "scope": "All Git-tracked files except MANIFEST.json itself",
        "sections": dict(sorted(sections.items())),
        "files": files,
        "n_files": len(files),
        "total_bytes": total_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    expected = build_manifest()
    if args.check:
        current = json.loads(MANIFEST.read_text())
        if current != expected:
            print("manifest check: FAIL")
            return 1
        print(f"manifest check: PASS ({expected['n_files']} files)")
        return 0
    MANIFEST.write_text(json.dumps(expected, indent=2) + "\n")
    print(f"wrote {MANIFEST} ({expected['n_files']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
