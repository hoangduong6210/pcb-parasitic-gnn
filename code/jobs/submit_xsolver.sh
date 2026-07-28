#!/bin/bash
#SBATCH -J job-xsolver
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH -N1 -n8 --mem=16G -t 00:59:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== Q3 xsolver: FastHenry field-grade train + Neumann cross-solver validation ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight smoke (<10s on allocated node) ==="
/usr/bin/python3 - <<'PY'
from fem_inductance_ref import neumann_totals
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
               {"x0":0,"y0":0,"z_mm":0.3,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"}]}
r=neumann_totals(lay); assert r and r["L_mut_nH"]>0, r
print("neumann preflight ok: Lm=%.2f Lp=%.2f Ls=%.2f nH" % (r["L_mut_nH"], r["L_pri_nH"], r["L_sec_nH"]))
PY
echo "=== running xsolver (all Neumann + FH solves on this compute node only) ==="
/usr/bin/python3 -u experiments/anchors/experiments_xsolver.py
echo DONE; date
