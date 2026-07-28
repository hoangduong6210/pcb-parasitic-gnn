#!/bin/bash
#SBATCH -J job-pcb-gnn-v1
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH -N1 -n8 --mem=16G -t 00:55:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

# HARD RULE compliance (2026-06-17 directive): the real GNN training pipeline
# for this project runs on a compute node, NEVER on the login node.

set -euo pipefail

echo "=== this project Research Pipeline v1 — REAL GNN (HARD RULE compliant) ==="
echo "Job ID:    ${SLURM_JOB_ID:-NA}"
echo "Hostname:  $(hostname)"
echo "Partition: ${SLURM_JOB_PARTITION:-NA}"
echo "Start:     $(date)"

cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
PY=/usr/bin/python3

echo "=== Pre-flight: torch + tiny forward/backward smoke (fail fast before heavy work) ==="
$PY - <<'PYEOF'
import torch, numpy as np
from gnn_baseline import PCBParasiticGNN, collate, count_params
g = {"node_feat": np.random.randn(5,9).astype("float32"),
     "edge_feat": np.random.randn(6,7).astype("float32"),
     "edge_index": np.array([[0,1,2,3,4,0],[1,2,3,4,0,2]]),
     "edge_dim":7, "y": np.zeros(4,dtype="float32")}
b = collate([g,g])
m = PCBParasiticGNN()
out = m(b); loss = out.pow(2).mean(); loss.backward()
assert out.shape == (2,4), out.shape
print("smoke OK: params=", count_params(m), "out", tuple(out.shape), "grad_ok")
PYEOF

echo "=== Step 1: generate dataset (2000 samples, wider graphs, all-pairs reference) ==="
$PY data/generate_synth.py --n 2000 --big --out ../datasets/synth_v1 --seed 42

echo "=== Step 2: train + evaluate the GNN ==="
$PY core/pipeline.py \
    --data ../datasets/synth_v1 \
    --out  ../results/run_v1 \
    --seed 42 --epochs 300 --batch_size 32 --hidden 96 --layers 4

echo "=== DONE ==="
echo "Results: ../results/run_v1/results.json"
echo "End: $(date)"
sacct -j ${SLURM_JOB_ID} --format=JobID,JobName,Partition,State,Elapsed,MaxRSS 2>/dev/null || true
