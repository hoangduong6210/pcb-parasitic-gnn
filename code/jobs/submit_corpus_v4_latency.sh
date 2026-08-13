#!/bin/bash
#SBATCH --job-name=pcb-v4-latency
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=02:00:00
#SBATCH --array=0-99%50
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"; export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${PCB_GNN_V4_CORPUS_DIR:?Set the finalized corpus-v4 directory}"
: "${PCB_GNN_V4_BUNDLE_DIR:?Set the finalized corpus-v4 safe bundle directory}"
: "${FASTHENRY_BIN:?Set the verified FastHenry executable}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v4_latency_task.py \
  --corpus "$PCB_GNN_V4_CORPUS_DIR" --bundle "$PCB_GNN_V4_BUNDLE_DIR" \
  --n-designs 100 --inference-repetitions 30 --fem-timeout-s 3600
