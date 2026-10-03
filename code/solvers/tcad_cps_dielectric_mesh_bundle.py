"""Deterministic bounded array chunks; byte-only verification needs no NumPy.

Writing/loading real mesh arrays belongs to a guarded compute worker. Unit
tests use tiny synthetic arrays. This module has no executable entry point.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

from tcad_cps_dielectric_mesh_audit import ARRAY_DTYPES, SCHEMA, packet_sha256

WIDTH = {"coordinates_mm": 3, "tetrahedron_nodes": 4, "triangle_nodes": 3}


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_directory(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("absolute bundle directory required")
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("symlink in bundle directory")
    return path


def write_bundle(path, packet, cfg, *, used_bytes=0):
    import numpy as np
    path = safe_directory(path)
    if set(packet) != set(ARRAY_DTYPES):
        raise ValueError("bundle packet schema mismatch")
    arrays = {k: np.ascontiguousarray(packet[k], dtype=dtype) for k, dtype in ARRAY_DTYPES.items()}
    total = sum(a.nbytes for a in arrays.values())
    if not 0 <= used_bytes < cfg["per_mode_bytes_max"] or not 0 < total <= cfg["per_mode_bytes_max"]-used_bytes:
        raise ValueError("combined raw/final payload cap exceeded")
    step = cfg["chunk_bytes_max"]
    if type(step) is not int or step <= 0 or step % 8:
        raise ValueError("chunk cap must be positive and eight-byte aligned")
    # Never overwrite or repair a partial bundle after a worker interruption.
    path.mkdir(exist_ok=False)
    manifest = {"schema": cfg["schema"], "packet_sha256": packet_sha256(arrays),
        "payload_bytes": total, "arrays": {}}
    for name, array in arrays.items():
        chunks, data = [], memoryview(array).cast("B")
        for ordinal, offset in enumerate(range(0, array.nbytes, step)):
            filename = f"{name}.{ordinal:04d}.bin"
            payload = data[offset:offset+step]
            with (path / filename).open("xb") as stream:
                stream.write(payload)
            chunks.append({"name": filename, "offset": offset, "bytes": len(payload),
                           "sha256": hashlib.sha256(payload).hexdigest()})
        manifest["arrays"][name] = {"dtype": array.dtype.str, "shape": list(array.shape),
                                    "bytes": array.nbytes, "chunks": chunks}
    with (path / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    check_bundle(path, cfg)
    return manifest


def check_bundle(path, cfg):
    """Exact file/byte/shape closure only; never load or replay numeric arrays."""
    path = safe_directory(path)
    if (path / "manifest.json").is_symlink():
        raise ValueError("unsafe bundle manifest")
    if (path / "manifest.json").stat().st_size > 1024*1024:
        raise ValueError("bundle manifest exceeds one-MiB metadata cap")
    manifest = json.loads((path / "manifest.json").read_text())
    if (set(manifest) != {"schema", "packet_sha256", "payload_bytes", "arrays"}
            or manifest["schema"] != cfg["schema"] or not re.fullmatch("[a-f0-9]{64}", manifest["packet_sha256"])
            or set(manifest["arrays"]) != set(ARRAY_DTYPES)):
        raise ValueError("bundle manifest schema mismatch")
    total, names, lengths = 0, {"manifest.json"}, {}
    aggregate = hashlib.sha256((SCHEMA + "\0").encode())
    for name, dtype in ARRAY_DTYPES.items():
        row = manifest["arrays"][name]
        if set(row) != {"dtype", "shape", "bytes", "chunks"} or row["dtype"] != dtype:
            raise ValueError("bundle array schema/dtype mismatch")
        shape = row["shape"]
        if (not isinstance(shape, list) or len(shape) != (2 if name in WIDTH else 1)
                or any(type(v) is not int or v <= 0 for v in shape)
                or (name in WIDTH and shape[1] != WIDTH[name])):
            raise ValueError("bundle array shape mismatch")
        lengths[name] = shape[0]
        size = math.prod(shape)*8
        if size > cfg["per_mode_bytes_max"]-total:
            raise ValueError("bundle declared payload exceeds cap")
        header = json.dumps({"name": name, "dtype": dtype, "shape": shape}, sort_keys=True, separators=(",", ":"))
        aggregate.update(header.encode() + b"\0")
        if type(row["bytes"]) is not int or row["bytes"] != size or not isinstance(row["chunks"], list):
            raise ValueError("bundle array byte count mismatch")
        offset, step = 0, cfg["chunk_bytes_max"]
        if len(row["chunks"]) != (size+step-1)//step:
            raise ValueError("bundle chunk count mismatch")
        for ordinal, chunk in enumerate(row["chunks"]):
            filename = f"{name}.{ordinal:04d}.bin"
            count = min(step, size-offset)
            if (set(chunk) != {"name", "offset", "bytes", "sha256"} or chunk["name"] != filename
                    or type(chunk["offset"]) is not int or chunk["offset"] != offset
                    or type(chunk["bytes"]) is not int or chunk["bytes"] != count):
                raise ValueError("bundle chunk name/offset/count mismatch")
            member = path / filename
            if member.is_symlink() or not member.is_file() or member.stat().st_size != count:
                raise ValueError("bundle chunk bytes/hash mismatch")
            digest = hashlib.sha256()
            with member.open("rb") as stream:
                for payload in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(payload)
                    aggregate.update(payload)
            if digest.hexdigest() != chunk["sha256"]:
                raise ValueError("bundle chunk bytes/hash mismatch")
            names.add(filename)
            offset += count
        total += size
    for anchor, others in (("node_tags", ["coordinates_mm"]), ("triangle_tags", ["triangle_nodes", "triangle_faces"]),
                          ("tetrahedron_tags", ["tetrahedron_nodes", "tetrahedron_volumes", "min_sicn", "min_det_jac_mm3"])):
        if any(lengths[n] != lengths[anchor] for n in others):
            raise ValueError("bundle related-array lengths differ")
    if (type(manifest["payload_bytes"]) is not int or total != manifest["payload_bytes"]
            or not 0 < total <= cfg["per_mode_bytes_max"] or {p.name for p in path.iterdir()} != names):
        raise ValueError("bundle payload cap/file closure mismatch")
    if aggregate.hexdigest() != manifest["packet_sha256"]:
        raise ValueError("bundle canonical packet byte hash mismatch")
    return manifest


def load_bundle(path, cfg):
    """Numerical loading is compute-only for real packets; never used by collector."""
    import numpy as np
    manifest = check_bundle(path, cfg)
    arrays = {}
    for name, row in manifest["arrays"].items():
        value = np.empty(row["shape"], dtype=row["dtype"])
        data = memoryview(value).cast("B")
        for chunk in row["chunks"]:
            with (Path(path) / chunk["name"]).open("rb") as stream:
                if stream.readinto(data[chunk["offset"]:chunk["offset"]+chunk["bytes"]]) != chunk["bytes"]:
                    raise ValueError("short bundle read")
        arrays[name] = value
    if packet_sha256(arrays) != manifest["packet_sha256"]:
        raise ValueError("loaded canonical packet hash mismatch")
    return arrays
