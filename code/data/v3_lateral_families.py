"""Deterministic geometry-valid lateral-registration families for v3 ranking."""
from __future__ import annotations

import copy
from functools import lru_cache

import numpy as np

from gen_corpus_v3 import make_layout_v3
from geometry_contract import geometry_sha256, validate_layout


@lru_cache(maxsize=1)
def eligible_bases(n_families: int = 70) -> tuple[tuple[int, dict, float, float], ...]:
    selected = []
    for layout_id in range(1500):
        layout = make_layout_v3(42000 + layout_id)
        secondary = [trace for trace in layout["traces"] if trace["net"] == "sec"]
        edge = float(layout["design_rules"]["board_edge_margin_mm"])
        low = edge - min(float(trace["x0"]) for trace in secondary)
        high = layout["board_w_mm"] - edge - max(
            float(trace["x0"]) + float(trace["length_mm"]) for trace in secondary
        )
        low, high = max(low, -1.5), min(high, 1.5)
        if high - low >= 2.0:
            selected.append((layout_id, layout, low, high))
        if len(selected) == n_families:
            return tuple(selected)
    raise ValueError(f"only found {len(selected)} eligible lateral families")


def make_family(family_id: int, variants: int = 7) -> list[dict]:
    if not 0 <= family_id < 70 or variants != 7:
        raise ValueError("canonical study uses 70 families and seven variants")
    base_layout_id, base, low, high = eligible_bases(70)[family_id]
    records = []
    for variant_id, offset in enumerate(np.linspace(low, high, variants)):
        layout = copy.deepcopy(base)
        layout["controlled_variant"] = {
            "family_id": family_id, "base_layout_id": base_layout_id,
            "lever": "secondary_global_x_offset_mm", "offset_mm": float(offset),
        }
        for trace in layout["traces"]:
            if trace["net"] == "sec":
                trace["x0"] = round(float(trace["x0"]) + float(offset), 9)
        validate_layout(layout)
        records.append({
            "family_id": family_id, "variant_id": variant_id,
            "base_layout_id": base_layout_id, "offset_mm": float(offset),
            "geometry_sha256": geometry_sha256(layout), "layout": layout,
        })
    return records
