"""No-solver tests for the v3 split registry."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "code/core", ROOT / "code/data"):
    sys.path.insert(0, str(directory))

from v3_dataset import split_indices  # noqa: E402


def _samples() -> list[dict]:
    return [
        {"family": [pri, sec]}
        for pri in range(4, 10) for sec in range(4, 10) for _ in range(3)
    ]


def test_random_split_is_seeded_and_disjoint() -> None:
    samples = _samples()
    train, test = split_indices(samples, 42, "random")
    assert len(train) == int(0.8 * len(samples))
    assert set(train).isdisjoint(test)
    assert sorted(train + test) == list(range(len(samples)))
    assert (train, test) == split_indices(samples, 42, "random")


def test_family_split_has_no_family_leakage() -> None:
    samples = _samples()
    train, test = split_indices(samples, 42, "family")
    train_families = {tuple(samples[index]["family"]) for index in train}
    test_families = {tuple(samples[index]["family"]) for index in test}
    assert train_families.isdisjoint(test_families)
    assert sorted(train + test) == list(range(len(samples)))
