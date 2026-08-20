#!/usr/bin/env python3
"""Build the immutable source/panel lock for Corpus V4 latency execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_v4_latency_contract import (  # noqa: E402
    LatencyContractError,
    write_execution_lock,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--panel-records", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = write_execution_lock(
            args.out,
            protocol_path=args.protocol,
            plan_path=args.plan,
            task_manifest_path=args.task_manifest,
            panel_records_path=args.panel_records,
        )
    except (KeyError, LatencyContractError, OSError, TypeError, ValueError) as exc:
        print(f"Corpus V4 latency execution lock: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
