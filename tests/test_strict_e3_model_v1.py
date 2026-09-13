"""Synthetic-only tests: no corpus, solver or optimization is executed."""
from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code/models/gnn"))
from gnn_baseline import collate
from strict_e3_ablation_v1 import ScalarDistanceModel, SymmetryNormalizer, make_arms, matched_width, parameter_count


@pytest.fixture(autouse=True)
def small_threads():
    prior = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(prior)


def sample(empty: bool = False) -> dict:
    rng = np.random.default_rng(12)
    nodes = rng.normal(size=(5, 9))
    indices = np.asarray([(i, j) for i in range(5) for j in range(5) if i != j], dtype=np.int64).T
    if empty:
        indices = np.empty((2, 0), dtype=np.int64)
    return {"node_feat": nodes, "edge_feat": rng.normal(size=(indices.shape[1], 7)), "edge_index": indices, "reference_r3": np.array([1., 2., 3., .5])}


def work(empty: bool = False) -> dict:
    raw = sample(empty)
    return SymmetryNormalizer({0: raw}, [0]).transform(raw)


@pytest.mark.parametrize("moving", [False, True])
@pytest.mark.parametrize("determinant", [-1, 1])
@pytest.mark.parametrize("empty", [False, True])
def test_encoded_e3_and_translation(moving, determinant, empty):
    torch.manual_seed(5)
    model = ScalarDistanceModel(16, moving).eval()
    original = work(empty)
    q, _ = np.linalg.qr(np.random.default_rng(91).normal(size=(3, 3)))
    if np.linalg.det(q) * determinant < 0:
        q[:, 0] *= -1
    q = q.astype(np.float32)
    translation = np.array([.7, -1.2, 2.1], dtype=np.float32)
    changed = dict(original)
    changed["node_feat"] = original["node_feat"].copy()
    changed["node_feat"][:, :3] = original["node_feat"][:, :3] @ q.T + translation
    with torch.no_grad():
        y, h, x = model.forward_states(collate([original]))
        yt, ht, xt = model.forward_states(collate([changed]))
    torch.testing.assert_close(yt, y, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(ht, h, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(xt, x @ torch.from_numpy(q).T + torch.from_numpy(translation), rtol=2e-5, atol=2e-6)
    if not moving:
        torch.testing.assert_close(x, torch.from_numpy(original["node_feat"][:, :3]), rtol=0, atol=0)


@pytest.mark.parametrize("moving", [False, True])
def test_permutation_and_batching(moving):
    model = ScalarDistanceModel(16, moving).eval()
    original = work()
    order = np.array([3, 0, 4, 1, 2])
    changed = dict(original)
    changed["node_feat"] = original["node_feat"][order]
    changed["edge_index"] = np.argsort(order)[original["edge_index"]]
    with torch.no_grad():
        base, hidden, coords = model.forward_states(collate([original]))
        output, permhidden, permcoords = model.forward_states(collate([changed]))
        combined = model(collate([original, changed]))
    torch.testing.assert_close(output, base, rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(permhidden, hidden[order], rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(permcoords, coords[order], rtol=2e-5, atol=2e-6)
    torch.testing.assert_close(combined, torch.cat([base, output]), rtol=2e-5, atol=2e-6)


@pytest.mark.parametrize("width", [8, 96, 101])
@pytest.mark.parametrize("layers", [1, 4])
@pytest.mark.parametrize("moving", [False, True])
def test_analytic_parameter_count(width, layers, moving):
    model = ScalarDistanceModel(width, moving, layers)
    assert sum(p.numel() for p in model.parameters()) == parameter_count(width, moving, layers)
    assert model.layers[-1].coord is None
    assert sum(layer.coord is not None for layer in model.layers) == (layers - 1 if moving else 0)


def test_width_selection_consumes_no_random_state():
    state = torch.random.get_rng_state().clone()
    numpy_state = np.random.get_state()
    py_state = random.getstate()
    assert matched_width() == 101
    assert parameter_count(96, True) == 301354
    assert parameter_count(101, False) == 301997
    assert torch.equal(state, torch.random.get_rng_state())
    assert np.array_equal(numpy_state[1], np.random.get_state()[1])
    assert py_state == random.getstate()


def test_seeded_factory_pairs_tensors_and_ignores_previous_rng():
    arms, receipt = make_arms(41, strict_hidden=16)
    torch.rand(33)
    np.random.random(33)
    random.random()
    replay, repeated_receipt = make_arms(41, strict_hidden=16)
    assert receipt == repeated_receipt
    for name in arms:
        for key, value in arms[name].state_dict().items():
            assert torch.equal(value, replay[name].state_dict()[key])
    for key, value in arms["fixed96"].state_dict().items():
        assert torch.equal(value, arms["strict96"].state_dict()[key])
        assert hashlib.sha256(value.numpy().tobytes()).hexdigest() == receipt["shared_tensor_sha256"][key]
    different, _ = make_arms(42, strict_hidden=16)
    assert not torch.equal(arms["strict96"].node_enc[0].weight, different["strict96"].node_enc[0].weight)


def test_every_parameter_has_prediction_gradient():
    model = ScalarDistanceModel(16, True)
    prediction = model(collate([work()]))
    prediction.square().sum().backward()
    for name, parameter in model.named_parameters():
        assert parameter.grad is not None, name
        assert torch.isfinite(parameter.grad).all(), name
        assert torch.any(parameter.grad != 0), name


def test_coincident_nodes_have_finite_backward():
    graph = work()
    graph["node_feat"][:, :3] = 0
    model = ScalarDistanceModel(16, True)
    model(collate([graph])).sum().backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())


def test_normalization_is_train_only_float64_and_inverts_without_clipping():
    raw = sample()
    samples = {0: raw, 1: {"malformed": "held-out must never be read"}}
    normalizer = SymmetryNormalizer(samples, [0])
    changed = SymmetryNormalizer({0: raw, 1: sample(True)}, [0])
    for name, value in normalizer.arrays().items():
        assert value.dtype == np.float64
        np.testing.assert_array_equal(value, changed.arrays()[name])
    indices = raw["edge_index"]
    expected = np.sqrt(np.mean(np.sum((raw["node_feat"][indices[0], :3] - raw["node_feat"][indices[1], :3])**2, axis=1)))
    assert normalizer.coordinate_scale == expected
    np.testing.assert_allclose(normalizer.inverse(normalizer.transform(raw)["y"]), raw["reference_r3"])
    assert (normalizer.inverse(np.full(4, -1e10)) < 0).all()
    assert normalizer.transform(raw)["edge_feat"].shape[1] == 3
    raw_without_label = {k: v for k, v in raw.items() if k != "reference_r3"}
    assert np.array_equal(normalizer.transform(raw_without_label)["y"], np.zeros(4))


def test_normalization_commutes_with_encoded_rigid_transform():
    raw = sample()
    normalizer = SymmetryNormalizer({0: raw}, [0])
    transformed = dict(raw)
    transformed["node_feat"] = raw["node_feat"].copy()
    q = np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., -1.]])
    t = np.array([1., 2., 3.])
    transformed["node_feat"][:, :3] = raw["node_feat"][:, :3] @ q.T + t
    original_work, changed_work = normalizer.transform(raw), normalizer.transform(transformed)
    np.testing.assert_allclose(changed_work["node_feat"][:, :3], original_work["node_feat"][:, :3] @ q.T + t / normalizer.coordinate_scale, atol=2e-7)
    np.testing.assert_array_equal(original_work["node_feat"][:, 3:], changed_work["node_feat"][:, 3:])
    np.testing.assert_array_equal(original_work["edge_feat"], changed_work["edge_feat"])


def test_edgeless_normalization_has_defined_scale_and_floors():
    normalizer = SymmetryNormalizer({0: sample(True)}, [0])
    assert normalizer.coordinate_scale == 1.0
    np.testing.assert_array_equal(normalizer.edge_scale, np.full(3, 1e-6))
    np.testing.assert_array_equal(normalizer.target_scale, np.full(4, 1e-8))
    assert normalizer.transform(sample(True))["edge_feat"].shape == (0, 3)


@pytest.mark.parametrize("ids", [[], [0, 0]])
def test_bad_training_ids_rejected(ids):
    with pytest.raises(ValueError):
        SymmetryNormalizer({0: sample()}, ids)


@pytest.mark.parametrize("bad", [float("nan"), 0., -1.])
def test_bad_training_targets_rejected(bad):
    raw = sample()
    raw["reference_r3"][0] = bad
    with pytest.raises(ValueError):
        SymmetryNormalizer({0: raw}, [0])


def test_edge_vector_columns_do_not_enter_normalized_metadata():
    raw = sample()
    normalizer = SymmetryNormalizer({0: raw}, [0])
    changed = dict(raw)
    changed["edge_feat"] = raw["edge_feat"].copy()
    changed["edge_feat"][:, [0, 2, 3, 4]] *= 1000
    np.testing.assert_array_equal(normalizer.transform(raw)["edge_feat"], normalizer.transform(changed)["edge_feat"])
