"""Independent contracts for the claim-bearing Corpus-v4 latency pipeline.

These tests intentionally describe the version-2 pipeline rather than the
archival 100-design implementation.  Solver work remains a SLURM-only
integration stage; the tests here exercise deterministic planning, validation,
statistics, and archive contracts without launching a field solve.
"""
from __future__ import annotations

import ast
import copy
import hashlib
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
ADMISSION_SCRIPT = PROOFS / "admit_corpus_v4_latency_preflight.py"
FINALIZER_SCRIPT = PROOFS / "finalize_corpus_v4_latency.py"
PLANNER_SCRIPT = PROOFS / "plan_corpus_v4_latency.py"
RESUME_SCRIPT = PROOFS / "plan_corpus_v4_latency_resume.py"
CONTRACT_SCRIPT = PROOFS / "corpus_v4_latency_contract.py"
ARCHIVE_VERIFIER = QUALITY / "verify_corpus_v4_latency_archive.py"

PROTOCOL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-protocol.v2"
TASK_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-task.v3"
RECORD_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-record.v2"
FINAL_SCHEMA = "pcb-gnn.corpus-v4-paired-latency-final.v3"
PREFLIGHT_ADMISSION_SCHEMA = (
    "pcb-gnn.corpus-v4-paired-latency-preflight-admission.v2"
)

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
        "code/experiments/proofs/admit_corpus_v4_latency_preflight.py",
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


def test_failure_artifact_is_immutable_and_not_an_acceptance_manifest(
    tmp_path: Path,
) -> None:
    runner = _load_module(TASK_SCRIPT, "latency_v2_runner_failure_artifact")
    resume = _load_module(RESUME_SCRIPT, "latency_v2_resume_failure_artifact")
    resume.ROOT = tmp_path
    destination = tmp_path / "failures" / "job_8300000" / "task_000"
    failure = {
        "admission_eligible": False,
        "claim_eligible": False,
        "failure_code": "reference_agreement_exceeded",
        "integrity": {"passed": False},
        "schema": runner.FAILURE_SCHEMA,
        "status": "failed",
    }

    runner._atomic_failure_directory(destination, failure)

    assert json.loads((destination / "failure.json").read_text(encoding="utf-8")) == failure
    manifest = json.loads(
        (destination / "FAILURE_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == runner.FAILURE_MANIFEST_SCHEMA
    assert set(manifest["files_sha256"]) == {"failure.json"}
    assert not (destination / "TASK_MANIFEST.json").exists()
    assert resume._manifest_candidates([tmp_path / "failures"]) == []
    with pytest.raises(FileExistsError, match="overwrite failure attempt"):
        runner._atomic_failure_directory(destination, failure)


def test_output_labels_resolve_relative_and_absolute_paths_without_escape(
    tmp_path: Path,
) -> None:
    runner = _load_module(TASK_SCRIPT, "latency_v2_runner_output_label")
    runner.ROOT = tmp_path
    relative = Path("results/task_000")
    absolute = tmp_path / "results" / "task_000"

    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert runner._repo_relative_output(relative) == "results/task_000"
        assert runner._repo_relative_output(absolute) == "results/task_000"
        with pytest.raises(ValueError, match="escapes the repository"):
            runner._repo_relative_output(tmp_path.parent / "outside")
    finally:
        os.chdir(previous)


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


def _latency_array_scheduler(
    *, task_id: int = 152, raw_job_id: str = "8300152"
) -> dict[str, Any]:
    return {
        "array_job_id": "8300000",
        "array_task_id": task_id,
        "job_id": raw_job_id,
        "scheduler_record": {
            "Account": "pgs0407",
            "AllocTRES": "cpu=25,mem=48G",
            "ReqTRES": "cpu=25,mem=48G",
        },
    }


def _latency_terminal_row(
    *, task_id: int = 152, raw_job_id: str = "8300152"
) -> dict[str, str]:
    return {
        "Account": "pgs0407",
        "AllocTRES": "mem=48G,cpu=25",
        "ElapsedRaw": "600",
        "ExitCode": "0:0",
        "JobID": f"8300000_{task_id}",
        "JobIDRaw": raw_job_id,
        "ReqTRES": "mem=48G,cpu=25",
        "State": "COMPLETED",
        "Partition": "nextgen",
        "Timelimit": "02:00:00",
        "NodeList": "nextgen-test",
        "Restarts": "0",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _materialize_preflight_admission_fixture(
    tmp_path: Path,
    contract: ModuleType,
) -> dict[str, Any]:
    contract.ROOT = tmp_path
    task_ids = (0, 152, 305)
    array_job_id = "8300000"
    source_head = "d" * 40
    checkpoint_sha = "c" * 64
    bindings = {
        "execution_lock_sha256": "1" * 64,
        "panel_records_sha256": "2" * 64,
        "plan_sha256": "3" * 64,
        "protocol_sha256": "4" * 64,
        "task_manifest_sha256": "5" * 64,
    }
    source_hashes = {
        "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py": "9" * 64,
        "code/experiments/proofs/admit_corpus_v4_latency_preflight.py": "a" * 64,
        "code/jobs/submit_corpus_v4_latency_preflight.sh": "b" * 64,
    }
    repeat_protocol_path = tmp_path / "protocols/corpus_v4_fem_repeatability_v1.json"
    repeat_protocol_path.parent.mkdir(parents=True)
    repeat_protocol_path.write_text('{"schema":"test"}\n', encoding="utf-8")
    source_hashes["protocols/corpus_v4_fem_repeatability_v1.json"] = _sha256(
        repeat_protocol_path
    )
    repeat_source_job = "8100000"
    repeat_finalizer_job = "8200000"
    repeat_admission_path = (
        tmp_path
        / "results/corpus_v4/fem_repeatability/v1/admission"
        / f"source_job_{repeat_source_job}"
        / f"finalizer_job_{repeat_finalizer_job}"
        / "FINAL_ADMISSION.json"
    )
    repeat_admission_path.parent.mkdir(parents=True)
    repeat_admission = {
        "artifact_stage": "postterminal_finalizer_admission",
        "claim_eligible": False,
        "created_utc": "2026-08-20T00:00:00+00:00",
        "decision": {
            "paired_latency_preflight_may_resume": True,
            "provisional_preterminal_gate_pass": True,
            "terminal_finalizer_completed_zero": True,
        },
        "finalizer": {
            "accounting": {
                "row": {
                    "Account": "pgs0407",
                    "ExitCode": "0:0",
                    "JobID": repeat_finalizer_job,
                    "JobIDRaw": repeat_finalizer_job,
                    "Partition": "nextgen",
                    "State": "COMPLETED",
                }
            },
            "accounting_provenance": {"origin": "live_sacct"},
            "job_id": repeat_finalizer_job,
            "job_id_raw": repeat_finalizer_job,
        },
        "preterminal_final": {
            "final_manifest_path": "final/FINAL_MANIFEST.json",
            "final_manifest_sha256": "7" * 64,
            "final_result_path": "final/result.json",
            "final_result_sha256": "8" * 64,
            "finalizer_job_id": repeat_finalizer_job,
            "finalizer_scheduler_tres": {},
            "provisional_preterminal_gate_pass": True,
            "source_array_job_id": repeat_source_job,
        },
        "protocol_sha256": source_hashes[
            "protocols/corpus_v4_fem_repeatability_v1.json"
        ],
        "schema": contract.FEM_REPEATABILITY_ADMISSION_SCHEMA,
        "source_git_head": source_head,
        "speed_claim_eligible": False,
        "validator": {
            "path": "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py",
            "sha256": source_hashes[
                "code/experiments/proofs/admit_corpus_v4_fem_repeatability.py"
            ],
        },
    }
    repeat_admission_path.write_text(
        json.dumps(repeat_admission, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )
    repeatability_reference = {
        "path": repeat_admission_path.relative_to(tmp_path).as_posix(),
        "sha256": _sha256(repeat_admission_path),
    }
    contract.fem_repeatability_admission.authenticate_protocol = lambda *_: (
        {},
        {
            "protocol_sha256": source_hashes[
                "protocols/corpus_v4_fem_repeatability_v1.json"
            ]
        },
    )
    contract.fem_repeatability_admission.query_live_finalizer_accounting = (
        lambda *_: ([], {})
    )
    contract.fem_repeatability_admission.validate_admission_payload = (
        lambda *_args, **_kwargs: repeat_admission["preterminal_final"]
    )
    lock = {"source_sha256": source_hashes}
    tasks = [
        {
            "family_id": f"family-{task_id:03d}",
            "geometry_sha256": f"{task_id:064x}",
            "layout_id": task_id,
            "task_id": task_id,
        }
        for task_id in range(306)
    ]
    raw_job_ids = {0: "8300001", 152: "8300152", 305: array_job_id}
    entries: list[dict[str, Any]] = []
    for task_id in task_ids:
        task = tasks[task_id]
        scheduler = _latency_array_scheduler(
            task_id=task_id, raw_job_id=raw_job_ids[task_id]
        )
        scheduler["stage"] = "preflight"
        result = {
            "bindings": {
                **bindings,
                "checkpoint_archive_sha256": checkpoint_sha,
                "fem_repeatability_admission": repeatability_reference,
                "preflight_admission": None,
                "retry_pending_set": None,
            },
            "created_utc": "2026-08-20T00:00:00+00:00",
            "integrity": {"passed": True},
            "provenance": {
                "executed_batch_sha256": source_hashes[
                    "code/jobs/submit_corpus_v4_latency_preflight.sh"
                ],
                "scheduler": scheduler,
                "source_git_head": source_head,
                "source_sha256": source_hashes,
            },
            "record": _base_record(
                layout_id=task_id, family_id=task["family_id"]
            ),
            "schema": TASK_SCHEMA,
            "stage": "preflight",
            "task": task,
        }
        task_root = (
            tmp_path
            / "results/corpus_v4/latency/preflight/attempts"
            / f"job_{array_job_id}"
            / f"task_{task_id:03d}"
        )
        task_root.mkdir(parents=True)
        result_path = task_root / "result.json"
        result_path.write_text(
            json.dumps(result, allow_nan=False, sort_keys=True), encoding="utf-8"
        )
        manifest_path = task_root / "TASK_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "files_sha256": {"result.json": _sha256(result_path)},
                    "schema": (
                        "pcb-gnn.corpus-v4-paired-latency-"
                        "task-artifact-manifest.v2"
                    ),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        completion = _latency_terminal_row(
            task_id=task_id, raw_job_id=raw_job_ids[task_id]
        )
        completion["ReqTRES"] = "cpu=25,mem=48G"
        completion["AllocTRES"] = "cpu=25,mem=48G"
        entries.append(
            {
                "manifest_path": manifest_path.relative_to(tmp_path).as_posix(),
                "manifest_sha256": _sha256(manifest_path),
                "result_sha256": _sha256(result_path),
                "scheduler_completion": completion,
                "task_id": task_id,
            }
        )
    payload = {
        "accounting_provenance": {
            "canonical_rows_sha256": hashlib.sha256(
                contract.canonical_json_bytes(
                    sorted(
                        [entry["scheduler_completion"] for entry in entries],
                        key=lambda row: row["JobID"],
                    )
                )
            ).hexdigest(),
            "command": [
                "sacct",
                "-X",
                "-n",
                "-P",
                "-j",
                array_job_id,
                "--format=" + ",".join(contract.PREFLIGHT_SACCT_FIELDS),
            ],
            "queried_utc": "2026-08-20T00:01:00+00:00",
            "raw_stdout_sha256": "6" * 64,
            "row_count": 3,
        },
        "bindings": bindings,
        "claim_eligible": False,
        "entries": entries,
        "expected_task_ids": list(task_ids),
        "fem_repeatability_admission": repeatability_reference,
        "full_array_authorized": True,
        "n_accepted": 3,
        "n_expected": 3,
        "preflight_array_job_id": array_job_id,
        "schema": PREFLIGHT_ADMISSION_SCHEMA,
        "source_git_head": source_head,
        "status": "admitted-for-full-array",
        "validator_source_sha256": source_hashes[
            "code/experiments/proofs/admit_corpus_v4_latency_preflight.py"
        ],
    }
    return {
        "bindings": bindings,
        "checkpoint_sha": checkpoint_sha,
        "lock": lock,
        "payload": payload,
        "repeatability_reference": repeatability_reference,
        "source_head": source_head,
        "tasks": tasks,
    }


def _rewrite_preflight_fixture_result(
    fixture: dict[str, Any],
    tmp_path: Path,
    task_id: int,
    mutation: Any,
) -> None:
    entry = next(
        item for item in fixture["payload"]["entries"] if item["task_id"] == task_id
    )
    manifest_path = tmp_path / entry["manifest_path"]
    result_path = manifest_path.parent / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    mutation(result)
    result_path.write_text(
        json.dumps(result, allow_nan=False, sort_keys=True), encoding="utf-8"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "files_sha256": {"result.json": _sha256(result_path)},
                "schema": (
                    "pcb-gnn.corpus-v4-paired-latency-"
                    "task-artifact-manifest.v2"
                ),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    entry["result_sha256"] = _sha256(result_path)
    entry["manifest_sha256"] = _sha256(manifest_path)


@pytest.mark.parametrize(
    ("task_id", "raw_job_id"),
    ((152, "8300152"), (305, "8300000")),
)
def test_latency_terminal_array_completion_accepts_logical_and_raw_identity(
    task_id: int,
    raw_job_id: str,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, f"latency_terminal_identity_{task_id}")
    scheduler = _latency_array_scheduler(task_id=task_id, raw_job_id=raw_job_id)
    row = _latency_terminal_row(task_id=task_id, raw_job_id=raw_job_id)

    completion = contract.validate_terminal_array_completion(scheduler, [row])

    assert completion is not None
    assert completion["JobID"] == f"8300000_{task_id}"
    assert completion["JobIDRaw"] == raw_job_id
    assert completion["ReqTRES"] == "cpu=25,mem=48G"
    assert completion["AllocTRES"] == "cpu=25,mem=48G"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("JobID", "8300152"),
        ("JobIDRaw", "8300999"),
        ("Account", "wrong-account"),
        ("ReqTRES", "cpu=24,mem=48G"),
        ("AllocTRES", "cpu=24,mem=48G"),
        ("State", "FAILED"),
        ("ExitCode", "1:0"),
    ),
)
def test_latency_terminal_array_completion_rejects_identity_or_receipt_drift(
    field: str,
    value: str,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, f"latency_terminal_reject_{field}")
    scheduler = _latency_array_scheduler()
    row = {**_latency_terminal_row(), field: value}

    assert contract.validate_terminal_array_completion(scheduler, [row]) is None


def test_latency_terminal_array_completion_rejects_duplicate_logical_rows() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_terminal_duplicate")
    scheduler = _latency_array_scheduler()
    row = _latency_terminal_row()
    conflicting_raw = {**row, "JobIDRaw": "8300999"}

    assert (
        contract.validate_terminal_array_completion(
            scheduler, [row, conflicting_raw]
        )
        is None
    )


def test_latency_terminal_array_completion_requires_in_run_account() -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_terminal_missing_account")
    scheduler = _latency_array_scheduler()
    scheduler["scheduler_record"].pop("Account")

    assert (
        contract.validate_terminal_array_completion(
            scheduler, [_latency_terminal_row()]
        )
        is None
    )


def test_latency_resume_uses_shared_terminal_array_completion() -> None:
    resume = _load_module(RESUME_SCRIPT, "latency_v2_resume_account")
    result = {"provenance": {"scheduler": _latency_array_scheduler()}}
    row = _latency_terminal_row()

    assert resume._completion(result, [row])["Account"] == "pgs0407"
    assert resume._completion(result, [{**row, "Account": "wrong-account"}]) is None


def test_preflight_admission_accepts_exact_three_v3_successes(tmp_path: Path) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_preflight_admission_pass")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)

    observed = contract.validate_preflight_admission_payload(
        fixture["payload"],
        bindings=fixture["bindings"],
        expected_source_git_head=fixture["source_head"],
        tasks=fixture["tasks"],
        lock=fixture["lock"],
        checkpoint_archive_sha256=fixture["checkpoint_sha"],
    )

    assert observed == fixture["payload"]
    assert observed["claim_eligible"] is False
    assert observed["expected_task_ids"] == [0, 152, 305]
    assert observed["n_accepted"] == 3


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "rejected"),
        ("claim_eligible", True),
        ("full_array_authorized", False),
        ("source_git_head", "e" * 40),
        ("expected_task_ids", [0, 152]),
        ("n_accepted", 2),
    ),
)
def test_preflight_admission_rejects_top_level_contract_drift(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, f"latency_admission_reject_{field}")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    changed = {**fixture["payload"], field: value}

    with pytest.raises(ValueError, match="preflight admission"):
        contract.validate_preflight_admission_payload(
            changed,
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("task_id", 152),
        ("result_sha256", "f" * 64),
        ("manifest_sha256", "f" * 64),
    ),
)
def test_preflight_admission_rejects_duplicate_or_hash_drift(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, f"latency_admission_entry_{field}")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    changed = copy.deepcopy(fixture["payload"])
    changed["entries"][0][field] = value

    with pytest.raises(ValueError):
        contract.validate_preflight_admission_payload(
            changed,
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


def test_preflight_admission_rejects_failure_tree(tmp_path: Path) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_admission_failure_tree")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    failure_root = (
        tmp_path
        / "results/corpus_v4/latency/preflight/failures/job_8300000/task_000"
    )
    failure_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="failure tree"):
        contract.validate_preflight_admission_payload(
            fixture["payload"],
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


def test_preflight_admission_rejects_terminal_identity_drift(tmp_path: Path) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_admission_terminal_drift")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    changed = copy.deepcopy(fixture["payload"])
    changed["entries"][2]["scheduler_completion"]["JobIDRaw"] = "8300999"

    with pytest.raises(ValueError, match="terminal accounting"):
        contract.validate_preflight_admission_payload(
            changed,
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


@pytest.mark.parametrize(
    ("label", "mutation"),
    (
        ("v2", lambda result: result.__setitem__("schema", TASK_SCHEMA[:-1] + "2")),
        (
            "source",
            lambda result: result["provenance"].__setitem__(
                "source_git_head", "e" * 40
            ),
        ),
        (
            "wrapper",
            lambda result: result["provenance"].__setitem__(
                "executed_batch_sha256", "f" * 64
            ),
        ),
        (
            "root",
            lambda result: result["bindings"].__setitem__(
                "plan_sha256", "f" * 64
            ),
        ),
    ),
)
def test_preflight_admission_rejects_unauthenticated_success_artifact(
    tmp_path: Path,
    label: str,
    mutation: Any,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, f"latency_admission_artifact_{label}")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    _rewrite_preflight_fixture_result(fixture, tmp_path, 0, mutation)

    with pytest.raises(ValueError, match="task identity|source"):
        contract.validate_preflight_admission_payload(
            fixture["payload"],
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


def test_preflight_admission_rejects_extra_attempt_directory(tmp_path: Path) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_admission_extra_attempt")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    (
        tmp_path
        / "results/corpus_v4/latency/preflight/attempts/job_8300000/task_999"
    ).mkdir()

    with pytest.raises(ValueError, match="inventory"):
        contract.validate_preflight_admission_payload(
            fixture["payload"],
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


def test_preflight_admission_file_requires_canonical_path_and_hash(
    tmp_path: Path,
) -> None:
    contract = _load_module(CONTRACT_SCRIPT, "latency_admission_file")
    fixture = _materialize_preflight_admission_fixture(tmp_path, contract)
    admission_path = (
        tmp_path
        / "results/corpus_v4/latency/preflight/admission/job_8300000"
        / "PREFLIGHT_ADMISSION.json"
    )
    admission_path.parent.mkdir(parents=True)
    admission_path.write_text(
        json.dumps(fixture["payload"], allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )
    digest = _sha256(admission_path)

    _, reference = contract.validate_preflight_admission(
        admission_path,
        digest,
        bindings=fixture["bindings"],
        expected_source_git_head=fixture["source_head"],
        tasks=fixture["tasks"],
        lock=fixture["lock"],
        checkpoint_archive_sha256=fixture["checkpoint_sha"],
    )
    assert reference == {
        "path": (
            "results/corpus_v4/latency/preflight/admission/job_8300000/"
            "PREFLIGHT_ADMISSION.json"
        ),
        "sha256": digest,
    }
    with pytest.raises(ValueError, match="SHA-256|hash"):
        contract.validate_preflight_admission(
            admission_path,
            "f" * 64,
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )
    real_path = admission_path.with_name("real-admission.json")
    admission_path.rename(real_path)
    admission_path.symlink_to(real_path)
    with pytest.raises(ValueError, match="regular file"):
        contract.validate_preflight_admission(
            admission_path,
            digest,
            bindings=fixture["bindings"],
            expected_source_git_head=fixture["source_head"],
            tasks=fixture["tasks"],
            lock=fixture["lock"],
            checkpoint_archive_sha256=fixture["checkpoint_sha"],
        )


def _latency_runner_args(
    *,
    stage: str,
    admission: Path | None,
    admission_sha256: str | None,
    repeatability_admission: Path | None = None,
    repeatability_sha256: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        stage=stage,
        protocol=Path("protocol.json"),
        expected_protocol_sha256="1" * 64,
        plan=Path("plan.json"),
        expected_plan_sha256="2" * 64,
        task_manifest=Path("tasks.jsonl"),
        expected_task_manifest_sha256="3" * 64,
        execution_lock=Path("lock.json"),
        expected_execution_lock_sha256="4" * 64,
        expected_source_git_head="5" * 40,
        preflight_admission=admission,
        expected_preflight_admission_sha256=admission_sha256,
        fem_repeatability_admission=repeatability_admission,
        expected_fem_repeatability_admission_sha256=repeatability_sha256,
        pending_set=None,
        expected_pending_set_sha256=None,
        output_root=Path("results"),
    )


def test_full_runner_requires_paired_preflight_admission_arguments() -> None:
    runner = _load_module(TASK_SCRIPT, "latency_runner_admission_args")
    valid = _latency_runner_args(
        stage="full_array",
        admission=Path("PREFLIGHT_ADMISSION.json"),
        admission_sha256="a" * 64,
    )
    runner._require_runtime_args(valid)

    with pytest.raises(SystemExit, match="requires preflight admission"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="full_array", admission=None, admission_sha256=None
            )
        )
    with pytest.raises(SystemExit, match="path and digest"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="full_array",
                admission=Path("PREFLIGHT_ADMISSION.json"),
                admission_sha256=None,
            )
        )


def test_preflight_runner_rejects_admission_arguments() -> None:
    runner = _load_module(TASK_SCRIPT, "latency_preflight_rejects_admission")
    runner._require_runtime_args(
        _latency_runner_args(
            stage="preflight",
            admission=None,
            admission_sha256=None,
            repeatability_admission=Path("FINAL_ADMISSION.json"),
            repeatability_sha256="b" * 64,
        )
    )

    with pytest.raises(SystemExit, match="cannot consume"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="preflight",
                admission=Path("PREFLIGHT_ADMISSION.json"),
                admission_sha256="a" * 64,
                repeatability_admission=Path("FINAL_ADMISSION.json"),
                repeatability_sha256="b" * 64,
            )
        )


def test_preflight_runner_requires_paired_fem_repeatability_arguments() -> None:
    runner = _load_module(TASK_SCRIPT, "latency_preflight_repeatability_args")
    with pytest.raises(SystemExit, match="requires FEM repeatability admission"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="preflight", admission=None, admission_sha256=None
            )
        )
    with pytest.raises(SystemExit, match="path and digest"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="preflight",
                admission=None,
                admission_sha256=None,
                repeatability_admission=Path("FINAL_ADMISSION.json"),
            )
        )
    with pytest.raises(SystemExit, match="through preflight admission"):
        runner._require_runtime_args(
            _latency_runner_args(
                stage="full_array",
                admission=Path("PREFLIGHT_ADMISSION.json"),
                admission_sha256="a" * 64,
                repeatability_admission=Path("FINAL_ADMISSION.json"),
                repeatability_sha256="b" * 64,
            )
        )


def test_full_wrapper_cannot_omit_preflight_admission() -> None:
    source = (JOBS / "submit_corpus_v4_latency.sh").read_text(encoding="utf-8")

    assert ': "${PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION:?' in source
    assert ': "${PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION_SHA256:?' in source
    assert '--preflight-admission "$PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION"' in source
    assert (
        '--expected-preflight-admission-sha256 '
        '"$PCB_GNN_V4_LATENCY_PREFLIGHT_ADMISSION_SHA256"'
    ) in source


def test_preflight_wrapper_cannot_omit_fem_repeatability_admission() -> None:
    source = (JOBS / "submit_corpus_v4_latency_preflight.sh").read_text(
        encoding="utf-8"
    )

    assert ': "${PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION:?' in source
    assert ': "${PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION_SHA256:?' in source
    assert (
        '--fem-repeatability-admission '
        '"$PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION"'
    ) in source


def test_latency_admission_clis_expose_no_accounting_fixture() -> None:
    for path in (ADMISSION_SCRIPT, RESUME_SCRIPT):
        source = path.read_text(encoding="utf-8")
        assert "--accounting-file" not in source
        assert "accounting fixture" not in source
    assert (
        '--expected-fem-repeatability-admission-sha256 '
        '"$PCB_GNN_V4_FEM_REPEATABILITY_ADMISSION_SHA256"'
    ) in source


def test_admission_gate_precedes_model_and_solver_work() -> None:
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
    admission = [
        node.lineno
        for node in calls
        if call_name(node) == "validate_preflight_admission"
    ]
    repeatability = [
        node.lineno
        for node in calls
        if call_name(node) == "validate_fem_repeatability_admission"
    ]
    heavy = [
        node.lineno
        for node in calls
        if call_name(node)
        in {
            "load_designated_model",
            "measure_raw_record_inference",
            "run_solver_workflow",
        }
    ]
    assert len(admission) == 1
    assert len(repeatability) == 1
    assert heavy
    assert admission[0] < min(heavy)
    assert repeatability[0] < min(heavy)


def test_admission_builder_validates_before_creating_output() -> None:
    tree = ast.parse(ADMISSION_SCRIPT.read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]

    def lines(name: str) -> list[int]:
        result: list[int] = []
        for node in calls:
            function = node.func
            observed = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute) else ""
            )
            if observed == name:
                result.append(node.lineno)
        return sorted(result)

    validation = lines("validate_preflight_admission_payload")
    output_write = lines("atomic_write_json")
    output_mkdir = lines("mkdir")
    assert len(validation) == len(output_write) == len(output_mkdir) == 1
    assert validation[0] < output_mkdir[0] < output_write[0]


def test_admission_builder_failure_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_module(ADMISSION_SCRIPT, "latency_admission_no_output")
    builder.ROOT = tmp_path
    array_job_id = "8300000"
    out = (
        tmp_path
        / "results/corpus_v4/latency/preflight/admission/job_8300000"
        / "PREFLIGHT_ADMISSION.json"
    )
    repeatability_reference = {
        "path": (
            "results/corpus_v4/fem_repeatability/v1/admission/"
            "source_job_8100000/finalizer_job_8200000/FINAL_ADMISSION.json"
        ),
        "sha256": "9" * 64,
    }
    for task_id in (0, 152, 305):
        task_root = (
            tmp_path
            / "results/corpus_v4/latency/preflight/attempts/job_8300000"
            / f"task_{task_id:03d}"
        )
        task_root.mkdir(parents=True)
        (task_root / "result.json").write_text(
            json.dumps(
                {
                    "bindings": {
                        "fem_repeatability_admission": repeatability_reference
                    },
                    "provenance": {"scheduler": {}},
                    "record": {},
                }
            ),
            encoding="utf-8",
        )
        (task_root / "TASK_MANIFEST.json").write_text("{}", encoding="utf-8")

    protocol = {
        "gnn_timing": {"measured_repetitions": 200},
        "inputs": {"checkpoint_archive": {"sha256": "c" * 64}},
    }
    tasks = [{"task_id": index} for index in range(306)]
    lock = {
        "source_sha256": {
            "code/experiments/proofs/admit_corpus_v4_latency_preflight.py": "a" * 64
        }
    }
    monkeypatch.setattr(builder, "validate_protocol", lambda *_: (protocol, "1" * 64))
    monkeypatch.setattr(
        builder,
        "validate_plan",
        lambda *_args, **_kwargs: ({}, tasks, [], "2" * 64, "3" * 64, "4" * 64),
    )
    monkeypatch.setattr(builder, "validate_root_closure", lambda **_: None)
    monkeypatch.setattr(
        builder, "validate_execution_lock", lambda *_args, **_kwargs: (lock, "5" * 64)
    )
    monkeypatch.setattr(builder, "_source_head", lambda: "d" * 40)
    monkeypatch.setattr(
        builder,
        "_query_sacct",
        lambda *_: (
            [_latency_terminal_row(task_id=index) for index in (0, 152, 305)],
            {},
        ),
    )
    monkeypatch.setattr(builder, "validate_timing_record", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        builder,
        "validate_terminal_array_completion",
        lambda *_: _latency_terminal_row(task_id=0, raw_job_id="8300001"),
    )
    monkeypatch.setattr(
        builder,
        "validate_preflight_admission_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("blocked")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(ADMISSION_SCRIPT),
            "--protocol", "protocol.json",
            "--expected-protocol-sha256", "1" * 64,
            "--plan", "plan.json",
            "--expected-plan-sha256", "2" * 64,
            "--task-manifest", "tasks.jsonl",
            "--expected-task-manifest-sha256", "3" * 64,
            "--execution-lock", "lock.json",
            "--expected-execution-lock-sha256", "5" * 64,
            "--expected-source-git-head", "d" * 40,
            "--array-job-id", array_job_id,
            "--out", str(out),
        ],
    )

    with pytest.raises(ValueError, match="blocked"):
        builder.main()
    assert not out.exists()
    assert not out.parent.exists()


def test_latency_v3_schemas_propagate_preflight_binding() -> None:
    runner = _load_module(TASK_SCRIPT, "latency_v3_runner_schema")
    resume = _load_module(RESUME_SCRIPT, "latency_v3_resume_schema")
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v3_final_schema")
    archive = _load_module(ARCHIVE_VERIFIER, "latency_v3_archive_schema")

    assert runner.TASK_SCHEMA.endswith(".v3")
    assert runner.PENDING_SCHEMA.endswith(".v3")
    assert resume.CANDIDATE_SCHEMA.endswith(".v3")
    assert resume.ACCEPTED_SCHEMA.endswith(".v3")
    assert resume.PENDING_SCHEMA.endswith(".v3")
    assert finalizer.ACCEPTED_SCHEMA.endswith(".v3")
    assert finalizer.FINAL_SCHEMA.endswith(".v3")
    assert archive.ARCHIVE_SCHEMA.endswith(".v3")
    for source in (
        TASK_SCRIPT.read_text(encoding="utf-8"),
        RESUME_SCRIPT.read_text(encoding="utf-8"),
        FINALIZER_SCRIPT.read_text(encoding="utf-8"),
        ARCHIVE_VERIFIER.read_text(encoding="utf-8"),
    ):
        assert "preflight_admission" in source


def test_retry_pending_set_is_bound_to_same_preflight_admission(
    tmp_path: Path,
) -> None:
    runner = _load_module(TASK_SCRIPT, "latency_v3_pending_admission")
    admission = {
        "path": (
            "results/corpus_v4/latency/preflight/admission/job_8300000/"
            "PREFLIGHT_ADMISSION.json"
        ),
        "sha256": "a" * 64,
    }
    bindings = {
        "execution_lock_sha256": "1" * 64,
        "panel_records_sha256": "2" * 64,
        "plan_sha256": "3" * 64,
        "preflight_admission": admission,
        "protocol_sha256": "4" * 64,
        "task_manifest_sha256": "5" * 64,
    }
    pending_path = tmp_path / "pending_task_set.json"
    payload = {
        **bindings,
        "n_pending": 2,
        "pending_task_ids": [7, 11],
        "schema": runner.PENDING_SCHEMA,
    }
    pending_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    assert runner._validate_pending_set(
        pending_path, _sha256(pending_path), bindings=bindings
    ) == [7, 11]

    changed = copy.deepcopy(payload)
    changed["preflight_admission"]["sha256"] = "b" * 64
    pending_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="retry contract"):
        runner._validate_pending_set(
            pending_path, _sha256(pending_path), bindings=bindings
        )


def test_finalizer_accepted_set_retains_preflight_admission(tmp_path: Path) -> None:
    finalizer = _load_module(FINALIZER_SCRIPT, "latency_v3_accepted_admission")
    bindings = {
        "execution_lock_sha256": "1" * 64,
        "panel_records_sha256": "2" * 64,
        "plan_sha256": "3" * 64,
        "protocol_sha256": "4" * 64,
        "task_manifest_sha256": "5" * 64,
    }
    admission = {"path": "results/preflight.json", "sha256": "a" * 64}
    accepted_path = tmp_path / "accepted_artifact_set.json"
    accepted_path.write_text(
        json.dumps(
            {
                **bindings,
                "candidate_index": {"path": "candidate.json", "sha256": "b" * 64},
                "entries": [{"task_id": task_id} for task_id in range(306)],
                "n_accepted": 306,
                "n_expected": 306,
                "preflight_admission": admission,
                "schema": finalizer.ACCEPTED_SCHEMA,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    entries, observed_admission = finalizer._accepted_entries(
        accepted_path, _sha256(accepted_path), bindings=bindings
    )
    assert len(entries) == 306
    assert observed_admission == admission


def test_latency_finalizer_and_archive_cross_check_terminal_account() -> None:
    finalizer_source = FINALIZER_SCRIPT.read_text(encoding="utf-8")
    verifier_source = ARCHIVE_VERIFIER.read_text(encoding="utf-8")

    assert "validate_terminal_array_completion" in finalizer_source
    assert "JobID,JobIDRaw,Account,State" in verifier_source
    assert "validate_terminal_array_completion" in verifier_source
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


def test_source_stability_gate_precedes_authenticated_failure_write() -> None:
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

    stability = sorted(
        node.lineno for node in calls if call_name(node) == "_validate_source_stability"
    )
    failure_writes = sorted(
        node.lineno for node in calls if call_name(node) == "_atomic_failure_directory"
    )

    assert len(stability) == 2
    assert len(failure_writes) == 1
    assert stability[0] < failure_writes[0] < stability[1]


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


def test_validate_only_reports_current_schemas_without_running_a_solver() -> None:
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
