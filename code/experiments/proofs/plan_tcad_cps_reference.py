#!/usr/bin/env python3
"""Create/check a geometry-only development panel; never mesh, solve or fit."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))
from geometry_contract import trace_box, xy_clearance_mm
from scientific_artifact import atomic_write_json, sha256_file
from verified_geometry_corpus import load_verified_geometry_corpus

PROTOCOL = ROOT / "protocols/tcad_cps_reference_v1.json"
PANEL = ROOT / "results/tcad/cps_reference_v1/plan/panel.json"


def rank_key(row: dict) -> str:
    return hashlib.sha256(
        ("tcad-cps-reference-v1:" + row["geometry_sha256"]).encode()
    ).hexdigest()


def descriptors(layout: dict) -> dict:
    traces = layout["traces"]
    boxes = [trace_box(layout, trace) for trace in traces]
    clearances, overlap = [], 0.0
    for i, j in combinations(range(len(traces)), 2):
        a, b = boxes[i], boxes[j]
        if traces[i]["layer"] == traces[j]["layer"]:
            clearances.append(xy_clearance_mm(a, b))
        if traces[i]["net"] != traces[j]["net"]:
            overlap += max(0.0, min(a[1], b[1]) - max(a[0], b[0])) * max(
                0.0, min(a[3], b[3]) - max(a[2], b[2])
            )
    return {
        "n_conductors": len(traces),
        "same_layer_clearance_mm": min(clearances) if clearances else math.hypot(
            layout["board_w_mm"], layout["board_h_mm"]
        ),
        "no_same_layer_pairs": not clearances,
        "opposite_net_overlap_mm2": overlap,
    }


def halves(rows: list[dict], key: str) -> tuple[list[dict], list[dict]]:
    ordered = sorted(rows, key=lambda row: (row["descriptors"][key], rank_key(row)))
    middle = len(ordered) // 2
    if middle == 0:
        raise ValueError("empty geometry stratum; no fallback is permitted")
    return ordered[:middle], ordered[middle:]


def panel_from_records(records: list[dict], protocol: dict) -> dict:
    # Project only geometry keys so labels cannot affect ordering or output.
    rows = [
        {"layout_id": r["layout_id"], "geometry_sha256": r["geometry_sha256"],
         "layout": r["layout"], "descriptors": descriptors(r["layout"])}
        for r in records
    ]
    selected, cells = [], []
    lower = 0
    for count_bin, upper in enumerate(protocol["selection"]["conductor_count_upper_bounds"]):
        group = [r for r in rows if lower < r["descriptors"]["n_conductors"] <= upper]
        for gap_bin, gap_group in enumerate(halves(group, "same_layer_clearance_mm")):
            for overlap_bin, cell in enumerate(halves(gap_group, "opposite_net_overlap_mm2")):
                if not cell:
                    raise ValueError("empty selection cell")
                cell_id = f"count{count_bin}-gap{gap_bin}-overlap{overlap_bin}"
                representative = min(cell, key=rank_key)
                selected.append({**representative, "cell_id": cell_id, "count_bin": count_bin})
                cells.append({
                    "cell_id": cell_id, "population": len(cell),
                    "count_interval": [lower + 1, upper],
                    "clearance_range_mm": [min(r["descriptors"]["same_layer_clearance_mm"] for r in cell), max(r["descriptors"]["same_layer_clearance_mm"] for r in cell)],
                    "overlap_range_mm2": [min(r["descriptors"]["opposite_net_overlap_mm2"] for r in cell), max(r["descriptors"]["opposite_net_overlap_mm2"] for r in cell)],
                    "selected_geometry_sha256": representative["geometry_sha256"],
                })
        lower = upper
    if len(selected) != protocol["selection"]["panel_size"] or sum(c["population"] for c in cells) != len(rows):
        raise ValueError("panel coverage differs from the protocol")
    if len({r["geometry_sha256"] for r in selected}) != len(selected):
        raise ValueError("duplicate geometry in panel")
    sentinels = []
    for count_bin in range(3):
        group = [r for r in selected if r["count_bin"] == count_bin]
        sentinel = min(group, key=lambda r: (
            -r["descriptors"]["n_conductors"], -r["descriptors"]["opposite_net_overlap_mm2"],
            r["descriptors"]["same_layer_clearance_mm"], rank_key(r),
        ))
        sentinels.append(sentinel["layout_id"])
    return {"schema": "pcb-gnn.tcad-cps-reference-panel.v1", "selection": protocol["selection"],
            "cells": cells, "rows": selected, "pilot_layout_ids": sentinels,
            "target_values_used": False, "is_blind_model_test": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    records, _ = load_verified_geometry_corpus(ROOT / protocol["geometry"]["directory"], protocol["geometry"])
    panel = panel_from_records(records, protocol)
    panel["protocol_sha256"] = sha256_file(PROTOCOL)
    if args.check:
        if json.loads(PANEL.read_text()) != panel:
            raise SystemExit("panel does not reconstruct from geometry and protocol")
    else:
        if PANEL.exists():
            raise SystemExit("refusing to replace an existing panel; use --check")
        atomic_write_json(PANEL, panel)
    print(json.dumps({"panel_size": len(panel["rows"]), "pilot_layout_ids": panel["pilot_layout_ids"],
                      "panel_sha256": sha256_file(PANEL), "checked": args.check}))


if __name__ == "__main__":
    main()
