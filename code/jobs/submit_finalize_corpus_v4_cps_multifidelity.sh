#!/bin/bash
#SBATCH --job-name=pcb-v4-cps-final
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
export PCB_GNN_EXECUTED_BATCH_SCRIPT="$(readlink -f "$0")"
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
: "${PCB_GNN_V3_CORPUS_DIR:?Set finalized source corpus-v3 directory}"
: "${PCB_GNN_CPS_EXECUTION_LOCK:?Set the frozen execution-lock path}"
: "${PCB_GNN_CPS_EXECUTION_LOCK_SHA256:?Set the frozen execution-lock SHA-256}"
: "${PCB_GNN_CPS_R3_ARTIFACT_SET:?Set accepted R3 artifact-set path}"
: "${PCB_GNN_CPS_R3_ARTIFACT_SET_SHA256:?Set accepted R3 artifact-set SHA-256}"
: "${PCB_GNN_CPS_R4_ARTIFACT_SET:?Set accepted R4 artifact-set path}"
: "${PCB_GNN_CPS_R4_ARTIFACT_SET_SHA256:?Set accepted R4 artifact-set SHA-256}"
PLAN_DIR="${PCB_GNN_CPS_MF_PLAN_DIR:-$PCB_GNN_ROOT/results/corpus_v4/cps_multifidelity/plan/v1}"
EXPECTED_PLAN_SHA256="419061ea537dc8a6fa6dee649025249ea652eeefdbfc4304f15400b0eeea517a"
"$PCB_GNN_PYTHON" -u code/experiments/proofs/finalize_corpus_v4_cps_multifidelity.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" \
  --protocol protocols/corpus_v4_cps_multifidelity_v1.json \
  --plan "$PLAN_DIR/plan.json" \
  --expected-plan-sha256 "$EXPECTED_PLAN_SHA256" \
  --execution-lock "$PCB_GNN_CPS_EXECUTION_LOCK" \
  --expected-execution-lock-sha256 "$PCB_GNN_CPS_EXECUTION_LOCK_SHA256" \
  --r3-manifest "$PLAN_DIR/r3_manifest.jsonl" \
  --r4-manifest "$PLAN_DIR/r4_manifest.jsonl" \
  --r3-artifact-set "$PCB_GNN_CPS_R3_ARTIFACT_SET" \
  --r3-artifact-set-sha256 "$PCB_GNN_CPS_R3_ARTIFACT_SET_SHA256" \
  --r4-artifact-set "$PCB_GNN_CPS_R4_ARTIFACT_SET" \
  --r4-artifact-set-sha256 "$PCB_GNN_CPS_R4_ARTIFACT_SET_SHA256" \
  --out results/corpus_v4/cps_multifidelity/final/job_"$SLURM_JOB_ID"
