"""Login-safe trust-boundary tests for the Corpus V4 accuracy archive."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "code/experiments/proofs", ROOT / "code/quality"):
    sys.path.insert(0, str(directory))

import corpus_v4_accuracy_contract_v2 as contract  # noqa: E402
import finalize_corpus_v4_accuracy_v2 as finalizer  # noqa: E402
import verify_corpus_v4_accuracy_archive_v2 as archive  # noqa: E402


def _mock_sacct(
    monkeypatch: pytest.MonkeyPatch, *, stdout: str, returncode: int = 0
) -> None:
    def run(command: list[str], **_: Any) -> SimpleNamespace:
        assert command == [
            "sacct",
            "-X",
            "-n",
            "-P",
            "-j",
            "8200000",
            "--format=JobIDRaw,State,ExitCode,ElapsedRaw,ReqTRES,AllocTRES",
        ]
        return SimpleNamespace(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(archive.subprocess, "run", run)


def test_completed_finalizer_accepts_one_exact_terminal_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_sacct(
        monkeypatch,
        stdout=(
            "8200000|COMPLETED+|0:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n"
            "8200000.batch|COMPLETED|0:0|90|cpu=2,mem=16G|cpu=3,mem=16G|\n"
        ),
    )

    receipt = archive._completed_finalizer("8200000")

    assert receipt == {
        "AllocTRES": "cpu=3,mem=16G",
        "ElapsedRaw": "91",
        "ExitCode": "0:0",
        "JobIDRaw": "8200000",
        "ReqTRES": "cpu=2,mem=16G",
        "State": "COMPLETED",
    }


@pytest.mark.parametrize(
    ("returncode", "stdout"),
    (
        (
            1,
            "8200000|COMPLETED|0:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n",
        ),
        (
            0,
            "8200000|FAILED|0:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n",
        ),
        (
            0,
            "8200000|COMPLETED|1:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n",
        ),
        (
            0,
            "8200000|COMPLETED|0:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n"
            "8200000|COMPLETED|0:0|91|cpu=2,mem=16G|cpu=3,mem=16G|\n",
        ),
    ),
)
def test_completed_finalizer_rejects_query_state_exit_and_duplicates(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str
) -> None:
    _mock_sacct(monkeypatch, stdout=stdout, returncode=returncode)

    with pytest.raises(ValueError, match="exact COMPLETED/0:0"):
        archive._completed_finalizer("8200000")


@pytest.mark.parametrize("job_id", ("", "8200000_1", "82.0", "true"))
def test_completed_finalizer_rejects_noncanonical_job_id(job_id: str) -> None:
    with pytest.raises(ValueError, match="canonical numeric"):
        archive._completed_finalizer(job_id)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _analysis_inventory_fixture(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, Any], Path, str]:
    monkeypatch.setattr(archive, "ROOT", root)
    monkeypatch.setattr(contract, "ROOT", root)
    accepted_set_path = root / "accepted" / "accepted_set.json"
    _write_json(accepted_set_path, {"fixture": "accepted"})
    accepted_set_sha256 = archive.sha256_file(accepted_set_path)

    analysis_root = root / "analysis"
    local_names = {
        "checkpoint_index.json",
        "matrices.json",
        "reference_fidelity_gap.json",
        "summary.json",
        "task_metrics.json",
        "task_index.json",
        *(f"predictions/task_{task_id:02d}.jsonl" for task_id in range(25)),
    }
    files: dict[str, dict[str, str]] = {
        "accepted_set": {
            "path": accepted_set_path.relative_to(root).as_posix(),
            "sha256": accepted_set_sha256,
        }
    }
    for name in sorted(local_names):
        artifact = analysis_root / name
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"fixture:{name}\n")
        files[name] = {"path": name, "sha256": archive.sha256_file(artifact)}
    payload: dict[str, Any] = {"files": files, "schema": archive.ANALYSIS_SCHEMA}
    analysis_path = analysis_root / "ANALYSIS_MANIFEST.json"
    _write_json(analysis_path, payload)
    return analysis_path, payload, accepted_set_path, accepted_set_sha256


def _verify_fixture(
    analysis_path: Path,
    *,
    accepted_set_path: Path,
    accepted_set_sha256: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    return archive._verify_analysis_inventory(
        analysis_path,
        archive.sha256_file(analysis_path),
        accepted_set_path=accepted_set_path,
        accepted_set_sha256=accepted_set_sha256,
    )


def test_analysis_inventory_accepts_only_the_exact_hash_closed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_path, payload, accepted_path, accepted_sha = _analysis_inventory_fixture(
        tmp_path, monkeypatch
    )

    observed_payload, observed = _verify_fixture(
        analysis_path,
        accepted_set_path=accepted_path,
        accepted_set_sha256=accepted_sha,
    )

    assert observed_payload == payload
    assert set(observed) == {
        "checkpoint_index.json",
        "matrices.json",
        "reference_fidelity_gap.json",
        "summary.json",
        "task_metrics.json",
        "task_index.json",
        *(f"predictions/task_{task_id:02d}.jsonl" for task_id in range(25)),
    }
    assert observed["summary.json"] == archive.sha256_file(
        analysis_path.parent / "summary.json"
    )


def test_analysis_inventory_rejects_an_extra_local_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_path, _, accepted_path, accepted_sha = _analysis_inventory_fixture(
        tmp_path, monkeypatch
    )
    (analysis_path.parent / "extra.txt").write_text("not admitted\n")

    with pytest.raises(ValueError, match="inventory is not exact"):
        _verify_fixture(
            analysis_path,
            accepted_set_path=accepted_path,
            accepted_set_sha256=accepted_sha,
        )


def test_analysis_inventory_rejects_a_tampered_file_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_path, _, accepted_path, accepted_sha = _analysis_inventory_fixture(
        tmp_path, monkeypatch
    )
    (analysis_path.parent / "summary.json").write_text("tampered bytes\n")

    with pytest.raises(ValueError, match="summary.json"):
        _verify_fixture(
            analysis_path,
            accepted_set_path=accepted_path,
            accepted_set_sha256=accepted_sha,
        )


def test_analysis_inventory_rejects_a_tampered_manifest_hash_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_path, payload, accepted_path, accepted_sha = _analysis_inventory_fixture(
        tmp_path, monkeypatch
    )
    changed = copy.deepcopy(payload)
    changed["files"]["summary.json"]["sha256"] = "0" * 64
    _write_json(analysis_path, changed)

    with pytest.raises(ValueError, match="summary.json"):
        _verify_fixture(
            analysis_path,
            accepted_set_path=accepted_path,
            accepted_set_sha256=accepted_sha,
        )


def test_analysis_inventory_rejects_a_noncanonical_record_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_path, payload, accepted_path, accepted_sha = _analysis_inventory_fixture(
        tmp_path, monkeypatch
    )
    changed = copy.deepcopy(payload)
    changed["files"]["summary.json"]["path"] = "./summary.json"
    _write_json(analysis_path, changed)

    with pytest.raises(ValueError, match="path is not canonical"):
        _verify_fixture(
            analysis_path,
            accepted_set_path=accepted_path,
            accepted_set_sha256=accepted_sha,
        )


def _archive_replay_fixture(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SimpleNamespace, dict[str, int]]:
    """Build a small mocked scientific graph around the real archive branch."""
    monkeypatch.setattr(archive, "ROOT", root)
    monkeypatch.setattr(contract, "ROOT", root)
    monkeypatch.setattr(finalizer, "ROOT", root)
    plan_root = root / "plan"
    analysis_root = root / "analysis"
    accepted_root = root / "resume"
    for directory in (plan_root, analysis_root, accepted_root):
        directory.mkdir(parents=True)

    task_rows: list[dict[str, Any]] = []
    accepted_entries: list[dict[str, Any]] = []
    candidate_entries: list[dict[str, Any]] = []
    task_index_entries: list[dict[str, Any]] = []
    checkpoint_entries: list[dict[str, Any]] = []
    for task_id in range(25):
        canonical = contract.canonical_task_row(task_id)
        task_rows.append(
            {
                **canonical,
                "partitions": {"test": {"layout_ids": list(range(39))}},
                "r4_test_layout_ids": list(range(39)),
            }
        )
        manifest = root / "attempts" / f"task_{task_id:02d}" / "TASK_MANIFEST.json"
        _write_json(manifest, {"task_id": task_id})
        relative = manifest.relative_to(root).as_posix()
        digest = archive.sha256_file(manifest)
        completion = {
            "AllocTRES": "cpu=16,mem=48G",
            "ElapsedRaw": "123",
            "ExitCode": "0:0",
            "JobIDRaw": f"8100000_{task_id}",
            "ReqTRES": "cpu=8,mem=48G",
            "State": "COMPLETED",
        }
        accepted_entries.append(
            {
                "manifest_path": relative,
                "manifest_sha256": digest,
                "scheduler_completion": completion,
                "task_id": task_id,
            }
        )
        candidate_entries.append(
            {"path": relative, "sha256": digest, "task_id": task_id}
        )
        prediction_name = f"predictions/task_{task_id:02d}.jsonl"
        task_index_entries.append(
            {
                "manifest_path": relative,
                "manifest_sha256": digest,
                "prediction_path": prediction_name,
                "prediction_sha256": "9" * 64,
                "scheduler_completion": completion,
                "task_id": task_id,
            }
        )
        checkpoint_entries.append(
            {
                **canonical,
                "archive_sha256": "a" * 64,
                "bundle_path": (manifest.parent / "bundle")
                .relative_to(root)
                .as_posix(),
                "metadata_sha256": "b" * 64,
                "smoke_examples_sha256": "c" * 64,
            }
        )

    candidate_path = accepted_root / "candidate_index.json"
    _write_json(
        candidate_path,
        {"entries": candidate_entries, "schema": contract.CANDIDATE_SCHEMA},
    )
    accepted_path = accepted_root / "accepted_artifact_set.json"
    roots = {
        "execution_lock_sha256": "d" * 64,
        "plan_sha256": "e" * 64,
        "protocol_sha256": "f" * 64,
        "task_manifest_sha256": "1" * 64,
    }
    _write_json(
        accepted_path,
        {
            **roots,
            "candidate_index": {
                "path": candidate_path.relative_to(root).as_posix(),
                "sha256": archive.sha256_file(candidate_path),
            },
            "decision": {
                "checkpoint_set_complete": True,
                "claim_eligible": False,
                "held_out_inference_may_start": True,
                "speed_claim_eligible": False,
            },
            "entries": accepted_entries,
            "n_accepted": 25,
            "n_expected": 25,
            "rejected_candidates": [],
            "schema": contract.ACCEPTED_SCHEMA,
        },
    )
    evaluation_rows = [
        {
            "evaluation_only_r4_cps": {"value": 1.0} if index < 39 else None,
            "family_id": "family-0" if index < 39 else f"family-{index}",
            "layout_id": index,
        }
        for index in range(1500)
    ]
    expected_counts = {
        "r4_family_split_appearance_histogram": {"195": 1},
        "r4_layout_split_appearance_histogram": {"5": 39},
        "r4_panel_split_layout_memberships": 195,
        "r4_task_layout_evaluations": 975,
        "r4_unique_families_across_split_panels": 1,
        "r4_unique_layouts_across_split_panels": 39,
        "r4_unseen_selected_families": 0,
        "r4_unseen_selected_layouts": 0,
        "tasks": 25,
    }
    source_head = "2" * 40
    runtime = {
        "numpy_distribution": "2.0.2",
        "python": "3.9.21",
        "torch_distribution": "2.8.0",
    }
    task_software = {
        **runtime,
        "scipy": "1.13.1",
        "torch_build": "2.8.0",
    }
    finalizer_receipt = {
        "AllocTRES": "billing=3,cpu=3,mem=16G,node=1",
        "ElapsedRaw": "91",
        "ExitCode": "0:0",
        "JobIDRaw": "8200000",
        "ReqTRES": "billing=2,cpu=2,mem=16G,node=1",
        "State": "COMPLETED",
    }
    summary = {
        "bindings": {
            "accepted_set_sha256": archive.sha256_file(accepted_path),
            **roots,
            "expected_source_git_head": source_head,
        },
        "counts": expected_counts,
        "created_utc": "2026-08-29T12:00:00+00:00",
        "designated_downstream_checkpoint": checkpoint_entries[12],
        "provenance": {
            "finalizer_runtime": {**runtime, "torch_build": "2.8.0"},
            "scheduler": {
                "job_id": "8200000",
                "scheduler_record": {
                    "AllocTRES": "cpu=3,mem=16G,node=1,billing=3",
                    "ReqTRES": "cpu=2,mem=16G,node=1,billing=2",
                },
            },
            "source_file_sha256": {},
            "source_git_head": source_head,
            "task_software": task_software,
        },
        "schema": archive.FINAL_SCHEMA,
        "scientific_scope": finalizer.SCIENTIFIC_SCOPE,
    }
    inventory = {
        "checkpoint_index.json": "9" * 64,
        "matrices.json": "9" * 64,
        "reference_fidelity_gap.json": "9" * 64,
        "summary.json": "9" * 64,
        "task_metrics.json": "9" * 64,
        "task_index.json": "9" * 64,
        **{f"predictions/task_{task_id:02d}.jsonl": "9" * 64 for task_id in range(25)},
    }
    analysis = {
        "files": {
            "accepted_set": {
                "path": accepted_path.relative_to(root).as_posix(),
                "sha256": archive.sha256_file(accepted_path),
            },
            **{
                name: {"path": name, "sha256": digest}
                for name, digest in inventory.items()
            },
        },
        "schema": archive.ANALYSIS_SCHEMA,
    }
    documents = {
        "accepted_artifact_set.json": json.loads(accepted_path.read_text()),
        "candidate_index.json": json.loads(candidate_path.read_text()),
        "checkpoint_index.json": {
            "entries": checkpoint_entries,
            "schema": "pcb-gnn.corpus-v4-accuracy-checkpoint-index.v2",
        },
        "matrices.json": {
            "schema": "pcb-gnn.corpus-v4-accuracy-matrices.v2",
            "views": {"fixture": True},
        },
        "reference_fidelity_gap.json": {
            "complete_selected_registry": {},
            "interpretation": "fixture",
            "per_split": [],
            "schema": finalizer.REFERENCE_GAP_SCHEMA,
        },
        "summary.json": summary,
        "task_metrics.json": {
            "entries": [
                {"metrics": {}, "task": contract.canonical_task_row(task_id)}
                for task_id in range(25)
            ],
            "schema": finalizer.TASK_METRICS_SCHEMA,
        },
        "task_index.json": {
            "entries": task_index_entries,
            "schema": "pcb-gnn.corpus-v4-accuracy-task-index.v2",
        },
    }

    monkeypatch.setattr(
        archive,
        "validate_protocol",
        lambda *_: (
            {
                "evaluation": {"passivity_relative_tolerance": 1e-9},
                "inputs": {},
                "runtime": runtime,
            },
            roots["protocol_sha256"],
        ),
    )
    monkeypatch.setattr(
        archive,
        "validate_plan",
        lambda *_args, **_kwargs: (
            {"planner_source_sha256": {}},
            task_rows,
            roots["plan_sha256"],
            roots["task_manifest_sha256"],
        ),
    )
    monkeypatch.setattr(
        archive,
        "validate_execution_lock",
        lambda *_: ({"source_sha256": {}}, roots["execution_lock_sha256"]),
    )
    monkeypatch.setattr(archive, "validate_root_closure", lambda **_: None)
    monkeypatch.setattr(archive, "_validate_execution_git_closure", lambda *_: None)
    monkeypatch.setattr(archive, "_validate_upstream_archive", lambda *_: None)
    monkeypatch.setattr(
        archive,
        "_verify_analysis_inventory",
        lambda *_args, **_kwargs: (analysis, inventory),
    )
    monkeypatch.setattr(
        archive,
        "_validate_accepted_set",
        lambda *_args, **_kwargs: accepted_entries,
    )
    monkeypatch.setattr(
        archive, "validate_file_manifest", lambda *_: {"files_sha256": {}}
    )
    monkeypatch.setattr(
        archive,
        "validate_attempt",
        lambda _path, *, task_row, **_kwargs: {
            "bindings": {"retry_pending_set": None},
            "checkpoint": {
                "archive_sha256": "a" * 64,
                "metadata_sha256": "b" * 64,
                "smoke_examples_sha256": "c" * 64,
            },
            "provenance": {"software": task_software},
            "task": contract.canonical_task_row(task_row["task_id"]),
        },
    )
    monkeypatch.setattr(
        archive, "recompute_task_metrics", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(archive, "build_matrices", lambda *_: {"fixture": True})
    monkeypatch.setattr(
        archive,
        "build_reference_fidelity_gap",
        lambda *_: documents["reference_fidelity_gap.json"],
    )

    archive_path = analysis_root / "ARCHIVE_MANIFEST.json"

    def load_document(path: Path) -> dict[str, Any]:
        if path == archive_path:
            return json.loads(path.read_text())
        return documents[path.name]

    def load_rows(path: Path) -> list[dict[str, Any]]:
        if path.name == "evaluation_dataset.jsonl":
            return evaluation_rows
        return []

    calls = {"sacct": 0}

    def completed(job_id: str) -> dict[str, str]:
        assert job_id == "8200000"
        calls["sacct"] += 1
        return copy.deepcopy(finalizer_receipt)

    monkeypatch.setattr(archive, "load_json", load_document)
    monkeypatch.setattr(archive, "load_jsonl", load_rows)
    monkeypatch.setattr(archive, "_completed_finalizer", completed)
    args = SimpleNamespace(
        accepted_set=accepted_path,
        analysis_manifest=analysis_root / "ANALYSIS_MANIFEST.json",
        check=False,
        execution_lock=root / "execution-lock.json",
        expected_accepted_set_sha256=archive.sha256_file(accepted_path),
        expected_analysis_manifest_sha256="3" * 64,
        expected_execution_lock_sha256=roots["execution_lock_sha256"],
        expected_plan_sha256=roots["plan_sha256"],
        expected_protocol_sha256=roots["protocol_sha256"],
        expected_source_git_head=source_head,
        expected_task_manifest_sha256=roots["task_manifest_sha256"],
        out=archive_path,
        plan=plan_root / "plan.json",
        protocol=root / "protocol.json",
        require_git_tracked=False,
        task_manifest=plan_root / "task_manifest.jsonl",
    )
    return args, calls


def test_archive_creation_then_offline_check_never_requeries_sacct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, calls = _archive_replay_fixture(tmp_path, monkeypatch)

    created = archive.verify_archive(args)
    assert args.out.is_file()
    assert calls["sacct"] == 1

    args.check = True
    monkeypatch.setattr(
        archive,
        "_completed_finalizer",
        lambda *_: (_ for _ in ()).throw(AssertionError("offline check queried sacct")),
    )
    checked = archive.verify_archive(args)

    assert checked == created
    assert calls["sacct"] == 1


def test_archive_offline_check_rejects_tampered_stored_finalizer_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args, _ = _archive_replay_fixture(tmp_path, monkeypatch)
    archive.verify_archive(args)
    stored = json.loads(args.out.read_text())
    stored["finalizer_scheduler_completion"]["AllocTRES"] = "cpu=2,mem=16G"
    _write_json(args.out, stored)
    args.check = True
    monkeypatch.setattr(
        archive,
        "_completed_finalizer",
        lambda *_: (_ for _ in ()).throw(AssertionError("offline check queried sacct")),
    )

    with pytest.raises(ValueError, match="post-run TRES|deterministic reconstruction"):
        archive.verify_archive(args)
