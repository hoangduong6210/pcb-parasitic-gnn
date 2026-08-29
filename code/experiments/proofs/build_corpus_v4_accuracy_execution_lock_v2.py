#!/usr/bin/env python3
"""Build the immutable source/plan lock for Corpus V4 accuracy execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_v4_accuracy_contract_v2 import write_execution_lock  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = write_execution_lock(
        args.out,
        protocol_path=args.protocol,
        plan_path=args.plan,
        task_manifest_path=args.task_manifest,
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
