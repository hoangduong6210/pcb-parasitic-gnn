"""No-solver geometry tests for controlled v3 lateral families."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from geometry_contract import validate_layout  # noqa: E402
from v3_lateral_families import make_family  # noqa: E402


def test_seventy_lateral_families_have_seven_unique_valid_variants() -> None:
    hashes = set()
    for family_id in range(70):
        family = make_family(family_id)
        assert len(family) == 7
        offsets = [record["offset_mm"] for record in family]
        assert offsets == sorted(offsets)
        assert offsets[-1] - offsets[0] >= 2.0
        for record in family:
            validate_layout(record["layout"])
            assert record["geometry_sha256"] not in hashes
            hashes.add(record["geometry_sha256"])
    assert len(hashes) == 490
