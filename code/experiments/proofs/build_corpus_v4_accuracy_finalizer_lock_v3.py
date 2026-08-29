#!/usr/bin/env python3
"""Build a finalizer-only lock over one immutable V3 training execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_v4_accuracy_contract_v3 import (  # noqa: E402
    write_finalizer_execution_lock,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--accepted-set", type=Path, required=True)
    parser.add_argument("--training-execution-lock", type=Path, required=True)
    parser.add_argument("--expected-training-execution-lock-sha256", required=True)
    parser.add_argument("--expected-training-source-git-head", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = write_finalizer_execution_lock(
        args.out,
        protocol_path=args.protocol,
        plan_path=args.plan,
        task_manifest_path=args.task_manifest,
        accepted_set_path=args.accepted_set,
        training_lock_path=args.training_execution_lock,
        expected_training_lock_sha256=args.expected_training_execution_lock_sha256,
        expected_training_source_git_head=args.expected_training_source_git_head,
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
