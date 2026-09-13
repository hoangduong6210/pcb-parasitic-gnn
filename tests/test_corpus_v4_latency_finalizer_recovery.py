"""Solver-free guards for finalizer-only recovery of unchanged latency data."""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))
sys.path.insert(0, str(ROOT / "code/core"))


def _verifier():
    path = ROOT / "code/quality/verify_corpus_v4_latency_archive_v3.py"
    spec = importlib.util.spec_from_file_location("latency_recovery_verifier", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_fixture():
    bindings = {
        "expected_source_git_head": "a" * 40,
        "expected_finalizer_source_git_head": "b" * 40,
        "execution_lock_sha256": "1" * 64,
        "finalizer_execution_lock_sha256": "2" * 64,
        "accepted_set_sha256": "3" * 64,
    }
    finalizer_lock = {"source_sha256": {"original.py": "4" * 64, "recovery.py": "5" * 64}}
    summary = {
        "bindings": copy.deepcopy(bindings),
        "provenance": {
            "source_git_head": "b" * 40,
            "source_sha256": copy.deepcopy(finalizer_lock["source_sha256"]),
        },
    }
    return bindings, finalizer_lock, summary


def test_summary_accepts_separate_task_and_finalizer_roots():
    bindings, lock, summary = _source_fixture()
    _verifier().validate_summary_source_roots(
        summary, expected_bindings=bindings, finalizer_lock=lock,
        expected_finalizer_source_git_head="b" * 40,
    )


@pytest.mark.parametrize("mutation", [
    "task_head", "finalizer_head", "accepted_set", "task_lock", "finalizer_lock",
    "old_provenance", "missing_recovery_source", "changed_source", "missing_provenance",
])
def test_summary_rejects_root_substitution(mutation):
    bindings, lock, summary = _source_fixture()
    names = {
        "task_head": "expected_source_git_head",
        "finalizer_head": "expected_finalizer_source_git_head",
        "accepted_set": "accepted_set_sha256",
        "task_lock": "execution_lock_sha256",
        "finalizer_lock": "finalizer_execution_lock_sha256",
    }
    if mutation in names:
        summary["bindings"][names[mutation]] = "changed"
    elif mutation == "old_provenance":
        summary["provenance"]["source_git_head"] = "a" * 40
    elif mutation == "missing_recovery_source":
        del summary["provenance"]["source_sha256"]["recovery.py"]
    elif mutation == "changed_source":
        summary["provenance"]["source_sha256"]["original.py"] = "0" * 64
    else:
        summary["provenance"] = None
    with pytest.raises(ValueError, match="source roots"):
        _verifier().validate_summary_source_roots(
            summary, expected_bindings=bindings, finalizer_lock=lock,
            expected_finalizer_source_git_head="b" * 40,
        )


def _accounting():
    return {
        "JobID": "9999999", "State": "COMPLETED", "ExitCode": "0:0",
        "Restarts": "0", "ElapsedRaw": "18", "Partition": "nextgen",
        "Timelimit": "00:20:00", "NodeList": "a0104", "Account": "pgs0407",
        "ReqTRES": "cpu=2,mem=8G,node=1,billing=2",
        "AllocTRES": "cpu=3,mem=8G,node=1,billing=3",
    }


def _mock_sacct(monkeypatch, verifier, row, returncode=0):
    text = "|".join(row.get(field, "") for field in verifier.PREFLIGHT_SACCT_FIELDS) + "|\n"
    monkeypatch.setattr(verifier.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=text, returncode=returncode,
    ))


def test_finalizer_completed_zero_is_required(monkeypatch):
    verifier = _verifier()
    _mock_sacct(monkeypatch, verifier, _accounting())
    completion = verifier._completion("9999999")
    assert completion["State"] == "COMPLETED"
    assert completion["ExitCode"] == "0:0"


@pytest.mark.parametrize("field,value", [
    ("State", "FAILED"), ("ExitCode", "1:0"), ("State", "RUNNING"),
    ("Restarts", "1"), ("ElapsedRaw", "0"), ("ElapsedRaw", "1201"),
    ("Partition", "debug"), ("Timelimit", "01:00:00"), ("NodeList", "Unknown"),
    ("JobID", "7271384"),
])
def test_failed_or_mismatched_finalizer_cannot_be_admitted(monkeypatch, field, value):
    verifier = _verifier()
    row = _accounting()
    row[field] = value
    _mock_sacct(monkeypatch, verifier, row)
    with pytest.raises(ValueError, match="COMPLETED/0:0"):
        verifier._completion("9999999")


def test_scheduler_query_failure_is_not_completion(monkeypatch):
    verifier = _verifier()
    _mock_sacct(monkeypatch, verifier, _accounting(), returncode=1)
    with pytest.raises(ValueError, match="COMPLETED/0:0"):
        verifier._completion("9999999")


def test_original_timing_sources_are_byte_identical():
    """Recovery must not silently change any of the 39 measurement sources."""
    lock = json.loads((ROOT / "protocols/corpus_v4_latency_fem_v2_execution_lock_v1.json").read_text())
    assert len(lock["source_sha256"]) == 39
    for name, digest in lock["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def test_recovery_uses_original_statistics_function():
    from finalize_corpus_v4_latency_v2 import summarize_records
    assert _verifier().summarize_records is summarize_records


@pytest.mark.parametrize("extra", ["symlink", "directory", "file"])
def test_analysis_inventory_rejects_unmanifested_children(tmp_path, extra):
    root = tmp_path / "analysis"
    root.mkdir()
    (root / "summary.json").write_text("{}")
    path = root / "extra"
    if extra == "symlink":
        path.symlink_to(root / "summary.json")
    elif extra == "directory":
        path.mkdir()
    else:
        path.write_text("extra")
    with pytest.raises(ValueError, match="inventory"):
        _verifier().validate_analysis_inventory(root, {"summary.json"})


def test_analysis_inventory_rejects_symlinked_root(tmp_path):
    root = tmp_path / "analysis"
    root.mkdir()
    (root / "summary.json").write_text("{}")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="ordinary directory"):
        _verifier().validate_analysis_inventory(alias, {"summary.json"})


def test_analysis_inventory_accepts_exact_ordinary_files(tmp_path):
    (tmp_path / "summary.json").write_text("{}")
    _verifier().validate_analysis_inventory(tmp_path, {"summary.json"})


def _lock_fixture():
    import corpus_v4_latency_finalizer_contract_v3 as contract
    task_path = ROOT / "protocols/corpus_v4_latency_fem_v2_execution_lock_v1.json"
    task_lock = json.loads(task_path.read_text())
    task_sha = hashlib.sha256(task_path.read_bytes()).hexdigest()
    payload = {
        "schema": contract.FINALIZER_LOCK_SCHEMA,
        "task_execution_lock_sha256": task_sha,
        "expected_task_source_git_head": "a" * 40,
        "accepted_set_sha256": "3" * 64,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in contract.FINALIZER_SOURCE_NAMES
        },
    }
    return contract, task_lock, task_sha, payload


def _validate_lock_fixture(tmp_path, fixture, payload):
    contract, task_lock, task_sha, _ = fixture
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(payload, sort_keys=True))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return contract.validate_finalizer_execution_lock(
        path, digest, task_lock=task_lock, task_lock_sha256=task_sha,
        accepted_set_sha256="3" * 64, expected_task_source_git_head="a" * 40,
    )


def test_finalizer_lock_authenticates_real_unchanged_source_closure(tmp_path):
    fixture = _lock_fixture()
    assert len(fixture[3]["source_sha256"]) == 44
    validated, _ = _validate_lock_fixture(tmp_path, fixture, fixture[3])
    assert validated == fixture[3]


@pytest.mark.parametrize("mutation", [
    "task_lock", "accepted_set", "task_head", "original_source", "recovery_source",
    "missing_source", "extra_source", "schema", "extra_field",
])
def test_finalizer_lock_rejects_independent_root_or_source_mutation(tmp_path, mutation):
    fixture = _lock_fixture()
    contract, _, _, original = fixture
    payload = copy.deepcopy(original)
    if mutation == "task_lock":
        payload["task_execution_lock_sha256"] = "0" * 64
    elif mutation == "accepted_set":
        payload["accepted_set_sha256"] = "0" * 64
    elif mutation == "task_head":
        payload["expected_task_source_git_head"] = "b" * 40
    elif mutation == "original_source":
        payload["source_sha256"][contract.EXECUTION_SOURCE_NAMES[0]] = "0" * 64
    elif mutation == "recovery_source":
        payload["source_sha256"]["code/quality/verify_corpus_v4_latency_archive_v3.py"] = "0" * 64
    elif mutation == "missing_source":
        payload["source_sha256"].pop(next(iter(payload["source_sha256"])))
    elif mutation == "extra_source":
        payload["source_sha256"]["unexpected.py"] = "0" * 64
    elif mutation == "schema":
        payload["schema"] = "unknown"
    else:
        payload["unreviewed"] = True
    with pytest.raises(ValueError):
        _validate_lock_fixture(tmp_path, fixture, payload)


def test_finalizer_lock_rejects_symlink_even_with_correct_bytes(tmp_path):
    fixture = _lock_fixture()
    contract, task_lock, task_sha, payload = fixture
    path = tmp_path / "real.json"
    path.write_text(json.dumps(payload))
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(ValueError, match="hash-mismatched"):
        contract.validate_finalizer_execution_lock(
            alias, hashlib.sha256(path.read_bytes()).hexdigest(),
            task_lock=task_lock, task_lock_sha256=task_sha,
            accepted_set_sha256="3" * 64, expected_task_source_git_head="a" * 40,
        )


def test_recovery_preserves_all_existing_scientific_functions():
    def functions(version):
        path = ROOT / f"code/experiments/proofs/finalize_corpus_v4_latency_v{version}.py"
        return {
            node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef)
        }
    old, new = functions(2), functions(3)
    excluded = {"main", "_parse_args", "_runtime_required", "validate_finalizer_source"}
    for name in old.keys() - excluded:
        assert new[name] == old[name], name


def test_recovery_reconstructs_identical_statistics_on_finite_fixture():
    from finalize_corpus_v4_latency_v2 import summarize_records as old_summary
    from finalize_corpus_v4_latency_v3 import summarize_records as new_summary
    from test_corpus_v4_latency_v2_pipeline import _base_record
    records = [
        _base_record(layout_id=1, family_id="a", fasthenry_ms=1.0, fem_ms=1.0),
        _base_record(layout_id=2, family_id="a", fasthenry_ms=50.0, fem_ms=50.0, inference_ms=10.0),
        _base_record(layout_id=3, family_id="b", fasthenry_ms=50.0, fem_ms=50.0, inference_ms=100.0),
        _base_record(layout_id=4, family_id="b", fasthenry_ms=4.0, fem_ms=4.0),
    ]
    kwargs = dict(expected_repetitions=200, bootstrap_resamples=1000, bootstrap_seed=20260820)
    assert new_summary(records, **kwargs) == old_summary(records, **kwargs)


@pytest.mark.parametrize("relative", [True, False])
def test_output_directory_handles_relative_and_absolute_paths(monkeypatch, relative):
    import finalize_corpus_v4_latency_v3 as finalizer
    monkeypatch.chdir(ROOT)
    root = Path("results/corpus_v4/latency_fem_v2/final")
    if not relative:
        root = ROOT / root
    output = finalizer.canonical_output_directory(root, "9999999")
    assert output.is_absolute()
    assert output.relative_to(ROOT).as_posix() == "results/corpus_v4/latency_fem_v2/final/job_9999999"


def test_output_directory_rejects_out_of_scope_location():
    import finalize_corpus_v4_latency_v3 as finalizer
    with pytest.raises((ValueError, SystemExit)):
        finalizer.canonical_output_directory(ROOT / "results/other", "9999999")
