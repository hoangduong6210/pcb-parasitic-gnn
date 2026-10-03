"""Metadata/hash-only collector regression; no native CAD or numerical replay."""
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code/experiments/proofs"), str(REPO / "code/solvers")]
import archive_tcad_cps_dielectric_cad_v1 as archive
from test_tcad_cps_dielectric_cad import P, result
from scientific_artifact import atomic_write_json, sha256_file


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def prepare(monkeypatch, tmp_path, outcome="pass"):
    source = tmp_path / "execution"
    directory = source / archive.DIRECTORY
    directory.mkdir(parents=True)
    record = {"scheduler": {"JobId": archive.JOB, "NodeList": "test-node", "NumCPUs": "3"}, "modes": {}, "failure": None}
    length = 1 if outcome == "toy_failure" else 2 if outcome == "sentinel_timeout" else 3
    modes = P["dielectric_cad"]["modes"][:length]
    incomplete = length != 3
    for mode in modes:
        passed = not (incomplete and mode == modes[-1])
        arm = {"passed": passed, "failure": None if passed else "worker wall-time cap exceeded"}
        if passed:
            arm["result"] = result(mode, split=outcome == "negative" and mode == "repeat1")
        record["modes"][mode] = arm
        atomic_write_json(directory / f"{mode}.json", arm)
        (directory / f"{mode}.stdout").write_text("synthetic native log\n")
        (directory / f"{mode}.stderr").write_text("")
    record.update(archive.contract.assessment(record, P))
    atomic_write_json(directory / "attempt.json", record)
    for src, _ in archive.log_pairs():
        (source / src).parent.mkdir(exist_ok=True)
        (source / src).write_text("synthetic scheduler log\n")
    protocol = tmp_path / archive.contract.PROTOCOL
    protocol.parent.mkdir(parents=True)
    shutil.copyfile(REPO / archive.contract.PROTOCOL, protocol)
    atomic_write_json(tmp_path / archive.SUBMISSION, {"job_id": archive.JOB, "source_commit": archive.COMMIT,
        "lock_sha256": archive.LOCK_SHA, "protocol_sha256": sha256_file(protocol)})
    row = dict(zip(archive.COLUMNS, [archive.JOB, "FAILED" if incomplete else "COMPLETED",
        "2:0" if incomplete else "0:0", "0", "100", "3", "8G", "test-node"]))
    raw = "|".join(row[k] for k in archive.COLUMNS)
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    # The frozen CAD runner owns full receipt semantics; isolate collector checks.
    monkeypatch.setattr(archive, "review_attempt", lambda _: record)
    monkeypatch.setattr(archive, "accounting", lambda _: (raw, [row]))
    monkeypatch.setattr(archive.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=archive.COMMIT + "\n"))
    return source, record, row


@pytest.mark.parametrize("outcome,count", [("pass", 14), ("negative", 14), ("toy_failure", 8), ("sentinel_timeout", 11)])
def test_collect_exact_outcomes(monkeypatch, tmp_path, outcome, count):
    source, _, _ = prepare(monkeypatch, tmp_path, outcome)
    manifest = archive.collect(source)
    assert archive.check_archive() == manifest
    assert len(manifest["files_sha256"]) == count
    assert manifest["diagnosis"]["diagnostic_passed"] == (outcome == "pass")
    for key in ("mesh_generated", "mesh_feasible", "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible"):
        assert manifest["diagnosis"][key] is False
    before = {p: sha256_file(tmp_path / p) for p in manifest["files_sha256"]}
    with pytest.raises(ValueError, match="overwrite"):
        archive.collect(source)
    assert before == {p: sha256_file(tmp_path / p) for p in manifest["files_sha256"]}


@pytest.mark.parametrize("field,value", [("JobID", "1"), ("State", "RUNNING"), ("ExitCode", "1:0"),
    ("Restarts", "1"), ("ElapsedRaw", "901"), ("ElapsedRaw", "nan"), ("ElapsedRaw", "0"),
    ("AllocCPUS", "1"), ("ReqMem", "160G"), ("NodeList", "other")])
def test_nonterminal_or_wrong_accounting_prevents_writes(monkeypatch, tmp_path, field, value):
    source, _, row = prepare(monkeypatch, tmp_path)
    row[field] = value
    monkeypatch.setattr(archive, "accounting", lambda _: ("|".join(row[k] for k in archive.COLUMNS), [row]))
    with pytest.raises(ValueError):
        archive.collect(source)
    assert not (tmp_path / archive.DIRECTORY).exists()


@pytest.mark.parametrize("corruption", ["member", "extra", "extra_log", "identity", "diagnosis", "numeric_flag", "accounting", "submission", "symlink"])
def test_archive_corruption_rejected(monkeypatch, tmp_path, corruption):
    source, _, _ = prepare(monkeypatch, tmp_path)
    manifest = archive.collect(source)
    if corruption == "member": (tmp_path / archive.DIRECTORY / "toy.stdout").write_text("changed")
    elif corruption == "extra": (tmp_path / archive.MANIFEST.parent / "extra").write_text("")
    elif corruption == "extra_log": (tmp_path / archive.MANIFEST.parent / "logs/extra").write_text("")
    elif corruption == "identity": manifest["source_commit"] = "other"
    elif corruption == "diagnosis": manifest["diagnosis"]["reference_qualified"] = True
    elif corruption == "numeric_flag": manifest["diagnosis"]["reference_qualified"] = 0
    elif corruption == "accounting": manifest["accounting"][0]["ExitCode"] = "1:0"
    elif corruption == "submission":
        receipt = archive.contract.read_json(tmp_path / archive.SUBMISSION)
        receipt["job_id"] = "other"
        atomic_write_json(tmp_path / archive.SUBMISSION, receipt)
        manifest["files_sha256"][str(archive.SUBMISSION)] = sha256_file(tmp_path / archive.SUBMISSION)
    else:
        path = tmp_path / archive.DIRECTORY / "toy.stdout"
        path.rename(tmp_path / "target")
        path.symlink_to(tmp_path / "target")
    atomic_write_json(tmp_path / archive.MANIFEST, manifest)
    with pytest.raises(ValueError):
        archive.check_archive()


def test_metadata_reviewer_scrubs_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(archive, "sha256_file", lambda _: archive.LOCK_SHA)
    monkeypatch.setenv("GH_TOKEN", "synthetic-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-secret")
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout='{"complete":true}')
    monkeypatch.setattr(archive.subprocess, "run", run)
    assert archive.review_attempt(tmp_path) == {"complete": True}
    command, kwargs = calls[0]
    assert "check_source(execution=False)" in command[2] and "validate_attempt" in command[2]
    assert "GH_TOKEN" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
    assert kwargs["env"]["PCB_TCAD_SOURCE_COMMIT"] == archive.COMMIT
    assert kwargs["timeout"] == 60 and kwargs["check"] is True


def test_source_and_accounting_scope(monkeypatch, tmp_path):
    source, _, row = prepare(monkeypatch, tmp_path)
    raw = "|".join(row[k] for k in archive.COLUMNS)
    assert archive.parse_accounting(raw) == [row]
    with pytest.raises(ValueError, match="malformed"):
        archive.parse_accounting(raw + "|extra")
    link = tmp_path / "linked"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        archive.collect(link)
    with pytest.raises(ValueError, match="separate"):
        archive.collect(tmp_path)
    monkeypatch.setattr(archive.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="other\n"))
    with pytest.raises(ValueError, match="commit"):
        archive.collect(source)


def test_preserved_native_cad_archive():
    manifest = archive.check_archive()
    assert sha256_file(REPO / archive.MANIFEST) == "31704965e6b2b725ae5f8abc40dd4c30481f79874024aa1873bbd68c327122e0"
    assert len(manifest["files_sha256"]) == 14
    assert manifest["accounting"] == [dict(zip(archive.COLUMNS,
        ["7651941", "COMPLETED", "0:0", "0", "51", "3", "8G", "a0102"]))]
    state = manifest["diagnosis"]
    assert state["complete"] is True and state["diagnostic_passed"] is True and state["repeatability_passed"] is True
    for key in ("mesh_generated", "mesh_feasible", "field_solver_executed", "reference_qualified", "training_may_start", "claim_eligible"):
        assert state[key] is False
    record = json.loads((REPO / archive.DIRECTORY / "attempt.json").read_text())
    results = {m: arm["result"] for m, arm in record["modes"].items()}
    assert results["toy"]["cad_report_sha256"] == "ffbf35380c0d76c808a49d79309b8830e34091e887b7f59c33c56045ce7e33ad"
    assert results["local1"]["cad_report"] == results["repeat1"]["cad_report"]
    assert results["local1"]["cad_report_sha256"] == "185994c79376c221d5d4dfc3cbc893988669eafe8cad9f2223f3f89c78d76dc7"
    for mode, value in results.items():
        summary = value["cad_summary"]
        assert summary["retained_volumes"] == 1 and len(summary["outer_faces"]) == 6
        assert summary["before_entity_counts"]["3"] == (3 if mode == "toy" else 27)
        assert summary["after_entity_counts"] == ({"0": 24, "1": 36, "2": 18, "3": 1} if mode == "toy" else {"0": 216, "1": 324, "2": 162, "3": 1})
        assert (REPO / archive.DIRECTORY / f"{mode}.stderr").read_bytes() == b""
        assert not any(k in value for k in ("cps_pf", "mesh_sha256", "system_sha256"))
