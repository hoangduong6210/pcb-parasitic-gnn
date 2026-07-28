#!/bin/bash
#SBATCH -J job-leakage
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
echo "=== derived leakage + coupling k from the field-grade model ==="; hostname; date
cd ${REPO_ROOT}/code

# Install optional tree boosters (sklearn + xgboost already present on node)
:

source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
export OMP_NUM_THREADS=4

# FULL field-grade (FEM+FH solves) — heavy, allowed only here on nextgen
/usr/bin/python3 -u experiments/derived/experiments_leakage.py --out ../results/run_leakage

echo DONE; date
ls -l ../results/run_leakage/results_leakage.json || true