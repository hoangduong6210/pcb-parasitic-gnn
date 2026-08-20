#!/bin/bash
#SBATCH --job-name=pcb-v4-accuracy
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --array=0-24%5
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
# Explicit public-series identity retained for release contract: --series corpus_v4
: "${PCB_GNN_V4_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || {
  echo "Resolved job root differs from PCB_GNN_V4_EXECUTION_ROOT" >&2
  exit 2
}
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8
export OPENBLAS_NUM_THREADS=8
export NUMEXPR_NUM_THREADS=8
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_ACCURACY_PLAN_SHA256:?Pin the plan SHA-256}"
: "${PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256:?Pin the task-manifest SHA-256}"
: "${PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256:?Pin the execution-lock SHA-256}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"

RETRY_ARGS=()
if [[ -n "${PCB_GNN_V4_ACCURACY_PENDING_SET:-}" || -n "${PCB_GNN_V4_ACCURACY_PENDING_SET_SHA256:-}" ]]; then
  : "${PCB_GNN_V4_ACCURACY_PENDING_SET:?Set the repository-relative pending-set path}"
  : "${PCB_GNN_V4_ACCURACY_PENDING_SET_SHA256:?Pin the pending-set SHA-256}"
  RETRY_ARGS=(
    --pending-set "$PCB_GNN_V4_ACCURACY_PENDING_SET"
    --expected-pending-set-sha256 "$PCB_GNN_V4_ACCURACY_PENDING_SET_SHA256"
  )
fi

"$PCB_GNN_PYTHON" -u code/experiments/proofs/run_corpus_v4_accuracy_task.py \
  --protocol protocols/corpus_v4_accuracy_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_ACCURACY_PROTOCOL_SHA256" \
  --plan results/corpus_v4/accuracy/plan/v1/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_ACCURACY_PLAN_SHA256" \
  --task-manifest results/corpus_v4/accuracy/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$PCB_GNN_V4_ACCURACY_TASK_MANIFEST_SHA256" \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_ACCURACY_EXECUTION_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  "${RETRY_ARGS[@]}" \
  --output-root results/corpus_v4/accuracy/jobs
