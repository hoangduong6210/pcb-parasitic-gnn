#!/bin/bash
#SBATCH --job-name=pcb-v4-base-final
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

: "${PCB_GNN_BASELINE_ROOT:?Pin the archive checkout}"
: "${PCB_GNN_BASELINE_PROTOCOL_SHA256:?Pin the baseline protocol}"
: "${PCB_GNN_BASELINE_LOCK_SHA256:?Pin the baseline execution lock}"
: "${PCB_GNN_BASELINE_SOURCE_COMMIT:?Pin the training and analysis source commit}"
STAGE="${1:?Choose admit, finalize or verify}"
shift
case "$STAGE" in admit|finalize|verify) ;; *) exit 2 ;; esac
EXECUTION_ROOT="$(cd "$PCB_GNN_BASELINE_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]]
cd "$EXECUTION_ROOT"
export BLIS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONHASHSEED=0
export TZ=UTC LC_ALL=C.UTF-8 CUDA_VISIBLE_DEVICES=""
export PCB_GNN_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"
export PCB_GNN_EXECUTED_BATCH_SHA256="$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)"
[[ "$PCB_GNN_EXECUTED_BATCH_SHA256" == "$(sha256sum code/jobs/submit_finalize_corpus_v4_baseline_v1.sh | cut -d' ' -f1)" ]]

"$PCB_GNN_PYTHON" -u code/experiments/proofs/corpus_v4_baseline_v1.py "$STAGE" \
  --protocol protocols/corpus_v4_baseline_fem_v2_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_BASELINE_PROTOCOL_SHA256" \
  --execution-lock protocols/corpus_v4_baseline_fem_v2_execution_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_BASELINE_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_BASELINE_SOURCE_COMMIT" \
  "$@"
