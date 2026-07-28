#!/bin/bash
#SBATCH -J job-t2-equivariant
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=24G -t 05:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== T2: E(n)-equivariant + physics-informed GNN ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
/usr/bin/python3 - <<'PY'
import numpy as np, torch
from gnn_equivariant import PCBEquivariantGNN
from gnn_baseline import collate
g={"node_feat":np.random.randn(6,9).astype('float32'),"edge_feat":np.random.randn(8,7).astype('float32'),
   "edge_index":np.array([[0,1,2,3,4,5,0,1],[1,2,3,4,5,0,2,3]]),"edge_dim":7,"y":np.zeros(4,'float32')}
assert PCBEquivariantGNN()(collate([g,g])).shape==(2,4); print("preflight ok")
PY
/usr/bin/python3 -u experiments/architecture/experiments_t2.py
echo DONE; date
