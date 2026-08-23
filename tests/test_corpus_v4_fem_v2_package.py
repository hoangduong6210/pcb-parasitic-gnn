from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATH = ROOT / "code/experiments/proofs/corpus_v4_fem_v2_production.py"
PACKAGE_PATH = ROOT / "code/experiments/proofs/corpus_v4_fem_v2_package.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


production = load_module("corpus_v4_fem_v2_production", PRODUCTION_PATH)
package = load_module("corpus_v4_fem_v2_package", PACKAGE_PATH)
PROTOCOL = json.loads((ROOT / production.PROTOCOL_RELATIVE).read_text(encoding="utf-8"))


def manifest(count: int) -> list[dict]:
    return [
        {"geometry_sha256": f"{index:064x}", "layout_id": index, "task_index": index}
        for index in range(count)
    ]


def source_row(
    *, job_id: str = "123", local_id: int = 0, state: str = "COMPLETED", exit_code: str = "0:0"
) -> dict[str, str]:
    return {
        "JobID": f"{job_id}_{local_id}",
        "JobIDRaw": f"{job_id}_{local_id}",
        "State": state,
        "ExitCode": exit_code,
        "Account": "pgs0407",
        "Partition": "nextgen",
        "Timelimit": "02:00:00",
        "NodeList": "ascend-n001",
        "Restarts": "0",
        "ElapsedRaw": "10",
        "ReqTRES": "billing=1,cpu=1,mem=48G,node=1",
        "AllocTRES": "billing=1,cpu=1,mem=48G,node=1",
    }


def finalizer_row(job_id: str = "789") -> dict[str, str]:
    return {
        "JobID": job_id,
        "JobIDRaw": job_id,
        "State": "COMPLETED",
        "ExitCode": "0:0",
        "Account": "pgs0407",
        "Partition": "nextgen",
        "Timelimit": "00:30:00",
        "NodeList": "ascend-n002",
        "Restarts": "0",
        "ElapsedRaw": "12",
        "ReqTRES": "billing=2,cpu=2,mem=16G,node=1",
        "AllocTRES": "billing=2,cpu=2,mem=16G,node=1",
    }


def test_source_binding_is_hash_pinned_and_repository_scoped() -> None:
    relative = f"{production.PLAN_ROOT_RELATIVE}/r3_dispatch_000.json"
    digest = production.sha256_file(ROOT / relative)
    parsed = package.parse_source_binding(f"123|{relative}|{digest}")
    assert parsed == {
        "dispatch_path": relative,
        "dispatch_sha256": digest,
        "source_array_job_id": "123",
    }
    with pytest.raises(ValueError, match="JOBID"):
        package.parse_source_binding(f"123|{relative}")
    with pytest.raises(ValueError, match="malformed"):
        package.parse_source_binding(f"123|{relative}|not-a-hash")
    with pytest.raises(ValueError):
        package.parse_source_binding(f"123|../outside.json|{'0' * 64}")


def test_retry_binding_must_equal_prior_admission_pending_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(production, "ROOT", tmp_path)
    monkeypatch.setattr(package, "ROOT", tmp_path)
    pending = tmp_path / "results/pending_task_set.json"
    pending.parent.mkdir(parents=True)
    payload = {
        "entries": [{"geometry_sha256": "0" * 64, "layout_id": 0, "task_index": 0}],
        "execution_lock_sha256": "3" * 64,
        "fidelity_id": production.FIDELITIES[0],
        "manifest_sha256": "4" * 64,
        "plan_sha256": "2" * 64,
        "protocol_sha256": "1" * 64,
        "schema": package.PENDING_SET_SCHEMA,
    }
    pending.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    pending_sha = package.sha256_file(pending)
    admission = tmp_path / "results/FINAL_ADMISSION.json"
    admission.write_text(
        json.dumps(
            {
                "preterminal_files": {
                    "pending_set_path": "results/different.json",
                    "pending_set_sha256": pending_sha,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    roots = {
        "execution_lock_sha256": "3" * 64,
        "plan_sha256": "2" * 64,
        "protocol_sha256": "1" * 64,
    }
    with pytest.raises(ValueError, match="pending set bound"):
        package.validate_dispatch_binding(
            roots,
            {
                "dispatch_path": "results/pending_task_set.json",
                "dispatch_sha256": pending_sha,
                "source_array_job_id": "123",
            },
            fidelity_id=production.FIDELITIES[0],
            manifest=payload["entries"],
            manifest_sha256="4" * 64,
            retry_authority={
                "path": "results/FINAL_ADMISSION.json",
                "sha256": package.sha256_file(admission),
            },
        )


def test_component_accounting_requires_exact_dispatch_coverage() -> None:
    fidelity = production.FIDELITIES[0]
    binding = {"source_array_job_id": "123"}
    dispatch = {"fidelity_id": fidelity, "entries": manifest(2)}
    rows = [source_row(local_id=0), source_row(local_id=1)]
    indexed = package.validate_component_accounting(
        rows, binding=binding, dispatch=dispatch, protocol=PROTOCOL
    )
    assert set(indexed) == {0, 1}
    assert all(row["terminal_success"] for row in indexed.values())

    with pytest.raises(ValueError, match="coverage"):
        package.validate_component_accounting(
            rows[:1], binding=binding, dispatch=dispatch, protocol=PROTOCOL
        )
    bad = copy.deepcopy(rows)
    bad[1]["ReqTRES"] = "billing=2,cpu=2,mem=48G,node=1"
    with pytest.raises(ValueError, match="differs"):
        package.validate_component_accounting(
            bad, binding=binding, dispatch=dispatch, protocol=PROTOCOL
        )

    cancelled = source_row(state="CANCELLED", exit_code="0:15")
    cancelled.update(
        {
            "AllocTRES": "",
            "ElapsedRaw": "0",
            "NodeList": "None",
        }
    )
    indexed = package.validate_component_accounting(
        [cancelled],
        binding=binding,
        dispatch={"fidelity_id": fidelity, "entries": manifest(1)},
        protocol=PROTOCOL,
    )
    assert indexed[0]["terminal_success"] is False


def test_parse_accounting_rejects_truncated_rows() -> None:
    valid = "|".join(package.ACCOUNTING_FIELDS) + "|\n" + "|".join(source_row().values()) + "|\n"
    assert len(package.parse_accounting(valid)) == 1
    with pytest.raises(ValueError, match="field count"):
        package.parse_accounting("123|COMPLETED|0:0\n")


@pytest.mark.parametrize(
    ("accepted", "pending", "negative", "outcome", "retry", "dataset"),
    (
        (3, 0, 0, "POSITIVE", False, True),
        (2, 1, 0, "INDETERMINATE", True, False),
        (2, 0, 1, "TERMINAL_NEGATIVE", False, False),
    ),
)
def test_wave_classification_is_fail_closed(
    accepted: int, pending: int, negative: int, outcome: str, retry: bool, dataset: bool
) -> None:
    decision = package.classify_wave(
        expected_count=3,
        accepted_count=accepted,
        pending_count=pending,
        negative_count=negative,
    )
    assert decision["scientific_outcome"] == outcome
    assert decision["retry_may_start"] is retry
    assert decision["dataset_finalize_may_start"] is dataset


def test_wave_state_is_cumulative_and_terminal_negative_persists() -> None:
    rows = manifest(3)
    accepted, pending, negative, decision = package.build_wave_state(
        manifest=rows,
        prior_accepted=[{"task_index": 0, "artifact": "a"}],
        prior_negative=[{"task_index": 1, "failure_class": "genuine_numerical_or_resource_failure"}],
        current={2: ("pending", None)},
    )
    assert [row["task_index"] for row in accepted] == [0]
    assert [row["task_index"] for row in pending] == [2]
    assert [row["task_index"] for row in negative] == [1]
    assert decision["scientific_outcome"] == "TERMINAL_NEGATIVE"
    assert decision["retry_may_start"] is False

    with pytest.raises(ValueError, match="reruns"):
        package.build_wave_state(
            manifest=rows,
            prior_accepted=[{"task_index": 0}],
            prior_negative=[],
            current={0: ("pending", None)},
        )


def test_finalizer_admission_requires_completed_zero_exit() -> None:
    terminal = package.validate_finalizer_terminal(finalizer_row(), finalizer_job_id="789")
    assert terminal["terminal_success"] is True
    bad = finalizer_row()
    bad["State"] = "FAILED"
    bad["ExitCode"] = "1:0"
    with pytest.raises(ValueError, match="postterminal"):
        package.validate_finalizer_terminal(bad, finalizer_job_id="789")


def test_scheduler_only_timeout_is_terminal_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package, "package_root", lambda: tmp_path)
    row = source_row(state="TIMEOUT", exit_code="0:0")
    row.update(
        {
            "array_task_id": 0,
            "normalized_state": "TIMEOUT",
            "terminal_success": False,
        }
    )
    classification, artifact = package.load_attempt(
        roots={},
        fidelity_id=production.FIDELITIES[0],
        manifest_row={"geometry_sha256": "0" * 64, "layout_id": 0, "task_index": 0},
        manifest_sha256="1" * 64,
        binding={"source_array_job_id": "123"},
        dispatch_sha256="2" * 64,
        terminal=row,
    )
    assert classification == "terminal_negative"
    assert artifact["failure_class"] == "genuine_numerical_or_resource_failure"
    assert artifact["artifact_stage"] == "scheduler_only_resource_failure"

    row["normalized_state"] = "COMPLETED"
    row["terminal_success"] = True
    with pytest.raises(ValueError, match="lacks a task attempt"):
        package.load_attempt(
            roots={},
            fidelity_id=production.FIDELITIES[0],
            manifest_row={"geometry_sha256": "0" * 64, "layout_id": 0, "task_index": 0},
            manifest_sha256="1" * 64,
            binding={"source_array_job_id": "123"},
            dispatch_sha256="2" * 64,
            terminal=row,
        )


def test_unbound_valid_attempt_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package, "package_root", lambda: tmp_path)
    task = tmp_path / "attempts/r3/job_999/task_0000"
    task.mkdir(parents=True)
    (task / "TASK_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (task / "result.json").write_text(
        json.dumps(
            {
                "fidelity": {"fidelity_id": production.FIDELITIES[0]},
                "provenance": {
                    "execution_lock_sha256": "3" * 64,
                    "plan_sha256": "2" * 64,
                    "protocol_sha256": "1" * 64,
                    "source_git_head": "4" * 40,
                },
                "schema": production.TASK_SCHEMA,
                "task_pass": True,
                "task_index": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="absent from the cumulative source inventory"):
        package.reject_unbound_valid_attempts(
            roots={
                "execution_lock_sha256": "3" * 64,
                "plan_sha256": "2" * 64,
                "protocol_sha256": "1" * 64,
                "source_git_head": "4" * 40,
            },
            fidelity_id=production.FIDELITIES[0],
            allowed_attempts=set(),
        )
    package.reject_unbound_valid_attempts(
        roots={
            "execution_lock_sha256": "3" * 64,
            "plan_sha256": "2" * 64,
            "protocol_sha256": "1" * 64,
            "source_git_head": "4" * 40,
        },
        fidelity_id=production.FIDELITIES[0],
        allowed_attempts={("999", 0)},
    )


def test_pending_valid_attempt_lineage_survives_the_next_wave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(package, "package_root", lambda: tmp_path)
    task = tmp_path / "attempts/r3/job_999/task_0000"
    task.mkdir(parents=True)
    (task / "TASK_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    roots = {
        "execution_lock_sha256": "3" * 64,
        "plan_sha256": "2" * 64,
        "protocol": PROTOCOL,
        "protocol_sha256": "1" * 64,
        "source_git_head": "4" * 40,
    }
    (task / "result.json").write_text(
        json.dumps(
            {
                "fidelity": {"fidelity_id": production.FIDELITIES[0]},
                "provenance": {
                    "execution_lock_sha256": roots["execution_lock_sha256"],
                    "plan_sha256": roots["plan_sha256"],
                    "protocol_sha256": roots["protocol_sha256"],
                    "source_git_head": roots["source_git_head"],
                },
                "schema": production.TASK_SCHEMA,
                "task_pass": True,
                "task_index": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = manifest(2)

    def fake_dispatch(
        _roots: dict,
        binding: dict,
        **_kwargs: object,
    ) -> dict:
        index = 0 if binding["source_array_job_id"] == "999" else 1
        return {
            "entries": [rows[index]],
            "fidelity_id": production.FIDELITIES[0],
            "schema": production.DISPATCH_SCHEMA,
        }

    monkeypatch.setattr(package, "validate_dispatch_binding", fake_dispatch)
    monkeypatch.setattr(
        package,
        "validate_component_accounting",
        lambda _rows, *, binding, dispatch, protocol: {
            int(dispatch["entries"][0]["task_index"]): {
                "JobID": f"{binding['source_array_job_id']}_0",
                "canonical_task_index": int(dispatch["entries"][0]["task_index"]),
            }
        },
    )
    monkeypatch.setattr(package, "load_attempt", lambda **_kwargs: ("pending", None))
    first = package.collect_wave(
        roots=roots,
        fidelity_id=production.FIDELITIES[0],
        manifest=rows,
        manifest_sha256="5" * 64,
        bindings=[{"dispatch_sha256": "6" * 64, "source_array_job_id": "999"}],
        accounting_rows=[],
        prior_accepted=[],
        prior_negative=[],
        prior_source_inventory=[],
        retry_authority=None,
    )
    assert first[-1] == [{"source_array_job_id": "999", "task_index": 0}]
    second = package.collect_wave(
        roots=roots,
        fidelity_id=production.FIDELITIES[0],
        manifest=rows,
        manifest_sha256="5" * 64,
        bindings=[{"dispatch_sha256": "7" * 64, "source_array_job_id": "1000"}],
        accounting_rows=[],
        prior_accepted=[],
        prior_negative=[],
        prior_source_inventory=first[-1],
        retry_authority=None,
    )
    assert second[-1] == [
        {"source_array_job_id": "999", "task_index": 0},
        {"source_array_job_id": "1000", "task_index": 1},
    ]


def test_atomic_package_directory_is_immutable(tmp_path: Path) -> None:
    target = tmp_path / "receipt"
    package.atomic_directory(
        target,
        {"result.json": {"ok": True}, "rows.jsonl": [{"index": 0}]},
        {"schema": "test.v1"},
    )
    final_manifest = json.loads((target / "FINAL_MANIFEST.json").read_text(encoding="utf-8"))
    assert set(final_manifest["files_sha256"]) == {"result.json", "rows.jsonl"}
    with pytest.raises(SystemExit, match="overwrite"):
        package.atomic_directory(target, {"result.json": {}}, {"schema": "test.v1"})


def test_joint_dataset_builder_requires_exact_1500_plus_198(monkeypatch: pytest.MonkeyPatch) -> None:
    result_by_path: dict[str, dict] = {}
    accepted_by_fidelity: dict[str, list[dict]] = {}
    roots = {"protocol": PROTOCOL}
    for fidelity in production.FIDELITIES:
        count = int(PROTOCOL["fidelities"][fidelity]["coverage"])
        entries: list[dict] = []
        for index in range(count):
            relative = f"results/test/{fidelity}_{index}.json"
            geometry = f"{index:064x}"
            entries.append(
                {
                    "artifact_result_path": relative,
                    "artifact_result_sha256": "a" * 64,
                    "geometry_sha256": geometry,
                    "layout_id": index,
                    "task_index": index,
                }
            )
            result_by_path[relative] = {
                "schema": production.TASK_SCHEMA,
                "task_pass": True,
                "task_index": index,
                "fidelity": {"fidelity_id": fidelity},
                "geometry": {"geometry_sha256": geometry, "layout_id": index},
                "worker_result": {
                    "cps_pf": 1.0 + index / 1000.0,
                    "mesh_nodes": 100,
                    "mesh_tetrahedra": 300,
                    "relative_residual": 1e-10,
                    "system_sha256": "b" * 64,
                },
            }
        accepted_by_fidelity[fidelity] = entries

    monkeypatch.setattr(package, "safe_repo_path", lambda path, _label: Path(path))
    monkeypatch.setattr(package, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(package, "read_json", lambda path, _label: result_by_path[str(path)])
    observations = package.build_dataset_observations(
        roots=roots, accepted_by_fidelity=accepted_by_fidelity
    )
    assert len(observations) == 1698
    assert {row["fidelity_id"] for row in observations} == set(production.FIDELITIES)

    shortened = {key: list(value) for key, value in accepted_by_fidelity.items()}
    shortened[production.FIDELITIES[1]] = shortened[production.FIDELITIES[1]][:-1]
    with pytest.raises(ValueError, match="coverage"):
        package.build_dataset_observations(roots=roots, accepted_by_fidelity=shortened)


def test_finalizer_wrappers_are_solver_free_and_resource_bounded() -> None:
    wave = ROOT / package.WAVE_WRAPPER_RELATIVE
    dataset = ROOT / package.DATASET_WRAPPER_RELATIVE
    for wrapper in (wave, dataset):
        text = wrapper.read_text(encoding="utf-8")
        assert "#SBATCH --cpus-per-task=2" in text
        assert "#SBATCH --mem=16G" in text
        assert "#SBATCH --time=00:30:00" in text
        assert "corpus_v4_fem_v2_package.py" in text
        assert "fasthenry" not in text.lower()
        assert "solve_capacitance" not in text
        subprocess.run(["bash", "-n", str(wrapper)], check=True)
    assert "afterany" in wave.read_text(encoding="utf-8")
    assert "PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS" in wave.read_text(encoding="utf-8")


def test_package_module_is_solver_free_and_exposes_separate_admissions() -> None:
    text = PACKAGE_PATH.read_text(encoding="utf-8")
    assert "run_repeatability_worker(" not in text
    assert "solve_capacitance(" not in text
    commands = package.parser()._subparsers._group_actions[0].choices
    assert set(commands) == {"finalize-wave", "admit-wave", "finalize-dataset", "admit-dataset"}
    assert '"accuracy_protocol_may_be_frozen": True' in text
    assert '"training_may_start": True' not in text
