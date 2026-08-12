#!/bin/bash
#SBATCH -J job-pfc-real
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== T-REAL: 3-D FEM vs EER40 GP95 datasheet AL ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
if [[ ! -d "${PCB_GNN_MAGAI_ROOT:-}/engine" ]]; then
  echo "Set PCB_GNN_MAGAI_ROOT to the MagAI repository (directory containing engine/)." >&2
  exit 2
fi
export PYTHONPATH="${PCB_GNN_MAGAI_ROOT}:${PYTHONPATH}"
"$PCB_GNN_PYTHON" - <<'PY'
from engine.sim.skfem_magnetostatic_3d import solve_magnetostatic_3d  # import smoke
print("engine 3-D solver import OK")
PY
"$PCB_GNN_PYTHON" experiments/anchors/experiments_pfc.py
echo DONE; date
