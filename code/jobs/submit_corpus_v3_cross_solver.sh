#!/bin/bash
#SBATCH --job-name=pcb-v3-xsolver
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
: "${PCB_GNN_V3_CORPUS_DIR:?Set the finalized v3 corpus directory}"
: "${PCB_GNN_V3_BUNDLE_DIR:?Set the finalized safe-bundle directory}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_corpus_v3_cross_solver.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" --bundle "$PCB_GNN_V3_BUNDLE_DIR" --n-designs 70
