#!/bin/bash
#SBATCH -J job-leakage
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== derived leakage + coupling k from the field-grade model ==="; hostname; date
cd ${REPO_ROOT}/code

# Install optional tree boosters (sklearn + xgboost already present on node)
:

source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
export OMP_NUM_THREADS=4

# FULL field-grade (FEM+FH solves) — heavy, allowed only here on nextgen
"$PCB_GNN_PYTHON" -u experiments/derived/experiments_leakage.py --out ../results/run_leakage

echo DONE; date
ls -l ../results/run_leakage/results_leakage.json || true
