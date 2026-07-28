#!/bin/bash
#SBATCH -J job-trees-q1
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n8 --mem=32G -t 03:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== Q1 trees baselines on field-grade pooled vector ==="; hostname; date
cd ${REPO_ROOT}/code

# Install optional tree boosters (sklearn + xgboost already present on node)
python3 -m pip install --user --quiet lightgbm catboost 2>/dev/null || echo "[submit] lightgbm/catboost pip note (may already be present or net restricted)"

source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
export OMP_NUM_THREADS=4

# FULL field-grade (FEM+FH solves) — heavy, allowed only here on nextgen
/usr/bin/python3 -u experiments/baselines/experiments_trees.py --use-field-labels --max-cand 400 --out ../results/run_trees

echo DONE; date
ls -l ../results/run_trees/results_trees.json || true