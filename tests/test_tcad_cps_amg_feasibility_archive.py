"""Metadata-only terminal-archive tests; all new numerical values are fixtures."""
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "code/experiments/proofs"), str(REPO / "code/solvers")]
import archive_tcad_cps_amg_feasibility_v1 as archive
from test_tcad_cps_amg_feasibility import synthetic_result
from scientific_artifact import atomic_write_json, sha256_file


@pytest.fixture(autouse=True)
def release_synthetic_fixture_files(tmp_path):
    """Keep per-run inode use bounded; never touch research artifacts."""
    yield
    shutil.rmtree(tmp_path)


def fixture(root, outcome="pass"):
    p = archive.contract.protocol()
    smoke = archive.directory("smoke")
    shutil.copytree(REPO / smoke, root / smoke)
    fields = ["JobID", "State", "ExitCode", "Restarts", "ElapsedRaw", "AllocCPUS", "ReqMem", "NodeList"]
    rows = [dict(zip(fields, values)) for values in [
        ["7650458", "COMPLETED", "0:0", "0", "8", "3", "8G", "a0102"],
        ["7650556", "COMPLETED", "0:0", "0", "100", "41", "160G", "test-node"],
        ["7650557", "COMPLETED", "0:0", "0", "2", "3", "8G", "test-node"],
    ]]
    complete = outcome != "incomplete"
    if not complete:
        for row in rows[1:]:
            row.update(State="FAILED", ExitCode="2:0")
    identity = archive.expected_identity()
    runtime = archive.expected_runtime(p)
    smoke_binding = {"job_id": "7650458", "attempt_sha256": archive.SMOKE_SHA, "accounting": [rows[0]]}
    record = {**identity, "scheduler": {"JobId": "7650556"}, "runtime": runtime,
              "phase": "feasibility", "layout_id": 597, "passed": complete, "failure": None,
              "smoke": smoke_binding, "arms": {}}
    path = root / archive.directory("feasibility")
    path.mkdir(parents=True)
    for spec in archive.contract.arms_for("feasibility", p)[:7 if complete else 2]:
        name = spec["name"]
        passed = complete or name == "local0"
        result = synthetic_result(name=name)
        result.update(identity, scheduler={"JobId": "7650556"}, runtime=runtime)
        if outcome == "negative" and name == "support1":
            result["cps_pf"] = 106.
        (path / f"{name}.stdout").write_text("RESULT=" + json.dumps(result) + "\n" if passed else "STAGE={}\n")
        (path / f"{name}.stderr").write_text("" if passed else "fixture worker timeout\n")
        arm = {"arm": spec, "passed": passed, "returncode": 0 if passed else -9,
               "failure": None if passed else "worker wall-time cap exceeded",
               "elapsed_s": 10 if passed else 1200.5, "observed_peak_rss_gib": .1,
               "files_sha256": {f"{name}.{suffix}": sha256_file(path / f"{name}.{suffix}") for suffix in ("stdout", "stderr")}}
        if passed:
            arm["result"] = result
        record["arms"][name] = arm
        atomic_write_json(path / f"{name}.json", arm)
    atomic_write_json(path / "attempt.json", record)
    final = root / archive.directory("finalize")
    final.mkdir(parents=True)
    (final / "sacct.txt").write_text("|".join(rows[1][key] for key in fields) + "\n")
    summary = {**identity, **archive.contract.assess_feasibility(record if complete else {}, p),
               "scheduler": {"JobId": "7650557"}, "runtime": runtime, "feasibility_job_id": "7650556",
               "attempt_sha256": sha256_file(path / "attempt.json"), "accounting": [rows[1]],
               "accounting_sha256": sha256_file(final / "sacct.txt"), "smoke": smoke_binding,
               "observed_arms": {n: {"passed": a["passed"], "failure": a["failure"]} for n, a in record["arms"].items()},
               "errors": [] if complete else ["AMG feasibility did not complete with zero exit and restarts"]}
    atomic_write_json(final / "summary.json", summary)
    for src, _ in archive.log_pairs():
        (root / src).parent.mkdir(exist_ok=True)
        (root / src).write_text("synthetic scheduler log\n")
    return rows


@pytest.mark.parametrize("outcome", ["pass", "negative", "incomplete"])
def test_review_retains_success_negative_and_incomplete(tmp_path, outcome):
    rows = fixture(tmp_path, outcome)
    diagnosis, members, smoke_members = archive.review(tmp_path, rows)
    assert diagnosis["complete"] == (outcome != "incomplete")
    assert diagnosis["feasibility_passed"] == (outcome == "pass")
    assert len(smoke_members) == 7
    assert len(members) == (24 if outcome != "incomplete" else 9)
    for key in ("reference_qualified", "three_sentinel_qualification", "continuum_convergence_established",
                "training_may_start", "claim_eligible", "automatic_expansion"):
        assert diagnosis[key] is False


@pytest.mark.parametrize("corruption", ["source", "runtime", "raw_log", "coverage", "comparison", "claim", "attempt_hash", "accounting", "observed", "extra_file", "symlink", "parent_nan"])
def test_review_rejects_corrupt_terminal_evidence(tmp_path, corruption):
    rows = fixture(tmp_path)
    attempt_path = tmp_path / archive.directory("feasibility") / "attempt.json"
    summary_path = tmp_path / archive.directory("finalize") / "summary.json"
    attempt = json.loads(attempt_path.read_text())
    summary = json.loads(summary_path.read_text())
    if corruption == "source":
        attempt["source_commit"] = "other"
    elif corruption == "runtime":
        attempt["runtime"]["threads"]["OMP_NUM_THREADS"] = "25"
    elif corruption == "raw_log":
        (attempt_path.parent / "local0.stdout").write_text("changed\n")
    elif corruption == "coverage":
        del attempt["arms"]["local0"]
    elif corruption == "comparison":
        summary["comparisons"]["mesh"]["relative_difference_pct"] = 99
    elif corruption == "claim":
        summary["reference_qualified"] = True
    elif corruption == "attempt_hash":
        summary["attempt_sha256"] = "0" * 64
    elif corruption == "accounting":
        (summary_path.parent / "sacct.txt").write_text("other\n")
    elif corruption == "observed":
        summary["observed_arms"]["local0"]["passed"] = False
    elif corruption == "extra_file":
        (attempt_path.parent / "unexpected.json").write_text("{}")
    elif corruption == "symlink":
        target = tmp_path / "redirected"
        (attempt_path.parent / "local0.stdout").rename(target)
        (attempt_path.parent / "local0.stdout").symlink_to(target)
    elif corruption == "parent_nan":
        attempt["arms"]["local0"]["elapsed_s"] = float("nan")
        (attempt_path.parent / "local0.json").write_text(json.dumps(attempt["arms"]["local0"]) + "\n")
    # NaN is deliberately serialized for this rejection test, not as a scientific artifact.
    attempt_path.write_text(json.dumps(attempt) + "\n")
    atomic_write_json(summary_path, summary)
    with pytest.raises(ValueError):
        archive.review(tmp_path, rows)


@pytest.mark.parametrize("change", ["running", "restart", "duplicate", "missing", "smoke_failed"])
def test_terminal_accounting_is_required(tmp_path, change):
    rows = fixture(tmp_path)
    if change == "running":
        rows[1]["State"] = "RUNNING"
    elif change == "restart":
        rows[1]["Restarts"] = "1"
    elif change == "duplicate":
        rows.append(copy.deepcopy(rows[1]))
    elif change == "missing":
        rows.pop()
    else:
        rows[0].update(State="FAILED", ExitCode="2:0")
    with pytest.raises(ValueError):
        archive.review(tmp_path, rows)


@pytest.mark.parametrize("outcome", ["pass", "negative", "incomplete"])
def test_collect_exact_bytes_and_refuse_overwrite(monkeypatch, tmp_path, outcome):
    source = tmp_path / "source"
    rows = fixture(source, outcome)
    shutil.copytree(source / archive.directory("smoke"), tmp_path / archive.directory("smoke"))
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    monkeypatch.setattr(archive, "accounting", lambda job: ("", [r for r in rows if r["JobID"] == job]))
    manifest = archive.collect(source)
    assert len(manifest["files_sha256"]) == (35 if outcome != "incomplete" else 20)
    assert archive.check_archive() == manifest
    for path, digest in manifest["files_sha256"].items():
        assert sha256_file(tmp_path / path) == digest
    with pytest.raises(ValueError, match="overwrite"):
        archive.collect(source)
    (tmp_path / archive.MANIFEST.parent / "logs/unlisted.txt").write_text("extra")
    with pytest.raises(ValueError, match="closure"):
        archive.check_archive()


def test_execution_source_lock_is_unchanged():
    archive.contract.check_source(execution=False)
    assert sha256_file(REPO / archive.contract.LOCK) == archive.LOCK_SHA


def test_actual_failed_study_archive_preserves_mesh_timeout():
    manifest = archive.check_archive()
    assert len(manifest["files_sha256"]) == 20
    assert sha256_file(REPO / archive.MANIFEST) == "d476cbf411192c4b4c109dfcb98551afe2ed39eb994211f19fdda04a65c628bc"
    diagnosis = manifest["diagnosis"]
    assert diagnosis["complete"] is False and diagnosis["feasibility_passed"] is False
    assert set(diagnosis["observed_arms"]) == {"local0", "local1"}
    assert diagnosis["observed_arms"]["local0"]["passed"] is True
    assert diagnosis["observed_arms"]["local1"] == {"passed": False, "failure": "worker wall-time cap exceeded"}
    raw = (REPO / archive.directory("feasibility") / "local1.stdout").read_text()
    stages = [json.loads(line[6:])["stage"] for line in raw.splitlines() if line.startswith("STAGE=")]
    assert stages == ["geometry_validated", "occ_fragmented", "mesh_generate_started"]
    assert "RESULT=" not in raw
