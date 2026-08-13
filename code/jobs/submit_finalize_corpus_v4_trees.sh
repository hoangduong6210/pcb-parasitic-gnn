#!/bin/bash
#SBATCH --job-name=pcb-v4-tree-final
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
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
: "${PCB_GNN_V4_TREES_ARRAY_JOB_ID:?Set the completed corpus-v4 tree array ID}"
: "${PCB_GNN_V4_ACCURACY_FINAL:?Set the finalized corpus-v4 accuracy JSON path}"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v3_trees.py \
  --source-array-job-id "$PCB_GNN_V4_TREES_ARRAY_JOB_ID" \
  --gnn-final "$PCB_GNN_V4_ACCURACY_FINAL" --series corpus_v4
