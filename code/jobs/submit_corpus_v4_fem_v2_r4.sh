#!/bin/bash
#SBATCH --job-name=pcb-v4-fem-v2-r4
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=160G
#SBATCH --time=03:00:00
#SBATCH --array=0-0%2
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
#SBATCH --no-requeue
set -euo pipefail

: "${PCB_GNN_V4_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || exit 2
cd "$PCB_GNN_ROOT"

export BLIS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export PCB_GNN_GMSH_THREADS=1
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_FEM_V2_PRODUCTION_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_FEM_V2_PRODUCTION_PLAN_SHA256:?Pin the plan SHA-256}"
: "${PCB_GNN_V4_FEM_V2_PRODUCTION_LOCK_SHA256:?Pin the execution-lock SHA-256}"
: "${PCB_GNN_V4_FEM_V2_DISPATCH:?Pin the R4 dispatch path}"
: "${PCB_GNN_V4_FEM_V2_DISPATCH_SHA256:?Pin the R4 dispatch SHA-256}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"

RETRY_ARGS=()
if [[ -n "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION:-}" || -n "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256:-}" ]]; then
  : "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION:?Retry admission path and SHA-256 are both required}"
  : "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256:?Retry admission path and SHA-256 are both required}"
  RETRY_ARGS+=(
    --prior-admission "$PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION"
    --expected-prior-admission-sha256 "$PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256"
  )
fi

"$PCB_GNN_PYTHON" -u code/experiments/proofs/corpus_v4_fem_v2_production.py run \
  --protocol protocols/corpus_v4_fem_v2_production_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_PROTOCOL_SHA256" \
  --plan results/corpus_v4/cps_reference_v2/production/v1/plan/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_PLAN_SHA256" \
  --execution-lock protocols/corpus_v4_fem_v2_production_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_LOCK_SHA256" \
  --manifest results/corpus_v4/cps_reference_v2/production/v1/plan/r4_manifest.jsonl \
  --dispatch "$PCB_GNN_V4_FEM_V2_DISPATCH" \
  --expected-dispatch-sha256 "$PCB_GNN_V4_FEM_V2_DISPATCH_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  "${RETRY_ARGS[@]}" \
  --output-root results/corpus_v4/cps_reference_v2/production/v1/attempts/r4
