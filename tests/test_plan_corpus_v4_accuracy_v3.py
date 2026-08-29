"""Focused contracts for the deterministic Corpus V4 accuracy plan."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

import plan_corpus_v4_accuracy_v3 as planner  # noqa: E402


def _json(payload: bytes) -> dict:
    value = json.loads(payload)
    assert isinstance(value, dict)
    return value


def _jsonl(payload: bytes) -> list[dict]:
    return [json.loads(line) for line in payload.decode("utf-8").splitlines() if line]


@pytest.fixture(scope="module")
def artifacts() -> dict[str, bytes]:
    first = planner.build_artifacts(root=ROOT, protocol_path=planner.DEFAULT_PROTOCOL)
    second = planner.build_artifacts(root=ROOT, protocol_path=planner.DEFAULT_PROTOCOL)
    assert first == second
    return first


def test_joined_dataset_uses_r3_not_legacy_cps(
    artifacts: dict[str, bytes],
) -> None:
    rows = _jsonl(artifacts["evaluation_dataset.jsonl"])
    assert len(rows) == 1500
    assert [row["layout_id"] for row in rows] == list(range(1500))
    assert len({row["geometry_sha256"] for row in rows}) == 1500
    assert {row["schema"] for row in rows} == {planner.DATASET_ROW_SCHEMA}
    assert sum(row["evaluation_only_r4_cps"] is not None for row in rows) == 198

    source_labels = planner.load_jsonl(ROOT / "datasets/corpus_v3/labels.jsonl")
    protocol = planner.load_json(planner.DEFAULT_PROTOCOL)
    observations = planner.load_jsonl(
        ROOT / protocol["inputs"]["final_observations"]["path"]
    )
    r3_layout_zero = next(
        row["cps_pf"]
        for row in observations
        if row["layout_id"] == 0 and row["fidelity_id"] == "cps_fem_r3_p16_t1_v2"
    )
    joined = rows[0]["training_reference"]
    assert joined["Cps_pF"] == {
        "fidelity_id": "cps_fem_r3_p16_t1_v2",
        "units": "pF",
        "value": r3_layout_zero,
    }
    assert joined["Cps_pF"]["value"] != source_labels[0]["Cps_pF"]
    assert set(joined) == set(planner.TARGET_NAMES)
    assert "timing_ms" not in rows[0]
    assert "coupling_coefficient" not in rows[0]


def test_task_grid_is_dense_row_major_and_designates_task_12(
    artifacts: dict[str, bytes],
) -> None:
    tasks = _jsonl(artifacts["task_manifest.jsonl"])
    assert len(tasks) == 25
    assert [row["task_id"] for row in tasks] == list(range(25))
    assert [
        (row["split_seed"], row["init_seed"]) for row in tasks
    ] == [
        (split_seed, init_seed)
        for split_seed in planner.EXPECTED_SEEDS
        for init_seed in planner.EXPECTED_SEEDS
    ]
    designated = [row for row in tasks if row["designated_downstream_checkpoint"]]
    assert len(designated) == 1
    assert (designated[0]["task_id"], designated[0]["split_seed"], designated[0]["init_seed"]) == (
        12,
        42,
        42,
    )
    assert {row["schema"] for row in tasks} == {planner.TASK_SCHEMA}


def test_every_task_pins_exact_partition_counts_and_memberships(
    artifacts: dict[str, bytes],
) -> None:
    tasks = _jsonl(artifacts["task_manifest.jsonl"])
    evaluation_sha = planner.sha256_bytes(artifacts["evaluation_dataset.jsonl"])
    by_split: dict[int, list[dict]] = {}
    for row in tasks:
        by_split.setdefault(row["split_seed"], []).append(row)
        assert row["evaluation_dataset_sha256"] == evaluation_sha
        assert row["partition_counts"] == planner.EXPECTED_LAYOUT_COUNTS[row["split_seed"]]
        assert row["partition_family_counts"] == planner.EXPECTED_FAMILY_COUNTS
        assert row["r4_test_layout_count"] == 39
        assert len(row["r4_test_layout_ids"]) == 39
        assert len(row["r4_test_geometry_sha256"]) == 39
        assert set(row["partition_layout_ids_sha256"]) == {
            "train",
            "validation",
            "test",
        }
        assert set(row["partition_family_ids_sha256"]) == {
            "train",
            "validation",
            "test",
        }
        for partition in ("train", "validation", "test"):
            frozen = row["partitions"][partition]
            assert row["partition_layout_ids_sha256"][partition] == planner.sha256_bytes(
                planner.canonical_json_bytes(frozen["layout_ids"])
            )
            assert row["partition_family_ids_sha256"][partition] == planner.sha256_bytes(
                planner.canonical_json_bytes(frozen["family_ids"])
            )
        assert row["r4_test_layout_ids_sha256"] == planner.sha256_bytes(
            planner.canonical_json_bytes(row["r4_test_layout_ids"])
        )
        assert set(row["r4_test_layout_ids"]) <= set(
            row["partitions"]["test"]["layout_ids"]
        )

    assert set(by_split) == set(planner.EXPECTED_SEEDS)
    for split_tasks in by_split.values():
        assert len(split_tasks) == 5
        assert len(
            {
                json.dumps(row["partition_layout_ids_sha256"], sort_keys=True)
                for row in split_tasks
            }
        ) == 1
        assert len({row["r4_test_layout_ids_sha256"] for row in split_tasks}) == 1


def test_plan_binds_both_artifacts_and_records_overlap_scope(
    artifacts: dict[str, bytes],
) -> None:
    plan = _json(artifacts["plan.json"])
    assert plan["schema"] == planner.PLAN_SCHEMA
    assert plan["artifact_sha256"] == {
        "evaluation_dataset.jsonl": planner.sha256_bytes(
            artifacts["evaluation_dataset.jsonl"]
        ),
        "task_manifest.jsonl": planner.sha256_bytes(artifacts["task_manifest.jsonl"]),
        **{
            name: planner.sha256_bytes(artifacts[name])
            for name in planner.TRAINING_ARTIFACT_NAMES
        },
    }
    assert plan["counts"] == {
        "designated_downstream_tasks": 1,
        "evaluation_rows": 1500,
        "families": 66,
        "r3_observations": 1500,
        "r4_observations": 198,
        "split_rows": 5,
        "tasks": 25,
        "training_rows_by_split": {
            "40": 1209,
            "41": 1218,
            "42": 1194,
            "43": 1201,
            "44": 1208,
        },
    }
    assert plan["designated_downstream"] == {
        "init_seed": 42,
        "split_seed": 42,
        "task_id": 12,
    }
    assert plan["r4_test_overlap"] == {
        "panel_memberships": 195,
        "unique_families": 45,
        "unique_layouts": 135,
    }
    assert plan["scientific_scope"] == {
        "preacceptance_r4_bytes_present": False,
        "preacceptance_test_reference_bytes_present": False,
        "legacy_cps_used": False,
        "random_split_used": False,
        "r4_role": "evaluation-only on each split's 39 selected test layouts",
        "test_panels_are_independent": False,
    }


def test_training_artifacts_are_split_scoped_and_forbid_heldout_fields(
    artifacts: dict[str, bytes],
) -> None:
    tasks = _jsonl(artifacts["task_manifest.jsonl"])
    for split_index, split_seed in enumerate(planner.EXPECTED_SEEDS):
        task = tasks[split_index * 5]
        name = f"training_split_{split_seed}.jsonl"
        rows = _jsonl(artifacts[name])
        expected_ids = (
            task["partitions"]["train"]["layout_ids"]
            + task["partitions"]["validation"]["layout_ids"]
        )
        assert [row["layout_id"] for row in rows] == expected_ids
        assert not set(expected_ids) & set(task["partitions"]["test"]["layout_ids"])
        assert task["training_dataset"] == {
            "path": name,
            "sha256": planner.sha256_bytes(artifacts[name]),
        }
        assert {row["schema"] for row in rows} == {planner.TRAINING_ROW_SCHEMA}
        assert all(
            set(row)
            == {
                "family_id",
                "geometry_sha256",
                "layout",
                "layout_id",
                "partition",
                "schema",
                "split_seed",
                "target_fidelity_ids",
                "target_order",
                "target_units",
                "target_values",
            }
            for row in rows
        )
        serialized = artifacts[name].lower()
        assert b"r4" not in serialized
        assert b"evaluation_only" not in serialized


def test_training_artifact_is_invariant_to_heldout_reference_mutation(
    artifacts: dict[str, bytes],
) -> None:
    evaluation = _jsonl(artifacts["evaluation_dataset.jsonl"])
    tasks = _jsonl(artifacts["task_manifest.jsonl"])
    task = tasks[0]
    layouts = {
        row["layout_id"]: row
        for row in planner.load_jsonl(ROOT / "datasets/corpus_v3/layouts.jsonl")
    }
    split = {"partitions": task["partitions"], "split_seed": task["split_seed"]}
    baseline = planner.canonical_jsonl_bytes(
        planner.build_training_rows(split, layouts, evaluation)
    )
    changed = copy.deepcopy(evaluation)
    for layout_id in task["partitions"]["test"]["layout_ids"]:
        changed[layout_id]["training_reference"]["Cps_pF"]["value"] *= 1000.0
        changed[layout_id]["evaluation_only_r4_cps"] = {
            "fidelity_id": "synthetic-heldout-mutation",
            "units": "pF",
            "value": 1e12,
        }
    assert planner.canonical_jsonl_bytes(
        planner.build_training_rows(split, layouts, changed)
    ) == baseline


def test_split_validation_fails_closed_on_membership_tampering() -> None:
    protocol = planner.load_json(planner.DEFAULT_PROTOCOL)
    registry = planner.load_json(
        ROOT / "results/corpus_v4/cps_multifidelity/plan/v1/split_registry.json"
    )
    family_rows = planner.load_jsonl(
        ROOT / "results/corpus_v4/cps_multifidelity/plan/v1/geometry_families.jsonl"
    )
    selection = planner.load_json(
        ROOT / "results/corpus_v4/cps_multifidelity/plan/v1/hf_selection_registry.json"
    )
    family_members = {
        row["family_id"]: set(row["member_layout_ids"]) for row in family_rows
    }
    selected = {row["layout_id"] for row in selection["rows"]}

    tampered = copy.deepcopy(registry)
    tampered["rows"][0]["partitions"]["test"]["layout_ids"][0] = tampered[
        "rows"
    ][0]["partitions"]["train"]["layout_ids"][0]
    with pytest.raises(planner.AccuracyPlanError):
        planner.validate_split_registry(tampered, family_members, selected, protocol)


def test_protocol_validation_rejects_random_or_changed_seed_design() -> None:
    protocol = planner.load_json(planner.DEFAULT_PROTOCOL)
    changed = copy.deepcopy(protocol)
    changed["seeds"]["split"][-1] = 45
    with pytest.raises(planner.AccuracyPlanError, match="5x5"):
        planner.validate_protocol(changed)

    changed = copy.deepcopy(protocol)
    changed["forbidden_actions"]["random_or_regenerated_split"] = False
    with pytest.raises(planner.AccuracyPlanError, match="prohibitions"):
        planner.validate_protocol(changed)


def test_planner_input_resolver_rejects_intermediate_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    payload = real / "input.json"
    payload.write_text("{}\n", encoding="utf-8")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)

    with pytest.raises(planner.AccuracyPlanError, match="traverses a symlink"):
        planner.resolve_repo_file(
            tmp_path,
            {
                "path": "alias/input.json",
                "sha256": planner.sha256_file(payload),
            },
            "fixture input",
        )


def test_materialization_is_non_overwriting_and_check_is_exact(
    artifacts: dict[str, bytes], tmp_path: Path
) -> None:
    out = tmp_path / "plan/v1"
    planner.materialize_plan(out, artifacts)
    planner.materialize_plan(out, artifacts, check=True)
    with pytest.raises(planner.AccuracyPlanError, match="overwrite"):
        planner.materialize_plan(out, artifacts)

    (out / "unexpected.txt").write_text("not admitted\n", encoding="utf-8")
    with pytest.raises(planner.AccuracyPlanError, match="inventory"):
        planner.materialize_plan(out, artifacts, check=True)


def test_cli_check_mode_uses_the_same_deterministic_contract(
    artifacts: dict[str, bytes], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "cli-plan"
    monkeypatch.setattr(planner, "build_artifacts", lambda **_: artifacts)
    monkeypatch.setattr(sys, "argv", ["planner", "--out", str(out)])
    assert planner.main() == 0
    monkeypatch.setattr(sys, "argv", ["planner", "--out", str(out), "--check"])
    assert planner.main() == 0
