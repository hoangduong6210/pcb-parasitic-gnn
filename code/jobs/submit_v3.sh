#!/bin/bash
#SBATCH -J job-v3-sweep
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=24G -t 03:30:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== this project v3 sweeps ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PY'
from experiments_v2 import train_eval, prepare  # import smoke
print("import ok")
PY
/usr/bin/python3 experiments/rounds/experiments_v3.py
echo DONE; date
