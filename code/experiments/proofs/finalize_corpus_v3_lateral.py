#!/usr/bin/env python3
"""Verify and finalize all 490 controlled v3 lateral variants."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))
from geometry_contract import geometry_sha256, validate_layout, validate_passive_labels  # noqa: E402
from v3_dataset import sha256  # noqa: E402

SCHEMA = "pcb-gnn.corpus-v3-lateral-final.v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-array-job-id", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit lateral finalization through SLURM")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    if dirty:
        raise SystemExit("Refusing lateral finalization from a dirty tracked worktree")
    source = ROOT / "results/corpus_v3/lateral/jobs" / f"job_{args.source_array_job_id}"
    records, metas = [], []
    for task_id in range(14):
        records_path = source / f"task_{task_id:02d}_records.jsonl"
        meta = json.loads((source / f"task_{task_id:02d}_meta.json").read_text())
        if meta.get("schema") != "pcb-gnn.corpus-v3-lateral-label-task.v1":
            raise ValueError(f"task {task_id} schema mismatch")
        if meta["provenance"]["slurm_array_job_id"] != args.source_array_job_id:
            raise ValueError(f"task {task_id} job mismatch")
        if meta["provenance"]["git_head"] != head or meta["provenance"]["git_dirty_paths"]:
            raise ValueError(f"task {task_id} source mismatch")
        if sha256(records_path) != meta["records_sha256"]:
            raise ValueError(f"task {task_id} records hash mismatch")
        metas.append(meta)
        records.extend(json.loads(line) for line in records_path.read_text().splitlines() if line)
    if len(records) != 490:
        raise ValueError(f"expected 490 variants, found {len(records)}")
    keys = [(record["family_id"], record["variant_id"]) for record in records]
    if sorted(keys) != [(family, variant) for family in range(70) for variant in range(7)]:
        raise ValueError("family/variant registry incomplete or duplicated")
    source_maps = {json.dumps(meta["provenance"]["file_sha256"], sort_keys=True) for meta in metas}
    if len(source_maps) != 1:
        raise ValueError("lateral tasks used mixed source maps")
    hashes = set()
    spreads = []
    for record in records:
        validate_layout(record["layout"])
        validate_passive_labels(record["label"])
        digest = geometry_sha256(record["layout"])
        if digest != record["geometry_sha256"] or digest in hashes:
            raise ValueError("geometry hash mismatch or duplicate")
        hashes.add(digest)
    for family in range(70):
        cps = [record["label"]["Cps_pF"] for record in records if record["family_id"] == family]
        spreads.append((max(cps) - min(cps)) / min(cps) * 100.0)
    output = ROOT / "results/corpus_v3/lateral/final" / f"job_{os.environ['SLURM_JOB_ID']}"
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "lateral_families.jsonl"
    artifact.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in sorted(records, key=lambda row: (row["family_id"], row["variant_id"]))))
    summary = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"], "source_array_job_id": args.source_array_job_id,
            "git_head": head, "git_dirty_paths": dirty,
            "source_file_sha256": json.loads(next(iter(source_maps))),
        },
        "gates": {"n_families": 70, "n_variants": 490, "n_unique_geometry": len(hashes),
                  "geometry_valid": True, "labels_passive": True},
        "cps_within_family_spread_pct": {
            "min": float(np.min(spreads)), "median": float(np.median(spreads)), "max": float(np.max(spreads)),
        },
        "artifacts_sha256": {"lateral_families.jsonl": sha256(artifact)},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
