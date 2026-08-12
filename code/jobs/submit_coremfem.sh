#!/bin/bash
#SBATCH -J job-coremfem
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== Q2: core-inclusive magnetostatic FEM (planar-LLC + EER40 AL anchor) ==="
hostname; date
cd ${REPO_ROOT}
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
if [[ ! -d "${PCB_GNN_MAGAI_ROOT:-}/engine" ]]; then
  echo "Set PCB_GNN_MAGAI_ROOT to the MagAI repository (directory containing engine/)." >&2
  exit 2
fi
export PYTHONPATH="${PCB_GNN_MAGAI_ROOT}:${PYTHONPATH}"
echo "PYTHONPATH=$PYTHONPATH"
echo "=== pre-flight smoke (<10s, login OK): import only, no heavy solve ==="
"$PCB_GNN_PYTHON" - <<'PY'
from engine.sim.skfem_magnetostatic_3d import solve_magnetostatic_3d  # import smoke
print("engine 3-D solver import OK (EER40 path)")
from fasthenry_ref import fasthenry_totals
print("fasthenry_ref OK")
PY
echo "=== run experiment (ALL FEM solves inside this sbatch job) ==="
"$PCB_GNN_PYTHON" code/experiments/anchors/experiments_coremfem.py
echo "DONE"; date
