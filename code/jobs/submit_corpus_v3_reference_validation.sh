#!/bin/bash
#SBATCH --job-name=pcb-v3-refval
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --array=0-8%9
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V3_CORPUS_DIR:?Set the finalized v3 corpus directory}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v3_reference_validation.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" --timeout-s 1200
