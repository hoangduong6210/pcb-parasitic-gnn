#!/bin/bash
#SBATCH -J job-t1b-fhgrade
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=24G -t 02:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T1b: GNN field-grade vs FastHenry 3-D ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PY'
from fasthenry_ref import fasthenry_totals
from experiments_v5 import train  # import smoke
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
                {"x0":0,"y0":0,"z_mm":0.3,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"}]}
assert fasthenry_totals(lay,1e5)["L_mut_nH"]>0; print("preflight ok")
PY
/usr/bin/python3 experiments/labels/experiments_t1b.py
echo DONE; date
