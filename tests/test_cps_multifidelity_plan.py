"""Contracts for the frozen Cps multi-fidelity protocol and plan."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocols/corpus_v4_cps_multifidelity_v1.json"
PLAN_ROOT = ROOT / "results/corpus_v4/cps_multifidelity/plan/v1"
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

from build_corpus_v4_cps_candidate_index import build_entries  # noqa: E402
from plan_corpus_v4_cps_submission_shards import build_shards  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_protocol_keeps_fidelities_explicit_and_rejects_ground_truth() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["schema"] == "pcb-gnn.cps-multifidelity-protocol.v1"
    assert protocol["fidelities"] == {
        "cps_fem_r3_p16": {
            "coverage": 1500,
            "pad_mm": 16.0,
            "refine": 3,
            "role": "bulk_low_fidelity",
        },
        "cps_fem_r4_p16": {
            "coverage": 198,
            "pad_mm": 16.0,
            "refine": 4,
            "role": "higher_fidelity_validation",
        },
    }
    assert protocol["scientific_semantics"]["r3_converged_to_r4"] is False
    assert protocol["scientific_semantics"]["r4_continuum_converged"] is False
    assert "ground_truth" in protocol["scientific_semantics"]["forbidden_claims"]


def test_plan_closes_all_artifact_hashes_and_task_coverage() -> None:
    plan = json.loads((PLAN_ROOT / "plan.json").read_text())
    assert plan["counts"] == {
        "families": 66,
        "geometries": 1500,
        "r3_tasks": 1500,
        "r4_tasks": 198,
    }
    assert plan["protocol_sha256"] == _sha256(PROTOCOL)
    assert plan["planner_environment"] == {"numpy": "2.0.2", "python": "3.9.21"}
    for name, expected in plan["planner_source_sha256"].items():
        assert _sha256(ROOT / name) == expected
    for name, expected in plan["artifact_sha256"].items():
        assert _sha256(PLAN_ROOT / name) == expected

    for name, expected_count, fidelity_id in (
        ("r3_manifest.jsonl", 1500, "cps_fem_r3_p16"),
        ("r4_manifest.jsonl", 198, "cps_fem_r4_p16"),
    ):
        rows = _jsonl(PLAN_ROOT / name)
        assert len(rows) == expected_count
        assert [row["task_index"] for row in rows] == list(range(expected_count))
        assert {row["fidelity_id"] for row in rows} == {fidelity_id}
        assert {row["schema"] for row in rows} == {
            "pcb-gnn.cps-multifidelity-task-manifest.v1"
        }
        assert len({row["geometry_sha256"] for row in rows}) == expected_count
        assert len({row["layout_id"] for row in rows}) == expected_count
        assert {row["solver_contract_id"] for row in rows} == {
            plan["solver_contract_ids"][fidelity_id]
        }
        assert {row["protocol_sha256"] for row in rows} == {
            plan["protocol_sha256"]
        }


def test_selection_is_three_per_family_and_includes_all_anchors() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    selection = json.loads((PLAN_ROOT / "hf_selection_registry.json").read_text())
    rows = selection["rows"]
    anchors = set(protocol["validation_selection"]["mandatory_geometry_sha256"])
    selected = {row["geometry_sha256"] for row in rows}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["family_id"]] = counts.get(row["family_id"], 0) + 1
    assert len(rows) == 198
    assert len(counts) == 66
    assert set(counts.values()) == {3}
    assert anchors <= selected
    assert sum(row["is_mandatory_anchor"] for row in rows) == 9
    assert len(selected) == 198
    for family_id in counts:
        ranks = {
            row["selection_rank_within_family"]
            for row in rows
            if row["family_id"] == family_id
        }
        assert ranks == {0, 1, 2}
    assert all("family_coverage_fraction" in row for row in rows)
    assert all("family_expansion_weight" in row for row in rows)
    assert all("probability" not in key for row in rows for key in row)

    r4 = _jsonl(PLAN_ROOT / "r4_manifest.jsonl")
    assert {row["geometry_sha256"] for row in r4} == selected


def test_swap_closed_splits_are_exact_disjoint_and_exhaustive() -> None:
    registry = json.loads((PLAN_ROOT / "split_registry.json").read_text())
    assert registry["schema"] == "pcb-gnn.swap-closed-split-registry.v1"
    assert {row["split_seed"] for row in registry["rows"]} == {40, 41, 42, 43, 44}
    assert len(registry["rows"]) == 5
    expected_sizes = {
        40: (1039, 170, 291),
        41: (1066, 152, 282),
        42: (1012, 182, 306),
        43: (1076, 125, 299),
        44: (1055, 153, 292),
    }
    for row in registry["rows"]:
        partitions = row["partitions"]
        train = set(partitions["train"]["layout_ids"])
        validation = set(partitions["validation"]["layout_ids"])
        test = set(partitions["test"]["layout_ids"])
        assert not train & validation
        assert not train & test
        assert not validation & test
        assert train | validation | test == set(range(1500))
        assert tuple(len(partitions[name]["family_ids"]) for name in (
            "train", "validation", "test"
        )) == (46, 7, 13)
        assert (len(train), len(validation), len(test)) == expected_sizes[
            row["split_seed"]
        ]


def test_family_registry_is_schema_bound_and_matches_every_split() -> None:
    families = _jsonl(PLAN_ROOT / "geometry_families.jsonl")
    assert len(families) == 66
    assert {row["schema"] for row in families} == {
        "pcb-gnn.geometry-family-registry.v1"
    }
    all_layouts = [layout_id for row in families for layout_id in row["member_layout_ids"]]
    assert sorted(all_layouts) == list(range(1500))
    family_members = {row["family_id"]: set(row["member_layout_ids"]) for row in families}
    registry = json.loads((PLAN_ROOT / "split_registry.json").read_text())
    for split in registry["rows"]:
        for partition in split["partitions"].values():
            expected_layouts = {
                layout_id
                for family_id in partition["family_ids"]
                for layout_id in family_members[family_id]
            }
            assert set(partition["layout_ids"]) == expected_layouts


def test_r3_submission_shards_are_dense_disjoint_and_exhaustive() -> None:
    rows = _jsonl(PLAN_ROOT / "r3_manifest.jsonl")
    plan = json.loads((PLAN_ROOT / "plan.json").read_text())
    shards = build_shards(
        rows,
        plan_sha256=_sha256(PLAN_ROOT / "plan.json"),
        manifest_sha256=plan["artifact_sha256"]["r3_manifest.jsonl"],
        execution_lock_sha256="a" * 64,
        max_array_size=1001,
    )
    assert [len(shard["pending"]) for shard in shards] == [1001, 499]
    indices = [[entry["task_index"] for entry in shard["pending"]] for shard in shards]
    assert indices[0] == list(range(1001))
    assert indices[1] == list(range(1001, 1500))
    assert not set(indices[0]) & set(indices[1])
    assert all(shard["execution_lock_sha256"] == "a" * 64 for shard in shards)

    retry_rows = [rows[index] for index in (3, 5, 1002)]
    retry_shards = build_shards(
        retry_rows,
        plan_sha256=_sha256(PLAN_ROOT / "plan.json"),
        manifest_sha256=plan["artifact_sha256"]["r3_manifest.jsonl"],
        execution_lock_sha256="a" * 64,
        max_array_size=2,
    )
    assert [
        entry["task_index"] for shard in retry_shards for entry in shard["pending"]
    ] == [3, 5, 1002]
    assert [len(shard["pending"]) for shard in retry_shards] == [2, 1]


def test_candidate_index_uses_only_completed_task_artifacts(tmp_path: Path) -> None:
    attempt = tmp_path / "results/attempts/job_123"
    attempt.mkdir(parents=True)
    completed = attempt / "task_0007.json"
    completed.write_text('{"task_pass": true}\n')
    (attempt / "task_0007.started.json").write_text("{}\n")
    (attempt / "notes.json").write_text("{}\n")
    entries = build_entries([attempt, attempt], root=tmp_path)
    assert entries == [
        {
            "path": "results/attempts/job_123/task_0007.json",
            "sha256": _sha256(completed),
        }
    ]
