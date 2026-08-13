#!/bin/bash
#SBATCH --job-name=pcb-v4-trees
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --array=0-9%10
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"; export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V4_CORPUS_DIR:?Set the finalized corpus-v4 directory}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v3_trees.py \
  --corpus "$PCB_GNN_V4_CORPUS_DIR" --series corpus_v4
