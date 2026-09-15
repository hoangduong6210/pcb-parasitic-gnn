#!/bin/bash
#SBATCH --job-name=pcb-v4-e3-final-v1
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

: "${PCB_GNN_E3_ROOT:?Pin the archive checkout}"
: "${PCB_GNN_E3_PROTOCOL_SHA256:?Pin the strict-E3 protocol}"
: "${PCB_GNN_E3_LOCK_SHA256:?Pin the strict-E3 execution lock}"
: "${PCB_GNN_E3_SOURCE_COMMIT:?Pin the training and analysis source commit}"
STAGE="${1:?Choose admit, finalize or verify}"
shift
case "$STAGE" in admit|finalize|verify) ;; *) exit 2 ;; esac
EXECUTION_ROOT="$(cd "$PCB_GNN_E3_ROOT" && pwd -P)"
cd "$EXECUTION_ROOT"
[[ "$(git rev-parse HEAD)" == "$PCB_GNN_E3_SOURCE_COMMIT" || "$STAGE" == verify ]]
[[ -z "$(git status --short --untracked-files=no)" ]]
[[ -z "$(git status --short --untracked-files=all -- code protocols requirements-proof.txt)" ]]
SITE_PACKAGES="$(/usr/bin/python3 -c 'import site; print(site.getusersitepackages())')"
[[ -d "$SITE_PACKAGES" ]]
EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"
EXECUTED_BATCH_SHA256="$(sha256sum "$EXECUTED_BATCH_SCRIPT" | cut -d' ' -f1)"
[[ "$EXECUTED_BATCH_SHA256" == "$(sha256sum code/jobs/submit_finalize_corpus_v4_strict_e3_fem_v2_v1.sh | cut -d' ' -f1)" ]]

/usr/bin/env -i \
  PATH=/usr/bin:/bin PYTHONPATH="$SITE_PACKAGES" PYTHONNOUSERSITE=1 \
  TMPDIR=/tmp OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  NUMEXPR_NUM_THREADS=2 BLIS_NUM_THREADS=2 PYTHONHASHSEED=0 \
  TZ=UTC LC_ALL=C.UTF-8 CUDA_VISIBLE_DEVICES= \
  SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" SLURM_JOB_ID="$SLURM_JOB_ID" \
  SLURM_JOB_PARTITION="$SLURM_JOB_PARTITION" SLURM_MEM_PER_NODE="$SLURM_MEM_PER_NODE" \
  PCB_GNN_EXECUTED_BATCH_SCRIPT="$EXECUTED_BATCH_SCRIPT" \
  PCB_GNN_EXECUTED_BATCH_SHA256="$EXECUTED_BATCH_SHA256" \
  /usr/bin/python3 -u code/experiments/proofs/corpus_v4_strict_e3_fem_v2_v1.py "$STAGE" \
  --protocol protocols/corpus_v4_strict_e3_fem_v2_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_E3_PROTOCOL_SHA256" \
  --execution-lock protocols/corpus_v4_strict_e3_fem_v2_execution_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_E3_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_E3_SOURCE_COMMIT" \
  "$@"
