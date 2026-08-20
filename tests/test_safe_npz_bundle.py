"""Security and deterministic-roundtrip contracts for safe NPZ bundles."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/inference"))

import safe_npz_bundle as bundle_module  # noqa: E402
from safe_npz_bundle import (  # noqa: E402
    ARCHIVE_NAME,
    METADATA_NAME,
    ArraySpec,
    BundleLimits,
    SafeBundleError,
    load_safe_npz_bundle,
    sha256_file,
    write_safe_npz_bundle,
)


SMOKE_INPUT = np.asarray([[0.25, -0.5], [1.5, 0.75]], dtype=np.float32)
SMOKE_INPUT_SHA256 = hashlib.sha256(SMOKE_INPUT.tobytes(order="C")).hexdigest()
PAYLOAD = {
    "architecture": {
        "edge_dim": 7,
        "hidden": 2,
        "n_layers": 1,
        "n_targets": 2,
        "node_dim": 9,
    },
    "format_role": "PCBParasiticGNN state_dict and train-only normalization",
    "targets": ["Cps_pF", "L_pri_nH"],
}


def fixture_arrays() -> dict[str, np.ndarray]:
    return {
        "norm_nfs": np.asarray([1.0, 2.0], dtype=np.float32),
        "norm_ys": np.asarray([0.5, 1.5], dtype=np.float64),
        "state__readout.bias": np.asarray([0.1, -0.2], dtype=np.float32),
        "state__readout.weight": np.asarray(
            [[1.0, 2.0], [-0.5, 0.25]], dtype=np.float32
        ),
    }


def fixture_specs() -> dict[str, ArraySpec]:
    return {
        "norm_nfs": ArraySpec("float32", (2,), strictly_positive=True),
        "norm_ys": ArraySpec("float64", (2,), strictly_positive=True),
        "state__readout.bias": ArraySpec("float32", (2,)),
        "state__readout.weight": ArraySpec("float32", (2, 2)),
    }


def smoke_hook(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    weight = arrays["state__readout.weight"]
    bias = arrays["state__readout.bias"]
    prediction = SMOKE_INPUT @ weight.T + bias
    return {"prediction": np.asarray(prediction, dtype=np.float32)}


def write_fixture(path: Path) -> dict[str, str]:
    return write_safe_npz_bundle(
        path,
        arrays=fixture_arrays(),
        specs=fixture_specs(),
        payload=PAYLOAD,
        smoke_hook=smoke_hook,
        smoke_input_sha256=SMOKE_INPUT_SHA256,
        smoke_rtol=0.0,
        smoke_atol=0.0,
    )


def load_fixture(path: Path, hashes: dict[str, str], **kwargs: object):
    options = {
        "expected_metadata_sha256": hashes[METADATA_NAME],
        "expected_specs": fixture_specs(),
        "expected_payload": PAYLOAD,
        "smoke_hook": smoke_hook,
        "expected_smoke_input_sha256": SMOKE_INPUT_SHA256,
        "require_smoke": True,
    }
    options.update(kwargs)
    return load_safe_npz_bundle(path, **options)


def canonical_metadata_bytes(value: dict[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def rewrite_metadata(path: Path, mutate) -> str:
    metadata_path = path / METADATA_NAME
    metadata = json.loads(metadata_path.read_text())
    mutate(metadata)
    content = canonical_metadata_bytes(metadata)
    metadata_path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def npy_bytes(value: np.ndarray) -> bytes:
    output = io.BytesIO()
    np.lib.format.write_array(output, value, version=(2, 0), allow_pickle=False)
    return output.getvalue()


def npy_header_only(*, dtype: str, shape: tuple[int, ...]) -> bytes:
    output = io.BytesIO()
    np.lib.format.write_array_header_2_0(
        output,
        {
            "descr": np.lib.format.dtype_to_descr(np.dtype(dtype)),
            "fortran_order": False,
            "shape": shape,
        },
    )
    return output.getvalue()


def replace_zip(path: Path, members: list[tuple[str, bytes]]) -> str:
    archive_path = path / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)
    digest = sha256_file(archive_path)
    rewrite_metadata(
        path,
        lambda metadata: metadata["archive"].update(
            {
                "bytes": archive_path.stat().st_size,
                "sha256": digest,
            }
        ),
    )
    return digest


def test_state_dict_bundle_roundtrip_is_canonical_and_smoke_checked(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    hashes = write_fixture(first)
    second_hashes = write_fixture(second)

    assert hashes == second_hashes
    assert (first / ARCHIVE_NAME).read_bytes() == (second / ARCHIVE_NAME).read_bytes()
    assert (first / METADATA_NAME).read_bytes() == (second / METADATA_NAME).read_bytes()
    metadata = json.loads((first / METADATA_NAME).read_text())
    assert (first / METADATA_NAME).read_bytes() == canonical_metadata_bytes(metadata)
    assert hashes[ARCHIVE_NAME] == sha256_file(first / ARCHIVE_NAME)
    assert hashes[METADATA_NAME] == sha256_file(first / METADATA_NAME)

    loaded = load_fixture(first, hashes)
    assert loaded.archive_sha256 == hashes[ARCHIVE_NAME]
    assert loaded.metadata_sha256 == hashes[METADATA_NAME]
    assert loaded.payload == PAYLOAD
    assert set(loaded.arrays) == set(fixture_specs())
    for name, expected in fixture_arrays().items():
        np.testing.assert_array_equal(loaded.arrays[name], expected)


def test_archive_hash_is_checked_before_numpy_load(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    archive = path / ARCHIVE_NAME
    content = bytearray(archive.read_bytes())
    content[-1] ^= 0x01
    archive.write_bytes(content)

    called = False

    def forbidden_numpy_load(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("numpy.load must not run before archive hash validation")

    monkeypatch.setattr(bundle_module.np, "load", forbidden_numpy_load)
    with pytest.raises(SafeBundleError, match="archive SHA-256 mismatch"):
        load_fixture(path, hashes)
    assert called is False


def test_metadata_requires_external_hash_and_canonical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    metadata_path = path / METADATA_NAME
    metadata = json.loads(metadata_path.read_text())
    noncanonical = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    metadata_path.write_bytes(noncanonical)

    with pytest.raises(SafeBundleError, match="metadata SHA-256 mismatch"):
        load_fixture(path, hashes)
    forged_hash = hashlib.sha256(noncanonical).hexdigest()
    with pytest.raises(SafeBundleError, match="not canonical"):
        load_safe_npz_bundle(
            path,
            expected_metadata_sha256=forged_hash,
            expected_specs=fixture_specs(),
            expected_payload=PAYLOAD,
        )


@pytest.mark.parametrize("unsafe_name", ("../escape.npy", "/absolute.npy", "dir/value.npy"))
def test_zip_traversal_and_nested_members_are_rejected(
    tmp_path: Path, unsafe_name: str
) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    members = [
        (f"{name}.npy", npy_bytes(value))
        for name, value in fixture_arrays().items()
    ]
    members.append((unsafe_name, npy_bytes(np.asarray([1.0], dtype=np.float32))))
    replace_zip(path, members)
    metadata_hash = sha256_file(path / METADATA_NAME)

    with pytest.raises(SafeBundleError, match="unsafe member path"):
        load_fixture(path, {**hashes, METADATA_NAME: metadata_hash})


def test_zip_duplicate_and_unexpected_members_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    members = [
        (f"{name}.npy", npy_bytes(value))
        for name, value in fixture_arrays().items()
    ]
    members.append(members[0])
    with pytest.warns(UserWarning, match="Duplicate name"):
        replace_zip(path, members)
    metadata_hash = sha256_file(path / METADATA_NAME)
    with pytest.raises(SafeBundleError, match="duplicate members"):
        load_fixture(path, {**hashes, METADATA_NAME: metadata_hash})

    # Recreate a clean bundle and add a non-allowlisted but safe member name.
    second = tmp_path / "second"
    second_hashes = write_fixture(second)
    members = [
        (f"{name}.npy", npy_bytes(value))
        for name, value in fixture_arrays().items()
    ] + [("extra.npy", npy_bytes(np.asarray([1.0], dtype=np.float32)))]
    replace_zip(second, members)
    second_metadata_hash = sha256_file(second / METADATA_NAME)
    with pytest.raises(SafeBundleError, match="exact allowlist"):
        load_fixture(second, {**second_hashes, METADATA_NAME: second_metadata_hash})


def test_archive_and_expanded_size_limits_apply_before_array_loading(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    archive_size = (path / ARCHIVE_NAME).stat().st_size
    with pytest.raises(SafeBundleError, match="compressed-size"):
        load_fixture(
            path,
            hashes,
            limits=BundleLimits(max_archive_bytes=archive_size - 1),
        )
    with pytest.raises(SafeBundleError, match="expanded size"):
        load_fixture(
            path,
            hashes,
            limits=BundleLimits(
                max_archive_bytes=archive_size + 1,
                max_expanded_bytes=1,
                max_member_expanded_bytes=1024 * 1024,
            ),
        )
    metadata_size = (path / METADATA_NAME).stat().st_size
    with pytest.raises(SafeBundleError, match="metadata.*file-size"):
        load_fixture(
            path,
            hashes,
            limits=BundleLimits(max_metadata_bytes=metadata_size - 1),
        )


def test_npy_header_is_preflighted_before_numpy_allocation(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    members = [
        (f"{name}.npy", npy_bytes(value))
        for name, value in fixture_arrays().items()
        if name != "state__readout.weight"
    ]
    members.append(
        (
            "state__readout.weight.npy",
            npy_header_only(dtype="float32", shape=(1_000_000_000,)),
        )
    )
    replace_zip(path, members)
    metadata_hash = sha256_file(path / METADATA_NAME)

    def forbidden_numpy_load(*args, **kwargs):
        raise AssertionError("numpy.load must not run before NPY header validation")

    monkeypatch.setattr(bundle_module.np, "load", forbidden_numpy_load)
    with pytest.raises(SafeBundleError, match="NPY header differs"):
        load_fixture(path, {**hashes, METADATA_NAME: metadata_hash})


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda arrays: arrays.__setitem__(
                "norm_nfs", np.asarray([1.0, 2.0], dtype=np.float64)
            ),
            "dtype mismatch",
        ),
        (
            lambda arrays: arrays.__setitem__(
                "state__readout.bias", np.asarray([[0.1, -0.2]], dtype=np.float32)
            ),
            "shape mismatch",
        ),
        (
            lambda arrays: arrays.__setitem__(
                "state__readout.bias", np.asarray([np.nan, -0.2], dtype=np.float32)
            ),
            "non-finite",
        ),
        (
            lambda arrays: arrays.__setitem__(
                "norm_nfs", np.asarray([1.0, 0.0], dtype=np.float32)
            ),
            "strictly positive",
        ),
    ),
)
def test_writer_rejects_dtype_shape_nonfinite_and_nonpositive_scales(
    tmp_path: Path, mutate, message: str
) -> None:
    arrays = fixture_arrays()
    mutate(arrays)
    with pytest.raises(SafeBundleError, match=message):
        write_safe_npz_bundle(
            tmp_path / "bundle",
            arrays=arrays,
            specs=fixture_specs(),
            payload=PAYLOAD,
        )


def test_caller_specs_and_payload_are_external_contracts(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    wrong_specs = fixture_specs()
    wrong_specs["state__readout.bias"] = ArraySpec("float32", (3,))
    with pytest.raises(SafeBundleError, match="caller.*exact specification"):
        load_safe_npz_bundle(
            path,
            expected_metadata_sha256=hashes[METADATA_NAME],
            expected_specs=wrong_specs,
            expected_payload=PAYLOAD,
        )
    with pytest.raises(SafeBundleError, match="payload differs"):
        load_safe_npz_bundle(
            path,
            expected_metadata_sha256=hashes[METADATA_NAME],
            expected_specs=fixture_specs(),
            expected_payload={"architecture": {}},
        )


def test_smoke_fixture_hash_and_prediction_are_enforced(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    with pytest.raises(SafeBundleError, match="smoke input SHA-256"):
        load_safe_npz_bundle(
            path,
            expected_metadata_sha256=hashes[METADATA_NAME],
            expected_specs=fixture_specs(),
            expected_payload=PAYLOAD,
            smoke_hook=smoke_hook,
            expected_smoke_input_sha256="0" * 64,
            require_smoke=True,
        )

    def wrong_smoke(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        result = smoke_hook(arrays)["prediction"].copy()
        result[0, 0] += np.float32(1.0)
        return {"prediction": result}

    with pytest.raises(SafeBundleError, match="smoke prediction mismatch"):
        load_safe_npz_bundle(
            path,
            expected_metadata_sha256=hashes[METADATA_NAME],
            expected_specs=fixture_specs(),
            expected_payload=PAYLOAD,
            smoke_hook=wrong_smoke,
            expected_smoke_input_sha256=SMOKE_INPUT_SHA256,
            require_smoke=True,
        )


def test_bundle_inventory_symlinks_and_overwrite_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bundle"
    hashes = write_fixture(path)
    with pytest.raises(SafeBundleError, match="overwrite"):
        write_fixture(path)

    (path / "extra.txt").write_text("unexpected\n")
    with pytest.raises(SafeBundleError, match="exactly two regular files"):
        load_fixture(path, hashes)
    (path / "extra.txt").unlink()
    (path / METADATA_NAME).unlink()
    (path / METADATA_NAME).symlink_to(tmp_path / "missing")
    with pytest.raises(SafeBundleError, match="exactly two regular files"):
        load_fixture(path, hashes)
