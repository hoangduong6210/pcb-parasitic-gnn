#!/usr/bin/env python3
"""Verify the immutable corpus files used by the published experiments."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXPECTED = {
    "synth_v1/layouts.jsonl": "7ac79e2ef0ab82770b6b37c2345d790b808745029d476f61d23607c589893bf8",
    "synth_v1/labels.json": "1438d3c2e5e52a0d4f8b7bead8f842767df200aa32b1971e5862b0b194c8797d",
    "synth_v1/meta.json": "6bd6e13b44cd80da823030e8b48f2ae875c317c63e2eace76a2880aec4f62636",
    "synth_v2/layouts.jsonl": "d0751f18c8e80a8801c2142b95b0ff126b14e452bb2190ea806c88d1c9297ddc",
    "synth_v2/labels.json": "86947645075a1a87190bf86b29c5845ba51ccdd5b701fdc92436e30c78ac10e0",
    "synth_v2/meta.json": "d3034782d9989ca856b4cea917b525581eb2a396d5a802acf9361805d8213be4",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("datasets"))
    parser.add_argument(
        "--corpus", choices=("synth_v1", "synth_v2"),
        help="verify one corpus instead of every known corpus",
    )
    parser.add_argument(
        "--require-layouts",
        action="store_true",
        help="fail when the large, intentionally untracked layout files are absent",
    )
    args = parser.parse_args()

    failures: list[str] = []
    for relative, expected in EXPECTED.items():
        if args.corpus and not relative.startswith(args.corpus + "/"):
            continue
        path = args.data_root / relative
        if not path.exists():
            if path.name == "layouts.jsonl" and not args.require_layouts:
                print(f"SKIP {relative}: regenerate or provide PCB_GNN_DATA_ROOT")
                continue
            failures.append(f"missing: {relative}")
            continue
        actual = sha256(path)
        state = "OK" if actual == expected else "MISMATCH"
        print(f"{state} {relative} {actual}")
        if actual != expected:
            failures.append(f"hash mismatch: {relative}")

    if failures:
        raise SystemExit("corpus verification failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
