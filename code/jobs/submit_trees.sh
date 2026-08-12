#!/bin/bash
#SBATCH -J job-trees-q1
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
echo "=== Q1 trees baselines on field-grade pooled vector ==="; hostname; date
cd ${REPO_ROOT}/code

# Dependencies must be installed before submission from a pinned environment;
# a compute job must not mutate its environment or depend on network access.
"$PCB_GNN_PYTHON" -c 'import lightgbm, catboost' 2>/dev/null || \
  echo "[submit] optional LightGBM/CatBoost unavailable; scripted fallbacks apply"

source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
export OMP_NUM_THREADS=4

# FULL field-grade (FEM+FH solves) — heavy, allowed only here on nextgen
"$PCB_GNN_PYTHON" -u experiments/baselines/experiments_trees.py --use-field-labels --max-cand 400 --out ../results/run_trees

echo DONE; date
ls -l ../results/run_trees/results_trees.json || true
