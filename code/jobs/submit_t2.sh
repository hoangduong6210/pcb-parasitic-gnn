#!/bin/bash
#SBATCH -J job-t2-equivariant
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=05:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== T2: E(n)-equivariant + physics-informed GNN ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
"$PCB_GNN_PYTHON" - <<'PY'
import numpy as np, torch
from gnn_equivariant import PCBEquivariantGNN
from gnn_baseline import collate
g={"node_feat":np.random.randn(6,9).astype('float32'),"edge_feat":np.random.randn(8,7).astype('float32'),
   "edge_index":np.array([[0,1,2,3,4,5,0,1],[1,2,3,4,5,0,2,3]]),"edge_dim":7,"y":np.zeros(4,'float32')}
assert PCBEquivariantGNN()(collate([g,g])).shape==(2,4); print("preflight ok")
PY
"$PCB_GNN_PYTHON" -u experiments/architecture/experiments_t2.py
echo DONE; date
