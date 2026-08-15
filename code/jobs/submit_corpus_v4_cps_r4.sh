#!/bin/bash
#SBATCH --job-name=pcb-v4-cps-r4
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=25
#SBATCH --mem=160G
#SBATCH --time=03:00:00
#SBATCH --array=0-197%2
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
export PCB_GNN_EXECUTED_BATCH_SCRIPT="$(readlink -f "$0")"
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export PCB_GNN_GMSH_THREADS=25
export PCB_GNN_MAX_MESH_NODES=10000000
export PCB_GNN_MAX_MESH_TETRAHEDRA=65000000
export PCB_GNN_MAX_RSS_KB=125829120
export PCB_GNN_MAX_OPERATOR_COMPLEXITY=1.25
: "${PCB_GNN_V3_CORPUS_DIR:?Set finalized source corpus-v3 directory}"
: "${PCB_GNN_CPS_EXECUTION_LOCK:?Set the frozen execution-lock path}"
: "${PCB_GNN_CPS_EXECUTION_LOCK_SHA256:?Set the frozen execution-lock SHA-256}"
PLAN_DIR="${PCB_GNN_CPS_MF_PLAN_DIR:-$PCB_GNN_ROOT/results/corpus_v4/cps_multifidelity/plan/v1}"
EXPECTED_PLAN_SHA256="419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a"
RETRY_ARGS=()
if [[ -n "${PCB_GNN_CPS_RETRY_TASK_SET:-}" ]]; then
  : "${PCB_GNN_CPS_RETRY_TASK_SET_SHA256:?Set the pinned retry task-set SHA-256}"
  RETRY_ARGS=(--retry-task-set "$PCB_GNN_CPS_RETRY_TASK_SET" --expected-retry-task-set-sha256 "$PCB_GNN_CPS_RETRY_TASK_SET_SHA256")
fi
"$PCB_GNN_PYTHON" -u code/experiments/proofs/run_corpus_v4_cps_multifidelity_task.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$EXPECTED_PLAN_SHA256" \
  --execution-lock "$PCB_GNN_CPS_EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$PCB_GNN_CPS_EXECUTION_LOCK_SHA256" \
  --manifest "$PLAN_DIR/r4_manifest.jsonl" \
  --output-root results/corpus_v4/cps_multifidelity/r4 \
  "${RETRY_ARGS[@]}" \
  --timeout-s 7200
