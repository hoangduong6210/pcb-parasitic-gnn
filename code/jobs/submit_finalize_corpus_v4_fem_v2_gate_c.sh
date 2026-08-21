#!/bin/bash
#SBATCH --job-name=pcb-v4-fem-v2-c-fin
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

: "${PCB_GNN_V4_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || exit 2
cd "$PCB_GNN_ROOT"

export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"
: "${PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION:?Pin the Gate-B admission path}"
: "${PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256:?Pin the Gate-B admission SHA-256}"
: "${PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID:?Pin the Gate-C source array JobID}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"

"$PCB_GNN_PYTHON" -u \
  code/experiments/proofs/finalize_corpus_v4_fem_v2_qualification.py \
  --stage gate_c \
  --protocol protocols/corpus_v4_fem_v2_qualification_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_FEM_V2_PROTOCOL_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  --source-array-job-id "$PCB_GNN_V4_FEM_V2_SOURCE_ARRAY_JOB_ID" \
  --prerequisite-admission "$PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION" \
  --expected-prerequisite-admission-sha256 \
    "$PCB_GNN_V4_FEM_V2_PREREQUISITE_ADMISSION_SHA256" \
  --input-root results/corpus_v4/cps_reference_v2/qualification/v1
