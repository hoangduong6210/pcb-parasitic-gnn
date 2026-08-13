#!/bin/bash
# Four-layout field-solver preflight. The 1,500-layout array must not be
# submitted until both tasks finish with every record valid.
#SBATCH --job-name=pcb-v3-preflight
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:45:00
#SBATCH --array=0-1
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"
: "${FASTHENRY_BIN:?Set FASTHENRY_BIN to a verified FastHenry executable before submission}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v3_field_labels.py \
  --n-total 4 --chunk-size 2 --seed-start 42000 \
  --fem-refine 1 --fem-timeout-s 180
