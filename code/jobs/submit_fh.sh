#!/bin/bash
#SBATCH -J job-fasthenry-val
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:40:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== T1: FastHenry 3-D inductance validation ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: fasthenry binary + 1 solve ==="
"$PCB_GNN_PYTHON" - <<'PY'
from fasthenry_ref import fasthenry_totals
lay={"traces":[{"x0":0,"y0":0,"z_mm":0.1,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":0,"net":"pri"},
                {"x0":0,"y0":0,"z_mm":0.3,"length_mm":40,"width_mm":3,"thick_mm":0.07,"layer":1,"net":"sec"}]}
r=fasthenry_totals(lay,1e5); assert r and r["L_mut_nH"]>0, r
print("fasthenry preflight ok:", round(r["L_mut_nH"],2),"nH")
PY
"$PCB_GNN_PYTHON" experiments/labels/experiments_fh.py
echo DONE; date
