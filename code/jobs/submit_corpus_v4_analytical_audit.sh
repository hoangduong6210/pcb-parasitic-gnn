#!/bin/bash
#SBATCH --job-name=pcb-v4-analytic
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"; export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V4_CORPUS_DIR:?Set the finalized corpus-v4 directory}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v4_analytical_audit.py \
  --corpus "$PCB_GNN_V4_CORPUS_DIR"
