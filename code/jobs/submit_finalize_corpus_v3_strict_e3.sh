#!/bin/bash
#SBATCH --job-name=pcb-v3-e3-final
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
: "${PCB_GNN_V3_STRICT_E3_ARRAY_JOB_ID:?Set the completed strict-E3 array job ID}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v3_strict_e3.py \
  --source-array-job-id "$PCB_GNN_V3_STRICT_E3_ARRAY_JOB_ID" \
  --bootstrap-resamples 10000 --equivalence-margin-pct 2.0
