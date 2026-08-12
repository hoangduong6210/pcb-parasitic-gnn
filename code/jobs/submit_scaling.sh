#!/bin/bash
#SBATCH -J job-scaling
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

# HARD RULE compliance: scaling/timing study runs on a compute node, not login.
set -euo pipefail
echo "=== this project scaling experiment ==="; echo "Host: $(hostname)"; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
"$PCB_GNN_PYTHON" - <<'PYEOF'
# fast pre-flight: knn_sparsify + one forward, fail before the sweep
import numpy as np, torch
from scaling_experiment import knn_sparsify
from gnn_baseline import PCBParasiticGNN, collate
nf=np.random.randn(12,9).astype('float32')
ei,ef=knn_sparsify(nf,k=4)
b=collate([{"node_feat":nf,"edge_feat":ef,"edge_index":ei,"edge_dim":7,"y":np.zeros(4,'float32')}])
with torch.no_grad(): out=PCBParasiticGNN()(b)
assert out.shape==(1,4); print("scaling smoke OK", tuple(out.shape), "knn_edges", ei.shape[1])
PYEOF
"$PCB_GNN_PYTHON" experiments/scaling/scaling_experiment.py --out ../results/scaling_v1 \
    --ckpt ../results/run_v1/gnn_checkpoint.pt
echo "=== DONE ==="; date
