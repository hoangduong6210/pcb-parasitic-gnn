#!/bin/bash
#SBATCH --job-name=pcb-multisplit
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"
export PYTHONHASHSEED=0

"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_multisplit_accuracy.py \
  --split-seeds 40 41 42 43 44 --init-seeds 40 41 42 43 44 \
  --epochs 200 --bootstrap-resamples 10000 \
  --bundle-split-seed 42 --bundle-init-seed 42
