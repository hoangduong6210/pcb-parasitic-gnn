"""Metadata-only archive checks; numerical fields are synthetic fixtures."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code/experiments/proofs"), str(REPO / "code/solvers")]
import archive_tcad_cps_hxt_postopt_v1 as archive
from test_tcad_cps_hxt_postopt import P, result
from scientific_artifact import atomic_write_json, sha256_file


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def fixture(root, outcome="pass"):
    record = {"scheduler": {"JobId": archive.JOB, "NodeList": "test-node", "NumCPUs": "41"},
              "modes": {}, "failure": None}
    directory = root / archive.DIRECTORY
    directory.mkdir(parents=True)
    for mode in P["hxt_postopt"]["modes"][:1 if outcome == "incomplete" else 3]:
        passed = not (outcome == "incomplete" and mode == "toy")
        arm = {"passed": passed, "failure": None if passed else "worker exited 1; retain stderr"}
        if passed:
            arm["result"] = result(mode)
            if outcome == "negative" and mode == "repeat1":
                arm["result"]["mesh_sha256"] = "b"*64
        record["modes"][mode] = arm
        atomic_write_json(directory / f"{mode}.json", arm)
        (directory / f"{mode}.stdout").write_text("synthetic native log\n")
        (directory / f"{mode}.stderr").write_text("")
    record.update(archive.contract.assessment(record, P))
    atomic_write_json(directory / "attempt.json", record)
    for src, _ in archive.log_pairs():
        (root / src).parent.mkdir(exist_ok=True)
        (root / src).write_text("synthetic scheduler log\n")
    row = dict(zip(archive.COLUMNS, [archive.JOB, "FAILED" if outcome == "incomplete" else "COMPLETED",
                   "2:0" if outcome == "incomplete" else "0:0", "0", "100", "41", "160G", "test-node"]))
    raw = "|".join(row[k] for k in archive.COLUMNS)
    return record, raw, [row]


def prepare_fixture(monkeypatch, tmp_path, outcome="pass"):
    source = tmp_path / "execution"
    source.mkdir()
    record, raw, rows = fixture(source, outcome)
    protocol = tmp_path / archive.contract.PROTOCOL
    protocol.parent.mkdir(parents=True)
    shutil.copyfile(REPO / archive.contract.PROTOCOL, protocol)
    receipt = {"job_id": archive.JOB, "source_commit": archive.COMMIT, "lock_sha256": archive.LOCK_SHA,
               "protocol_sha256": sha256_file(protocol)}
    atomic_write_json(tmp_path / archive.SUBMISSION, receipt)
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    # The immutable 51-test validator owns receipt semantics. These fixtures
    # isolate new collector/closure behavior, rather than duplicating it.
    monkeypatch.setattr(archive, "review_attempt", lambda _: record)
    monkeypatch.setattr(archive, "accounting", lambda _: (raw, rows))
    monkeypatch.setattr(archive.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=archive.COMMIT + "\n"))
    return source, record, raw, rows


@pytest.mark.parametrize("outcome", ["pass", "negative", "incomplete"])
def test_collect_and_check_all_outcomes(monkeypatch, tmp_path, outcome):
    source, record, _, _ = prepare_fixture(monkeypatch, tmp_path, outcome)
    manifest = archive.collect(source)
    assert archive.check_archive() == manifest
    assert manifest["diagnosis"]["complete"] == (outcome != "incomplete")
    assert manifest["diagnosis"]["diagnostic_passed"] == (outcome == "pass")
    assert manifest["diagnosis"]["mesh_feasible"] is False
    assert len(manifest["files_sha256"]) == (8 if outcome == "incomplete" else 14)
    for key in ("field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible", "automatic_expansion"):
        assert manifest["diagnosis"][key] is False
    before = {p: sha256_file(tmp_path / p) for p in manifest["files_sha256"]}
    with pytest.raises(ValueError, match="overwrite"):
        archive.collect(source)
    assert before == {p: sha256_file(tmp_path / p) for p in manifest["files_sha256"]}


@pytest.mark.parametrize("field,value", [("JobID", "1"), ("State", "RUNNING"), ("ExitCode", "1:0"),
    ("Restarts", "1"), ("ElapsedRaw", "3301"), ("ElapsedRaw", "nan"), ("ElapsedRaw", "0"),
    ("AllocCPUS", "1"), ("ReqMem", "200G"), ("NodeList", "other")])
def test_terminal_gate_precedes_writes(monkeypatch, tmp_path, field, value):
    source, _, _, rows = prepare_fixture(monkeypatch, tmp_path)
    rows[0][field] = value
    monkeypatch.setattr(archive, "accounting", lambda _: ("|".join(rows[0][k] for k in archive.COLUMNS), rows))
    with pytest.raises(ValueError):
        archive.collect(source)
    assert not (tmp_path / archive.DIRECTORY).exists()
    assert not (tmp_path / archive.MANIFEST).exists()


@pytest.mark.parametrize("corruption", ["member", "extra", "extra_log", "identity", "diagnosis", "numeric_flag", "accounting", "submission", "symlink"])
def test_archive_corruption_rejected(monkeypatch, tmp_path, corruption):
    source, _, _, _ = prepare_fixture(monkeypatch, tmp_path)
    manifest = archive.collect(source)
    if corruption == "member":
        (tmp_path / archive.DIRECTORY / "toy.stdout").write_text("changed")
    elif corruption == "extra":
        (tmp_path / archive.MANIFEST.parent / "extra").write_text("")
    elif corruption == "extra_log":
        (tmp_path / archive.MANIFEST.parent / "logs/extra").write_text("")
    elif corruption == "identity":
        manifest["source_commit"] = "other"
    elif corruption == "diagnosis":
        manifest["diagnosis"]["reference_qualified"] = True
    elif corruption == "numeric_flag":
        manifest["diagnosis"]["reference_qualified"] = 0
    elif corruption == "accounting":
        manifest["accounting"][0]["ExitCode"] = "1:0"
    elif corruption == "submission":
        receipt = archive.contract.read_json(tmp_path / archive.SUBMISSION)
        receipt["job_id"] = "other"
        atomic_write_json(tmp_path / archive.SUBMISSION, receipt)
        manifest["files_sha256"][str(archive.SUBMISSION)] = sha256_file(tmp_path / archive.SUBMISSION)
    elif corruption == "symlink":
        path = tmp_path / archive.DIRECTORY / "toy.stdout"
        path.rename(tmp_path / "target")
        path.symlink_to(tmp_path / "target")
    atomic_write_json(tmp_path / archive.MANIFEST, manifest)
    with pytest.raises(ValueError):
        archive.check_archive()


def test_metadata_reviewer_uses_frozen_validator_and_scrubs_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(archive, "sha256_file", lambda _: archive.LOCK_SHA)
    monkeypatch.setenv("GH_TOKEN", "synthetic-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-secret")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='{"complete":false}')
    monkeypatch.setattr(archive.subprocess, "run", run)
    assert archive.review_attempt(tmp_path) == {"complete": False}
    command, kwargs = calls[0]
    assert command[1] == "-c" and command[-1] == archive.JOB
    assert "validate_attempt" in command[2] and "check_source(execution=False)" in command[2]
    assert "GH_TOKEN" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
    assert kwargs["env"]["PCB_TCAD_SOURCE_COMMIT"] == archive.COMMIT
    assert kwargs["timeout"] == 60 and kwargs["check"] is True


def test_source_scope_and_raw_accounting(monkeypatch, tmp_path):
    source, _, raw, rows = prepare_fixture(monkeypatch, tmp_path)
    assert archive.parse_accounting(raw) == rows
    with pytest.raises(ValueError, match="malformed"):
        archive.parse_accounting(raw + "|extra")
    link = tmp_path / "linked-source"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        archive.collect(link)
    with pytest.raises(ValueError, match="separate"):
        archive.collect(tmp_path)
    monkeypatch.setattr(archive.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="other\n"))
    with pytest.raises(ValueError, match="commit"):
        archive.collect(source)
