#!/bin/bash
#SBATCH --job-name=pcb-v4-cps
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=12:00:00
#SBATCH --array=0-149%50
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"; export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V3_CORPUS_DIR:?Set finalized source corpus-v3 directory}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v4_refined_cps.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" --n-total 1500 --chunk-size 10 --timeout-s 3600
