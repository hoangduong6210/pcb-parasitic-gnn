#!/bin/bash
#SBATCH -J job-v2-rigor
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=24G
#SBATCH --time=04:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

# HARD RULE: rigor pass (FEM ground truth + multi-seed + baselines) on a
# compute node, never on login.
set -euo pipefail
echo "=== this project v2 rigor pass ==="; echo "Host: $(hostname)"; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
export OMP_NUM_THREADS=4
PY="$PCB_GNN_PYTHON"

echo "=== Pre-flight: FEM self-test + tiny GNN/MLP forward (fail fast) ==="
$PY - <<'PYEOF'
import numpy as np, torch
from fem_capacitance_ref import fem_pair_capacitance_pf
c = fem_pair_capacitance_pf(3.0,3.0,0.07,0.2,40.0,4.2)
assert c>0, c
print("FEM self-test C=%.3f pF (ok)"%c)
from experiments_v2 import PooledMLP, prepare
from gnn_baseline import PCBParasiticGNN, collate
g={"node_feat":np.random.randn(6,9).astype('float32'),
   "edge_feat":np.random.randn(8,7).astype('float32'),
   "edge_index":np.array([[0,1,2,3,4,5,0,1],[1,2,3,4,5,0,2,3]]),
   "edge_dim":7,"y":np.zeros(4,'float32')}
b=collate([g,g])
assert PooledMLP()(b).shape==(2,4)
assert PCBParasiticGNN()(b).shape==(2,4)
print("model smoke ok")
PYEOF

echo "=== Run v2 experiments ==="
$PY experiments/rounds/experiments_v2.py --data ../datasets/synth_v1 --out ../results/run_v2 --epochs 200

echo "=== DONE ==="; date
sacct -j ${SLURM_JOB_ID} --format=JobID,JobName,State,Elapsed,MaxRSS 2>/dev/null | head -3 || true
