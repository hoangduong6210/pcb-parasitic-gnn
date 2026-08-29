"""Fail-closed contracts for the Corpus V4 accuracy dataset join."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/data"))

from corpus_v4_accuracy_dataset_v3 import (  # noqa: E402
    EXPECTED_PARTITION_LAYOUTS,
    INDUCTANCE_FIDELITY_ID,
    R3_FIDELITY_ID,
    R4_FIDELITY_ID,
    TARGET_NAMES,
    TRAINING_ROW_KEYS,
    TRAINING_ROW_SCHEMA,
    CorpusV4AccuracyDatasetError,
    _load_json,
    _load_jsonl,
    _resolve_input,
    _validate_family_rows,
    _validate_inductance_rows,
    _validate_layout_rows,
    _validate_observation_rows,
    _validate_protocol,
    _validate_selection,
    _validate_splits,
    load_corpus_v4_accuracy_dataset_v3,
    load_training_split_dataset_v3,
)


PROTOCOL_PATH = ROOT / "protocols/corpus_v4_accuracy_v3.json"


@pytest.fixture(scope="session")
def canonical_dataset():
    return load_corpus_v4_accuracy_dataset_v3(ROOT, PROTOCOL_PATH)


@pytest.fixture(scope="session")
def canonical_components():
    protocol = _load_json(PROTOCOL_PATH)
    paths = {
        name: ROOT / record["path"] for name, record in protocol["inputs"].items()
    }
    layouts = _validate_layout_rows(_load_jsonl(paths["layouts"]))
    r3, r4 = _validate_observation_rows(
        _load_jsonl(paths["final_observations"]), layouts
    )
    family_rows = _load_jsonl(paths["geometry_families"])
    members, family_by_layout = _validate_family_rows(family_rows, layouts)
    selection = _load_json(paths["hf_selection_registry"])
    selected = _validate_selection(selection, layouts, family_by_layout, r4)
    splits = _load_json(paths["split_registry"])
    return {
        "family_by_layout": family_by_layout,
        "family_rows": family_rows,
        "layouts": layouts,
        "members": members,
        "r3": r3,
        "r4": r4,
        "selected": selected,
        "selection": selection,
        "splits": splits,
    }


def _training_row(sample, *, partition: str, split_seed: int) -> dict:
    return {
        "family_id": sample.family_id,
        "geometry_sha256": sample.geometry_sha256,
        "layout": dict(sample.layout),
        "layout_id": sample.layout_id,
        "partition": partition,
        "schema": TRAINING_ROW_SCHEMA,
        "split_seed": split_seed,
        "target_fidelity_ids": [
            R3_FIDELITY_ID,
            INDUCTANCE_FIDELITY_ID,
            INDUCTANCE_FIDELITY_ID,
            INDUCTANCE_FIDELITY_ID,
        ],
        "target_order": list(TARGET_NAMES),
        "target_units": ["pF", "nH", "nH", "nH"],
        "target_values": list(sample.training_target_values),
    }


def _write_training_rows(path: Path, rows: list[dict]) -> str:
    payload = "".join(
        json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
        for row in rows
    ).encode("utf-8")
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture
def training_split_fixture(tmp_path: Path, canonical_dataset):
    split = canonical_dataset.splits[40]
    samples = canonical_dataset.sample_by_layout_id()
    train = samples[split.train.layout_ids[0]]
    validation = samples[split.validation.layout_ids[0]]
    test = samples[split.test.layout_ids[0]]
    rows = [
        _training_row(train, partition="train", split_seed=40),
        _training_row(validation, partition="validation", split_seed=40),
    ]
    task_row = {
        "partitions": {
            "train": {
                "family_ids": [train.family_id],
                "layout_ids": [train.layout_id],
            },
            "validation": {
                "family_ids": [validation.family_id],
                "layout_ids": [validation.layout_id],
            },
            "test": {
                "family_ids": [test.family_id],
                "layout_ids": [test.layout_id],
            },
        },
        "split_seed": 40,
    }
    path = tmp_path / "training_split_40.jsonl"
    digest = _write_training_rows(path, rows)
    return {
        "digest": digest,
        "path": path,
        "rows": rows,
        "samples": {"test": test, "train": train, "validation": validation},
        "task_row": task_row,
    }


def test_training_split_loader_accepts_exact_order_hash_membership_and_targets(
    training_split_fixture,
) -> None:
    fixture = training_split_fixture
    loaded = load_training_split_dataset_v3(
        fixture["path"],
        expected_sha256=fixture["digest"],
        task_row=fixture["task_row"],
    )

    train = fixture["samples"]["train"]
    validation = fixture["samples"]["validation"]
    assert loaded.split_seed == 40
    assert loaded.artifact_sha256 == fixture["digest"]
    assert loaded.train_layout_ids == (train.layout_id,)
    assert loaded.validation_layout_ids == (validation.layout_id,)
    assert [sample.layout_id for sample in loaded.samples] == [
        train.layout_id,
        validation.layout_id,
    ]
    assert loaded.samples[0].training_target_values == train.training_target_values
    assert loaded.samples[1].training_target_values == validation.training_target_values
    assert all(
        sample.r3_artifact_sha256 == fixture["digest"] for sample in loaded.samples
    )
    assert all(set(row) == TRAINING_ROW_KEYS for row in fixture["rows"])


@pytest.mark.parametrize("mutation", ("extra", "missing", "schema"))
def test_training_split_loader_rejects_nonexact_row_schema(
    training_split_fixture, mutation: str
) -> None:
    fixture = training_split_fixture
    rows = copy.deepcopy(fixture["rows"])
    if mutation == "extra":
        rows[0]["evaluation_only_r4_cps"] = None
        expected = "key set is not exact"
    elif mutation == "missing":
        del rows[0]["target_units"]
        expected = "key set is not exact"
    else:
        rows[0]["schema"] = "pcb-gnn.corpus-v4-accuracy-training-row.v2"
        expected = "schema or split differs"
    digest = _write_training_rows(fixture["path"], rows)

    with pytest.raises(CorpusV4AccuracyDatasetError, match=expected):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=digest,
            task_row=fixture["task_row"],
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("target_order", ["L_pri_nH", "Cps_pF", "L_sec_nH", "L_mut_nH"], "target order"),
        (
            "target_fidelity_ids",
            [
                R4_FIDELITY_ID,
                INDUCTANCE_FIDELITY_ID,
                INDUCTANCE_FIDELITY_ID,
                INDUCTANCE_FIDELITY_ID,
            ],
            "target fidelity",
        ),
        ("target_units", ["nH", "pF", "nH", "nH"], "target units"),
    ),
)
def test_training_split_loader_rejects_target_order_fidelity_and_units(
    training_split_fixture, field: str, value: list[str], message: str
) -> None:
    fixture = training_split_fixture
    rows = copy.deepcopy(fixture["rows"])
    rows[0][field] = value
    digest = _write_training_rows(fixture["path"], rows)

    with pytest.raises(CorpusV4AccuracyDatasetError, match=message):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=digest,
            task_row=fixture["task_row"],
        )


def test_training_split_loader_rejects_reordered_membership(
    training_split_fixture,
) -> None:
    fixture = training_split_fixture
    rows = list(reversed(copy.deepcopy(fixture["rows"])))
    digest = _write_training_rows(fixture["path"], rows)

    with pytest.raises(CorpusV4AccuracyDatasetError, match="exact ordered"):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=digest,
            task_row=fixture["task_row"],
        )


def test_training_split_loader_rejects_test_partition_and_test_layout(
    training_split_fixture,
) -> None:
    fixture = training_split_fixture
    rows = copy.deepcopy(fixture["rows"])
    rows[1] = _training_row(
        fixture["samples"]["test"], partition="test", split_seed=40
    )
    digest = _write_training_rows(fixture["path"], rows)

    with pytest.raises(CorpusV4AccuracyDatasetError, match="partition is not admitted"):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=digest,
            task_row=fixture["task_row"],
        )


def test_training_split_loader_rejects_overlapping_task_membership(
    training_split_fixture,
) -> None:
    fixture = training_split_fixture
    task_row = copy.deepcopy(fixture["task_row"])
    task_row["partitions"]["test"]["layout_ids"].append(
        fixture["samples"]["train"].layout_id
    )

    with pytest.raises(CorpusV4AccuracyDatasetError, match="intersects held-out"):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=fixture["digest"],
            task_row=task_row,
        )


def test_training_split_loader_rejects_wrong_split_and_hash(
    training_split_fixture,
) -> None:
    fixture = training_split_fixture
    wrong_split_rows = copy.deepcopy(fixture["rows"])
    wrong_split_rows[0]["split_seed"] = 41
    wrong_split_digest = _write_training_rows(fixture["path"], wrong_split_rows)
    with pytest.raises(CorpusV4AccuracyDatasetError, match="schema or split differs"):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256=wrong_split_digest,
            task_row=fixture["task_row"],
        )

    _write_training_rows(fixture["path"], fixture["rows"])
    with pytest.raises(CorpusV4AccuracyDatasetError, match="hash mismatch"):
        load_training_split_dataset_v3(
            fixture["path"],
            expected_sha256="0" * 64,
            task_row=fixture["task_row"],
        )


def test_canonical_loader_keeps_training_and_r4_evaluation_separate(
    canonical_dataset,
) -> None:
    dataset = canonical_dataset
    assert len(dataset.samples) == 1500
    assert [sample.layout_id for sample in dataset.samples] == list(range(1500))
    assert len(dataset.r4_evaluation) == 198
    assert set(dataset.splits) == {40, 41, 42, 43, 44}
    assert dataset.target_fidelity_ids == {
        "Cps_pF": R3_FIDELITY_ID,
        "L_pri_nH": INDUCTANCE_FIDELITY_ID,
        "L_sec_nH": INDUCTANCE_FIDELITY_ID,
        "L_mut_nH": INDUCTANCE_FIDELITY_ID,
        "Cps_pF_evaluation_only": R4_FIDELITY_ID,
    }
    assert not hasattr(dataset.samples[0], "cps_r4_pf")
    assert all(len(sample.training_target_values) == 4 for sample in dataset.samples)
    with pytest.raises(TypeError):
        dataset.r4_evaluation[0] = dataset.r4_evaluation.get(0)  # type: ignore[index]


def test_frozen_splits_are_exact_and_each_has_39_r4_tests(canonical_dataset) -> None:
    for seed, split in canonical_dataset.splits.items():
        assert len(split.train.family_ids) == 46
        assert len(split.validation.family_ids) == 7
        assert len(split.test.family_ids) == 13
        assert len(split.train.layout_ids) == EXPECTED_PARTITION_LAYOUTS[seed]["train"]
        assert (
            len(split.validation.layout_ids)
            == EXPECTED_PARTITION_LAYOUTS[seed]["validation"]
        )
        assert len(split.test.layout_ids) == EXPECTED_PARTITION_LAYOUTS[seed]["test"]
        assert len(split.r4_test_layout_ids) == 39
        assert set(split.r4_test_layout_ids) <= set(split.test.layout_ids)
        assert set(split.r4_test_layout_ids) <= set(canonical_dataset.r4_evaluation)


def test_training_cps_comes_only_from_r3_and_legacy_cps_is_ignored(
    canonical_dataset,
) -> None:
    sample = canonical_dataset.samples[0]
    legacy = json.loads(
        (ROOT / "datasets/corpus_v3/labels.jsonl").read_text().splitlines()[0]
    )
    observations = [
        json.loads(line)
        for line in (
            ROOT / _load_json(PROTOCOL_PATH)["inputs"]["final_observations"]["path"]
        ).read_text().splitlines()
    ]
    r3 = next(
        row
        for row in observations
        if row["layout_id"] == 0 and row["fidelity_id"] == R3_FIDELITY_ID
    )
    assert sample.cps_r3_pf == r3["cps_pf"]
    assert sample.cps_r3_pf != legacy["Cps_pF"]
    assert sample.l_pri_nh == legacy["L_pri_nH"]
    assert sample.l_sec_nh == legacy["L_sec_nH"]
    assert sample.l_mut_nh == legacy["L_mut_nH"]

    key = (0, "a" * 64)
    layouts = {key: {}}
    base = {
        "layout_id": 0,
        "geometry_sha256": "a" * 64,
        "L_pri_nH": 4.0,
        "L_sec_nH": 9.0,
        "L_mut_nH": 3.0,
        "Cps_pF": -999999.0,
    }
    changed = dict(base, Cps_pF="not-even-numeric")
    assert _validate_inductance_rows([base], layouts) == _validate_inductance_rows(
        [changed], layouts
    )


def _small_layout_map() -> dict[tuple[int, str], dict]:
    return {
        (0, "a" * 64): {},
        (1, "b" * 64): {},
    }


def _small_observations() -> list[dict]:
    rows = []
    for layout_id, geometry in ((0, "a" * 64), (1, "b" * 64)):
        rows.append(
            {
                "artifact_result_path": f"results/test/job_{layout_id}/result.json",
                "artifact_result_sha256": f"{layout_id + 1:064x}",
                "cps_pf": 10.0 + layout_id,
                "fidelity_id": R3_FIDELITY_ID,
                "geometry_sha256": geometry,
                "layout_id": layout_id,
                "mesh_nodes": 100 + layout_id,
                "mesh_tetrahedra": 200 + layout_id,
                "relative_residual": 1e-12,
                "system_sha256": f"{layout_id + 11:064x}",
                "units": "pF",
            }
        )
    rows.append(
        {
            "artifact_result_path": "results/test/job_r4/result.json",
            "artifact_result_sha256": "f" * 64,
            "cps_pf": 9.0,
            "fidelity_id": R4_FIDELITY_ID,
            "geometry_sha256": "a" * 64,
            "layout_id": 0,
            "mesh_nodes": 300,
            "mesh_tetrahedra": 600,
            "relative_residual": 1e-12,
            "system_sha256": "e" * 64,
            "units": "pF",
        }
    )
    return rows


def test_cps_observations_join_on_id_and_geometry_and_reject_duplicates() -> None:
    layouts = _small_layout_map()
    valid = _small_observations()
    r3, r4 = _validate_observation_rows(
        valid, layouts, expected_r3=2, expected_r4=1
    )
    assert set(r3) == set(layouts)
    assert set(r4) == {(0, "a" * 64)}

    duplicate = copy.deepcopy(valid)
    duplicate[1] = copy.deepcopy(duplicate[0])
    with pytest.raises(CorpusV4AccuracyDatasetError, match="duplicate Cps"):
        _validate_observation_rows(duplicate, layouts, expected_r3=2, expected_r4=1)

    wrong_geometry = copy.deepcopy(valid)
    wrong_geometry[0]["geometry_sha256"] = "c" * 64
    with pytest.raises(CorpusV4AccuracyDatasetError, match="not a layout"):
        _validate_observation_rows(
            wrong_geometry, layouts, expected_r3=2, expected_r4=1
        )


@pytest.mark.parametrize("bad_value", (True, 0.0, -1.0, float("inf")))
def test_cps_observations_reject_nonpositive_or_nonfinite_values(
    bad_value: object,
) -> None:
    rows = _small_observations()
    rows[0]["cps_pf"] = bad_value
    with pytest.raises(CorpusV4AccuracyDatasetError, match="positive and finite|numeric"):
        _validate_observation_rows(
            rows, _small_layout_map(), expected_r3=2, expected_r4=1
        )


def test_cps_observations_reject_missing_extra_and_wrong_fidelity() -> None:
    valid = _small_observations()
    with pytest.raises(CorpusV4AccuracyDatasetError, match="cardinality"):
        _validate_observation_rows(
            valid[:-1], _small_layout_map(), expected_r3=2, expected_r4=1
        )

    wrong_fidelity = copy.deepcopy(valid)
    wrong_fidelity[-1]["fidelity_id"] = "legacy_cps"
    with pytest.raises(CorpusV4AccuracyDatasetError, match="fidelity or unit"):
        _validate_observation_rows(
            wrong_fidelity, _small_layout_map(), expected_r3=2, expected_r4=1
        )

    extra = copy.deepcopy(valid)
    extra.append(dict(extra[-1], layout_id=1, geometry_sha256="b" * 64))
    with pytest.raises(CorpusV4AccuracyDatasetError, match="cardinality"):
        _validate_observation_rows(
            extra, _small_layout_map(), expected_r3=2, expected_r4=1
        )


def test_inductance_join_rejects_hash_mismatch_duplicate_and_passivity() -> None:
    layouts = _small_layout_map()
    labels = [
        {
            "layout_id": layout_id,
            "geometry_sha256": geometry,
            "L_pri_nH": 4.0,
            "L_sec_nH": 9.0,
            "L_mut_nH": 3.0,
        }
        for layout_id, geometry in ((0, "a" * 64), (1, "b" * 64))
    ]
    assert len(_validate_inductance_rows(labels, layouts)) == 2

    mismatch = copy.deepcopy(labels)
    mismatch[0]["geometry_sha256"] = "c" * 64
    with pytest.raises(CorpusV4AccuracyDatasetError, match="not a layout"):
        _validate_inductance_rows(mismatch, layouts)

    duplicate = copy.deepcopy(labels)
    duplicate[1] = copy.deepcopy(duplicate[0])
    with pytest.raises(CorpusV4AccuracyDatasetError, match="duplicate inductance"):
        _validate_inductance_rows(duplicate, layouts)

    nonpassive = copy.deepcopy(labels)
    nonpassive[0]["L_mut_nH"] = 7.0
    with pytest.raises(CorpusV4AccuracyDatasetError, match="passivity"):
        _validate_inductance_rows(nonpassive, layouts)


def test_family_registry_identity_is_recomputed_from_layouts(
    canonical_components,
) -> None:
    tampered = copy.deepcopy(canonical_components["family_rows"])
    tampered[0]["family_id"] = "turns-00-00"
    tampered[0]["lower_turn_count"] = 0
    tampered[0]["upper_turn_count"] = 0
    with pytest.raises(CorpusV4AccuracyDatasetError, match="family identity"):
        _validate_family_rows(tampered, canonical_components["layouts"])


def test_r4_selection_must_equal_observations_and_remain_balanced(
    canonical_components,
) -> None:
    tampered = copy.deepcopy(canonical_components["selection"])
    tampered["rows"][0]["geometry_sha256"] = "0" * 64
    with pytest.raises(CorpusV4AccuracyDatasetError, match="selection identity"):
        _validate_selection(
            tampered,
            canonical_components["layouts"],
            canonical_components["family_by_layout"],
            canonical_components["r4"],
        )


def test_split_registry_rejects_duplicates_and_wrong_r4_test_count(
    canonical_components,
) -> None:
    duplicate = copy.deepcopy(canonical_components["splits"])
    train_ids = duplicate["rows"][0]["partitions"]["train"]["layout_ids"]
    train_ids[1] = train_ids[0]
    with pytest.raises(CorpusV4AccuracyDatasetError, match="count or type"):
        _validate_splits(
            duplicate,
            canonical_components["members"],
            canonical_components["selected"],
        )

    seed40 = canonical_dataset_r4_seed40(canonical_components)
    incomplete_r4 = set(canonical_components["selected"])
    incomplete_r4.remove(seed40)
    with pytest.raises(CorpusV4AccuracyDatasetError, match="exactly 39"):
        _validate_splits(
            canonical_components["splits"],
            canonical_components["members"],
            incomplete_r4,
        )


def canonical_dataset_r4_seed40(canonical_components) -> int:
    test_ids = set(
        canonical_components["splits"]["rows"][0]["partitions"]["test"][
            "layout_ids"
        ]
    )
    return next(iter(test_ids & canonical_components["selected"]))


def test_protocol_rejects_legacy_cps_or_r4_training_permission() -> None:
    protocol = _load_json(PROTOCOL_PATH)
    _validate_protocol(protocol)

    legacy = copy.deepcopy(protocol)
    legacy["forbidden_actions"]["legacy_cps_as_training_target"] = False
    with pytest.raises(CorpusV4AccuracyDatasetError, match="not frozen"):
        _validate_protocol(legacy)

    r4_training = copy.deepcopy(protocol)
    r4_training["forbidden_actions"]["r4_in_optimization"] = False
    with pytest.raises(CorpusV4AccuracyDatasetError, match="not frozen"):
        _validate_protocol(r4_training)


def test_input_path_requires_repository_relative_exact_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    import hashlib

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert _resolve_input(
        tmp_path, {"path": "artifact.json", "sha256": digest}, "fixture"
    ) == artifact

    with pytest.raises(CorpusV4AccuracyDatasetError, match="hash-mismatched"):
        _resolve_input(
            tmp_path, {"path": "artifact.json", "sha256": "0" * 64}, "fixture"
        )
    with pytest.raises(CorpusV4AccuracyDatasetError, match="unsafe"):
        _resolve_input(
            tmp_path, {"path": "../artifact.json", "sha256": digest}, "fixture"
        )
