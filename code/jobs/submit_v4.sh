#!/bin/bash
#SBATCH -J job-v4-induc-gen
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== this project v4: inductance FEM + generalization ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: FD-magnetostatic self-test ==="
"$PCB_GNN_PYTHON" - <<'PY'
from fem_inductance_ref import fem_pair_mutual_nh
m1=fem_pair_mutual_nh(3.0,3.0,0.07,0.2,40.0)
m2=fem_pair_mutual_nh(3.0,3.0,0.07,0.8,40.0)
assert m1>0 and m2>0, (m1,m2)
assert m1>m2, ("mutual should drop with separation", m1, m2)
print("induc self-test ok: M(0.2mm)=%.3f > M(0.8mm)=%.3f nH"%(m1,m2))
PY
"$PCB_GNN_PYTHON" experiments/rounds/experiments_v4.py
echo DONE; date
