"""Independent contracts for the claim-bearing Corpus-v4 latency pipeline.

These tests intentionally describe the version-2 pipeline rather than the
archival 100-design implementation.  Solver work remains a SLURM-only
integration stage; the tests here exercise deterministic planning, validation,
statistics, and archive contracts without launching a field solve.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / "code/experiments/proofs"
JOBS = ROOT / "code/jobs"
QUALITY = ROOT / "code/quality"
PROTOCOL_PATH = ROOT / "protocols/corpus_v4_latency_v1.json"
TASK_SCRIPT = PROOFS / "experiments_corpus_v4_latency_task.py"
FINALIZER_SCRIPT = PROOFS / "finalize_corpus_v4_latency.py"
PLANNER_SCRIPT = PROOFS / "plan_corpus_v4_latency.py"
RESUME_SCRIPT = PROOFS / "plan_corpus_v4_latency_resume.py"
CONTRACT_SCRIPT = PROOFS / "corpus_v4_latency_contract.py"
ARCHIVE_VERIFIER = QUALITY / "verify_corpus_v4_latency_archive.py"

PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-protocol.v2"
TASK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v2"
RECORD_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-record.v2"
FINAL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-final.v2"

EXPECTED_CHECKPOINT = {
    "task_id": 12,
    "split_seed": 42,
    "init_seed": 42,
    "archive_sha256": "f3f8e8607aa8b71413946152f6d6ff344d3d970e8cee3e31915d4991e190dd2a",
    "metadata_sha256": "b606aa2ea612abd5e5d2be92b3d96ebf8c27365837b58de9e338b280a5ac47a9",
    "smoke_input_sha256": "3a9716838c36c2a519d0242075abe1b18960238a963fa4b9faab587dc1dbb752",
    "accuracy_archive_sha256": "0335dbf90f41ac68443a454072280b1796422f0bd0be233cec3be3c2996f80c4",
}

def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"missing claim-bearing latency module: {path.relative_to(ROOT)}"
    for directory in (
        PROOFS,
        ROOT / "code/core",
        ROOT / "code/data",
        ROOT / "code/inference",
        ROOT / "code/models/gnn",
        ROOT / "code/solvers",
    ):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _protocol() -> dict[str, Any]:
    assert PROTOCOL_PATH.is_file(), "the v2 latency protocol must be a tracked input"
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _validate_only(script: Path, *arguments: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(script), *arguments, "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout.splitlines()[-1])


def _materialize(artifacts: dict[str, bytes], directory: Path) -> None:
    directory.mkdir(exist_ok=True)
    for name, content in artifacts.items():
        (directory / name).write_bytes(content)


def _base_record(
    *,
    layout_id: int = 10,
    family_id: str = "turns-04-04",
    fasthenry_ms: float = 4.0,
    fem_ms: float = 500.0,
    inference_ms: float = 2.0,
) -> dict[str, Any]:
    pre_solver = [inference_ms] * 100
    post_solver = [inference_ms] * 100
    repetitions = pre_solver + post_solver
    paired_ms = fasthenry_ms + fem_ms
    return {
        "family_id": family_id,
        "geometry_sha256": f"{layout_id:064x}",
        "inference_raw_record_ms": {
            "median": float(np.median(repetitions)),
            "post_solver_median": float(np.median(post_solver)),
            "post_solver_repetitions": post_solver,
            "pre_solver_median": float(np.median(pre_solver)),
            "pre_solver_repetitions": pre_solver,
            "repetitions": repetitions,
            "timed_repetitions": 200,
            "warmups": 50,
        },
        "layout_id": layout_id,
        "model_load_ms": 10.0,
        "prediction": [1.0, 2.0, 3.0, 0.5],
        "reference": [1.0, 2.0, 3.0, 0.5],
        "rerun_reference": [1.0, 2.0, 3.0, 0.5],
        "schema": RECORD_SCHEMA,
        "solver_label_max_relative_drift": 0.0,
        "solver_label_relative_drift": [0.0, 0.0, 0.0, 0.0],
        "solver_ms": {
            "fasthenry": fasthenry_ms,
            "fem_r3_p16": fem_ms,
            "paired_four_target": paired_ms,
        },
        "solver_telemetry": {
            "fasthenry": {
                "returncode": 0,
                "start_ns": 1_000_000,
                "stop_ns": 1_000_000 + int(fasthenry_ms * 1e6),
            },
            "fem_r3_p16": {
                "checks": {"converged": True},
                "observed": {
                    "cps_pf": 1.0,
                    "pad_mm": 16.0,
                    "refine": 3,
                    "solver_info": 0,
                },
                "start_ns": 2_000_000,
                "stop_ns": 2_000_000 + int(fem_ms * 1e6),
            },
        },
        "speedup_paired_four_target_x": paired_ms / float(np.median(repetitions)),
        "timer": {
            "clock": "perf_counter_ns",
            "monotonic": True,
        },
        "winding_coupling_coefficient": 0.5,
    }


def _sbatch_directives(path: Path) -> dict[str, str]:
    directives: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#SBATCH "):
            continue
        token = line.removeprefix("#SBATCH ").strip()
        if "=" in token:
            key, value = token.split("=", 1)
        else:
            key, value = token.split(maxsplit=1)
        directives[key] = value
    return directives


def _independent_family_cluster_interval(
    records: list[dict[str, Any]], *, resamples: int, seed: int
) -> list[float]:
    by_family: dict[str, np.ndarray] = {}
    for family in sorted({record["family_id"] for record in records}):
        by_family[family] = np.asarray(
            [
                record["speedup_paired_four_target_x"]
                for record in records
                if record["family_id"] == family
            ],
            dtype=np.float64,
        )
    families = sorted(by_family)
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        selected = rng.choice(families, size=len(families), replace=True)
        draws[index] = float(
            np.median(np.concatenate([by_family[family] for family in selected]))
        )
    return np.percentile(draws, [2.5, 97.5], method="linear").tolist()


def test_v2_protocol_freezes_checkpoint_solver_boundary_and_statistics() -> None:
    protocol = _protocol()
    assert set(protocol) == {
        "checkpoint",
        "forbidden_actions",
        "gnn_timing",
        "inputs",
        "panel",
        "protocol_name",
        "resources",
        "runtime",
        "schema",
        "solver_workflow",
        "statistics",
    }
    assert protocol["schema"] == PROTOCOL_SCHEMA
    assert protocol["checkpoint"]["designated_task_id"] == 12
    assert protocol["checkpoint"]["split_seed"] == 42
    assert protocol["checkpoint"]["init_seed"] == 42
    assert protocol["checkpoint"]["bundle_schema"] == "pcb-gnn.safe-npz-bundle.v1"
    assert protocol["panel"]["n_designs"] == 306
    assert protocol["panel"]["n_families"] == 13
    assert protocol["panel"]["selection_uses_labels_predictions_or_timings"] is False
    assert protocol["resources"]["scheduler_account"] == "pgs0407"
    assert protocol["inputs"]["accuracy_archive"]["sha256"] == EXPECTED_CHECKPOINT[
        "accuracy_archive_sha256"
    ]
    assert protocol["inputs"]["checkpoint_archive"]["sha256"] == EXPECTED_CHECKPOINT[
        "archive_sha256"
    ]
    assert protocol["inputs"]["checkpoint_metadata"]["sha256"] == EXPECTED_CHECKPOINT[
        "metadata_sha256"
    ]
    assert protocol["inputs"]["checkpoint_smoke_examples"]["sha256"] == EXPECTED_CHECKPOINT[
        "smoke_input_sha256"
    ]

    solver = protocol["solver_workflow"]
    assert solver["capacitance"] == {
        "fidelity_id": "cps_fem_r3_p16",
        "linear_solver": "pyamg_smoothed_aggregation_cg",
        "pad_mm": 16.0,
        "refine": 3,
        "target": "Cps_pF",
        "timeout_s": 1800,
    }
    assert solver["inductance"]["frequency_hz"] == 100_000.0
    assert solver["inductance"]["targets"] == [
        "L_pri_nH",
        "L_sec_nH",
        "L_mut_nH",
    ]
    assert solver["execution_order"] == ["FastHenry", "FEM-R3P16"]

    timing = protocol["gnn_timing"]
    assert timing["boundary_name"] == (
        "warm-loaded in-memory raw-JSON-record-to-four-output latency"
    )
    assert timing["warmup_repetitions"] == 50
    assert timing["measured_repetitions_per_block"] == 100
    assert timing["measured_repetitions"] == 200
    assert timing["measurement_blocks"] == [
        "100 repetitions before the solver workflow",
        "100 repetitions after the solver workflow",
    ]
    assert protocol["statistics"]["design_gnn_latency"] == (
        "median of 200 measured repetitions"
    )
    assert protocol["statistics"]["primary_estimand"] == (
        "median over 306 designs of paired solver latency divided by design-median GNN latency"
    )
    bootstrap = protocol["statistics"]["bootstrap"]
    assert bootstrap["cluster_unit"] == "held-out geometry family"
    assert bootstrap["resamples"] == 10_000
    assert bootstrap["seed"] == 20260820
    assert bootstrap["percentiles"] == [2.5, 97.5]
    assert bootstrap["quantile_method"] == "Hyndman-Fan type 7"


def test_plan_is_exactly_the_306_layout_task12_test_partition(tmp_path: Path) -> None:
    planner = _load_module(PLANNER_SCRIPT, "latency_v2_planner_for_test")
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_for_plan_test")
    artifacts = planner.build_artifacts(root=ROOT, protocol_path=PROTOCOL_PATH)
    _materialize(artifacts, tmp_path)
    plan, rows, panel, _, _, _ = contract.validate_plan(
        tmp_path / "plan.json",
        tmp_path / "task_manifest.jsonl",
        tmp_path / "panel_records.jsonl",
    )
    accuracy_rows = [
        json.loads(line)
        for line in (
            ROOT / "results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    expected_ids = accuracy_rows[12]["partitions"]["test"]["layout_ids"]
    expected_families = set(
        accuracy_rows[12]["partitions"]["test"]["family_ids"]
    )
    assert len(rows) == 306
    assert len(panel) == 306
    assert [row["task_id"] for row in rows] == list(range(306))
    assert [row["layout_id"] for row in rows] == expected_ids
    assert {row["family_id"] for row in rows} == expected_families
    assert len(expected_families) == 13
    assert plan["checkpoint"]["task_id"] == 12
    assert plan["checkpoint"]["split_seed"] == 42
    assert plan["checkpoint"]["init_seed"] == 42
    assert plan["checkpoint"]["archive_sha256"] == EXPECTED_CHECKPOINT["archive_sha256"]
    assert plan["checkpoint"]["metadata_sha256"] == EXPECTED_CHECKPOINT["metadata_sha256"]
    assert plan["checkpoint"]["smoke_examples_sha256"] == EXPECTED_CHECKPOINT[
        "smoke_input_sha256"
    ]


def test_execution_source_closure_includes_all_claim_bearing_stages() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_for_source_test")
    required = {
        "code/experiments/proofs/corpus_v4_latency_contract.py",
        "code/experiments/proofs/plan_corpus_v4_latency.py",
        "code/experiments/proofs/experiments_corpus_v4_latency_task.py",
        "code/experiments/proofs/finalize_corpus_v4_latency.py",
        "code/inference/corpus_v4_latency_inference.py",
        "code/inference/safe_npz_bundle.py",
        "code/jobs/slurm_job_env.sh",
        "code/jobs/submit_corpus_v4_latency.sh",
        "code/jobs/submit_corpus_v4_latency_preflight.sh",
        "code/jobs/submit_finalize_corpus_v4_latency.sh",
        "code/models/gnn/gnn_baseline.py",
        "code/quality/verify_corpus_v4_latency_archive.py",
        "code/solvers/fasthenry_latency.py",
        "code/solvers/fasthenry_ref.py",
        "code/solvers/fem_corpus_v4_latency.py",
        "code/solvers/fem_capacitance_3d.py",
        "code/solvers/fem_cps_diagnostic_worker.py",
        "protocols/corpus_v4_latency_v1.json",
        "requirements-proof.txt",
    }
    assert required <= set(contract.EXECUTION_SOURCE_NAMES)


def test_protocol_input_hash_drift_is_rejected_before_execution() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_for_binding_test")
    protocol = _protocol()
    assert set(contract.resolve_protocol_inputs(protocol)) == set(protocol["inputs"])

    changed = copy.deepcopy(protocol)
    changed["inputs"]["checkpoint_archive"]["sha256"] = "d" * 64
    with pytest.raises(ValueError, match="hash|SHA-256|digest"):
        contract.resolve_protocol_inputs(changed)


def test_raw_record_timer_honors_warmup_and_repetition_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inference = _load_module(
        ROOT / "code/inference/corpus_v4_latency_inference.py",
        "latency_v2_inference_for_timer_test",
    )
    raw_record = b'{"resident":"bytes"}'
    observed: list[bytes] = []

    def fake_predict(model: Any, normalizer: Any, raw_layout: bytes) -> np.ndarray:
        del model, normalizer
        observed.append(raw_layout)
        return np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)

    ticks = iter(range(0, 1_000_000_000, 1_000_000))
    monkeypatch.setattr(inference, "predict_raw_record", fake_predict)
    monkeypatch.setattr(inference.time, "perf_counter_ns", lambda: next(ticks))

    pre = inference.measure_raw_record_inference(
        object(), object(), raw_record, warmups=50, repetitions=100
    )
    post = inference.measure_raw_record_inference(
        object(), object(), raw_record, warmups=0, repetitions=100
    )
    assert len(observed) == 250
    assert all(value is raw_record for value in observed)
    assert pre["warmup_repetitions"] == 50
    assert post["warmup_repetitions"] == 0
    assert len(pre["repetitions_ms"]) == len(post["repetitions_ms"]) == 100
    assert pre["median_ms"] == post["median_ms"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "raw_record",
    (
        b'{"root":1,"root":2}',
        b'{"root":NaN}',
        b'{ "root":1}',
        b"",
    ),
)
def test_raw_record_boundary_rejects_duplicate_nonfinite_or_noncanonical_json(
    raw_record: bytes,
) -> None:
    inference = _load_module(
        ROOT / "code/inference/corpus_v4_latency_inference.py",
        "latency_v2_inference_for_json_test",
    )
    with pytest.raises(ValueError):
        inference.parse_canonical_layout(raw_record)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda row: row["solver_ms"].__setitem__("fasthenry", 0.0),
        lambda row: row["solver_ms"].__setitem__("fem_r3_p16", np.inf),
        lambda row: row["solver_ms"].__setitem__("paired_four_target", 999.0),
        lambda row: row["inference_raw_record_ms"]["repetitions"].__setitem__(0, np.nan),
        lambda row: row["inference_raw_record_ms"].__setitem__("median", 0.0),
        lambda row: row["inference_raw_record_ms"].__setitem__("repetitions", [2.0] * 199),
        lambda row: row.__setitem__("speedup_paired_four_target_x", -1.0),
        lambda row: row.pop("geometry_sha256"),
    ),
)
def test_timing_record_rejects_nonfinite_zero_and_malformed_values(mutation: Any) -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_finalizer_for_record_test")
    record = _base_record()
    finalizer.validate_timing_record(record, expected_repetitions=200)
    changed = copy.deepcopy(record)
    mutation(changed)
    with pytest.raises(ValueError):
        finalizer.validate_timing_record(changed, expected_repetitions=200)


def test_summary_uses_paired_median_of_ratios_and_rejects_duplicates() -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_finalizer_for_summary_test")
    records = [
        _base_record(layout_id=1, family_id="a", fasthenry_ms=0.5, fem_ms=0.5, inference_ms=1.0),
        _base_record(
            layout_id=2, family_id="a", fasthenry_ms=50.0, fem_ms=50.0,
            inference_ms=10.0,
        ),
        _base_record(
            layout_id=3, family_id="b", fasthenry_ms=50.5, fem_ms=50.5,
            inference_ms=100.0,
        ),
        _base_record(layout_id=4, family_id="b", fasthenry_ms=4.0, fem_ms=4.0, inference_ms=2.0),
    ]
    summary = finalizer.summarize_records(
        records,
        expected_repetitions=200,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260820,
    )
    ratios = np.asarray(
        [record["speedup_paired_four_target_x"] for record in records],
        dtype=np.float64,
    )
    ratio_of_medians = float(
        np.median([record["solver_ms"]["paired_four_target"] for record in records])
        / np.median([record["inference_raw_record_ms"]["median"] for record in records])
    )
    assert summary["median_paired_speedup_x"] == pytest.approx(float(np.median(ratios)))
    assert summary["median_paired_speedup_x"] != pytest.approx(ratio_of_medians)

    duplicate = copy.deepcopy(records)
    duplicate[-1]["layout_id"] = duplicate[0]["layout_id"]
    with pytest.raises(ValueError, match="duplicate"):
        finalizer.summarize_records(
            duplicate,
            expected_repetitions=200,
            bootstrap_resamples=10_000,
            bootstrap_seed=20260820,
        )


def test_family_cluster_bootstrap_is_deterministic_and_independently_recomputed() -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v2_finalizer_for_bootstrap_test")
    records = [
        _base_record(layout_id=1, family_id="a", fem_ms=96.0, inference_ms=2.0),
        _base_record(layout_id=2, family_id="a", fem_ms=196.0, inference_ms=2.0),
        _base_record(layout_id=3, family_id="b", fem_ms=16.0, inference_ms=2.0),
        _base_record(layout_id=4, family_id="b", fem_ms=36.0, inference_ms=2.0),
        _base_record(layout_id=5, family_id="c", fem_ms=6.0, inference_ms=2.0),
        _base_record(layout_id=6, family_id="c", fem_ms=10.0, inference_ms=2.0),
    ]
    expected = _independent_family_cluster_interval(
        records, resamples=10_000, seed=20260820
    )
    first = finalizer.summarize_records(
        records,
        expected_repetitions=200,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260820,
    )
    second = finalizer.summarize_records(
        records,
        expected_repetitions=200,
        bootstrap_resamples=10_000,
        bootstrap_seed=20260820,
    )
    assert first == second
    assert first[
        "median_paired_speedup_family_cluster_bootstrap_95_interval"
    ] == pytest.approx(expected)
    assert first["bootstrap_cluster"] in {"family", "family_id"}
    assert first["bootstrap_resamples"] == 10_000
    semantics = first["interval_semantics"].lower()
    assert "descriptive" in semantics
    assert "population" in semantics
    assert "confidence interval" in semantics


def test_slurm_resources_are_the_proven_r3_profile() -> None:
    task = _sbatch_directives(JOBS / "submit_corpus_v4_latency.sh")
    assert task["--account"] == "pgs0407"
    assert task["--partition"] == "nextgen"
    assert task["--nodes"] == "1"
    assert task["--ntasks"] == "1"
    assert task["--cpus-per-task"] == "25"
    assert task["--mem"] == "48G"
    assert task["--time"] == "02:00:00"
    assert task["--array"] == "0-305%8"

    finalizer = _sbatch_directives(JOBS / "submit_finalize_corpus_v4_latency.sh")
    assert finalizer["--account"] == "pgs0407"
    assert int(finalizer["--cpus-per-task"]) <= 2
    assert finalizer["--mem"] == "8G"
    assert finalizer["--time"] == "00:20:00"

    preflight = _sbatch_directives(JOBS / "submit_corpus_v4_latency_preflight.sh")
    assert preflight["--account"] == "pgs0407"


def _latency_preflight_environment(
    monkeypatch: pytest.MonkeyPatch, *, account: str = "pgs0407"
) -> None:
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)
    values = {
        "BLIS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "PCB_GNN_GMSH_THREADS": "25",
        "SLURM_ARRAY_JOB_ID": "8300000",
        "SLURM_ARRAY_TASK_COUNT": "3",
        "SLURM_ARRAY_TASK_ID": "152",
        "SLURM_ARRAY_TASK_MAX": "305",
        "SLURM_ARRAY_TASK_MIN": "0",
        "SLURM_CPUS_PER_TASK": "25",
        "SLURM_JOB_ACCOUNT": account,
        "SLURM_JOB_ID": "8300152",
        "SLURM_JOB_PARTITION": "nextgen",
        "SLURM_MEM_PER_NODE": str(48 * 1024),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _latency_preflight_scheduler_fields(*, account: str = "pgs0407") -> dict[str, str]:
    return {
        "Account": account,
        "AllocTRES": "cpu=25,mem=48G",
        "ArrayJobId": "8300000",
        "ArrayTaskId": "152",
        "ArrayTaskThrottle": "1",
        "CPUs/Task": "25",
        "JobId": "8300152",
        "JobState": "RUNNING",
        "MinMemoryNode": "48G",
        "NumCPUs": "25",
        "NumTasks": "1",
        "Partition": "nextgen",
        "ReqTRES": "cpu=25,mem=48G",
        "TimeLimit": "02:00:00",
        "TresPerTask": "cpu=25",
    }


def _mock_latency_scontrol(
    monkeypatch: pytest.MonkeyPatch,
    contract: ModuleType,
    fields: dict[str, str],
) -> None:
    output = " ".join(f"{name}={value}" for name, value in fields.items()) + "\n"

    def run(command: list[str], **_: Any) -> SimpleNamespace:
        assert command == ["scontrol", "show", "job", "-o", "8300000_152"]
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(contract.subprocess, "run", run)


def test_latency_slurm_guard_records_frozen_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_account_pass")
    _latency_preflight_environment(monkeypatch)
    _mock_latency_scontrol(monkeypatch, contract, _latency_preflight_scheduler_fields())

    receipt = contract.validate_slurm_allocation(_protocol(), stage="preflight")

    assert receipt["scheduler_record"]["Account"] == "pgs0407"


@pytest.mark.parametrize(
    ("environment_account", "scheduler_account"),
    [("wrong-account", "pgs0407"), ("pgs0407", "wrong-account")],
)
def test_latency_slurm_guard_rejects_account_drift(
    monkeypatch: pytest.MonkeyPatch,
    environment_account: str,
    scheduler_account: str,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_account_reject")
    _latency_preflight_environment(monkeypatch, account=environment_account)
    _mock_latency_scontrol(
        monkeypatch,
        contract,
        _latency_preflight_scheduler_fields(account=scheduler_account),
    )

    with pytest.raises(SystemExit, match="frozen preflight resources"):
        contract.validate_slurm_allocation(_protocol(), stage="preflight")


def test_latency_resume_requires_matching_terminal_account() -> None:
    resume = _load_module(RESUME_SCRIPT, "latency_v2_resume_account")
    result = {
        "provenance": {
            "scheduler": {
                "job_id": "8300152",
                "scheduler_record": {
                    "Account": "pgs0407",
                    "AllocTRES": "cpu=25,mem=48G",
                    "ReqTRES": "cpu=25,mem=48G",
                },
            }
        }
    }
    row = {
        "Account": "pgs0407",
        "AllocTRES": "mem=48G,cpu=25",
        "ElapsedRaw": "600",
        "ExitCode": "0:0",
        "JobID": "8300152",
        "JobIDRaw": "8300152",
        "ReqTRES": "mem=48G,cpu=25",
        "State": "COMPLETED",
    }

    assert resume._completion(result, [row])["Account"] == "pgs0407"
    mismatch = {**row, "Account": "wrong-account"}
    assert resume._completion(result, [mismatch]) is None


def test_latency_finalizer_and_archive_cross_check_terminal_account() -> None:
    finalizer_source = FINALIZER_SCRIPT.read_text(encoding="utf-8")
    verifier_source = ARCHIVE_VERIFIER.read_text(encoding="utf-8")

    assert 'completion.get("Account")' in finalizer_source
    assert "JobID,JobIDRaw,Account,State" in verifier_source
    assert 'finalizer_completion.get("Account")' in verifier_source


def test_no_login_node_solver_path_and_guard_precedes_solver_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_v2_contract_for_slurm_test")
    protocol = _protocol()
    for name in tuple(value for value in os.environ if value.startswith("SLURM_")):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="SLURM"):
        contract.validate_slurm_allocation(protocol, stage="full_array")

    tree = ast.parse(TASK_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]

    def call_name(node: ast.Call) -> str:
        function = node.func
        if isinstance(function, ast.Name):
            return function.id
        if isinstance(function, ast.Attribute):
            return function.attr
        return ""

    guards = [node.lineno for node in calls if call_name(node) == "validate_slurm_allocation"]
    solvers = [
        node.lineno
        for node in calls
        if call_name(node)
        in {"run_fasthenry_timed", "run_fem_r3p16_timed", "run_solver_workflow"}
    ]
    assert guards, "the task must call the frozen SLURM allocation validator"
    assert solvers, "the task must expose the paired solver workflow"
    assert min(guards) < min(solvers)


def test_runner_places_solver_between_the_two_measurement_blocks() -> None:
    tree = ast.parse(TASK_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def call_name(node: ast.Call) -> str:
        function = node.func
        if isinstance(function, ast.Name):
            return function.id
        if isinstance(function, ast.Attribute):
            return function.attr
        return ""

    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]
    measurements = sorted(
        (node for node in calls if call_name(node) == "measure_raw_record_inference"),
        key=lambda node: node.lineno,
    )
    solvers = sorted(
        (node for node in calls if call_name(node) == "run_solver_workflow"),
        key=lambda node: node.lineno,
    )
    assert len(measurements) == 2
    assert len(solvers) == 1
    assert measurements[0].lineno < solvers[0].lineno < measurements[1].lineno
    post_warmups = next(
        keyword.value for keyword in measurements[1].keywords if keyword.arg == "warmups"
    )
    assert isinstance(post_warmups, ast.Constant) and post_warmups.value == 0


def test_validate_only_reports_v2_without_running_a_solver() -> None:
    task = _validate_only(TASK_SCRIPT)
    final = _validate_only(FINALIZER_SCRIPT)
    assert task["schema"] == TASK_SCHEMA
    assert task["array_tasks"] == 306
    assert task["fem_fidelity_id"] == "cps_fem_r3_p16"
    assert task["timing_boundary"] == "in-memory-raw-json-record-to-four-output"
    assert task["warmups"] == 50
    assert task["timed_repetitions"] == 200
    assert final["schema"] == FINAL_SCHEMA
    assert final["status"] == "validation-ok"
    assert final["bootstrap_cluster"] == "family"
    assert final["bootstrap_resamples"] == 10_000


def test_archive_verifier_supports_offline_tracked_clean_clone_check() -> None:
    assert ARCHIVE_VERIFIER.is_file(), "latency evidence requires an archive verifier"
    completed = subprocess.run(
        [sys.executable, str(ARCHIVE_VERIFIER), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--check" in completed.stdout
    assert "--require-git-tracked" in completed.stdout


def test_checkpoint_hash_constants_are_well_formed_and_not_placeholders() -> None:
    for name, digest in EXPECTED_CHECKPOINT.items():
        if not name.endswith("sha256"):
            continue
        assert len(digest) == 64
        int(digest, 16)
        assert len(set(digest)) > 8
