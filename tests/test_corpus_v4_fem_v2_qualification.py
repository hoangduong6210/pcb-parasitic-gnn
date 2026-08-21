from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code/experiments/proofs"))

import admit_corpus_v4_fem_v2_qualification as admit  # noqa: E402
import finalize_corpus_v4_fem_v2_qualification as finalize  # noqa: E402
import run_corpus_v4_fem_v2_qualification as runner  # noqa: E402


PROTOCOL_PATH = ROOT / "protocols/corpus_v4_fem_v2_qualification_v1.json"


def load_protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def payload(protocol: dict, stage: str, task: dict, cps_pf: float) -> dict:
    identity = f"{task['layout_id']:064x}"
    return {
        "stage": stage,
        "task": task,
        "worker_result": {
            "cps_pf": cps_pf,
            "mesh_nodes": 1000 + task["layout_id"],
            "mesh_tetrahedra": 5000 + task["layout_id"],
            "system_sha256": identity,
        },
    }


def test_protocol_freezes_dense_stage_mappings_and_canonical_root(tmp_path: Path) -> None:
    protocol = load_protocol()
    runner.validate_protocol(protocol)
    assert [len(runner.stage_tasks(protocol, stage)) for stage in runner.STAGES] == [45, 9, 21]
    assert [row["layout_id"] for row in runner.stage_tasks(protocol, "gate_a")[:6]] == [1055] * 5 + [407]
    assert runner.canonical_output_root(Path(runner.OUTPUT_ROOT_RELATIVE), "root") == (
        ROOT / runner.OUTPUT_ROOT_RELATIVE
    ).resolve()
    with pytest.raises(ValueError, match="must equal"):
        runner.canonical_output_root(tmp_path, "root")


def test_gate_a_replays_repeatability_and_mesh_identity() -> None:
    protocol = load_protocol()
    tasks = runner.stage_tasks(protocol, "gate_a")
    payloads = [payload(protocol, "gate_a", task, 10.0 + task["layout_id"] / 1000) for task in tasks]
    summary = finalize.summarize_gate_a(payloads, protocol)
    assert summary["gate_pass"] is True
    assert [row["repeat_id"] for row in summary["canonical_repeat0"]] == [0] * 9

    changed = copy.deepcopy(payloads)
    changed[1]["worker_result"]["system_sha256"] = "f" * 64
    assert finalize.summarize_gate_a(changed, protocol)["gate_pass"] is False


def test_gate_c_negative_mesh_delta_does_not_block_multifidelity_qualification() -> None:
    protocol = load_protocol()
    gate_a_tasks = runner.stage_tasks(protocol, "gate_a")
    gate_a_payloads = [payload(protocol, "gate_a", task, 10.0) for task in gate_a_tasks]
    gate_a_result = {"qualification_summary": finalize.summarize_gate_a(gate_a_payloads, protocol)}
    gate_c_payloads = [
        payload(protocol, "gate_c", task, 20.0)
        for task in runner.stage_tasks(protocol, "gate_c")
    ]
    summary = finalize.summarize_gate_c(gate_c_payloads, gate_a_result, protocol)
    assert summary["repeatability_pass"] is True
    assert summary["mesh_threshold_pass"] is False
    assert summary["multifidelity_qualification_pass"] is True
    assert summary["gate_pass"] is True
    assert (
        finalize.classify_scientific_outcome("gate_c", summary, True)
        == "SCIENTIFIC_NEGATIVE"
    )


def test_gate_b_threshold_and_gate_c_repeatability_fail_closed() -> None:
    protocol = load_protocol()
    gate_a_payloads = [
        payload(protocol, "gate_a", task, 10.0)
        for task in runner.stage_tasks(protocol, "gate_a")
    ]
    gate_a_result = {
        "qualification_summary": finalize.summarize_gate_a(
            gate_a_payloads, protocol
        )
    }
    gate_b_payloads = [
        payload(protocol, "gate_b", task, 10.0)
        for task in runner.stage_tasks(protocol, "gate_b")
    ]
    assert finalize.summarize_gate_b(
        gate_b_payloads, gate_a_result, protocol
    )["gate_pass"] is True
    gate_b_payloads[0]["worker_result"]["cps_pf"] = 20.0
    negative_domain = finalize.summarize_gate_b(
        gate_b_payloads, gate_a_result, protocol
    )
    assert negative_domain["gate_pass"] is False
    assert negative_domain["domain_delta"]["maximum_pct"] == 50.0

    gate_c_payloads = [
        payload(protocol, "gate_c", task, 20.0)
        for task in runner.stage_tasks(protocol, "gate_c")
    ]
    gate_c_payloads[2]["worker_result"]["system_sha256"] = "f" * 64
    negative_repeatability = finalize.summarize_gate_c(
        gate_c_payloads, gate_a_result, protocol
    )
    assert negative_repeatability["repeatability_pass"] is False
    assert negative_repeatability["multifidelity_qualification_pass"] is False
    assert negative_repeatability["gate_pass"] is False


def test_repeatability_and_percent_delta_boundaries_are_inclusive() -> None:
    protocol = load_protocol()
    gate_a_tasks = runner.stage_tasks(protocol, "gate_a")
    gate_a_payloads = [payload(protocol, "gate_a", task, 10.0) for task in gate_a_tasks]

    boundary_value = 10.0 / (1.0 - 1.0e-4)
    gate_a_payloads[1]["worker_result"]["cps_pf"] = boundary_value
    observed_spread = finalize.max_pairwise_relative([10.0, boundary_value])
    boundary_protocol = copy.deepcopy(protocol)
    boundary_protocol["gates"]["repeatability_max_relative"] = observed_spread
    assert finalize.summarize_gate_a(gate_a_payloads, boundary_protocol)["gate_pass"] is True
    boundary_protocol["gates"]["repeatability_max_relative"] = math.nextafter(
        observed_spread, 0.0
    )
    assert finalize.summarize_gate_a(gate_a_payloads, boundary_protocol)["gate_pass"] is False

    reference_by_layout = {
        anchor["layout_id"]: (49.0 if index < 8 else 95.0)
        for index, anchor in enumerate(protocol["anchors"])
    }
    admitted_gate_a = {
        "qualification_summary": finalize.summarize_gate_a(
            [
                payload(
                    protocol,
                    "gate_a",
                    task,
                    reference_by_layout[task["layout_id"]],
                )
                for task in gate_a_tasks
            ],
            protocol,
        )
    }
    gate_b_payloads = [
        payload(protocol, "gate_b", task, 50.0 if index < 8 else 100.0)
        for index, task in enumerate(runner.stage_tasks(protocol, "gate_b"))
    ]
    boundary = finalize.summarize_gate_b(gate_b_payloads, admitted_gate_a, protocol)
    assert boundary["gate_pass"] is True
    assert boundary["domain_delta"]["median_pct"] == pytest.approx(2.0)
    assert boundary["domain_delta"]["maximum_pct"] == pytest.approx(5.0)

    gate_b_payloads[-1]["worker_result"]["cps_pf"] = 101.0
    assert finalize.summarize_gate_b(
        gate_b_payloads, admitted_gate_a, protocol
    )["gate_pass"] is False


def test_prerequisite_identity_and_terminal_accounting_are_exact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    protocol = load_protocol()
    admission_path = (
        tmp_path
        / "admission/gate_a/source_job_100/finalizer_job_101/FINAL_ADMISSION.json"
    )
    admission_path.parent.mkdir(parents=True)
    admission = {
        "artifact_stage": "postterminal_finalizer_admission",
        "decision": {
            "next_stage": "gate_b",
            "next_stage_may_run": True,
            "qualification_stage_pass": True,
        },
        "protocol_sha256": "a" * 64,
        "schema": runner.ADMISSION_SCHEMA,
        "source_git_head": "b" * 40,
        "stage": "gate_a",
    }
    admission_path.write_text(json.dumps(admission), encoding="utf-8")
    admission_sha = hashlib.sha256(admission_path.read_bytes()).hexdigest()
    accepted = runner.validate_prerequisite(
        stage="gate_b",
        path=admission_path,
        expected_sha256=admission_sha,
        protocol_sha256="a" * 64,
        expected_source_git_head="b" * 40,
        output_root=tmp_path,
    )
    assert accepted is not None and accepted["stage"] == "gate_a"
    with pytest.raises(ValueError, match="positive predecessor"):
        runner.validate_prerequisite(
            stage="gate_b",
            path=admission_path,
            expected_sha256=admission_sha,
            protocol_sha256="a" * 64,
            expected_source_git_head="c" * 40,
            output_root=tmp_path,
        )

    fields = finalize.ACCOUNTING_FIELDS
    rows = []
    for task_id in range(45):
        row = {
            "JobID": f"100_{task_id}",
            "JobIDRaw": str(1000 + task_id),
            "State": "COMPLETED",
            "ExitCode": "0:0",
            "Account": "pgs0407",
            "Partition": "nextgen",
            "Timelimit": "02:00:00",
            "NodeList": f"a{task_id % 8:04d}",
            "Restarts": "0",
            "ElapsedRaw": "500",
            "ReqTRES": "billing=1,cpu=1,mem=48G,node=1",
            "AllocTRES": "billing=12,cpu=12,mem=48G,node=1",
        }
        assert set(row) == set(fields)
        rows.append(row)
    terminal = finalize.validate_terminal_accounting(
        rows,
        source_array_job_id="100",
        protocol=protocol,
        stage="gate_a",
    )
    assert len(terminal) == 45
    assert all(row["terminal_success"] for row in terminal)
    with pytest.raises(ValueError, match="exact dense coverage"):
        finalize.validate_terminal_accounting(
            rows[:-1],
            source_array_job_id="100",
            protocol=protocol,
            stage="gate_a",
        )


def test_stage_wrappers_freeze_all_three_resource_profiles() -> None:
    expected = {
        "gate_a": ("0-44%8", "48G", "02:00:00"),
        "gate_b": ("0-8%8", "48G", "02:00:00"),
        "gate_c": ("0-20%2", "160G", "03:00:00"),
    }
    for stage, (array, memory, limit) in expected.items():
        path = ROOT / f"code/jobs/submit_corpus_v4_fem_v2_{stage}.sh"
        text = path.read_text(encoding="utf-8")
        assert f"#SBATCH --array={array}" in text
        assert f"#SBATCH --mem={memory}" in text
        assert f"#SBATCH --time={limit}" in text
        assert f"--stage {stage}" in text
        finalizer = (
            ROOT / f"code/jobs/submit_finalize_corpus_v4_fem_v2_{stage}.sh"
        ).read_text(encoding="utf-8")
        assert f"--stage {stage}" in finalizer


def test_postterminal_admission_rejects_consistently_rehashed_pass_flip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Editing result and manifest together cannot bypass semantic replay."""
    protocol = load_protocol()
    tampered = {
        "decision": {
            "all_source_tasks_completed_zero": True,
            "provisional_multifidelity_v2_may_start": False,
            "provisional_qualification_stage_pass": True,
            "provisional_r3_v2_generation_may_start": False,
            "scientific_outcome": "POSITIVE",
        },
        "provenance": {"finalizer_scheduler": {}},
        "qualification_summary": {"gate_pass": True, "stage": "gate_a"},
        "source_array": {"artifacts": [], "terminal_accounting": [{"terminal_success": True}]},
    }
    monkeypatch.setattr(admit, "canonical_output_root", lambda *_: tmp_path)
    monkeypatch.setattr(admit, "authenticate_protocol", lambda *_: (protocol, "a" * 64))
    monkeypatch.setattr(admit, "validate_inputs", lambda *_: ({}, {"input": "b" * 64}))
    monkeypatch.setattr(admit, "_assert_source_stable", lambda **_: {"source": "c" * 64})
    monkeypatch.setattr(admit, "load_preterminal", lambda **_: (tampered, {}))
    monkeypatch.setattr(admit, "query_finalizer", lambda *_: ({}, {}))
    monkeypatch.setattr(admit, "validate_finalizer_terminal", lambda *_, **__: None)
    monkeypatch.setattr(admit, "query_accounting", lambda *_, **__: ([{}], {}))
    source_rows = [{"terminal_success": True}]
    monkeypatch.setattr(admit, "validate_terminal_accounting", lambda *_, **__: source_rows)
    monkeypatch.setattr(admit, "validate_preterminal_provenance", lambda *_, **__: None)
    monkeypatch.setattr(admit, "validate_prerequisite", lambda **_: None)
    monkeypatch.setattr(admit, "repo_relative", lambda path, *_: str(path))
    monkeypatch.setattr(admit, "load_tasks", lambda **_: ([{}], []))
    monkeypatch.setattr(
        admit,
        "build_summary",
        lambda *_: {"gate_pass": False, "stage": "gate_a"},
    )
    with pytest.raises(ValueError, match="summary does not replay"):
        admit.main(
            [
                "--stage", "gate_a",
                "--expected-protocol-sha256", "a" * 64,
                "--expected-source-git-head", "d" * 40,
                "--source-array-job-id", "101",
                "--finalizer-job-id", "102",
            ]
        )


def test_postterminal_admission_preserves_indeterminate_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    protocol = load_protocol()
    source_rows = [{"terminal_success": False}]
    preterminal = {
        "decision": {
            "all_source_tasks_completed_zero": False,
            "provisional_multifidelity_v2_may_start": False,
            "provisional_qualification_stage_pass": False,
            "provisional_r3_v2_generation_may_start": False,
            "scientific_outcome": "INDETERMINATE",
        },
        "prerequisite_admission": None,
        "provenance": {"finalizer_scheduler": {}},
        "source_array": {"artifacts": [], "terminal_accounting": source_rows},
    }
    monkeypatch.setattr(admit, "canonical_output_root", lambda *_: tmp_path)
    monkeypatch.setattr(admit, "authenticate_protocol", lambda *_: (protocol, "a" * 64))
    monkeypatch.setattr(admit, "validate_inputs", lambda *_: ({}, {"input": "b" * 64}))
    monkeypatch.setattr(admit, "_assert_source_stable", lambda **_: {"source": "c" * 64})
    monkeypatch.setattr(admit, "load_preterminal", lambda **_: (preterminal, {"bound": True}))
    monkeypatch.setattr(admit, "query_finalizer", lambda *_: ({}, {"terminal": True}))
    monkeypatch.setattr(admit, "validate_finalizer_terminal", lambda *_, **__: None)
    monkeypatch.setattr(admit, "query_accounting", lambda *_, **__: ([{}], {}))
    monkeypatch.setattr(admit, "validate_terminal_accounting", lambda *_, **__: source_rows)
    monkeypatch.setattr(admit, "validate_preterminal_provenance", lambda *_, **__: None)
    monkeypatch.setattr(admit, "validate_prerequisite", lambda **_: None)
    monkeypatch.setattr(admit, "repo_relative", lambda path, *_: str(path))

    admit.main(
        [
            "--stage", "gate_a",
            "--expected-protocol-sha256", "a" * 64,
            "--expected-source-git-head", "d" * 40,
            "--source-array-job-id", "101",
            "--finalizer-job-id", "102",
        ]
    )
    receipt = json.loads(
        (
            tmp_path
            / "admission/gate_a/source_job_101/finalizer_job_102/FINAL_ADMISSION.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["admission_eligible"] is False
    assert receipt["decision"]["qualification_stage_pass"] is False
    assert receipt["decision"]["scientific_outcome"] == "INDETERMINATE"
    assert receipt["decision"]["next_stage_may_run"] is False


def test_preterminal_provenance_replay_rejects_rehashed_tampering() -> None:
    protocol = load_protocol()
    source_hashes = protocol["computational_sources"]
    bindings = {"geometry": "a" * 64}
    accounting = {
        "canonical_rows_sha256": "b" * 64,
        "command": ["sacct", "-j", "101"],
        "origin": "live_sacct",
        "queried_utc": "2026-08-21T00:00:00+00:00",
        "raw_stdout_sha256": "c" * 64,
        "row_count": 45,
        "schema": finalize.ACCOUNTING_PROVENANCE_SCHEMA,
    }
    result = {
        "provenance": {
            "accounting": accounting,
            "executed_batch_sha256": source_hashes[
                finalize.FINALIZER_WRAPPERS["gate_a"]
            ],
            "finalizer_scheduler": {},
            "input_bindings": bindings,
            "source_git_head": "d" * 40,
            "source_sha256": source_hashes,
        }
    }
    admit.validate_preterminal_provenance(
        result,
        protocol=protocol,
        stage="gate_a",
        source_git_head="d" * 40,
        input_bindings=bindings,
        source_hashes=source_hashes,
        live_accounting=accounting,
    )
    tampered = copy.deepcopy(result)
    tampered["provenance"]["accounting"]["canonical_rows_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="accounting provenance"):
        admit.validate_preterminal_provenance(
            tampered,
            protocol=protocol,
            stage="gate_a",
            source_git_head="d" * 40,
            input_bindings=bindings,
            source_hashes=source_hashes,
            live_accounting=accounting,
        )


def test_finalizer_terminal_receipt_replays_allocated_resources() -> None:
    protocol = load_protocol()
    row = {
        "JobID": "102",
        "JobIDRaw": "102",
        "State": "COMPLETED",
        "ExitCode": "0:0",
        "Account": "pgs0407",
        "Partition": "nextgen",
        "Timelimit": "00:30:00",
        "NodeList": "a0001",
        "Restarts": "0",
        "ElapsedRaw": "12",
        "ReqTRES": "billing=2,cpu=2,mem=16G,node=1",
        "AllocTRES": "billing=4,cpu=4,mem=16G,node=1",
    }
    retained = {
        "allocated_cpus_per_task": 4,
        "job_id": "102",
        "memory_mb": 16384,
        "scheduler_record": {
            "Account": "pgs0407",
            "AllocTRES": row["AllocTRES"],
            "JobId": "102",
            "NodeList": "a0001",
            "Partition": "nextgen",
            "ReqTRES": row["ReqTRES"],
            "TimeLimit": "00:30:00",
        },
    }
    admit.validate_finalizer_terminal(
        row, protocol=protocol, retained=retained, finalizer_job_id="102"
    )
    tampered = copy.deepcopy(retained)
    tampered["scheduler_record"]["Partition"] = "wrong"
    with pytest.raises(ValueError, match="postterminal contract"):
        admit.validate_finalizer_terminal(
            row, protocol=protocol, retained=tampered, finalizer_job_id="102"
        )
