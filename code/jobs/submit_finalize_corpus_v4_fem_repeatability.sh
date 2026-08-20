#!/bin/bash
#SBATCH --job-name=pcb-v4-fem-rep-fin
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
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

export BLIS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C.UTF-8
export CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"

: "${PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID:?Pin the source array logical JobID}"
: "${PCB_GNN_V4_SOURCE_COMMIT:?Pin the exact clean Git commit}"

"$PCB_GNN_PYTHON" -u \
  code/experiments/proofs/finalize_corpus_v4_fem_repeatability.py \
  --protocol protocols/corpus_v4_fem_repeatability_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_FEM_REPEATABILITY_PROTOCOL_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_SOURCE_COMMIT" \
  --source-array-job-id "$PCB_GNN_V4_FEM_REPEATABILITY_SOURCE_ARRAY_JOB_ID" \
  --input-root results/corpus_v4/fem_repeatability/v1 \
  --output-root results/corpus_v4/fem_repeatability/v1/final
