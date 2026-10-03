"""Tiny deterministic byte bundles; no real mesh replay or native computation."""
import copy
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/solvers"))
import tcad_cps_dielectric_mesh_bundle as b
from test_tcad_cps_dielectric_mesh_audit import fixture

CFG = {"schema": "pcb-gnn.dielectric-mesh-bundle.v1", "chunk_bytes_max": 1024,
       "per_mode_bytes_max": 1000000}


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def test_exact_roundtrip_and_fresh_repeat(tmp_path):
    packet = fixture()[0]
    a, other = tmp_path / "a", tmp_path / "b"
    manifest = b.write_bundle(a, packet, CFG)
    assert manifest == b.write_bundle(other, packet, CFG)
    assert (a / "manifest.json").read_bytes() == (other / "manifest.json").read_bytes()
    loaded = b.load_bundle(a, CFG)
    assert all(np.array_equal(packet[k], loaded[k]) for k in packet)
    assert all(p.stat().st_size <= 1024 for p in a.glob("*.bin"))


@pytest.mark.parametrize("damage", ["chunk_hash", "packet_hash", "offset", "size", "name", "dtype", "shape", "count", "extra", "total"])
def test_corrupt_bundle_rejected(tmp_path, damage):
    directory = tmp_path / "bundle"
    value = b.write_bundle(directory, fixture()[0], CFG)
    row = value["arrays"]["node_tags"]
    if damage == "chunk_hash": row["chunks"][0]["sha256"] = "0"*64
    elif damage == "packet_hash": value["packet_sha256"] = "0"*64
    elif damage == "offset": row["chunks"][0]["offset"] = 8
    elif damage == "size": row["chunks"][0]["bytes"] -= 8
    elif damage == "name": row["chunks"][0]["name"] = "../node_tags.0000.bin"
    elif damage == "dtype": row["dtype"] = "<f8"
    elif damage == "shape": row["shape"] = [True]
    elif damage == "count": row["chunks"].pop()
    elif damage == "extra": (directory / "extra").write_text("unexpected")
    else: value["payload_bytes"] += 1
    (directory / "manifest.json").write_text(json.dumps(value))
    with pytest.raises(ValueError):
        b.check_bundle(directory, CFG)


def test_payload_cap_is_combined_before_write(tmp_path):
    packet = fixture()[0]
    value = b.write_bundle(tmp_path / "raw", packet, CFG)
    cap = {**CFG, "per_mode_bytes_max": 2*value["payload_bytes"]-1}
    with pytest.raises(ValueError, match="combined"):
        b.write_bundle(tmp_path / "final", packet, cap, used_bytes=value["payload_bytes"])
    assert not (tmp_path / "final").exists()


def test_no_overwrite_of_complete_or_partial_payload(tmp_path):
    path = tmp_path / "bundle"
    path.mkdir()
    (path / "partial.bin").write_bytes(b"retained")
    with pytest.raises(FileExistsError):
        b.write_bundle(path, fixture()[0], CFG)
    assert (path / "partial.bin").read_bytes() == b"retained"


@pytest.mark.parametrize("which", ["parent", "directory", "manifest", "chunk"])
def test_symlink_rejected(tmp_path, which):
    path = tmp_path / "bundle"
    b.write_bundle(path, fixture()[0], CFG)
    if which in ("parent", "directory"):
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path if which == "parent" else path, target_is_directory=True)
        path = alias / "bundle" if which == "parent" else alias
    else:
        target = path / ("manifest.json" if which == "manifest" else "node_tags.0000.bin")
        moved = tmp_path / "original"
        target.rename(moved)
        target.symlink_to(moved)
    with pytest.raises(ValueError, match="unsafe|symlink|hash"):
        b.check_bundle(path, CFG)


def test_changed_chunk_bytes_rejected(tmp_path):
    path = tmp_path / "bundle"
    b.write_bundle(path, fixture()[0], CFG)
    chunk = path / "node_tags.0000.bin"
    value = bytearray(chunk.read_bytes())
    value[0] ^= 1
    chunk.write_bytes(value)
    with pytest.raises(ValueError, match="hash"):
        b.check_bundle(path, CFG)


def test_metadata_checker_reconstructs_packet_digest_without_numpy(tmp_path, monkeypatch):
    import builtins
    path = tmp_path / "bundle"
    expected = b.write_bundle(path, fixture()[0], CFG)
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in ("numpy", "scipy", "gmsh", "skfem"):
            raise AssertionError("numerical import during byte verification")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert b.check_bundle(path, CFG) == expected
