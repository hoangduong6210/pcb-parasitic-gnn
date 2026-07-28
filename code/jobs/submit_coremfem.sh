#!/bin/bash
#SBATCH -J job-coremfem
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n8 --mem=32G -t 02:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== Q2: core-inclusive magnetostatic FEM (planar-LLC + EER40 AL anchor) ==="
hostname; date
cd ${REPO_ROOT}
# Task spec: PYTHONPATH=code:../.. (adjusted to reach engine at ADE/magai level)
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "PYTHONPATH=$PYTHONPATH"
echo "=== pre-flight smoke (<10s, login OK): import only, no heavy solve ==="
/usr/bin/python3 - <<'PY'
from engine.sim.skfem_magnetostatic_3d import solve_magnetostatic_3d  # import smoke
print("engine 3-D solver import OK (EER40 path)")
from fasthenry_ref import fasthenry_totals
print("fasthenry_ref OK")
PY
echo "=== run experiment (ALL FEM solves inside this sbatch job) ==="
/usr/bin/python3 code/experiments_coremfem.py
echo "DONE"; date
