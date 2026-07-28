#!/bin/bash
#SBATCH -J job-v4-induc-gen
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
echo "=== this project v4: inductance FEM + generalization ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: FD-magnetostatic self-test ==="
/usr/bin/python3 - <<'PY'
from fem_inductance_ref import fem_pair_mutual_nh
m1=fem_pair_mutual_nh(3.0,3.0,0.07,0.2,40.0)
m2=fem_pair_mutual_nh(3.0,3.0,0.07,0.8,40.0)
assert m1>0 and m2>0, (m1,m2)
assert m1>m2, ("mutual should drop with separation", m1, m2)
print("induc self-test ok: M(0.2mm)=%.3f > M(0.8mm)=%.3f nH"%(m1,m2))
PY
/usr/bin/python3 experiments/rounds/experiments_v4.py
echo DONE; date
