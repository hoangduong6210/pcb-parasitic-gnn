"""Tiny synthetic exact arithmetic and execution/receipt boundary tests only."""
import copy
from fractions import Fraction
import itertools
import io
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock
from contextlib import redirect_stdout

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "code/experiments/proofs"), str(ROOT / "code/solvers")]
import tcad_cps_jacobian_arithmetic as c
import tcad_cps_jacobian_arithmetic_worker as worker
import tcad_cps_jacobian_exact as exact
import run_tcad_cps_jacobian_arithmetic as runner
from tcad_cps_dielectric_mesh_bundle import write_bundle
from scientific_artifact import sha256_file, atomic_write_json

P = c.protocol()
LIMITS = P["worker_limits"]["raw"]


@pytest.fixture(autouse=True)
def release_synthetic_files(tmp_path):
    yield
    shutil.rmtree(tmp_path)


def packet(points=None, native=1.):
    xyz = np.array(points if points is not None else [[0.,0.,0.], [1.,0.,0.], [0.,1.,0.], [0.,0.,1.]])
    tags = np.arange(2**53+10, 2**53+14, dtype=np.int64)
    return {"node_tags": tags, "coordinates_mm": xyz, "tetrahedron_tags": np.array([123]),
        "tetrahedron_nodes": tags[None, :].copy(), "tetrahedron_volumes": np.array([7]),
        "triangle_tags": np.arange(21, 25), "triangle_nodes": tags[np.array(list(itertools.combinations(range(4), 3)))],
        "triangle_faces": np.arange(31, 35), "min_sicn": np.array([.5]), "min_det_jac_mm3": np.array([native])}


@pytest.mark.parametrize("perm", list(itertools.permutations(range(4))))
def test_exact_orientation_all_permutations(perm):
    p = [[Fraction(v) for v in row] for row in [[0,0,0], [1,0,0], [0,1,0], [0,0,1]]]
    expected = (-1)**sum(perm[i] > perm[j] for i in range(4) for j in range(i+1,4))
    assert exact.triple([p[i] for i in perm]) == expected
    assert exact.homogeneous([p[i] for i in perm]) == expected


@pytest.mark.parametrize("scale,offset", [(1,0), (.5,16), (8,-16), (2**-20, .125)])
def test_exact_translation_scale(scale, offset):
    a = packet()
    a["coordinates_mm"] = a["coordinates_mm"]*scale+offset
    a["min_det_jac_mm3"][:] = scale**3
    r = exact.diagnose(a, LIMITS, 1e-8)
    row = r["rows"][0]
    assert row["exact_determinant_mm3"] == exact.rational(Fraction.from_float(scale)**3)
    assert r["summary"]["original_gate_mismatches"] == 0
    assert row["node_tags"] == a["node_tags"].tolist()
    assert all(r[k] is False for k in c.CLOSED)


def test_exact_zero_retained_and_no_relative_divide_by_zero():
    a = packet([[0,0,0], [.1,.2,.3], [.7,.8,.9], [.2,.4,.6]], native=1e-18)
    r = exact.diagnose(a, LIMITS, 1e-8)
    row = r["rows"][0]
    assert r["summary"]["sign_counts"]["exact"]["zero"] == 1
    assert row["exact_determinant_mm3"] == {"numerator": "0", "denominator": "1"}
    assert row["errors_against_exact"]["native"]["relative"] is None
    assert not row["errors_against_exact"]["native"]["within_rtol"]
    assert "coordinates_hex_mm" in row


def test_exact_binary_value_not_intended_decimal_or_rounded_edges():
    a = packet([[.1,0,0], [1.,0,0], [.1,1,0], [.1,0,1]], native=.9)
    r = exact.diagnose(a, LIMITS, 1e-8)
    truth = Fraction(1)-Fraction.from_float(.1)
    assert truth != Fraction.from_float(.9) and truth != Fraction(9,10)
    assert r["rows"][0]["exact_determinant_mm3"] == exact.rational(truth)


@pytest.mark.parametrize("native", [-1., 0., 1., 2.])
def test_disagreement_is_diagnostic_not_suppressed(native):
    r = exact.diagnose(packet(native=native), LIMITS, 1e-8)
    assert r["summary"]["original_gate_mismatches"] == (native != 1.)
    assert len(r["rows"]) == 1 and r["summary"]["exact_methods_agree"]
    assert r["boundary_contract_passed"] is False


def test_exact_method_disagreement_fails(monkeypatch):
    monkeypatch.setattr(exact, "homogeneous", lambda p: Fraction(2))
    with pytest.raises(ValueError, match="methods disagree"):
        exact.diagnose(packet(), LIMITS, 1e-8)


@pytest.mark.parametrize("kind", ["nan", "unknown", "cap", "duplicate", "tolerance"])
def test_malformed_input_rejected(kind):
    a, limits, tol = packet(), dict(LIMITS), 1e-8
    if kind == "nan": a["coordinates_mm"][0,0] = np.nan
    if kind == "unknown": a["tetrahedron_nodes"][0,0] += 100
    if kind == "cap": limits["mesh_tetrahedra_max"] = 0
    if kind == "duplicate": a["node_tags"][0] = a["node_tags"][1]
    if kind == "tolerance": tol = 0
    with pytest.raises(ValueError):
        exact.diagnose(a, limits, tol)


def setup_worker(monkeypatch, tmp_path):
    p = copy.deepcopy(P)
    a = packet()
    report = exact.diagnose(a, LIMITS, 1e-8)
    for spec in p[c.PHASE]["inputs"].values():
        spec.update(packet_sha256=report["packet_sha256"], tetrahedra=1)
    monkeypatch.setattr(c, "ROOT", tmp_path)
    monkeypatch.setattr(c, "protocol", lambda: p)
    monkeypatch.setattr(c, "check_source", lambda **kw: {})
    monkeypatch.setattr(c, "check_allocation", lambda *a: {"JobId": "123"})
    monkeypatch.setattr(c, "check_runtime", lambda *a: runner.expected_runtime(p))
    monkeypatch.setattr(c, "identity", lambda: {"source_commit": "synthetic"})
    monkeypatch.setenv("SLURM_JOB_ID", "123")
    directory = c.attempt_directory("123", create=True)
    bundle = tmp_path / "input"
    write_bundle(bundle, a, p[c.parent.PHASE]["payload"])
    monkeypatch.setattr(c, "input_path", lambda *a: bundle)
    return p, directory


@pytest.mark.parametrize("guard", ["check_allocation", "check_source", "check_runtime"])
@pytest.mark.parametrize("entry", [worker, runner])
def test_entry_points_fail_before_numeric_work(monkeypatch, tmp_path, guard, entry):
    setup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(c, guard, Mock(side_effect=ValueError("guard failure")))
    numeric = Mock(side_effect=AssertionError("numeric work before guard"))
    monkeypatch.setattr(exact, "diagnose", numeric)
    monkeypatch.setattr(runner, "run", numeric)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "raw"])
    with pytest.raises(ValueError, match="guard failure"):
        entry.main()
    numeric.assert_not_called()


@pytest.mark.parametrize("mode", ["raw", "final", "repeat_final"])
def test_synthetic_worker_complete_receipt(monkeypatch, tmp_path, capsys, mode):
    p, directory = setup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", mode])
    worker.main()
    result = json.loads(capsys.readouterr().out.split("RESULT=")[1])
    runner.validate_result(result, mode, p, "123", directory)
    assert result["summary"]["tetrahedra"] == 1
    with pytest.raises(FileExistsError):
        worker.main()


@pytest.mark.parametrize("mutation", ["hash", "size", "packet", "mode", "job", "runtime", "claim", "time", "rss", "summary", "report_bytes"])
def test_result_mutation_rejected(monkeypatch, tmp_path, capsys, mutation):
    p, directory = setup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", "raw"])
    worker.main()
    r = json.loads(capsys.readouterr().out.split("RESULT=")[1])
    if mutation == "hash": r["report_sha256"] = "0"*64
    if mutation == "size": r["report_bytes"] += 1
    if mutation == "packet": r["packet_sha256"] = "0"*64
    if mutation == "mode": r["mode"] = "final"
    if mutation == "job": r["scheduler"]["JobId"] = "124"
    if mutation == "runtime": r["runtime"] = {}
    if mutation == "claim": r["claim_eligible"] = True
    if mutation == "time": r["elapsed_s"] = 181
    if mutation == "rss": r["peak_rss_gib"] = 7
    if mutation == "summary": r["summary"]["exact_methods_agree"] = False
    if mutation == "report_bytes":
        with (directory / "raw.report.json").open("a") as stream: stream.write(" ")
    with pytest.raises(ValueError):
        runner.validate_result(r, "raw", p, "123", directory)


def test_repeat_hash_and_complete_coverage_required():
    record = {"failure": None, "modes": {m: {"passed": True, "result": {"report_sha256": "abc"}} for m in P[c.PHASE]["modes"]}}
    assert c.assessment(record, P)["diagnostic_passed"]
    record["modes"]["repeat_final"]["result"]["report_sha256"] = "xyz"
    assert not c.assessment(record, P)["diagnostic_passed"]
    record["modes"].pop("repeat_final")
    assert not c.assessment(record, P)["complete"]
    assert all(c.assessment(record, P)[k] is False for k in c.CLOSED)


def test_frozen_source_byte_only():
    if not (ROOT / c.LOCK).exists():
        pytest.skip("pre-freeze only")
    assert c.check_source(execution=False)["files_sha256"]


def test_inheritance_and_wrapper():
    assert P["runtime"] == c.parent.protocol()["runtime"]
    assert P[c.PHASE]["jacobian_rtol"] == 1e-8 and P[c.PHASE]["jacobian_atol"] == 0
    text = (ROOT / c.WRAPPER).read_text()
    for value in ("--mem=8G", "--time=00:15:00", "--cpus-per-task=1", "--no-requeue", "PYTHONDONTWRITEBYTECODE=1"):
        assert value in text


def test_unknown_mode_and_symlink_attempt_rejected(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="unfrozen"):
        c.input_kind("repair", P)
    monkeypatch.setattr(c, "ROOT", tmp_path)
    destination = tmp_path / c.BASE
    destination.parent.mkdir(parents=True)
    destination.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        c.attempt_directory("123", create=True)


def test_changed_source_lock_fails_closed(monkeypatch):
    monkeypatch.setattr(c, "read_json", lambda path: {"files_sha256": {"changed": "abc"}})
    monkeypatch.setattr(c, "frozen_lock", lambda: {"files_sha256": {"changed": "def"}})
    with pytest.raises(ValueError, match="source/input lock"):
        c.check_source(execution=False)


def test_no_active_allocation_rejected(monkeypatch):
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("PCB_TCAD_BATCH_PHASE", c.PHASE)
    with pytest.raises(ValueError, match="login-node"):
        c.check_allocation(c.PHASE, P)


def synthetic_arm(monkeypatch, directory, mode):
    monkeypatch.setattr(sys, "argv", ["worker", "--mode", mode])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        worker.main()
    output = buffer.getvalue()
    (directory / f"{mode}.stdout").write_text(output)
    (directory / f"{mode}.stderr").write_text("")
    result = json.loads(output.split("RESULT=")[1])
    record = {"mode": mode, "passed": True, "returncode": 0, "failure": None,
        "elapsed_s": 1., "observed_peak_rss_gib": .1, "files_sha256": runner.mode_files(directory, mode), "result": result}
    atomic_write_json(directory / f"{mode}.json", record)
    return record


def complete_attempt(monkeypatch, tmp_path):
    p, directory = setup_worker(monkeypatch, tmp_path)
    record = {**c.identity(), "scheduler": {"JobId": "123"}, "runtime": runner.expected_runtime(p),
        "failure": None, "modes": {m: synthetic_arm(monkeypatch, directory, m) for m in p[c.PHASE]["modes"]}}
    record.update(c.assessment(record, p))
    atomic_write_json(directory / "attempt.json", record)
    return p, directory, record


def test_complete_synthetic_attempt_byte_review(monkeypatch, tmp_path):
    p, directory, record = complete_attempt(monkeypatch, tmp_path)
    monkeypatch.setattr(exact, "diagnose", Mock(side_effect=AssertionError("numeric replay forbidden in verifier")))
    assert runner.validate_attempt(directory, p) == record
    assert record["diagnostic_passed"] and record["repeatability_passed"]


@pytest.mark.parametrize("mutation", ["extra", "symlink", "log", "receipt", "skip", "flag", "restart_mode"])
def test_attempt_mutations_fail(monkeypatch, tmp_path, mutation):
    p, directory, record = complete_attempt(monkeypatch, tmp_path)
    if mutation == "extra": (directory / "extra").write_text("extra")
    if mutation == "symlink": (directory / "extra").symlink_to(directory / "raw.stdout")
    if mutation == "log": (directory / "raw.stdout").write_text("changed")
    if mutation == "receipt": record["modes"]["raw"]["returncode"] = 2
    if mutation == "skip": record["modes"].pop("raw")
    if mutation == "flag": record["claim_eligible"] = True
    if mutation == "restart_mode": record["modes"]["raw"]["passed"] = False
    atomic_write_json(directory / "attempt.json", record)
    with pytest.raises(ValueError):
        runner.validate_attempt(directory, p)


@pytest.mark.parametrize("cap", ["time", "rss"])
def test_parent_watchdog_kills_and_retains_partial_output(monkeypatch, tmp_path, cap):
    p, directory = setup_worker(monkeypatch, tmp_path)
    fake = Mock(pid=12345, returncode=None)
    fake.poll.return_value = None
    fake.wait.side_effect = lambda: setattr(fake, "returncode", -9)
    def popen(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        assert "GH_TOKEN" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]
        (directory / "raw.report.json").write_text("partial")
        return fake
    monkeypatch.setenv("GH_TOKEN", "synthetic-do-not-forward")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-do-not-forward")
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    monkeypatch.setattr(runner.time, "monotonic", Mock(side_effect=[0., 181. if cap == "time" else 1., 182. if cap == "time" else 2.]))
    monkeypatch.setattr(runner, "rss_gib", lambda pid: 7. if cap == "rss" else .1)
    kill = Mock()
    monkeypatch.setattr(runner.os, "killpg", kill)
    record = runner.bounded_mode(directory, "raw", p)
    assert record["passed"] is False and "cap exceeded" in record["failure"]
    assert "raw.report.json" in record["files_sha256"]
    kill.assert_called_once_with(12345, runner.signal.SIGKILL)


def test_parent_stops_after_first_failed_worker(monkeypatch, tmp_path):
    p, directory = setup_worker(monkeypatch, tmp_path)
    original = c.attempt_directory
    monkeypatch.setattr(c, "attempt_directory", lambda job, **kw: original(job))
    calls = []
    def failed(directory, mode, p):
        calls.append(mode)
        for suffix in ("stdout", "stderr"):
            (directory / f"{mode}.{suffix}").write_text("failure")
        record = {"mode": mode, "passed": False, "returncode": 2, "failure": "synthetic failure",
            "elapsed_s": 1., "observed_peak_rss_gib": .1, "files_sha256": runner.mode_files(directory, mode)}
        atomic_write_json(directory / f"{mode}.json", record)
        return record
    monkeypatch.setattr(runner, "bounded_mode", failed)
    assert not runner.run(p, {"JobId": "123"}, runner.expected_runtime(p))
    assert calls == ["raw"]
    assert runner.validate_attempt(directory, p)["complete"] is False
