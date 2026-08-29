#!/bin/bash
#SBATCH --job-name=pcb-v4-acc-v2-final
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
: "${PCB_GNN_V4_ACCURACY_V2_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_ACCURACY_V2_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || {
  echo "Resolved job root differs from PCB_GNN_V4_ACCURACY_V2_EXECUTION_ROOT" >&2
  exit 2
}
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export NUMEXPR_NUM_THREADS=2
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_ACCURACY_V2_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V2_PLAN_SHA256:?Pin the plan SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V2_TASK_MANIFEST_SHA256:?Pin the task-manifest SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V2_EXECUTION_LOCK_SHA256:?Pin the execution-lock SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V2_ACCEPTED_SET:?Set the repository-relative accepted-set path}"
: "${PCB_GNN_V4_ACCURACY_V2_ACCEPTED_SET_SHA256:?Pin the accepted-set SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V2_SOURCE_COMMIT:?Pin the exact clean Git commit}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v4_accuracy_v2.py \
  --protocol protocols/corpus_v4_accuracy_v2.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_ACCURACY_V2_PROTOCOL_SHA256" \
  --plan results/corpus_v4/accuracy_v2/plan/v1/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_ACCURACY_V2_PLAN_SHA256" \
  --task-manifest results/corpus_v4/accuracy_v2/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$PCB_GNN_V4_ACCURACY_V2_TASK_MANIFEST_SHA256" \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v2.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_ACCURACY_V2_EXECUTION_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_ACCURACY_V2_SOURCE_COMMIT" \
  --accepted-set "$PCB_GNN_V4_ACCURACY_V2_ACCEPTED_SET" \
  --expected-accepted-set-sha256 "$PCB_GNN_V4_ACCURACY_V2_ACCEPTED_SET_SHA256" \
  --output-root results/corpus_v4/accuracy_v2/final
