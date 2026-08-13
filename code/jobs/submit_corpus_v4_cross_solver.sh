#!/bin/bash
#SBATCH --job-name=pcb-v4-xsolver
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=01:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"; export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V4_CORPUS_DIR:?Set the finalized corpus-v4 directory}"
: "${PCB_GNN_V4_BUNDLE_DIR:?Set the finalized corpus-v4 safe bundle directory}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v3_cross_solver.py \
  --corpus "$PCB_GNN_V4_CORPUS_DIR" --bundle "$PCB_GNN_V4_BUNDLE_DIR" \
  --series corpus_v4 --n-designs 70
