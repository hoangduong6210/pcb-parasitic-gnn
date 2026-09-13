"""Design-only regression checks: no fitting, solver execution or result replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "protocols/corpus_v4_strict_e3_fem_v2_design_v1.json"
CONFIG = json.loads(DESIGN.read_text(encoding="utf-8"))


def parameter_count(hidden: int, coordinate_updates: bool) -> int:
    """Independent analytic count for four layers and three moving branches."""
    return 29 * hidden**2 + 61 * hidden + 7 + (
        3 * (hidden**2 + 2 * hidden + 1) if coordinate_updates else 0
    )


def test_design_cannot_authorize_training_or_claims() -> None:
    assert CONFIG["status"] == "implementation_pending"
    assert CONFIG["training_may_start"] is False
    assert CONFIG["claim_eligible"] is False
    assert CONFIG["execution_lock"] is None
    assert CONFIG["lifecycle"]["design_document_is_submission_authority"] is False
    assert set(CONFIG["lifecycle"]["missing_implementation"]) == {
        "pipeline", "sandbox_wrappers", "checkpoint_admission",
        "heldout_finalizer", "archive_replay",
    }


@pytest.mark.parametrize("group", ["upstream", "immutable_reuse_sources"])
def test_hash_only_upstream_bindings(group: str) -> None:
    for relative, digest in CONFIG[group].items():
        path = ROOT / relative
        assert not path.is_symlink()
        assert path.resolve().is_relative_to(ROOT.resolve())
        assert len(digest) == 64
        with path.open("rb") as handle:
            computed = hashlib.sha256()
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                computed.update(block)
        assert computed.hexdigest() == digest, relative


def test_grid_reuses_all_twenty_five_cells() -> None:
    seeds = CONFIG["seeds"]
    assert seeds["split"] == seeds["initialization"] == [40, 41, 42, 43, 44]
    assert seeds["cells"] == 25
    assert seeds["arms_per_cell"] == 3
    assert seeds["required_checkpoints"] == 75
    assert seeds["families_per_split"] == {"train": 46, "validation": 7, "test": 13}
    assert seeds["regenerate_splits"] is False


def test_all_arms_have_only_prediction_active_coordinate_branches() -> None:
    arms = CONFIG["arms"]
    assert set(arms) == {"coordinate_update", "fixed_same_width", "fixed_parameter_matched"}
    for name, arm in arms.items():
        moving = name == "coordinate_update"
        assert arm["layers"] == 4
        assert arm["coordinate_update_layers_zero_based"] == ([0, 1, 2] if moving else [])
        assert arm["parameters"] == parameter_count(arm["hidden"], moving)


def test_matched_width_is_analytic_nearest_without_model_initialization() -> None:
    strict = parameter_count(96, True)
    nearest = min(range(1, 193), key=lambda width: (abs(parameter_count(width, False) - strict), width))
    assert nearest == CONFIG["arms"]["fixed_parameter_matched"]["hidden"] == 101
    assert abs(parameter_count(nearest, False) - strict) / strict < 0.003


def test_symmetry_safe_feature_selection_and_normalization() -> None:
    features, norm = CONFIG["features"], CONFIG["normalization"]
    assert features["coordinate_columns"] == [0, 1, 2]
    assert features["node_scalar_columns"] == [3, 4, 5, 6, 7, 8]
    assert features["edge_scalar_columns"] == [1, 5, 6]
    assert features["raw_layout_regeneration_under_rotation"] is False
    assert norm["fit_partition"] == "train only"
    assert norm["moment_dtype"] == "float64"
    assert norm["population_std_ddof"] == 0
    assert norm["coordinate_centering"] is False
    assert norm["coordinate_per_axis_scaling"] is False
    assert norm["shared_between_arms"] is True
    assert norm["scalar_scale_floor"] == 1e-6
    assert norm["target_scale_floor"] == 1e-8


def test_optimization_matches_existing_fixed_accuracy_budget() -> None:
    upstream = json.loads((ROOT / "protocols/corpus_v4_accuracy_v3.json").read_text())
    for key in ("epochs", "batch_size", "optimizer", "learning_rate", "weight_decay",
                "gradient_clip_norm", "loss", "lr_schedule", "model_selection"):
        assert CONFIG["optimization"][key] == upstream["optimization"][key]
    assert CONFIG["optimization"]["hyperparameter_search_trials"] == 0
    assert CONFIG["optimization"]["refit_train_plus_validation"] is False


def test_initialization_and_minibatch_pairing_are_explicit() -> None:
    initialization = CONFIG["initialization"]
    assert initialization["seed_before_model_construction"] is True
    assert initialization["seed_sources"] == ["python", "numpy", "torch"]
    assert initialization["parameter_search_consumes_training_rng"] is False
    assert initialization["same_batch_order_all_arms"] is True
    assert initialization["interop_threads_set_once_per_process"] is True
    assert "hash and verify" in initialization["same_width_common_state"]


def test_evaluation_direction_and_uncertainty_do_not_overclaim() -> None:
    evaluation = CONFIG["evaluation"]
    assert evaluation["controls_reported"] == ["fixed_same_width", "fixed_parameter_matched"]
    assert "positive favors the fixed control" in evaluation["paired_difference"]
    assert evaluation["resampling"] == {
        "resamples": 10000, "seed": 20260913, "percentiles": [2.5, 97.5],
        "axes": ["split", "initialization"], "paired_draws": True,
        "semantics": "descriptive crossed-axis seed-grid sensitivity interval, not a population confidence interval",
    }
    for key in ("equivalence_conclusion_authorized", "prediction_clipping",
                "accuracy_threshold_is_integrity_gate", "heldout_inference_before_all_checkpoint_admission"):
        assert evaluation[key] is False
    assert evaluation["r4"] == "excluded; no R4 target or evaluation claim"
    assert "contextual" in CONFIG["architecture"]["historical_gnn_role"]


def test_checkpoint_and_replay_gates_are_not_optional() -> None:
    lifecycle = CONFIG["lifecycle"]
    assert "slurm_no_fit_task_private_sandbox_probe" in lifecycle["required_before_training"]
    assert "all_75_numeric_checkpoints" in lifecycle["required_before_heldout"]
    assert "terminal_scheduler_admission" in lifecycle["required_before_heldout"]
    assert "safe_bundle_schema_validation" in lifecycle["required_before_heldout"]
    assert "independent_numerical_replay" in lifecycle["required_before_claim_validation"]
    assert "clean_tracked_replay" in lifecycle["required_before_claim_validation"]
    assert lifecycle["heavy_work_location"] == "SLURM compute nodes only"
