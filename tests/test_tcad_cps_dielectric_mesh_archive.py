"""Byte-only preservation tests; actual mesh packets are never numerically loaded."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import archive_tcad_cps_dielectric_mesh_v1 as a
from scientific_artifact import atomic_write_json, sha256_file


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def prepare(monkeypatch, tmp_path):
    source = tmp_path / "execution"
    directory = source / a.DIRECTORY
    directory.mkdir(parents=True)
    paths = ["toy.stdout", "toy.stderr", "toy.payload/raw/partial.bin"]
    for name in paths:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic partial packet/log\n")
    arm = {"passed": False, "failure": "synthetic failure", "files_sha256": {n: sha256_file(directory / n) for n in paths}}
    record = {"scheduler": {"JobId": a.JOB, "NodeList": "test-node", "NumCPUs": "41"},
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
    row = dict(zip(a.COLUMNS, [a.JOB, "FAILED", "2:0", "0", "23", "41", "160G", "test-node"]))
    raw = "|".join(row[k] for k in a.COLUMNS)
    monkeypatch.setattr(a, "ROOT", tmp_path)
    # The immutable runner separately validates full receipt semantics.
    monkeypatch.setattr(a, "review_attempt", lambda _: record)
    monkeypatch.setattr(a, "accounting", lambda _: (raw, [row]))
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=a.COMMIT + "\n"))
    return source, record, row


def test_complete_partial_file_closure_and_no_overwrite(monkeypatch, tmp_path):
    source, record, _ = prepare(monkeypatch, tmp_path)
    manifest = a.collect(source)
    assert a.check_archive() == manifest
    assert len(manifest["files_sha256"]) == 9
    assert manifest["diagnosis"]["diagnostic_passed"] is False
    assert (tmp_path / a.DIRECTORY / "toy.payload/raw/partial.bin").read_bytes() == b"synthetic partial packet/log\n"
    with pytest.raises(ValueError, match="overwrite"):
        a.collect(source)


@pytest.mark.parametrize("field,value", [("JobID", "1"), ("State", "RUNNING"), ("ExitCode", "1:0"),
    ("Restarts", "1"), ("ElapsedRaw", "3301"), ("ElapsedRaw", "nan"), ("ElapsedRaw", "0"),
    ("AllocCPUS", "1"), ("ReqMem", "8G"), ("NodeList", "other")])
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
    if kind == "chunk": (tmp_path / a.DIRECTORY / "toy.payload/raw/partial.bin").write_bytes(b"changed")
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
        path = tmp_path / a.DIRECTORY / "toy.payload/raw/partial.bin"
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
        ["7652212", "FAILED", "2:0", "0", "23", "41", "160G", "a0116"]))]
    assert manifest["diagnosis"]["complete"] is False
    assert set(manifest["diagnosis"]["observed_modes"]) == {"toy"}
    err = (ROOT / a.DIRECTORY / "toy.stderr").read_text()
    assert "native and independently reconstructed Jacobians disagree" in err
    from tcad_cps_dielectric_mesh_bundle import check_bundle
    cfg = a.contract.protocol()[a.contract.PHASE]["payload"]
    expected = {"raw": ("7338595872a287e39b1ad7f978fcaab13c20cc4a30021ed5e768b1f05cb64807", 370448),
               "final": ("7a2b4c8a768bd2feb369e3be2c39531cf3a7c90ee7508cf6155bfc6a49e9b4f1", 363920)}
    for name, (digest, count) in expected.items():
        value = check_bundle(ROOT / a.DIRECTORY / f"toy.payload/{name}", cfg)
        assert value["packet_sha256"] == digest and value["payload_bytes"] == count
