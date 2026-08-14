#!/bin/bash
#SBATCH --job-name=pcb-v4-fem-final
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
export PCB_GNN_EXECUTED_FINALIZER_BATCH_SCRIPT="$(readlink -f "$0")"
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
: "${PCB_GNN_DIAGNOSTIC_ARRAY_JOB_ID:?Set source diagnostic array job ID}"
"$PCB_GNN_PYTHON" -u \
  code/experiments/proofs/finalize_corpus_v4_fem_native_diagnostic.py \
  --array-job-id "$PCB_GNN_DIAGNOSTIC_ARRAY_JOB_ID"
