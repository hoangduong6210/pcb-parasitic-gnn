#!/bin/bash
#SBATCH -J job-pcb-gnn-pipeline
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH -N1 -n4 --mem=8G -t 00:45:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

# HARD RULE compliance (2026-06-17 directive)
# Heavy research pipeline for this project must run on compute node, never login.

set -euo pipefail

echo "=== this project Research Pipeline (HARD RULE compliant) ==="
echo "Job ID: $SLURM_JOB_ID"
echo "Hostname: $(hostname)"
echo "Partition: $SLURM_JOB_PARTITION"
echo "Start: $(date)"

# Use system python (as required)
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH

cd ${REPO_ROOT}/code

# Use system python + local dir for imports (HARD RULE compliant)
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH

# 1. Generate modest dataset (low RAM, ~200 samples)
echo "=== Step 1: generate_synth ==="
/usr/bin/python3 data/generate_synth.py --n 250 --out ../datasets/synth_v0 --seed 42

# 2. Run the full experiment pipeline
echo "=== Step 2: run pipeline ==="
/usr/bin/python3 core/pipeline.py --data ../datasets/synth_v0 --out ../results/run_v0 --seed 42

echo "=== DONE ==="
echo "Results in ../results/run_v0/results.json"
echo "End: $(date)"
sacct -j $SLURM_JOB_ID --format=JobID,JobName,Partition,State,Elapsed,MaxRSS
