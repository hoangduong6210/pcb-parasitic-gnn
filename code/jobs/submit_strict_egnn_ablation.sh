#!/bin/bash
#SBATCH --job-name=pcb-strict-e3
#SBATCH --partition=cpu-exp
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/experiments_strict_egnn_ablation.py \
  --max-candidates 346 --seeds 42 43 44 45 46 \
  --caps 25 50 100 200 0 --epochs 200 --batch-size 32 \
  --strict-hidden 96 --fem-refine 1 --fem-timeout-s 90 \
  --bootstrap-resamples 10000 --timing-repeats 100 --split-seed 42 \
  --equivalence-margin-pct 2.0
