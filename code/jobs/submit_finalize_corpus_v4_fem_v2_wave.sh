#!/bin/bash
# Submit with: sbatch --dependency=afterany:<source-job-ids> this-script
# The afterany dependency is deliberate: failed/timed-out source components must
# still be classified and retained in the immutable cumulative wave receipt.
#SBATCH --job-name=pcb-v4-fem-v2-wave-final
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
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
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_FEM_V2_PRODUCTION_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_FEM_V2_PRODUCTION_PLAN_SHA256:?Pin the plan SHA-256}"
: "${PCB_GNN_V4_FEM_V2_PRODUCTION_LOCK_SHA256:?Pin the execution-lock SHA-256}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"
: "${PCB_GNN_V4_FEM_V2_FIDELITY_ID:?Pin the wave fidelity ID}"
: "${PCB_GNN_V4_FEM_V2_WAVE_ID:?Pin the nonnegative wave ID}"
: "${PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS:?Semicolon-separated JOBID|PATH|SHA256 bindings}"

IFS=';' read -r -a SOURCE_BINDINGS <<< "$PCB_GNN_V4_FEM_V2_SOURCE_BINDINGS"
(( ${#SOURCE_BINDINGS[@]} > 0 )) || { echo "empty source binding set" >&2; exit 2; }

ARGS=()
for binding in "${SOURCE_BINDINGS[@]}"; do
  [[ -n "$binding" ]] || { echo "empty source binding" >&2; exit 2; }
  ARGS+=(--source-binding "$binding")
done

if [[ -n "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION:-}" || -n "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256:-}" ]]; then
  : "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION:?Prior path and SHA-256 must be supplied together}"
  : "${PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256:?Prior path and SHA-256 must be supplied together}"
  ARGS+=(
    --prior-admission "$PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION"
    --expected-prior-admission-sha256 "$PCB_GNN_V4_FEM_V2_PRIOR_ADMISSION_SHA256"
  )
fi

"$PCB_GNN_PYTHON" -u code/experiments/proofs/corpus_v4_fem_v2_package.py finalize-wave \
  --protocol protocols/corpus_v4_fem_v2_production_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_PROTOCOL_SHA256" \
  --plan results/corpus_v4/cps_reference_v2/production/v1/plan/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_PLAN_SHA256" \
  --execution-lock protocols/corpus_v4_fem_v2_production_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_FEM_V2_PRODUCTION_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  --fidelity-id "$PCB_GNN_V4_FEM_V2_FIDELITY_ID" \
  --wave-id "$PCB_GNN_V4_FEM_V2_WAVE_ID" \
  "${ARGS[@]}"
