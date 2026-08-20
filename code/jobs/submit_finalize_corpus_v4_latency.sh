#!/bin/bash
#SBATCH --job-name=pcb-v4-lat-final
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

: "${PCB_GNN_V4_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || exit 2
cd "$PCB_GNN_ROOT"

export BLIS_NUM_THREADS=2
export MKL_NUM_THREADS=2
export NUMEXPR_NUM_THREADS=2
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_LATENCY_PROTOCOL_SHA256:?Pin the latency protocol SHA-256}"
: "${PCB_GNN_V4_LATENCY_PLAN_SHA256:?Pin the latency plan SHA-256}"
: "${PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256:?Pin the latency task-manifest SHA-256}"
: "${PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256:?Pin the latency execution-lock SHA-256}"
: "${PCB_GNN_V4_LATENCY_ACCEPTED_SET:?Set the repository-relative accepted-set path}"
: "${PCB_GNN_V4_LATENCY_ACCEPTED_SET_SHA256:?Pin the accepted-set SHA-256}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"

"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v4_latency.py \
  --protocol protocols/corpus_v4_latency_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_LATENCY_PROTOCOL_SHA256" \
  --plan results/corpus_v4/latency/plan/v1/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_LATENCY_PLAN_SHA256" \
  --task-manifest results/corpus_v4/latency/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$PCB_GNN_V4_LATENCY_TASK_MANIFEST_SHA256" \
  --execution-lock protocols/corpus_v4_latency_execution_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_LATENCY_EXECUTION_LOCK_SHA256" \
  --accepted-set "$PCB_GNN_V4_LATENCY_ACCEPTED_SET" \
  --expected-accepted-set-sha256 "$PCB_GNN_V4_LATENCY_ACCEPTED_SET_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  --output-root results/corpus_v4/latency/final
