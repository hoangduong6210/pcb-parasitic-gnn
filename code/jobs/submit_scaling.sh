#!/bin/bash
#SBATCH -J job-scaling
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH -N1 -n8 --mem=16G -t 00:30:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

# HARD RULE compliance: scaling/timing study runs on a compute node, not login.
set -euo pipefail
echo "=== this project scaling experiment ==="; echo "Host: $(hostname)"; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PYEOF'
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
/usr/bin/python3 experiments/scaling/scaling_experiment.py --out ../results/scaling_v1 \
    --ckpt ../results/run_v1/gnn_checkpoint.pt
echo "=== DONE ==="; date
