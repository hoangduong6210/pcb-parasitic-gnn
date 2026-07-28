#!/bin/bash
#SBATCH -J job-pfc-real
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n8 --mem=16G -t 01:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T-REAL: 3-D FEM vs EER40 GP95 datasheet AL ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PY'
from engine.sim.skfem_magnetostatic_3d import solve_magnetostatic_3d  # import smoke
print("engine 3-D solver import OK")
PY
/usr/bin/python3 experiments/anchors/experiments_pfc.py
echo DONE; date
