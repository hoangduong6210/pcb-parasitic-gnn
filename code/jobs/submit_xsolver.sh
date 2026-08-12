#!/bin/bash
#SBATCH -J job-xsolver
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=00:59:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== Q3 xsolver: FastHenry field-grade train + Neumann cross-solver validation ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight smoke (<10s on allocated node) ==="
"$PCB_GNN_PYTHON" - <<'PY'
from fem_inductance_ref import neumann_totals
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
               {"x0":0,"y0":0,"z_mm":0.3,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"}]}
r=neumann_totals(lay); assert r and r["L_mut_nH"]>0, r
print("neumann preflight ok: Lm=%.2f Lp=%.2f Ls=%.2f nH" % (r["L_mut_nH"], r["L_pri_nH"], r["L_sec_nH"]))
PY
echo "=== running xsolver (all Neumann + FH solves on this compute node only) ==="
"$PCB_GNN_PYTHON" -u experiments/anchors/experiments_xsolver.py
echo DONE; date
