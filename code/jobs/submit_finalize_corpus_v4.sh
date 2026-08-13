#!/bin/bash
#SBATCH --job-name=pcb-v4-final
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
: "${PCB_GNN_V3_CORPUS_DIR:?Set finalized source corpus-v3 directory}"
: "${PCB_GNN_V4_REFINEMENT_ARRAY_JOB_ID:?Set completed v4 refinement array job ID}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v4.py \
  --source-corpus "$PCB_GNN_V3_CORPUS_DIR" \
  --source-array-job-id "$PCB_GNN_V4_REFINEMENT_ARRAY_JOB_ID" --n-tasks 150
