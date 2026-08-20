"""Solver-free tests for the FEM-repeatability post-finalizer admission."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
ADMISSION_PATH = (
    ROOT
    / "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py"
)


def _load_admission() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fem_repeatability_final_admission_for_test", ADMISSION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _protocol() -> dict[str, Any]:
    return {
        "resources": {
            "finalizer": {
                "account": "pgs0407",
                "allocated_cpus_may_exceed_request": True,
                "cpus_per_task": 2,
                "memory_gib": 8,
                "nodes": 1,
                "ntasks": 1,
                "partition": "nextgen",
                "time_limit": "00:30:00",
            }
        }
    }


def _accounting_row(
    *, finalizer_job_id: str = "7300000", allocated_cpu: int = 3
) -> dict[str, str]:
    return {
        "JobID": finalizer_job_id,
        "JobIDRaw": finalizer_job_id,
        "State": "COMPLETED",
        "ExitCode": "0:0",
        "Account": "pgs0407",
        "Partition": "nextgen",
        "Timelimit": "00:30:00",
        "NodeList": "nextgen0027",
        "Restarts": "0",
        "ElapsedRaw": "93",
        "ReqTRES": "billing=2,cpu=2,mem=8G,node=1",
        "AllocTRES": (
            f"billing={allocated_cpu},cpu={allocated_cpu},mem=8G,node=1"
        ),
    }


def _accounting_text(row: dict[str, str], fields: tuple[str, ...]) -> str:
    return "|".join(row[name] for name in fields) + "|\n"


def _preterminal_payload(
    *,
    protocol_sha256: str,
    source_head: str,
    source_job: str = "7100000",
    finalizer_job: str = "7300000",
    provisional: bool = True,
    allocated_cpu: int = 3,
) -> dict[str, Any]:
    arm_a_pass = provisional
    summary_decision = {
        "arm_a_all_gates_pass": arm_a_pass,
        "arm_b_repeatability_gates_pass": True,
        "paired_latency_preflight_may_resume": False,
        "provisional_preterminal_gate_pass": provisional,
        "terminal_accounting_gate_applied": True,
        "tolerance_changed": False,
    }
    return {
        "admission_eligible": False,
        "artifact_stage": "preterminal_finalizer_output",
        "claim_eligible": False,
        "created_utc": "2026-08-20T12:00:00+00:00",
        "decision": {
            "all_15_scheduler_rows_completed_zero": provisional,
            "arm_a_all_gates_pass": arm_a_pass,
            "paired_latency_preflight_may_resume": False,
            "provisional_preterminal_gate_pass": provisional,
        },
        "post_run_admission": {
            "finalizer_job_id": finalizer_job,
            "required": True,
            "required_exit_code": "0:0",
            "required_state": "COMPLETED",
            "terminal_accounting_verified": False,
        },
        "protocol_sha256": protocol_sha256,
        "provenance": {
            "finalizer_scheduler": {
                "job_id": finalizer_job,
                "scheduler_record": {
                    "ReqTRES": "cpu=2,mem=8G,node=1,billing=2",
                    "AllocTRES": (
                        f"node=1,mem=8G,cpu={allocated_cpu},billing={allocated_cpu}"
                    ),
                },
            },
            "source_git_head": source_head,
        },
        "repeatability_summary": {"decision": summary_decision},
        "schema": "pcb-gnn.corpus-v4-fem-repeatability-final.v1",
        "source_array": {"array_job_id": source_job},
        "speed_claim_eligible": False,
    }


def _materialize_preterminal(
    module: ModuleType,
    root: Path,
    *,
    provisional: bool = True,
    allocated_cpu: int = 3,
) -> tuple[str, str, str, str]:
    source_job = "7100000"
    finalizer_job = "7300000"
    protocol_sha = "a" * 64
    source_head = "b" * 40
    result_dir = (
        root
        / "results/corpus_v4/fem_repeatability/v1/final"
        / f"source_job_{source_job}"
        / f"finalizer_job_{finalizer_job}"
    )
    result = _preterminal_payload(
        protocol_sha256=protocol_sha,
        source_head=source_head,
        provisional=provisional,
        allocated_cpu=allocated_cpu,
    )
    result_path = result_dir / "result.json"
    _write_json(result_path, result)
    _write_json(
        result_dir / "FINAL_MANIFEST.json",
        {
            "files_sha256": {"result.json": _sha256(result_path)},
            "finalizer_job_id": finalizer_job,
            "protocol_sha256": protocol_sha,
            "schema": "pcb-gnn.corpus-v4-fem-repeatability-final-manifest.v1",
            "source_array_job_id": source_job,
        },
    )
    module.ROOT = root
    return source_job, finalizer_job, protocol_sha, source_head


def _accounting_provenance(
    module: ModuleType, finalizer_job: str, row: dict[str, str]
) -> dict[str, Any]:
    raw = _accounting_text(row, module.ACCOUNTING_FIELDS)
    return {
        "canonical_rows_sha256": hashlib.sha256(
            module.canonical_json_bytes([row])
        ).hexdigest(),
        "command": module.accounting_command(finalizer_job),
        "queried_utc": "2026-08-20T12:01:00+00:00",
        "raw_stdout_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "row_count": 1,
    }


def test_positive_receipt_is_the_only_artifact_that_opens_resume(
    tmp_path: Path,
) -> None:
    admission = _load_admission()
    admission.validate_preterminal_payload = lambda *args, **kwargs: None
    source_job, finalizer_job, protocol_sha, source_head = _materialize_preterminal(
        admission, tmp_path, provisional=True, allocated_cpu=3
    )
    reference = admission.validate_preterminal_final(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
    )
    row = _accounting_row(allocated_cpu=3)
    payload = admission.build_admission_payload(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
        final_reference=reference,
        accounting_rows=[row],
        accounting_provenance=_accounting_provenance(
            admission, finalizer_job, row
        ),
        validator_source_sha256="c" * 64,
        created_utc="2026-08-20T12:02:00+00:00",
    )
    assert payload["schema"] == (
        "pcb-gnn.corpus-v4-fem-repeatability-final-admission.v1"
    )
    assert payload["decision"] == {
        "paired_latency_preflight_may_resume": True,
        "provisional_preterminal_gate_pass": True,
        "terminal_finalizer_completed_zero": True,
    }
    assert payload["claim_eligible"] is False
    assert payload["speed_claim_eligible"] is False
    assert payload["finalizer"]["job_id"] == finalizer_job
    assert payload["finalizer"]["job_id_raw"] == finalizer_job
    assert payload["finalizer"]["accounting"]["tres"]["AllocTRES"]["cpu"] == "3"


def test_receipt_semantic_replay_rejects_forged_reference_or_live_accounting(
    tmp_path: Path,
) -> None:
    admission = _load_admission()
    admission.validate_preterminal_payload = lambda *args, **kwargs: None
    source_job, finalizer_job, protocol_sha, source_head = _materialize_preterminal(
        admission, tmp_path, provisional=True, allocated_cpu=3
    )
    reference = admission.validate_preterminal_final(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
    )
    row = _accounting_row(allocated_cpu=3)
    payload = admission.build_admission_payload(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
        final_reference=reference,
        accounting_rows=[row],
        accounting_provenance=_accounting_provenance(
            admission, finalizer_job, row
        ),
        validator_source_sha256="c" * 64,
        created_utc="2026-08-20T12:02:00+00:00",
    )

    observed = admission.validate_admission_payload(
        payload,
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
        expected_validator_source_sha256="c" * 64,
        live_accounting_rows=[row],
    )
    assert observed == reference

    forged_reference = copy.deepcopy(payload)
    forged_reference["preterminal_final"]["final_result_path"] = "forged/result.json"
    with pytest.raises(ValueError, match="preterminal reference"):
        admission.validate_admission_payload(
            forged_reference,
            protocol=_protocol(),
            protocol_sha256=protocol_sha,
            expected_source_git_head=source_head,
            source_array_job_id=source_job,
            finalizer_job_id=finalizer_job,
            expected_validator_source_sha256="c" * 64,
            live_accounting_rows=[row],
        )

    changed_live_row = _accounting_row(allocated_cpu=4)
    with pytest.raises(ValueError, match="TRES differs|accounting differs"):
        admission.validate_admission_payload(
            payload,
            protocol=_protocol(),
            protocol_sha256=protocol_sha,
            expected_source_git_head=source_head,
            source_array_job_id=source_job,
            finalizer_job_id=finalizer_job,
            expected_validator_source_sha256="c" * 64,
            live_accounting_rows=[changed_live_row],
        )


def test_negative_provisional_gate_writes_a_closed_receipt(tmp_path: Path) -> None:
    admission = _load_admission()
    admission.validate_preterminal_payload = lambda *args, **kwargs: None
    source_job, finalizer_job, protocol_sha, source_head = _materialize_preterminal(
        admission, tmp_path, provisional=False, allocated_cpu=2
    )
    reference = admission.validate_preterminal_final(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
    )
    row = _accounting_row(allocated_cpu=2)
    payload = admission.build_admission_payload(
        protocol=_protocol(),
        protocol_sha256=protocol_sha,
        expected_source_git_head=source_head,
        source_array_job_id=source_job,
        finalizer_job_id=finalizer_job,
        final_reference=reference,
        accounting_rows=[row],
        accounting_provenance=_accounting_provenance(
            admission, finalizer_job, row
        ),
        validator_source_sha256="c" * 64,
        created_utc="2026-08-20T12:02:00+00:00",
    )
    assert payload["decision"]["paired_latency_preflight_may_resume"] is False
    assert payload["decision"]["terminal_finalizer_completed_zero"] is True


def test_preterminal_manifest_hash_and_provisional_logic_fail_closed(
    tmp_path: Path,
) -> None:
    admission = _load_admission()
    admission.validate_preterminal_payload = lambda *args, **kwargs: None
    source_job, finalizer_job, protocol_sha, source_head = _materialize_preterminal(
        admission, tmp_path
    )
    result_path = (
        tmp_path
        / "results/corpus_v4/fem_repeatability/v1/final"
        / f"source_job_{source_job}/finalizer_job_{finalizer_job}/result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["decision"]["provisional_preterminal_gate_pass"] = False
    _write_json(result_path, result)
    manifest_path = result_path.parent / "FINAL_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files_sha256"]["result.json"] = _sha256(result_path)
    _write_json(manifest_path, manifest)
    with pytest.raises(ValueError, match="provisional decision"):
        admission.validate_preterminal_final(
            protocol=_protocol(),
            protocol_sha256=protocol_sha,
            expected_source_git_head=source_head,
            source_array_job_id=source_job,
            finalizer_job_id=finalizer_job,
        )

    result["decision"]["provisional_preterminal_gate_pass"] = True
    _write_json(result_path, result)
    with pytest.raises(ValueError, match="manifest bindings"):
        admission.validate_preterminal_final(
            protocol=_protocol(),
            protocol_sha256=protocol_sha,
            expected_source_git_head=source_head,
            source_array_job_id=source_job,
            finalizer_job_id=finalizer_job,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("JobID", "7300001", "job identity"),
        ("JobIDRaw", "7300001", "job identity"),
        ("State", "FAILED", "COMPLETED/0:0"),
        ("ExitCode", "1:0", "COMPLETED/0:0"),
        ("Account", "wrong", "scheduler identity"),
        ("Partition", "wrong", "scheduler identity"),
        ("Timelimit", "00:29:59", "scheduler identity"),
        ("NodeList", "(null)", "scheduler identity"),
        ("Restarts", "1", "scheduler identity"),
        ("ElapsedRaw", "0", "scheduler identity"),
        ("ElapsedRaw", "1801", "scheduler identity"),
        ("ReqTRES", "billing=3,cpu=3,mem=8G,node=1", "ReqTRES"),
        ("AllocTRES", "billing=1,cpu=1,mem=8G,node=1", "AllocTRES"),
    ],
)
def test_terminal_accounting_rejects_identity_or_resource_drift(
    field: str, value: str, message: str
) -> None:
    admission = _load_admission()
    row = _accounting_row(allocated_cpu=3)
    row[field] = value
    retained = {
        "ReqTRES": {"billing": "2", "cpu": "2", "mem": "8G", "node": "1"},
        "AllocTRES": {"billing": "3", "cpu": "3", "mem": "8G", "node": "1"},
    }
    with pytest.raises(ValueError, match=message):
        admission.validate_finalizer_accounting(
            [row], "7300000", _protocol(), retained
        )


def test_terminal_allocation_must_match_preterminal_scheduler_provenance() -> None:
    admission = _load_admission()
    retained = {
        "ReqTRES": {"billing": "2", "cpu": "2", "mem": "8G", "node": "1"},
        "AllocTRES": {"billing": "2", "cpu": "2", "mem": "8G", "node": "1"},
    }
    with pytest.raises(ValueError, match="preterminal provenance"):
        admission.validate_finalizer_accounting(
            [_accounting_row(allocated_cpu=3)], "7300000", _protocol(), retained
        )


def test_parser_and_live_query_expose_no_accounting_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _load_admission()
    arguments = [
        "--expected-protocol-sha256",
        "a" * 64,
        "--expected-source-git-head",
        "b" * 40,
        "--source-array-job-id",
        "7100000",
        "--finalizer-job-id",
        "7300000",
    ]
    parsed = admission.parse_args(arguments)
    assert not hasattr(parsed, "accounting_file")

    row = _accounting_row(allocated_cpu=3)
    raw = _accounting_text(row, admission.ACCOUNTING_FIELDS)
    observed: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> SimpleNamespace:
        observed.append(command)
        return SimpleNamespace(returncode=0, stdout=raw, stderr="")

    monkeypatch.setattr(admission.subprocess, "run", fake_run)
    rows, provenance = admission.query_live_finalizer_accounting("7300000")
    assert rows == [row]
    assert observed == [admission.accounting_command("7300000")]
    assert "7100000" not in observed[0]
    assert provenance["row_count"] == 1


def test_clean_source_authentication_rejects_dirty_or_untracked_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission = _load_admission()
    admission.ROOT = tmp_path
    validator = tmp_path / admission.VALIDATOR_SOURCE
    validator.parent.mkdir(parents=True)
    validator.write_text("# validator\n", encoding="utf-8")
    source_head = "d" * 40

    outputs = {
        ("rev-parse", "HEAD"): source_head + "\n",
        ("status", "--short", "--untracked-files=no"): " M README.md\n",
        (
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        ): "",
        ("ls-files", "--error-unmatch", admission.VALIDATOR_SOURCE): (
            admission.VALIDATOR_SOURCE + "\n"
        ),
    }
    monkeypatch.setattr(
        admission, "_git_output", lambda arguments: outputs[tuple(arguments)]
    )
    with pytest.raises(ValueError, match="clean tracked tree"):
        admission.authenticate_clean_source(source_head)
    outputs[("status", "--short", "--untracked-files=no")] = ""
    outputs[
        (
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        )
    ] = "?? code/new.py\n"
    with pytest.raises(ValueError, match="untracked source"):
        admission.authenticate_clean_source(source_head)
    outputs[
        (
            "status",
            "--short",
            "--untracked-files=all",
            "--",
            "code",
            "protocols",
            "requirements-proof.txt",
        )
    ] = ""
    identity = admission.authenticate_clean_source(source_head)
    assert identity == {
        "source_git_head": source_head,
        "validator_source_sha256": _sha256(validator),
    }


def test_protocol_authentication_closes_validator_and_input_bytes(
    tmp_path: Path,
) -> None:
    admission = _load_admission()
    admission.validate_protocol = lambda protocol: None
    admission.ROOT = tmp_path
    validator = tmp_path / admission.VALIDATOR_SOURCE
    input_path = tmp_path / "datasets/frozen.json"
    validator.parent.mkdir(parents=True)
    input_path.parent.mkdir(parents=True)
    validator.write_text("# validator\n", encoding="utf-8")
    input_path.write_text("{}\n", encoding="utf-8")
    protocol = {
        "artifact_contract": {
            "post_finalizer_terminal_admission_required": True,
            "terminal_accounting_required": True,
        },
        "computational_sources": {
            admission.VALIDATOR_SOURCE: _sha256(validator),
        },
        "diagnostic_semantics": {
            "claim_eligible": False,
            "speed_claim_eligible": False,
        },
        "inputs": {
            "frozen": {
                "path": "datasets/frozen.json",
                "sha256": _sha256(input_path),
            }
        },
        "resources": _protocol()["resources"],
        "schema": admission.PROTOCOL_SCHEMA,
    }
    protocol_path = tmp_path / admission.PROTOCOL_RELATIVE
    _write_json(protocol_path, protocol)
    observed, identity = admission.authenticate_protocol(
        Path(admission.PROTOCOL_RELATIVE), _sha256(protocol_path)
    )
    assert observed == protocol
    assert identity["source_sha256"] == protocol["computational_sources"]
    assert identity["input_sha256"] == {"frozen": _sha256(input_path)}

    input_path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="input SHA-256 mismatch"):
        admission.authenticate_protocol(
            Path(admission.PROTOCOL_RELATIVE), _sha256(protocol_path)
        )


def test_receipt_write_is_canonical_atomic_and_non_overwriting(
    tmp_path: Path,
) -> None:
    admission = _load_admission()
    admission.ROOT = tmp_path
    payload = {
        "preterminal_final": {
            "finalizer_job_id": "7300000",
            "source_array_job_id": "7100000",
        },
        "schema": admission.ADMISSION_SCHEMA,
    }
    output = admission.canonical_admission_path("7100000", "7300000")
    admission.write_immutable_json(output, payload)
    assert json.loads(output.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError, match="immutable"):
        admission.write_immutable_json(output, payload)


def test_parser_rejects_extra_or_multiple_rows() -> None:
    admission = _load_admission()
    row = _accounting_row()
    raw = _accounting_text(row, admission.ACCOUNTING_FIELDS)
    parsed = admission.parse_accounting(raw)
    retained = {
        "ReqTRES": {"billing": "2", "cpu": "2", "mem": "8G", "node": "1"},
        "AllocTRES": {"billing": "3", "cpu": "3", "mem": "8G", "node": "1"},
    }
    with pytest.raises(ValueError, match="exactly one"):
        admission.validate_finalizer_accounting(
            parsed + [copy.deepcopy(parsed[0])],
            "7300000",
            _protocol(),
            retained,
        )
    with pytest.raises(ValueError, match="field count"):
        admission.parse_accounting(raw.rstrip("\n") + "unexpected|\n")
