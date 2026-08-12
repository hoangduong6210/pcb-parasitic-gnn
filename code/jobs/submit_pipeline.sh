#!/bin/bash
#SBATCH -J job-pcb-gnn-pipeline
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p debug-nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:45:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

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
"$PCB_GNN_PYTHON" data/generate_synth.py --n 250 --out ../datasets/synth_v0 --seed 42

# 2. Run the full experiment pipeline
echo "=== Step 2: run pipeline ==="
"$PCB_GNN_PYTHON" core/pipeline.py --data ../datasets/synth_v0 --out ../results/run_v0 --seed 42

echo "=== DONE ==="
echo "Results in ../results/run_v0/results.json"
echo "End: $(date)"
sacct -j $SLURM_JOB_ID --format=JobID,JobName,Partition,State,Elapsed,MaxRSS
