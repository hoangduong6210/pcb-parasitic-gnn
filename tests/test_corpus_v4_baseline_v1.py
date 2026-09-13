"""Synthetic, solver-free contracts for the separately versioned FEM-v2 baseline study."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
for directory in ("code/experiments/proofs", "code/models", "code/core"):
    sys.path.insert(0, str(ROOT / directory))

import corpus_v4_baseline_v1 as baseline  # noqa: E402


def normalization() -> dict[str, np.ndarray]:
    return {"norm.node_mean": np.zeros(9), "norm.node_scale": np.ones(9),
            "norm.edge_mean": np.zeros(7), "norm.edge_scale": np.ones(7),
            "norm.target_log1p_mean": np.log1p(np.arange(1., 5.)),
            "norm.target_log1p_scale": np.ones(4)}


def graph_sample() -> dict:
    nf, ef, ei = baseline.build_graph_from_planar_layout(small_layout()).to_feature_matrices()
    return {"node_feat": nf, "edge_feat": ef, "edge_index": ei,
            "reference_r3": np.arange(1., 5.), "family_id": "family_a"}


def test_pooling_is_48d_permutation_invariant_and_ignores_metadata() -> None:
    sample = graph_sample()
    original = baseline.features(sample, normalization())
    changed = copy.deepcopy(sample)
    changed["node_feat"] = changed["node_feat"][::-1]
    changed["edge_feat"] = changed["edge_feat"][::-1]
    changed.update({"reference_r3": np.full(4, np.nan), "family_id": "other",
                    "layout_id": 999999, "split": "test", "solver_wall_seconds": 1.e20})
    assert original.shape == (48,)
    np.testing.assert_allclose(original, baseline.features(changed, normalization()))
    block = np.array([[-3., 4.], [1., -1.]])
    np.testing.assert_allclose(baseline.pooled(block), [-1., 1.5, 1., 4., -np.log(3), np.log(4)])


def test_empty_edges_have_zero_21_feature_tail() -> None:
    sample = graph_sample()
    sample["edge_feat"] = np.empty((0, 7))
    features = baseline.features(sample, normalization())
    assert features.shape == (48,)
    np.testing.assert_array_equal(features[-21:], np.zeros(21))


@pytest.mark.parametrize("block", [np.zeros((1, 8)), np.zeros(9), np.full((1, 9), np.nan)])
def test_malformed_node_features_rejected(block: np.ndarray) -> None:
    sample = graph_sample()
    sample["node_feat"] = block
    with pytest.raises(ValueError):
        baseline.features(sample, normalization())


def test_node_edge_and_target_normalization_uses_training_only() -> None:
    samples = {0: graph_sample(), 1: graph_sample(), 2: graph_sample()}
    samples[1]["node_feat"] *= 2
    samples[1]["edge_feat"] *= 3
    samples[1]["reference_r3"] *= 4
    before = baseline.TrainOnlyNormalizer(samples, [0, 1]).arrays()
    for key in ("node_feat", "edge_feat", "reference_r3"):
        samples[2][key][:] = np.nan
    after = baseline.TrainOnlyNormalizer(samples, [0, 1]).arrays()
    for key in before:
        np.testing.assert_array_equal(before[key], after[key])
    np.testing.assert_allclose(before["norm.target_log1p_mean"], np.log1p(np.stack([samples[i]["reference_r3"] for i in (0, 1)])).mean(axis=0))
    np.testing.assert_allclose(before["norm.node_mean"], np.concatenate([samples[i]["node_feat"] for i in (0, 1)]).mean(axis=0), rtol=1e-6)
    with pytest.raises(ValueError, match="empty"):
        baseline.TrainOnlyNormalizer(samples, [])


@pytest.fixture
def tiny_packed_forest() -> tuple[dict, np.ndarray, np.ndarray]:
    """Fit a single four-row depth-one test tree, then repeat its numeric topology."""
    from sklearn.tree import DecisionTreeRegressor
    x = np.zeros((4, 48))
    x[:, 0] = [-2., -1., 1., 2.]
    y = np.array([[1., 2., 3., 4.], [1., 2., 3., 4.], [5., 6., 7., 8.], [5., 6., 7., 8.]])
    tree = DecisionTreeRegressor(max_depth=1, random_state=42).fit(x, y)
    arrays = baseline.pack_forest(SimpleNamespace(estimators_=[tree] * 500), "random_forest")
    return arrays, x, tree.predict(x)


def test_numeric_forest_inference_matches_sklearn(tiny_packed_forest: tuple) -> None:
    arrays, x, expected = tiny_packed_forest
    np.testing.assert_allclose(baseline.forest_predict(arrays, "random_forest", x), expected, rtol=0, atol=0)
    assert all(array.dtype.kind != "O" for array in arrays.values())


@pytest.mark.parametrize("mutation", ["tree_count", "cycle", "bad_feature", "nan_value", "float_children", "duplicate_parent"])
def test_malformed_numeric_forest_rejected(tiny_packed_forest: tuple, mutation: str) -> None:
    arrays, x, _ = tiny_packed_forest
    arrays = {name: value.copy() for name, value in arrays.items()}
    if mutation == "tree_count":
        arrays["random_forest.offsets"] = arrays["random_forest.offsets"][:-1]
    elif mutation == "cycle":
        arrays["random_forest.children_left"][0] = 0
    elif mutation == "bad_feature":
        arrays["random_forest.feature"][0] = 48
    elif mutation == "nan_value":
        arrays["random_forest.value"][0, 0] = np.nan
    elif mutation == "float_children":
        arrays["random_forest.children_left"] = arrays["random_forest.children_left"].astype(float)
    else:
        arrays["random_forest.children_right"][0] = arrays["random_forest.children_left"][0]
    with pytest.raises(ValueError):
        baseline.forest_predict(arrays, "random_forest", x)


def test_constant_is_logspace_training_mean_and_negative_prediction_not_clipped() -> None:
    arrays = normalization()
    x = np.zeros((3, 48))
    np.testing.assert_allclose(baseline.predict(arrays, "constant", x), np.tile(np.arange(1., 5.), (3, 1)))
    arrays.update({"ridge.coef": np.zeros((4, 48)), "ridge.intercept": np.full(4, -10.)})
    assert (baseline.predict(arrays, "ridge", x) < 0).all()
    with pytest.raises(ValueError):
        baseline.predict(arrays, "unknown", x)


@pytest.mark.parametrize("path", ["../escape.json", "/tmp/escape.json", "results/../../escape.json"])
def test_artifact_paths_reject_escape(path: str) -> None:
    with pytest.raises(ValueError):
        baseline.checked_path(path)


def metric_grid() -> list[dict]:
    return [{"task_id": task, "split_seed": 40 + task // 5, "init_seed": 40 + task % 5,
             "model": model, "target": target,
             "metrics": {"family_macro_mape_pct": 3.},
             "gnn_metrics": {"family_macro_mape_pct": 2.},
             "paired_family_macro_mape_difference_pp": 1.}
            for model in baseline.MODELS for target in baseline.TARGETS for task in range(25)]


def test_metric_summary_sign_and_deterministic_replicates() -> None:
    summary = baseline.summarize(metric_grid())
    for model in baseline.MODELS:
        entry = summary["models"][model][baseline.TARGETS[0]]
        assert entry["mean_paired_difference_pp"] == 1.
        assert entry["mean_family_macro_mape_pct"] == 3.
        assert entry["deterministic_model_repeated_initializations"] == (model in ("constant", "ridge"))
        assert entry["cells_better_than_gnn"] == 0
    assert summary["split_panels_independent"] is False


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_pair_delta", "wrong_seed"])
def test_metric_summary_rejects_inconsistent_grid(mutation: str) -> None:
    grid = metric_grid()
    if mutation == "missing":
        grid.pop()
    elif mutation == "duplicate":
        grid[1] = copy.deepcopy(grid[0])
    elif mutation == "wrong_pair_delta":
        grid[0]["paired_family_macro_mape_difference_pp"] = -10.
    else:
        grid[0]["split_seed"] = 999
    with pytest.raises(ValueError):
        baseline.summarize(grid)


@pytest.mark.parametrize("coverage", [list(range(24)), list(range(26)), [0] * 25, list(reversed(range(25)))])
def test_accepted_set_requires_exact_ordered_25_cells(monkeypatch: pytest.MonkeyPatch, coverage: list) -> None:
    args = SimpleNamespace(accepted_set=Path("unused.json"), expected_accepted_set_sha256="a" * 64,
                           expected_protocol_sha256="b" * 64, expected_execution_lock_sha256="c" * 64,
                           expected_source_git_head="d" * 40)
    payload = {"bindings": baseline.bindings(args), "heldout_inference_permitted": True,
               "accepted": [{"task_id": task} for task in coverage]}
    monkeypatch.setattr(baseline, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(baseline, "load_json", lambda _path: payload)
    with pytest.raises(ValueError, match="25"):
        baseline.accepted_tasks(args, {}, [])


def test_accepted_set_external_hash_checked_before_deserialization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "sha256_file", lambda _path: "b" * 64)
    monkeypatch.setattr(baseline, "load_json", lambda _path: pytest.fail("unverified accepted set was deserialized"))
    with pytest.raises(ValueError, match="hash"):
        baseline.accepted_tasks(SimpleNamespace(accepted_set=Path("unused"), expected_accepted_set_sha256="a" * 64), {}, [])


def test_terminal_receipt_rejects_restart_before_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = {"job_id": "123"}
    def accounting(argv: list, **_kwargs: object) -> SimpleNamespace:
        fields = argv[-1].removeprefix("--format=").split(",")
        row = {"JobIDRaw": "123", "Restarts": "1", "Partition": "nextgen", "Timelimit": "04:00:00"}
        return SimpleNamespace(stdout="|".join(row.get(field, "") for field in fields) + "\n")
    monkeypatch.setattr(baseline.subprocess, "run", accounting)
    with pytest.raises(ValueError, match="restart"):
        baseline.terminal(scheduler, "training")


def test_protocol_external_hash_fails_before_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    args = SimpleNamespace(protocol=Path("unused_protocol"), execution_lock=Path("unused_lock"),
                           expected_protocol_sha256="a" * 64, expected_execution_lock_sha256="b" * 64)
    monkeypatch.setattr(baseline, "sha256_file", lambda _path: "c" * 64)
    monkeypatch.setattr(baseline, "load_json", lambda _path: pytest.fail("unverified protocol was loaded"))
    with pytest.raises(ValueError, match="hash"):
        baseline.context(args)


def test_load_arrays_rejects_invented_array_schema_before_npz_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "load_safe_npz_bundle", lambda *_a, **_kw: pytest.fail("invalid schema reached NPZ loader"))
    with pytest.raises(ValueError, match="schema"):
        baseline.load_arrays(Path("unused/result.json"), {"bundle_specs": {"executable_pickle": {}}})


def test_safe_baseline_bundle_roundtrip_and_corrupt_npz_rejection(tmp_path: Path, tiny_packed_forest: tuple) -> None:
    arrays, x, expected = tiny_packed_forest
    arrays.update({name.replace("random_forest.", "extra_trees."): value.copy() for name, value in list(arrays.items())})
    arrays.update(normalization())
    arrays.update({"norm.pooled_mean": np.zeros(48), "norm.pooled_scale": np.ones(48),
                   "ridge.coef": np.zeros((4, 48)), "ridge.intercept": np.zeros(4)})
    specs = {name: baseline.ArraySpec(value.dtype.str, value.shape) for name, value in arrays.items()}
    result = {"bindings": {"test": "synthetic"}, "task": baseline.canonical_task_row(0),
              "bundle_specs": {name: spec.to_json() for name, spec in specs.items()}}
    baseline.write_safe_npz_bundle(tmp_path / "bundle", arrays=arrays, specs=specs,
                                  payload={"bindings": result["bindings"], "task": result["task"], "models": list(baseline.MODELS)})
    result["files"] = {name: baseline.sha256_file(tmp_path / name) for name in ("bundle/metadata.json", "bundle/weights_and_norm.npz")}
    loaded = baseline.load_arrays(tmp_path / "result.json", result)
    np.testing.assert_array_equal(baseline.forest_predict(loaded, "random_forest", x), expected)
    archive = tmp_path / "bundle/weights_and_norm.npz"
    archive.write_bytes(archive.read_bytes() + b"corruption")
    with pytest.raises(ValueError):
        baseline.load_arrays(tmp_path / "result.json", result)


def test_task_rejects_scheduler_cell_mismatch_before_checkpoint_access(monkeypatch: pytest.MonkeyPatch) -> None:
    args = SimpleNamespace(expected_protocol_sha256="a" * 64, expected_execution_lock_sha256="b" * 64,
                           expected_source_git_head="c" * 40)
    row = {"training_dataset": {"path": "training_split_40.jsonl", "sha256": "d" * 64}}
    lock = {"source_sha256": {}, "runtime": {}}
    result = {"bindings": baseline.bindings(args), "task": baseline.canonical_task_row(0),
              "source_sha256": {}, "runtime": {}, "heldout_bytes_opened": False, "training_started": True,
              "sandbox": {"filesystem_boundary_passed": True},
              "scheduler": {"array_task_id": 1, "array_job_id": "123", "job_id": "456"},
              "training_dataset": {"path": f"{baseline.PLAN}/training_split_40.jsonl", "sha256": "d" * 64},
              "files": {"bundle/metadata.json": "e" * 64, "bundle/weights_and_norm.npz": "f" * 64}}
    monkeypatch.setattr(baseline, "load_json", lambda _p: result)
    with pytest.raises(ValueError, match="task|scheduler|cell"):
        baseline.check_task(args, Path("unused/task_00/result.json"), 0, lock, [row])


def test_artifact_symlink_ancestor_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    (tmp_path / "real").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        baseline.checked_path("alias/result.json")


@pytest.mark.parametrize("mutation", ["trees", "ridge_alpha", "task_count", "clipping", "heldout", "feature_dim"])
def test_protocol_configuration_mutations_rejected(mutation: str) -> None:
    protocol = json.loads((ROOT / baseline.PROTOCOL).read_text())
    baseline.validate_protocol_config(protocol)
    if mutation == "trees":
        protocol["models"]["random_forest"]["n_estimators"] = 10
    elif mutation == "ridge_alpha":
        protocol["models"]["ridge"]["alpha"] = .01
    elif mutation == "task_count":
        protocol["seeds"]["tasks"] = 24
    elif mutation == "clipping":
        protocol["evaluation"]["prediction_clipping"] = True
    elif mutation == "heldout":
        protocol["evaluation"]["heldout_inference_before_all_checkpoint_admission"] = True
    else:
        protocol["features"]["pooled_dim"] = 49
    with pytest.raises(ValueError):
        baseline.validate_protocol_config(protocol)


def test_evaluate_does_not_materialize_heldout_before_complete_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    def rejected(*_args: object) -> None:
        raise ValueError("synthetic checkpoint rejected")
    monkeypatch.setattr(baseline, "accepted_tasks", rejected)
    monkeypatch.setattr(baseline, "load_jsonl", lambda *_args: pytest.fail("heldout materialized before admission"))
    with pytest.raises(ValueError, match="checkpoint rejected"):
        baseline.evaluate(SimpleNamespace(), {}, [])


def test_checkpoint_safe_schema_and_topology_validated_before_task_admitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    tmp_path = tmp_path / baseline.BASE / "jobs/job_123/task_00"
    tmp_path.mkdir(parents=True)
    args = SimpleNamespace(expected_protocol_sha256="a" * 64, expected_execution_lock_sha256="b" * 64,
                           expected_source_git_head="c" * 40)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for path in (tmp_path / "result.json", bundle / "metadata.json", bundle / "weights_and_norm.npz"):
        path.write_text("synthetic fixture")
    row = {"training_dataset": {"path": "training_split_40.jsonl", "sha256": "d" * 64}}
    result = {"bindings": baseline.bindings(args), "task": baseline.canonical_task_row(0),
              "source_sha256": {}, "runtime": {}, "heldout_bytes_opened": False, "training_started": True,
              "sandbox": {"filesystem_boundary_passed": True}, "scheduler": {"array_job_id": "123"},
              "training_dataset": {"path": f"{baseline.PLAN}/training_split_40.jsonl", "sha256": "d" * 64},
              "files": {name: baseline.sha256_file(tmp_path / name) for name in ("bundle/metadata.json", "bundle/weights_and_norm.npz")}}
    monkeypatch.setattr(baseline, "load_json", lambda _p: result)
    monkeypatch.setattr(baseline, "validate_scheduler_receipt", lambda *_a, **_kw: None)
    def reject_arrays(*_a: object, **_kw: object) -> None:
        raise ValueError("malformed checkpoint schema")
    monkeypatch.setattr(baseline, "load_arrays", reject_arrays)
    with pytest.raises(ValueError, match="malformed checkpoint schema"):
        baseline.check_task(args, tmp_path / "result.json", 0, {"source_sha256": {}, "runtime": {}}, [row])
    monkeypatch.setattr(baseline, "load_arrays", lambda *_a: {})
    def reject_tree(*_a: object, **_kw: object) -> None:
        raise ValueError("malformed topology")
    monkeypatch.setattr(baseline, "forest_predict", reject_tree)
    with pytest.raises(ValueError, match="malformed topology"):
        baseline.check_task(args, tmp_path / "result.json", 0, {"source_sha256": {}, "runtime": {}}, [row])


def test_crossed_axis_paired_interval_matches_independent_reconstruction() -> None:
    grid = metric_grid()
    for row in grid:
        delta = float(row["split_seed"] - 42) + .25 * (row["init_seed"] - 42)
        row["paired_family_macro_mape_difference_pp"] = delta
        row["metrics"]["family_macro_mape_pct"] = 10. + delta
        row["gnn_metrics"]["family_macro_mape_pct"] = 10.
    summary = baseline.summarize(grid)
    rng = np.random.default_rng(20260913)
    s = rng.integers(0, 5, (10000, 5))
    i = rng.integers(0, 5, (10000, 5))
    # Additive crossed effects make this independent of the implementation's indexing.
    bootstrap = (s - 2).mean(axis=1) + .25 * (i - 2).mean(axis=1)
    expected = np.quantile(bootstrap, [.025, .975], method="linear")
    for model in baseline.MODELS:
        np.testing.assert_allclose(summary["models"][model][baseline.TARGETS[0]]["paired_difference_crossed_axis_95pct_interval_pp"], expected)
    assert summary["resampling"]["resamples"] == 10000
    assert "not a population" in summary["resampling"]["semantics"]


def test_passivity_diagnostic_reports_without_repairing_or_dropping() -> None:
    prediction = np.array([[1., 4., 9., 6.], [1., 4., 9., -6.],
                           [1., 4., 9., 7.], [1., -4., -9., 0.], [-1., 4., 9., 1.]])
    original = prediction.copy()
    result = baseline.passivity_diagnostic(prediction)
    assert result["n_samples"] == 5
    assert result["n_inductance_psd_violations"] == 2
    assert result["inductance_psd_violation_rate_pct"] == 40.
    assert result["predictions_repaired"] is False
    assert result["integrity_gate"] is False
    np.testing.assert_array_equal(prediction, original)
    with pytest.raises(ValueError):
        baseline.passivity_diagnostic(np.full((1, 4), np.nan))


def test_verify_rejects_extra_analysis_file_before_numerical_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    folder = tmp_path / "job_123"
    folder.mkdir()
    for name in ("ANALYSIS_MANIFEST.json", "summary.json", "metrics.json", "predictions.jsonl", "unexpected.txt"):
        (folder / name).write_text("fixture")
    args = SimpleNamespace(analysis_manifest=folder / "ANALYSIS_MANIFEST.json", expected_analysis_manifest_sha256="a" * 64,
                           expected_protocol_sha256="b" * 64, expected_execution_lock_sha256="c" * 64,
                           expected_source_git_head="d" * 40)
    monkeypatch.setattr(baseline, "context", lambda *_a: ({}, {}, []))
    monkeypatch.setattr(baseline, "execution", lambda *_a: {})
    monkeypatch.setattr(baseline, "sha256_file", lambda _a: "a" * 64)
    monkeypatch.setattr(baseline, "load_json", lambda _a: {"bindings": baseline.bindings(args),
                         "files": {name: "a" * 64 for name in ("summary.json", "metrics.json", "predictions.jsonl")}})
    monkeypatch.setattr(baseline, "evaluate", lambda *_a: pytest.fail("extra file reached numerical replay"))
    with pytest.raises(ValueError, match="inventory"):
        baseline.verify(args)


def test_current_source_mutation_fails_before_runtime_or_input_access(monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = json.loads((ROOT / baseline.PROTOCOL).read_text())
    args = SimpleNamespace(protocol=Path("protocol.json"), execution_lock=Path("lock.json"),
                           expected_protocol_sha256="a" * 64, expected_execution_lock_sha256="b" * 64)
    lock = {"protocol_sha256": "a" * 64, "source_sha256": {name: "c" * 64 for name in baseline.SOURCES}}
    monkeypatch.setattr(baseline, "load_json", lambda path: protocol if path == args.protocol else lock)
    monkeypatch.setattr(baseline, "sha256_file", lambda path: "a" * 64 if path == args.protocol else ("b" * 64 if path == args.execution_lock else "d" * 64))
    monkeypatch.setattr(baseline, "runtime", lambda: pytest.fail("mutated source reached execution runtime"))
    with pytest.raises(ValueError, match="source mismatch"):
        baseline.context(args)


def test_training_namespace_requires_explicit_isolation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    protocol = json.loads((ROOT / baseline.PROTOCOL).read_text())
    monkeypatch.delenv("PCB_GNN_V4_ACCURACY_V3_SANDBOX_ACTIVE", raising=False)
    with pytest.raises(SystemExit, match="sandbox"):
        baseline._validate_training_sandbox(protocol, {})


def test_verify_original_symlink_argument_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    folder = tmp_path / "real"
    folder.mkdir()
    (folder / "ANALYSIS_MANIFEST.json").write_text("fixture")
    (tmp_path / "alias").symlink_to(folder, target_is_directory=True)
    args = SimpleNamespace(analysis_manifest=tmp_path / "alias/ANALYSIS_MANIFEST.json",
                           expected_analysis_manifest_sha256="a" * 64)
    monkeypatch.setattr(baseline, "context", lambda *_a: ({}, {}, []))
    monkeypatch.setattr(baseline, "execution", lambda *_a: {})
    monkeypatch.setattr(baseline, "load_json", lambda *_a: pytest.fail("symlink alias reached manifest deserialize"))
    with pytest.raises(ValueError, match="symlink|canonical"):
        baseline.verify(args)


@pytest.mark.parametrize(
    ("relative_path", "digest"),
    [
        ("protocols/corpus_v4_accuracy_execution_lock_v3r2.json", "8f70369457382ab1d4066e194b2f4664813ece98deb514628ead27fb365c5e8c"),
        ("protocols/corpus_v4_latency_fem_v2_execution_lock_v1.json", "b5ee0844267f261f7766bd1fb4265f8cf93da55f4194bcd67f81d38ada6061e5"),
        ("protocols/corpus_v4_accuracy_v3.json", "d4930c2e67e8c366466b8f847d71323b87ea33cce9a0b97644bbac550c7c0af1"),
    ],
)
def test_predecessor_scientific_roots_are_immutable(relative_path: str, digest: str) -> None:
    assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == digest


def small_layout() -> dict:
    """Two valid active legs; no solver labels or corpus content are required."""
    return {
        "geometry_schema": "pcb-planar-active-legs.v3",
        "board_w_mm": 30.0,
        "board_h_mm": 10.0,
        "n_layers": 2,
        "eps_r": 4.2,
        "stackup": {"layer_pitch_mm": 0.18, "layer_z0_mm": 0.05},
        "design_rules": {"same_layer_clearance_mm": 0.20, "board_edge_margin_mm": 0.0},
        "traces": [
            {"trace_id": "pri_000", "net": "pri", "layer": 0, "x0": 2.0, "y0": 2.0,
             "length_mm": 20.0, "width_mm": 2.0, "thick_mm": 0.035,
             "current_sign": 1, "segment_role": "active_leg", "turn_index": 0},
            {"trace_id": "sec_000", "net": "sec", "layer": 1, "x0": 3.0, "y0": 5.0,
             "length_mm": 18.0, "width_mm": 2.0, "thick_mm": 0.035,
             "current_sign": 1, "segment_role": "active_leg", "turn_index": 0},
        ],
    }


def test_training_wrapper_requires_pinned_environment_before_any_action() -> None:
    script = ROOT / "code/jobs/submit_corpus_v4_baseline_v1.sh"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PCB_GNN_BASELINE_")}
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert "PCB_GNN_BASELINE_ROOT" in result.stderr


def test_training_wrapper_has_narrow_task_and_training_only_mounts() -> None:
    script = (ROOT / "code/jobs/submit_corpus_v4_baseline_v1.sh").read_text()
    assert subprocess.run(["bash", "-n", str(ROOT / "code/jobs/submit_corpus_v4_baseline_v1.sh")]).returncode == 0
    for setting in ("--array=0-24%5", "--partition=nextgen", "--cpus-per-task=8", "--mem=48G", "--time=04:00:00"):
        assert "#SBATCH " + setting in script
    assert '--bind "$EXECUTION_ROOT/$TASK_RELATIVE" "/workspace/$TASK_RELATIVE"' in script
    assert '--ro-bind "$PLAN_ROOT/training_split_${SPLIT_SEED}.jsonl"' in script
    assert "evaluation_dataset.jsonl" not in script
    assert '--ro-bind "$EXECUTION_ROOT" /workspace' not in script
    assert '--ro-bind "$PLAN_ROOT" ' not in script
    assert "/usr/bin/env -i" in script
    assert "OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8" in script
    assert "--probe-only" in script
    assert '"$SLURM_ARRAY_TASK_COUNT" == 1' in script
