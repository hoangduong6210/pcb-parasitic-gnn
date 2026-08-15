"""Geometry-only loader for the finalized corpus-v3 scientific root."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geometry_contract import geometry_sha256, validate_layout
from scientific_artifact import require_file_sha256, sha256_file


def load_verified_geometry_corpus(
    directory: Path,
    contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load geometry without consuming any legacy capacitance label."""
    root = directory.resolve()
    summary_path = root / "summary.json"
    layouts_path = root / "layouts.jsonl"
    require_file_sha256(summary_path, contract["summary_sha256"], "corpus summary")
    require_file_sha256(layouts_path, contract["layouts_sha256"], "corpus layouts")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema") != contract["summary_schema"]:
        raise ValueError("unexpected finalized corpus schema")
    if summary.get("gates", {}).get(contract["required_gate"]) is not True:
        raise ValueError("required finalized corpus geometry gate is not true")
    if summary.get("artifacts_sha256", {}).get("layouts.jsonl") != sha256_file(
        layouts_path
    ):
        raise ValueError("summary does not bind the layouts artifact")

    records = [
        json.loads(line)
        for line in layouts_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(records) != int(contract["n_layouts"]):
        raise ValueError("geometry cardinality differs from protocol")

    seen_ids: set[int] = set()
    seen_hashes: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for record in records:
        layout_id = int(record["layout_id"])
        geometry_hash = str(record["geometry_sha256"])
        layout = record["layout"]
        validate_layout(layout)
        if geometry_sha256(layout) != geometry_hash:
            raise ValueError(f"geometry hash mismatch for layout {layout_id}")
        if layout_id in seen_ids or geometry_hash in seen_hashes:
            raise ValueError("duplicate layout ID or geometry hash")
        seen_ids.add(layout_id)
        seen_hashes.add(geometry_hash)
        normalized.append(
            {
                "layout_id": layout_id,
                "geometry_sha256": geometry_hash,
                "layout": layout,
            }
        )
    if len(seen_hashes) != int(contract["n_unique_geometry"]):
        raise ValueError("unique geometry count differs from protocol")
    normalized.sort(key=lambda row: row["layout_id"])
    return normalized, summary
