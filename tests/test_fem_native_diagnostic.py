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
sys.path.insert(0, str(SOLVERS))
sys.path.insert(0, str(CORE))

from fem_capacitance_3d import _solve_condensed_system  # noqa: E402


def test_direct_and_amg_cg_match_on_spd_system() -> None:
    matrix = diags((-np.ones(7), 2.0 * np.ones(8), -np.ones(7)), (-1, 0, 1)).tocsr()
    rhs = np.linspace(0.1, 0.8, 8)
    direct, direct_meta = _solve_condensed_system(
        matrix, rhs, linear_solver="direct", rtol=1e-10, maxiter=500
    )
    iterative, iterative_meta = _solve_condensed_system(
        matrix, rhs, linear_solver="amg_cg", rtol=1e-10, maxiter=500
    )
    np.testing.assert_allclose(iterative, direct, rtol=1e-9, atol=1e-11)
    assert direct_meta["relative_residual"] <= 1e-9
    assert iterative_meta["relative_residual"] <= 1e-9
    assert iterative_meta["solver_info"] == 0


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
    assert result["schema"] == "pcb-gnn.corpus-v4-fem-native-diagnostic-task.v1"
    assert result["status"] == "validation-ok"
    assert set(result["arms"]) == {"0", "1"}


def test_worker_exposes_native_stage_and_faulthandler_contract() -> None:
    worker = (ROOT / "code" / "solvers" / "fem_cps_diagnostic_worker.py").read_text()
    assert "faulthandler.enable(all_threads=True)" in worker
    assert '"STAGE="' in worker
    assert "strict=True" in worker
    assert "except Exception:\n        pass" not in worker
