#!/bin/bash
#SBATCH -J job-t4b-fix
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=24G -t 04:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T4b: fixed interleaving screening ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 -u experiments/ranking/experiments_t4b.py
echo DONE; date
