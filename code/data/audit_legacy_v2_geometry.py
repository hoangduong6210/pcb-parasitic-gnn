#!/usr/bin/env python3
"""Reconstruct and audit the superseded v2 corpus without running field solvers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from gen_corpus_fh import big_layout


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "pcb-gnn.legacy-v2-geometry-audit.v1"
PUBLIC_LABELS = ROOT / "datasets/synth_v2/labels.json"
FIELD_TARGETS = ROOT / "results/proof_updates/jobs/strict_e3/job_51174496/field_grade_targets.jsonl"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_box(trace: dict[str, Any]) -> tuple[float, ...]:
    x0 = float(trace.get("x0", 0.0))
    y0 = float(trace.get("y0", 0.0))
    zc = float(trace.get("z_mm", int(trace["layer"]) * 0.18 + 0.05))
    length = float(trace["length_mm"])
    width = float(trace["width_mm"])
    thickness = float(trace.get("thick_mm", 0.07))
    return x0, x0 + length, y0, y0 + width, zc - thickness / 2, zc + thickness / 2


def overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(
        min(a[high], b[high]) - max(a[low], b[low]) > 1e-9
        for low, high in ((0, 1), (2, 3), (4, 5))
    )


def audit_layout(layout: dict[str, Any]) -> dict[str, Any]:
    traces = layout["traces"]
    boxes = [raw_box(trace) for trace in traces]
    z_mismatches = sum(
        not math.isclose(
            float(trace.get("z_mm", math.nan)), int(trace["layer"]) * 0.18 + 0.05,
            rel_tol=0.0, abs_tol=1e-9,
        )
        for trace in traces
    )
    overlap_pairs = sum(
        overlap(boxes[left], boxes[right])
        for left in range(len(boxes)) for right in range(left + 1, len(boxes))
    )
    out_of_board = sum(
        box[0] < 0 or box[1] > float(layout["board_w_mm"])
        or box[2] < 0 or box[3] > float(layout["board_h_mm"])
        for box in boxes
    )
    fingerprint = hashlib.sha256(
        json.dumps(layout, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "n_traces": len(traces), "layer_z_mismatch_traces": z_mismatches,
        "overlap_pairs": overlap_pairs, "out_of_board_traces": out_of_board,
        "geometry_sha256": fingerprint,
    }


def passivity(labels: list[dict[str, Any]]) -> dict[str, Any]:
    coupling = np.asarray([
        abs(float(row["L_mut_nH"]))
        / math.sqrt(float(row["L_pri_nH"]) * float(row["L_sec_nH"]))
        for row in labels
    ])
    return {
        "n": len(labels), "n_k_gt_1": int(np.sum(coupling > 1.0 + 1e-9)),
        "k_min": float(coupling.min()), "k_median": float(np.median(coupling)),
        "k_max": float(coupling.max()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=1500)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        print(json.dumps({"schema": SCHEMA, "status": "validation-ok"}))
        return
    if not os.environ.get("SLURM_JOB_ID"):
        raise SystemExit("Submit this evidence-producing audit through SLURM")
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty_paths = subprocess.run(
        ["git", "status", "--short", "--untracked-files=no"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if dirty_paths:
        raise SystemExit("Refusing audit from a dirty tracked worktree")

    layouts = [big_layout(42 + layout_id, 36) for layout_id in range(args.n)]
    audits = [audit_layout(layout) for layout in layouts]
    public_labels = json.loads(PUBLIC_LABELS.read_text())
    field_attempts = [
        json.loads(line) for line in FIELD_TARGETS.read_text().splitlines() if line.strip()
    ]
    field_valid = [row for row in field_attempts if row.get("valid") and row.get("target")]
    field_labels = [
        {"Cps_pF": row["target"][0], "L_pri_nH": row["target"][1],
         "L_sec_nH": row["target"][2], "L_mut_nH": row["target"][3]}
        for row in field_valid
    ]
    target_names = ["Cps_pF", "L_pri_nH", "L_sec_nH", "L_mut_nH"]
    public_by_id = {int(row["id"]): row for row in public_labels}
    public_vs_field = {}
    for column, target in enumerate(target_names):
        relative = [
            abs(float(public_by_id[int(row["layout_id"])][target]) - float(row["target"][column]))
            / abs(float(row["target"][column])) * 100.0
            for row in field_valid
        ]
        public_vs_field[target] = {"median_relative_error_pct": float(np.median(relative))}

    field_audits = [audits[int(row["layout_id"])] for row in field_valid]
    result = {
        "schema": SCHEMA,
        "provenance": {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "git_head": git_head,
            "git_dirty_paths": dirty_paths,
            "file_sha256": {
                Path(__file__).relative_to(ROOT).as_posix(): sha256(Path(__file__)),
                "code/data/gen_corpus_fh.py": sha256(ROOT / "code/data/gen_corpus_fh.py"),
                "code/data/generate_synth.py": sha256(ROOT / "code/data/generate_synth.py"),
                PUBLIC_LABELS.relative_to(ROOT).as_posix(): sha256(PUBLIC_LABELS),
                FIELD_TARGETS.relative_to(ROOT).as_posix(): sha256(FIELD_TARGETS),
            },
        },
        "legacy_geometry": {
            "n_layouts": len(layouts),
            "n_traces": int(sum(row["n_traces"] for row in audits)),
            "layer_z_mismatch_traces": int(sum(row["layer_z_mismatch_traces"] for row in audits)),
            "layouts_with_layer_z_mismatch": int(sum(row["layer_z_mismatch_traces"] > 0 for row in audits)),
            "overlap_pairs": int(sum(row["overlap_pairs"] for row in audits)),
            "layouts_with_overlap": int(sum(row["overlap_pairs"] > 0 for row in audits)),
            "out_of_board_traces": int(sum(row["out_of_board_traces"] for row in audits)),
            "layouts_with_out_of_board": int(sum(row["out_of_board_traces"] > 0 for row in audits)),
            "exact_duplicate_layouts": len(audits) - len({row["geometry_sha256"] for row in audits}),
        },
        "public_mixed_labels": passivity(public_labels),
        "public_vs_field": public_vs_field,
        "field_grade": {
            "n_attempted": len(field_attempts), "n_valid": len(field_valid),
            **passivity(field_labels),
            "layouts_with_layer_z_mismatch": int(sum(row["layer_z_mismatch_traces"] > 0 for row in field_audits)),
            "layouts_with_overlap": int(sum(row["overlap_pairs"] > 0 for row in field_audits)),
            "layouts_with_out_of_board": int(sum(row["out_of_board_traces"] > 0 for row in field_audits)),
        },
    }
    output = ROOT / "results/data_integrity/jobs" / f"job_{os.environ['SLURM_JOB_ID']}" / "legacy_v2_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
