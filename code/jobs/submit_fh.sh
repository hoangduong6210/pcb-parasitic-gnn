#!/bin/bash
#SBATCH -J job-fasthenry-val
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH -N1 -n4 --mem=8G -t 00:40:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T1: FastHenry 3-D inductance validation ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: fasthenry binary + 1 solve ==="
/usr/bin/python3 - <<'PY'
from fasthenry_ref import fasthenry_totals
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
                {"x0":0,"y0":0,"z_mm":0.3,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"}]}
r=fasthenry_totals(lay,1e5); assert r and r["L_mut_nH"]>0, r
print("fasthenry preflight ok:", round(r["L_mut_nH"],2),"nH")
PY
/usr/bin/python3 experiments/labels/experiments_fh.py
echo DONE; date
