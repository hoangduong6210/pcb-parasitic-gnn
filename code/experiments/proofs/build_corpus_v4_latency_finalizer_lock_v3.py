#!/usr/bin/env python3
"""Build the analysis-only recovery lock over unchanged latency task evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/experiments/proofs"):
    sys.path.insert(0, str(directory))

from corpus_v4_latency_finalizer_contract_v3 import write_finalizer_execution_lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-execution-lock", type=Path, required=True)
    parser.add_argument("--expected-task-execution-lock-sha256", required=True)
    parser.add_argument("--accepted-set", type=Path, required=True)
    parser.add_argument("--expected-accepted-set-sha256", required=True)
    parser.add_argument("--expected-task-source-git-head", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = write_finalizer_execution_lock(
        args.out, task_lock_path=args.task_execution_lock,
        expected_task_lock_sha256=args.expected_task_execution_lock_sha256,
        accepted_set_path=args.accepted_set,
        expected_accepted_set_sha256=args.expected_accepted_set_sha256,
        expected_task_source_git_head=args.expected_task_source_git_head,
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
