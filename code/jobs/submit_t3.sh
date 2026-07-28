#!/bin/bash
#SBATCH -J job-t3-rfreq
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=24G -t 03:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T3: frequency-dependent R_ac/R_dc(f) ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PY'
import numpy as np
from fasthenry_ref import fasthenry_Rac_curve
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
                {"x0":0,"y0":0.5,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"}]}
r=fasthenry_Rac_curve(lay,np.logspace(4,8,21),nhinc=3,nwinc=3); assert r and r[1][-1]>2*r[1][0]; print("preflight ok")
PY
/usr/bin/python3 experiments/frequency/experiments_t3.py
echo DONE; date
