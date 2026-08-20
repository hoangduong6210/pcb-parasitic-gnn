#!/usr/bin/env python3
"""Strict, pickle-free NumPy checkpoint bundles for scientific inference.

The metadata hash is expected to come from an external task/artifact manifest.
It authenticates canonical ``metadata.json`` bytes; that metadata in turn pins
the NPZ byte hash and the exact array contract.  The archive hash is verified
before ZIP parsing or ``numpy.load``.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping

import numpy as np


SCHEMA = "pcb-gnn.safe-npz-bundle.v1"
ARCHIVE_NAME = "weights_and_norm.npz"
METADATA_NAME = "metadata.json"
FORMAT = "NumPy NPZ; allow_pickle=False"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
ARRAY_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
SmokeHook = Callable[[Mapping[str, np.ndarray]], Mapping[str, np.ndarray]]


class SafeBundleError(ValueError):
    """Raised when a bundle violates its integrity or safety contract."""


@dataclass(frozen=True)
class ArraySpec:
    """Exact on-disk contract for one numeric array."""

    dtype: str
    shape: tuple[int, ...]
    strictly_positive: bool = False

    def __post_init__(self) -> None:
        dtype = np.dtype(self.dtype)
        if dtype.hasobject or dtype.fields is not None or dtype.subdtype is not None:
            raise SafeBundleError("array dtype must be a plain non-object dtype")
        if dtype.kind not in "iufc":
            raise SafeBundleError("array dtype must be integer, floating, or complex")
        if not self.shape or any(type(size) is not int or size <= 0 for size in self.shape):
            raise SafeBundleError("array shape must contain positive integer dimensions")
        if self.strictly_positive and dtype.kind not in "iuf":
            raise SafeBundleError("strict positivity requires a real numeric dtype")

    @property
    def canonical_dtype(self) -> str:
        return np.dtype(self.dtype).str

    def to_json(self) -> dict[str, Any]:
        return {
            "dtype": self.canonical_dtype,
            "finite": True,
            "shape": list(self.shape),
            "strictly_positive": self.strictly_positive,
        }


@dataclass(frozen=True)
class BundleLimits:
    """Bounds applied before any NPZ array is materialized."""

    max_archive_bytes: int = 64 * 1024 * 1024
    max_expanded_bytes: int = 256 * 1024 * 1024
    max_member_expanded_bytes: int = 64 * 1024 * 1024
    max_metadata_bytes: int = 2 * 1024 * 1024
    max_members: int = 512
    max_smoke_values: int = 4096

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if type(value) is not int or value <= 0:
                raise SafeBundleError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class LoadedBundle:
    """Validated numeric arrays and immutable metadata payload."""

    arrays: Mapping[str, np.ndarray]
    payload: Mapping[str, Any]
    metadata_sha256: str
    archive_sha256: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SafeBundleError(f"metadata is not canonical JSON data: {exc}") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SafeBundleError(f"duplicate metadata key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise SafeBundleError(f"non-finite metadata number: {token}")


def _load_canonical_metadata(
    path: Path, expected_sha256: str, *, max_bytes: int
) -> dict[str, Any]:
    if not isinstance(expected_sha256, str) or SHA256_RE.fullmatch(expected_sha256) is None:
        raise SafeBundleError("expected metadata SHA-256 is malformed")
    metadata_bytes = path.stat().st_size
    if metadata_bytes <= 0 or metadata_bytes > max_bytes:
        raise SafeBundleError("metadata exceeds its file-size contract")
    content = path.read_bytes()
    observed = sha256_bytes(content)
    if observed != expected_sha256:
        raise SafeBundleError(
            f"metadata SHA-256 mismatch: expected {expected_sha256}, observed {observed}"
        )
    try:
        value = json.loads(
            content,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafeBundleError(f"invalid metadata JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SafeBundleError("metadata must be a JSON object")
    if content != canonical_json_bytes(value) + b"\n":
        raise SafeBundleError("metadata bytes are not canonical JSON plus one newline")
    return value


def _validate_array_name(name: Any) -> str:
    if not isinstance(name, str) or ARRAY_NAME_RE.fullmatch(name) is None:
        raise SafeBundleError(f"unsafe or unsupported array name: {name!r}")
    return name


def _spec_map_json(specs: Mapping[str, ArraySpec]) -> dict[str, dict[str, Any]]:
    if not specs:
        raise SafeBundleError("bundle must contain at least one array")
    result: dict[str, dict[str, Any]] = {}
    for name in sorted(specs):
        _validate_array_name(name)
        spec = specs[name]
        if not isinstance(spec, ArraySpec):
            raise SafeBundleError(f"array spec for {name!r} is not ArraySpec")
        result[name] = spec.to_json()
    return result


def _validate_array(array: Any, spec: ArraySpec, name: str) -> np.ndarray:
    if not isinstance(array, np.ndarray):
        raise SafeBundleError(f"array {name!r} must be a numpy.ndarray")
    if array.dtype.str != spec.canonical_dtype:
        raise SafeBundleError(
            f"array {name!r} dtype mismatch: {array.dtype.str} != {spec.canonical_dtype}"
        )
    if tuple(array.shape) != spec.shape:
        raise SafeBundleError(
            f"array {name!r} shape mismatch: {tuple(array.shape)} != {spec.shape}"
        )
    if array.dtype.hasobject or not np.isfinite(array).all():
        raise SafeBundleError(f"array {name!r} contains object or non-finite values")
    if spec.strictly_positive and not np.all(array > 0):
        raise SafeBundleError(f"normalization scale {name!r} must be strictly positive")
    return np.ascontiguousarray(array)


def _normalize_arrays(
    arrays: Mapping[str, np.ndarray], specs: Mapping[str, ArraySpec]
) -> dict[str, np.ndarray]:
    if set(arrays) != set(specs):
        raise SafeBundleError("array names differ from the exact expected specification")
    return {
        name: _validate_array(arrays[name], specs[name], name)
        for name in sorted(specs)
    }


def _zip_member_name(array_name: str) -> str:
    return f"{array_name}.npy"


def _deterministic_npz_bytes(arrays: Mapping[str, np.ndarray]) -> bytes:
    destination = io.BytesIO()
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for name in sorted(arrays):
            npy = io.BytesIO()
            np.lib.format.write_array(
                npy,
                arrays[name],
                version=(2, 0),
                allow_pickle=False,
            )
            info = zipfile.ZipInfo(_zip_member_name(name), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(
                info,
                npy.getvalue(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return destination.getvalue()


def _safe_member_name(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and len(path.parts) == 1
        and path.parts[0] not in {".", ".."}
        and name.endswith(".npy")
    )


def _inspect_npz(
    path: Path,
    *,
    specs: Mapping[str, ArraySpec],
    limits: BundleLimits,
) -> None:
    allowed_members = {_zip_member_name(name) for name in specs}
    archive_size = path.stat().st_size
    if archive_size <= 0 or archive_size > limits.max_archive_bytes:
        raise SafeBundleError("NPZ archive exceeds its compressed-size contract")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > limits.max_members:
                raise SafeBundleError("NPZ archive contains too many members")
            if len(names) != len(set(names)):
                raise SafeBundleError("NPZ archive contains duplicate members")
            if any(not _safe_member_name(name) for name in names):
                raise SafeBundleError("NPZ archive contains an unsafe member path")
            if set(names) != allowed_members:
                raise SafeBundleError("NPZ members differ from the exact allowlist")
            expanded = 0
            for info in infos:
                unix_mode = (info.external_attr >> 16) & 0o170000
                if (
                    info.is_dir()
                    or unix_mode == 0o120000
                    or info.flag_bits & 0x1
                    or info.file_size <= 0
                    or info.file_size > limits.max_member_expanded_bytes
                ):
                    raise SafeBundleError("NPZ member violates type, encryption, or size policy")
                expanded += info.file_size
                if expanded > limits.max_expanded_bytes:
                    raise SafeBundleError("NPZ expanded size exceeds its safety limit")
                array_name = info.filename.removesuffix(".npy")
                with archive.open(info, "r") as member:
                    version = np.lib.format.read_magic(member)
                    if version != (2, 0):
                        raise SafeBundleError("NPY member uses a non-canonical format version")
                    shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(
                        member
                    )
                    spec = specs[array_name]
                    if (
                        fortran_order
                        or dtype.hasobject
                        or dtype.fields is not None
                        or dtype.subdtype is not None
                        or dtype.str != spec.canonical_dtype
                        or tuple(shape) != spec.shape
                    ):
                        raise SafeBundleError(
                            f"NPY header differs from the exact specification for {array_name!r}"
                        )
                    expected_data_bytes = math.prod(shape) * dtype.itemsize
                    if info.file_size - member.tell() != expected_data_bytes:
                        raise SafeBundleError(
                            f"NPY payload size differs from its header for {array_name!r}"
                        )
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        if isinstance(exc, SafeBundleError):
            raise
        raise SafeBundleError(f"invalid NPZ ZIP container: {exc}") from exc


def _smoke_outputs(
    hook: SmokeHook,
    arrays: Mapping[str, np.ndarray],
    *,
    max_values: int,
) -> dict[str, dict[str, Any]]:
    raw = hook(MappingProxyType(dict(arrays)))
    if not isinstance(raw, Mapping) or not raw:
        raise SafeBundleError("smoke hook must return a non-empty mapping")
    output: dict[str, dict[str, Any]] = {}
    total_values = 0
    for name in sorted(raw):
        _validate_array_name(name)
        value = raw[name]
        if not isinstance(value, np.ndarray) or value.dtype.kind not in "iufc":
            raise SafeBundleError("smoke outputs must be numeric numpy arrays")
        if value.dtype.hasobject or not value.size or not np.isfinite(value).all():
            raise SafeBundleError("smoke output is empty, object, or non-finite")
        total_values += int(value.size)
        if total_values > max_values:
            raise SafeBundleError("smoke outputs exceed their value-count limit")
        canonical = np.ascontiguousarray(value)
        output[name] = {
            "dtype": canonical.dtype.str,
            "shape": list(canonical.shape),
            "values": canonical.tolist(),
        }
    return output


def _validate_smoke_metadata(smoke: Any, limits: BundleLimits) -> None:
    if smoke is None:
        return
    if not isinstance(smoke, dict) or set(smoke) != {
        "atol",
        "input_sha256",
        "outputs",
        "rtol",
    }:
        raise SafeBundleError("smoke metadata fields are not exact")
    input_sha256 = smoke.get("input_sha256")
    if not isinstance(input_sha256, str) or SHA256_RE.fullmatch(input_sha256) is None:
        raise SafeBundleError("smoke input SHA-256 is malformed")
    for name in ("atol", "rtol"):
        value = smoke.get(name)
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise SafeBundleError(f"smoke {name} must be finite and non-negative")
    outputs = smoke.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise SafeBundleError("smoke outputs are missing")
    total_values = 0
    for name, record in outputs.items():
        _validate_array_name(name)
        if not isinstance(record, dict) or set(record) != {"dtype", "shape", "values"}:
            raise SafeBundleError("smoke output fields are not exact")
        try:
            dtype = np.dtype(record["dtype"])
            array = np.asarray(record["values"], dtype=dtype)
        except (TypeError, ValueError) as exc:
            raise SafeBundleError("smoke output cannot be reconstructed") from exc
        shape = record["shape"]
        if (
            dtype.hasobject
            or dtype.kind not in "iufc"
            or not isinstance(shape, list)
            or any(type(size) is not int or size <= 0 for size in shape)
            or tuple(array.shape) != tuple(shape)
            or not np.isfinite(array).all()
        ):
            raise SafeBundleError("smoke output dtype, shape, or values are invalid")
        total_values += int(array.size)
    if total_values > limits.max_smoke_values:
        raise SafeBundleError("smoke metadata exceeds its value-count limit")


def _verify_smoke(
    smoke: dict[str, Any],
    hook: SmokeHook,
    arrays: Mapping[str, np.ndarray],
    limits: BundleLimits,
) -> None:
    observed = _smoke_outputs(hook, arrays, max_values=limits.max_smoke_values)
    expected = smoke["outputs"]
    if set(observed) != set(expected):
        raise SafeBundleError("smoke output names differ")
    for name in sorted(expected):
        expected_record = expected[name]
        observed_record = observed[name]
        if (
            observed_record["dtype"] != expected_record["dtype"]
            or observed_record["shape"] != expected_record["shape"]
        ):
            raise SafeBundleError(f"smoke output contract differs for {name!r}")
        dtype = np.dtype(expected_record["dtype"])
        expected_array = np.asarray(expected_record["values"], dtype=dtype)
        observed_array = np.asarray(observed_record["values"], dtype=dtype)
        if not np.allclose(
            observed_array,
            expected_array,
            rtol=float(smoke["rtol"]),
            atol=float(smoke["atol"]),
            equal_nan=False,
        ):
            raise SafeBundleError(f"smoke prediction mismatch for {name!r}")


def _metadata_specs(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    arrays = metadata.get("arrays")
    if not isinstance(arrays, dict):
        raise SafeBundleError("metadata array specification is missing")
    return arrays


def load_safe_npz_bundle(
    bundle: Path,
    *,
    expected_metadata_sha256: str,
    expected_specs: Mapping[str, ArraySpec],
    expected_payload: Mapping[str, Any] | None = None,
    smoke_hook: SmokeHook | None = None,
    expected_smoke_input_sha256: str | None = None,
    require_smoke: bool = False,
    limits: BundleLimits = BundleLimits(),
) -> LoadedBundle:
    """Load a hash-authenticated bundle after validating every archive member."""
    bundle = Path(bundle)
    if not bundle.is_dir() or bundle.is_symlink():
        raise SafeBundleError("bundle must be a real directory")
    entries = list(bundle.iterdir())
    if {entry.name for entry in entries} != {ARCHIVE_NAME, METADATA_NAME} or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SafeBundleError("bundle inventory must contain exactly two regular files")

    metadata_path = bundle / METADATA_NAME
    metadata = _load_canonical_metadata(
        metadata_path,
        expected_metadata_sha256,
        max_bytes=limits.max_metadata_bytes,
    )
    if set(metadata) != {"archive", "arrays", "format", "payload", "schema", "smoke"}:
        raise SafeBundleError("metadata fields are not exact")
    if metadata.get("schema") != SCHEMA or metadata.get("format") != FORMAT:
        raise SafeBundleError("unsupported safe-bundle identity")
    expected_spec_json = _spec_map_json(expected_specs)
    if _metadata_specs(metadata) != expected_spec_json:
        raise SafeBundleError("metadata arrays differ from the caller's exact specification")
    payload = metadata.get("payload")
    if not isinstance(payload, dict):
        raise SafeBundleError("metadata payload must be a JSON object")
    if expected_payload is not None and payload != dict(expected_payload):
        raise SafeBundleError("metadata payload differs from its expected contract")
    smoke = metadata.get("smoke")
    _validate_smoke_metadata(smoke, limits)
    if require_smoke and (smoke is None or smoke_hook is None):
        raise SafeBundleError("a smoke hook and smoke metadata are required")
    if smoke is not None and expected_smoke_input_sha256 is not None:
        if smoke["input_sha256"] != expected_smoke_input_sha256:
            raise SafeBundleError("smoke input SHA-256 differs from the expected fixture")

    archive_record = metadata.get("archive")
    if not isinstance(archive_record, dict) or set(archive_record) != {
        "bytes",
        "name",
        "sha256",
    }:
        raise SafeBundleError("archive metadata fields are not exact")
    if archive_record.get("name") != ARCHIVE_NAME:
        raise SafeBundleError("archive name is not canonical")
    archive_sha256 = archive_record.get("sha256")
    if not isinstance(archive_sha256, str) or SHA256_RE.fullmatch(archive_sha256) is None:
        raise SafeBundleError("archive SHA-256 is malformed")
    archive_path = bundle / ARCHIVE_NAME
    archive_bytes = archive_path.stat().st_size
    if type(archive_record.get("bytes")) is not int or archive_record["bytes"] != archive_bytes:
        raise SafeBundleError("archive byte count differs from metadata")
    if archive_bytes > limits.max_archive_bytes:
        raise SafeBundleError("NPZ archive exceeds its compressed-size contract")

    # This digest comparison intentionally precedes ZipFile and numpy.load.
    observed_archive_sha256 = sha256_file(archive_path)
    if observed_archive_sha256 != archive_sha256:
        raise SafeBundleError(
            f"archive SHA-256 mismatch: expected {archive_sha256}, "
            f"observed {observed_archive_sha256}"
        )
    _inspect_npz(archive_path, specs=expected_specs, limits=limits)

    arrays: dict[str, np.ndarray] = {}
    try:
        with np.load(archive_path, allow_pickle=False) as archive:
            if set(archive.files) != set(expected_specs):
                raise SafeBundleError("loaded NPZ keys differ from the exact specification")
            for name in sorted(expected_specs):
                arrays[name] = _validate_array(archive[name], expected_specs[name], name).copy()
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        if isinstance(exc, SafeBundleError):
            raise
        raise SafeBundleError(f"NPZ array loading failed: {exc}") from exc

    if smoke is not None and smoke_hook is not None:
        _verify_smoke(smoke, smoke_hook, arrays, limits)
    return LoadedBundle(
        arrays=MappingProxyType(arrays),
        payload=MappingProxyType(dict(payload)),
        metadata_sha256=expected_metadata_sha256,
        archive_sha256=archive_sha256,
    )


def _write_file_fsync(path: Path, content: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def write_safe_npz_bundle(
    bundle: Path,
    *,
    arrays: Mapping[str, np.ndarray],
    specs: Mapping[str, ArraySpec],
    payload: Mapping[str, Any],
    smoke_hook: SmokeHook | None = None,
    smoke_input_sha256: str | None = None,
    smoke_rtol: float = 1e-6,
    smoke_atol: float = 1e-7,
    limits: BundleLimits = BundleLimits(),
) -> dict[str, str]:
    """Atomically create a canonical bundle and verify its roundtrip before publish."""
    bundle = Path(bundle)
    parent = bundle.parent
    if bundle.exists() or bundle.is_symlink():
        raise SafeBundleError("refusing to overwrite an existing bundle")
    if parent.exists() and (not parent.is_dir() or parent.is_symlink()):
        raise SafeBundleError("bundle parent must be a real directory")
    parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_arrays(arrays, specs)
    spec_json = _spec_map_json(specs)
    archive_content = _deterministic_npz_bytes(normalized)
    if not archive_content or len(archive_content) > limits.max_archive_bytes:
        raise SafeBundleError("serialized NPZ exceeds its compressed-size contract")

    smoke: dict[str, Any] | None = None
    if smoke_hook is not None or smoke_input_sha256 is not None:
        if smoke_hook is None or not isinstance(smoke_input_sha256, str):
            raise SafeBundleError("smoke hook and input SHA-256 must be provided together")
        if SHA256_RE.fullmatch(smoke_input_sha256) is None:
            raise SafeBundleError("smoke input SHA-256 is malformed")
        if (
            type(smoke_rtol) not in {int, float}
            or type(smoke_atol) not in {int, float}
            or not math.isfinite(smoke_rtol)
            or not math.isfinite(smoke_atol)
            or smoke_rtol < 0
            or smoke_atol < 0
        ):
            raise SafeBundleError("smoke tolerances must be finite and non-negative")
        smoke = {
            "atol": float(smoke_atol),
            "input_sha256": smoke_input_sha256,
            "outputs": _smoke_outputs(
                smoke_hook, normalized, max_values=limits.max_smoke_values
            ),
            "rtol": float(smoke_rtol),
        }

    payload_dict = dict(payload)
    # Validate payload and the complete metadata through canonical serialization.
    metadata = {
        "archive": {
            "bytes": len(archive_content),
            "name": ARCHIVE_NAME,
            "sha256": sha256_bytes(archive_content),
        },
        "arrays": spec_json,
        "format": FORMAT,
        "payload": payload_dict,
        "schema": SCHEMA,
        "smoke": smoke,
    }
    metadata_content = canonical_json_bytes(metadata) + b"\n"
    metadata_sha256 = sha256_bytes(metadata_content)

    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle.name}.tmp-", dir=parent))
    try:
        _write_file_fsync(temporary / ARCHIVE_NAME, archive_content)
        _write_file_fsync(temporary / METADATA_NAME, metadata_content)
        _inspect_npz(
            temporary / ARCHIVE_NAME,
            specs=specs,
            limits=limits,
        )
        load_safe_npz_bundle(
            temporary,
            expected_metadata_sha256=metadata_sha256,
            expected_specs=specs,
            expected_payload=payload_dict,
            smoke_hook=smoke_hook,
            expected_smoke_input_sha256=smoke_input_sha256,
            require_smoke=smoke_hook is not None,
            limits=limits,
        )
        os.replace(temporary, bundle)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        METADATA_NAME: metadata_sha256,
        ARCHIVE_NAME: metadata["archive"]["sha256"],
    }


__all__ = [
    "ARCHIVE_NAME",
    "METADATA_NAME",
    "ArraySpec",
    "BundleLimits",
    "LoadedBundle",
    "SafeBundleError",
    "load_safe_npz_bundle",
    "sha256_file",
    "write_safe_npz_bundle",
]
