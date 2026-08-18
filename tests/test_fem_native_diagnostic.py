from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import diags


ROOT = Path(__file__).resolve().parents[1]
SOLVERS = ROOT / "code" / "solvers"
CORE = ROOT / "code" / "core"
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(SOLVERS))
sys.path.insert(0, str(CORE))

from fem_capacitance_3d import (  # noqa: E402
    _solve_primary_and_comparison,
    _sparse_system_sha256,
)
from fem_cps_diagnostic_worker import _json_default  # noqa: E402
from experiments.proofs.experiments_corpus_v4_fem_native_diagnostic import (  # noqa: E402
    parse_prefixed,
)
from experiments.proofs.finalize_corpus_v4_fem_native_diagnostic import (  # noqa: E402
    finalize,
)


def test_direct_and_amg_cg_match_on_spd_system() -> None:
    matrix = diags((-np.ones(7), 2.0 * np.ones(8), -np.ones(7)), (-1, 0, 1)).tocsr()
    rhs = np.linspace(0.1, 0.8, 8)
    direct, direct_meta, iterative, iterative_meta = _solve_primary_and_comparison(
        matrix,
        rhs,
        primary_solver="direct",
        comparison_solver="amg_cg",
        rtol=1e-10,
        maxiter=500,
    )
    assert iterative is not None and iterative_meta is not None
    np.testing.assert_allclose(iterative, direct, rtol=1e-9, atol=1e-11)
    assert direct_meta["relative_residual"] <= 1e-9
    assert iterative_meta["relative_residual"] <= 1e-9
    assert iterative_meta["solver_info"] == 0
    assert (
        direct_meta["input_system_sha256"]
        == iterative_meta["input_system_sha256"]
    )


def test_ci_installs_the_amg_dependency_used_by_the_contract_suite() -> None:
    requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "pyamg==5.3.0" in requirements
    assert "pyamg==5.3.0" in workflow


def test_native_diagnostic_validate_only_is_lightweight() -> None:
    script = (
        ROOT
        / "code"
        / "experiments"
        / "proofs"
        / "experiments_corpus_v4_fem_native_diagnostic.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--validate-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["schema"] == "pcb-gnn.corpus-v4-fem-native-diagnostic-task.v2"
    assert result["status"] == "validation-ok"
    assert result["protocol_revision"] == 2
    assert set(result["arms"]) == {"0", "1"}
    assert result["arms"]["0"] == [
        {
            "name": "direct_vs_amg_refine2",
            "refine": 2,
            "pad_mm": 12.0,
            "solver": "direct",
            "comparison_solver": "amg_cg",
        }
    ]


def test_worker_exposes_native_stage_and_faulthandler_contract() -> None:
    worker = (ROOT / "code" / "solvers" / "fem_cps_diagnostic_worker.py").read_text()
    assert "faulthandler.enable(all_threads=True)" in worker
    assert '"STAGE="' in worker
    assert "strict=True" in worker
    assert "except Exception:\n        pass" not in worker


def test_worker_serializes_numpy_telemetry_scalars() -> None:
    encoded = json.dumps(
        {
            "n_dofs": np.int32(242_172),
            "relative_residual": np.float32(1e-10),
            "converged": np.bool_(True),
            "shape": np.asarray([2, 3], dtype=np.int64),
        },
        default=_json_default,
    )
    decoded = json.loads(encoded)
    assert decoded["n_dofs"] == 242_172
    assert decoded["relative_residual"] == float(np.float32(1e-10))
    assert decoded["converged"] is True
    assert decoded["shape"] == [2, 3]


def test_worker_rejects_unsupported_telemetry_objects() -> None:
    with np.testing.assert_raises(TypeError):
        json.dumps({"bad": object()}, default=_json_default)
    with np.testing.assert_raises(TypeError):
        json.dumps({"bad": np.complex64(1 + 2j)}, default=_json_default)


def test_malformed_telemetry_is_preserved_without_masking_worker_failure() -> None:
    parsed, errors = parse_prefixed(
        ['noise', 'STAGE={"stage":"mesh_generated"}', 'STAGE={"stage":'],
        "STAGE=",
    )
    assert parsed == [{"stage": "mesh_generated"}]
    assert len(errors) == 1
    assert errors[0]["raw_line"] == 'STAGE={"stage":'


def test_sparse_system_fingerprint_is_deterministic_and_rhs_sensitive() -> None:
    matrix = diags((-np.ones(2), 2.0 * np.ones(3), -np.ones(2)), (-1, 0, 1)).tocsr()
    rhs = np.asarray([0.1, 0.2, 0.3])
    fingerprint = _sparse_system_sha256(matrix, rhs)
    assert _sparse_system_sha256(matrix.copy(), rhs.copy()) == fingerprint
    assert _sparse_system_sha256(matrix, rhs + 1e-12) != fingerprint


def test_native_diagnostic_finalizer_requires_both_tasks(tmp_path: Path) -> None:
    common = {
        "git_head": "a" * 40,
        "corpus_artifacts_sha256": {"layouts.jsonl": "b", "labels.jsonl": "c"},
        "file_sha256": {"worker.py": "d"},
        "package_versions": {"numpy": "1"},
        "thread_environment": {"OMP_NUM_THREADS": "1"},
        "slurm_resources": {"SLURM_CPUS_PER_TASK": "8"},
        "arm_timeout_s": 18000,
        "source_stable": True,
        "slurm_array_job_id": "123",
    }
    for task_id in (0, 1):
        payload = {
            "schema": "pcb-gnn.corpus-v4-fem-native-diagnostic-task.v2",
            "protocol_revision": 2,
            "task_id": task_id,
            "selection": {"layout_id": 1055, "geometry_sha256": "e"},
            "provenance": {
                **common,
                "slurm_array_task_id": task_id,
                "executed_batch_script": {
                    "path": f"/spool/task-{task_id}/slurm_script",
                    "sha256": "f",
                },
            },
            "gates": {"pass": True},
        }
        (tmp_path / f"task_{task_id:02d}.json").write_text(json.dumps(payload))
    summary = finalize(tmp_path, "123")
    assert summary["pass"] is True
    assert set(summary["task_artifacts_sha256"]) == {"task_00.json", "task_01.json"}

    failed = json.loads((tmp_path / "task_01.json").read_text())
    failed["gates"]["pass"] = False
    (tmp_path / "task_01.json").write_text(json.dumps(failed))
    with np.testing.assert_raises_regex(RuntimeError, "scientific gate failed"):
        finalize(tmp_path, "123")

    failed["gates"]["pass"] = True
    failed["provenance"]["slurm_array_task_id"] = 0
    (tmp_path / "task_01.json").write_text(json.dumps(failed))
    with np.testing.assert_raises_regex(RuntimeError, "SLURM task provenance"):
        finalize(tmp_path, "123")

    failed["provenance"]["slurm_array_task_id"] = 1
    failed["provenance"]["executed_batch_script"]["sha256"] = "different"
    (tmp_path / "task_01.json").write_text(json.dumps(failed))
    with np.testing.assert_raises_regex(RuntimeError, "different SLURM batch scripts"):
        finalize(tmp_path, "123")
