"""Byte-only preservation tests; actual reports are never numerically replayed."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import archive_tcad_cps_layer_grid_dyadic_v1 as a
from scientific_artifact import atomic_write_json, sha256_file


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def prepare(monkeypatch, tmp_path):
    source = tmp_path / "execution"
    directory = source / a.DIRECTORY
    directory.mkdir(parents=True)
    paths = ["toy.stdout", "toy.stderr", "toy.report.json"]
    for name in paths:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic partial packet/log\n")
    arm = {"passed": False, "failure": "synthetic failure", "files_sha256": {n: sha256_file(directory / n) for n in paths}}
    record = {"scheduler": {"JobId": a.JOB, "NodeList": "test-node", "NumCPUs": "3"},
              "modes": {"toy": arm}, "failure": None}
    record.update(a.contract.assessment(record, a.contract.protocol()))
    atomic_write_json(directory / "attempt.json", record)
    atomic_write_json(directory / "toy.json", arm)
    for src, _ in a.log_pairs():
        (source / src).parent.mkdir(exist_ok=True)
        (source / src).write_bytes(b"synthetic scheduler log\n")
    protocol = tmp_path / a.contract.PROTOCOL
    protocol.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / a.contract.PROTOCOL, protocol)
    atomic_write_json(tmp_path / a.SUBMISSION, {"job_id": a.JOB, "source_commit": a.COMMIT,
        "lock_sha256": a.LOCK_SHA, "protocol_sha256": sha256_file(protocol)})
    row = dict(zip(a.COLUMNS, [a.JOB, "FAILED", "2:0", "0", "23", "3", "8G", "test-node"]))
    toy = "|".join(row[k] for k in a.COLUMNS)
    monkeypatch.setattr(a, "ROOT", tmp_path)
    # The immutable runner separately validates full receipt semantics.
    monkeypatch.setattr(a, "review_attempt", lambda _: record)
    monkeypatch.setattr(a, "accounting", lambda _: (toy, [row]))
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=a.COMMIT + "\n"))
    return source, record, row


def test_complete_partial_file_closure_and_no_overwrite(monkeypatch, tmp_path):
    source, record, _ = prepare(monkeypatch, tmp_path)
    manifest = a.collect(source)
    assert a.check_archive() == manifest
    assert len(manifest["files_sha256"]) == 9
    assert manifest["diagnosis"]["diagnostic_passed"] is False
    assert (tmp_path / a.DIRECTORY / "toy.report.json").read_bytes() == b"synthetic partial packet/log\n"
    with pytest.raises(ValueError, match="overwrite"):
        a.collect(source)


@pytest.mark.parametrize("field,value", [("JobID", "1"), ("State", "RUNNING"), ("ExitCode", "1:0"),
    ("Restarts", "1"), ("ElapsedRaw", "901"), ("ElapsedRaw", "nan"), ("ElapsedRaw", "0"),
    ("AllocCPUS", "1"), ("ReqMem", "16G"), ("NodeList", "other")])
def test_wrong_accounting_prevents_writes(monkeypatch, tmp_path, field, value):
    source, _, row = prepare(monkeypatch, tmp_path)
    row[field] = value
    monkeypatch.setattr(a, "accounting", lambda _: ("|".join(row[k] for k in a.COLUMNS), [row]))
    with pytest.raises(ValueError):
        a.collect(source)
    assert not (tmp_path / a.DIRECTORY).exists()


@pytest.mark.parametrize("kind", ["chunk", "extra", "extra_log", "source", "flag", "flag_type", "accounting", "symlink", "submission"])
def test_corruption_rejected(monkeypatch, tmp_path, kind):
    source, record, _ = prepare(monkeypatch, tmp_path)
    manifest = a.collect(source)
    if kind == "chunk": (tmp_path / a.DIRECTORY / "toy.report.json").write_bytes(b"changed")
    elif kind == "extra": (tmp_path / a.MANIFEST.parent / "extra").write_text("")
    elif kind == "extra_log": (tmp_path / a.MANIFEST.parent / "logs/extra").write_text("")
    elif kind == "source": manifest["source_commit"] = "other"
    elif kind == "flag": manifest["diagnosis"]["reference_qualified"] = True
    elif kind == "flag_type": manifest["diagnosis"]["reference_qualified"] = 0
    elif kind == "accounting": manifest["accounting"][0]["ExitCode"] = "1:0"
    elif kind == "submission":
        value = a.contract.read_json(tmp_path / a.SUBMISSION)
        value["job_id"] = "other"
        atomic_write_json(tmp_path / a.SUBMISSION, value)
        manifest["files_sha256"][str(a.SUBMISSION)] = sha256_file(tmp_path / a.SUBMISSION)
    else:
        path = tmp_path / a.DIRECTORY / "toy.report.json"
        path.rename(tmp_path / "target")
        path.symlink_to(tmp_path / "target")
    atomic_write_json(tmp_path / a.MANIFEST, manifest)
    with pytest.raises(ValueError):
        a.check_archive()


@pytest.mark.parametrize("bad", ["../escape.bin", "/tmp/escape.bin", "different.payload/data.bin"])
def test_members_cannot_escape_mode_payload(bad):
    with pytest.raises(ValueError, match="unsafe"):
        a.members({"modes": {"toy": {"files_sha256": {bad: "0"*64}}}})


def test_reviewer_is_byte_only_and_scrubs_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "sha256_file", lambda _: a.LOCK_SHA)
    monkeypatch.setenv("GH_TOKEN", "synthetic-secret")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='{"complete":false}')
    monkeypatch.setattr(a.subprocess, "run", run)
    assert a.review_attempt(tmp_path) == {"complete": False}
    command, kwargs = calls[0]
    assert "check_source(execution=False)" in command[2] and "validate_attempt" in command[2]
    assert "load_bundle" not in command[2] and "audit_cad_mesh" not in command[2]
    assert "GH_TOKEN" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
    assert kwargs["timeout"] == 240


def test_actual_terminal_archive_metadata_only():
    if not (ROOT / a.MANIFEST).exists():
        pytest.skip("terminal collection has not run yet")
    manifest = a.check_archive()
    assert manifest["accounting"] == [dict(zip(a.COLUMNS,
        ["7653000", "COMPLETED", "0:0", "0", "58", "3", "8G", "a0113"]))]
    assert manifest["diagnosis"]["diagnostic_passed"] is True
    assert manifest["diagnosis"]["repeatability_passed"] is True
    assert manifest["diagnosis"]["planning_feasible"] is False
    assert all(manifest["diagnosis"][k] is False for k in a.contract.CLOSED)
    record = a.contract.read_json(ROOT / a.DIRECTORY / "attempt.json")
    expected = {"toy": (7728, 6440, 38640, [23,21,16], True),
                "local1": (14406816, 14104011, 84624066, [376,412,93], False),
                "repeat1": (14406816, 14104011, 84624066, [376,412,93], False)}
    for mode, (nodes, cells, tets, sizes, capacity) in expected.items():
        summary = record["modes"][mode]["result"]["summary"]
        assert (summary["tensor_node_upper_bound"], summary["dielectric_cells"], summary["tetrahedra"]) == (nodes, cells, tets)
        assert summary["planning_checks"] == {"node_upper_bound": capacity, "tetrahedron_count": capacity, "jacobian_condition_bound": True}
        report = a.contract.read_json(ROOT / a.DIRECTORY / f"{mode}.report.json")
        assert [v["point_count"] for v in report["axes"]] == sizes
        assert all(v["base_planes_mm"] == v["canonical_planes_mm"] for v in report["axes"])
        assert report["width_budget"]["far_spacing_reduced"] is not capacity
