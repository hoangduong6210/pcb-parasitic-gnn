"""Fast reproducibility/path contracts; never invoke field solvers or training."""
from __future__ import annotations

import importlib
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
for directory in (
    CODE / "core", CODE / "models" / "gnn", CODE / "solvers", CODE / "data",
    CODE / "experiments" / "labels", CODE / "experiments" / "ranking",
    CODE / "experiments" / "proofs",
):
    sys.path.insert(0, str(directory))

from experiments_v5 import Norm  # noqa: E402
from pipeline import fit_target_stats  # noqa: E402
from runtime_paths import fem_cps_worker_path  # noqa: E402


def sample(target: float) -> dict:
    return {
        "y": np.full(4, target, dtype=np.float32),
        "node_feat": np.full((2, 9), target, dtype=np.float32),
        "edge_feat": np.full((2, 7), target, dtype=np.float32),
    }


def test_target_stats_are_train_only() -> None:
    original = [sample(1), sample(3), sample(1e12)]
    changed = [sample(1), sample(3), sample(-1e20)]
    norm_a, norm_b = Norm(original, [0, 1]), Norm(changed, [0, 1])
    np.testing.assert_array_equal(norm_a.ym, norm_b.ym)
    np.testing.assert_array_equal(norm_a.ys, norm_b.ys)
    mean_a, std_a = fit_target_stats(original, [0, 1])
    mean_b, std_b = fit_target_stats(changed, [0, 1])
    np.testing.assert_array_equal(mean_a, mean_b)
    np.testing.assert_array_equal(std_a, std_b)


@pytest.mark.parametrize("factory", [Norm, lambda samples, indices: fit_target_stats(samples, indices)])
def test_target_stats_reject_empty_train_split(factory) -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        factory([sample(1)], [])


@pytest.mark.parametrize(
    "module_name",
    [
        "experiments_claim_proof", "experiments_strict_egnn_ablation",
        "experiments_femcps", "experiments_decision", "experiments_declat",
        "experiments_rank", "experiments_ranklat", "experiments_ranklat2",
    ],
)
def test_fem_callers_use_current_interpreter_and_resolved_worker(
    module_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(module_name)
    worker = tmp_path / "fem_cps_worker.py"
    worker.write_text("# sentinel\n")
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, kwargs=kwargs)
        return SimpleNamespace(stdout="CPS=12.5\n", stderr="", returncode=0)

    monkeypatch.setattr(module, "fem_cps_worker_path", lambda: worker)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.safe_fem_cps({"id": "unit"}, 0, 1) == 12.5
    assert seen["command"][:2] == [sys.executable, str(worker)]


def test_worker_and_slurm_root_contracts(tmp_path: Path) -> None:
    assert fem_cps_worker_path() == (CODE / "solvers" / "fem_cps_worker.py").resolve()
    helper = CODE / "jobs" / "slurm_job_env.sh"
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; printf "%s|%s" "$PCB_GNN_ROOT" "$PCB_GNN_CODE"',
         "bash", str(helper)],
        cwd=tmp_path,
        env={**os.environ, "PCB_GNN_PYTHON": sys.executable},
        capture_output=True, text=True, check=True,
    )
    assert result.stdout == f"{ROOT.resolve()}|{CODE.resolve()}"


def test_all_slurm_jobs_are_single_task_portable_and_executable() -> None:
    jobs = sorted((CODE / "jobs").glob("submit_*.sh"))
    assert len(jobs) >= 32
    for job in jobs:
        text = job.read_text()
        assert "slurm_job_env.sh" in text, job.name
        assert "#SBATCH --ntasks=1" in text, job.name
        assert "#SBATCH --cpus-per-task=" in text, job.name
        assert "$(dirname \"${BASH_SOURCE[0]}\")/.." not in text, job.name
        assert "/users/" not in text, job.name
        assert job.stat().st_mode & stat.S_IXUSR, job.name
        subprocess.run(["bash", "-n", str(job)], check=True)


def test_coremfem_dependency_and_path_are_explicit() -> None:
    for name in ("submit_coremfem.sh", "submit_pfc.sh"):
        text = (CODE / "jobs" / name).read_text()
        assert "PCB_GNN_MAGAI_ROOT" in text
        assert "code/experiments/anchors/experiments_coremfem.py" in text or name == "submit_pfc.sh"
        assert "../../magai" not in text
