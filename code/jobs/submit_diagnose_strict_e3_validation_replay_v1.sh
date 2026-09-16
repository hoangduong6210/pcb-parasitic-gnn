#!/bin/bash
#SBATCH --job-name=pcb-e3-replay-diag
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
: "${PCB_GNN_DIAG_ROOT:?Pin the diagnostic checkout}"
: "${PCB_GNN_DIAG_COMMIT:?Pin the diagnostic source commit}"
: "${PCB_GNN_E3_ROOT:?Pin frozen execution checkout}"
: "${PCB_GNN_E3_PROTOCOL_SHA256:?Pin frozen protocol}"
: "${PCB_GNN_E3_LOCK_SHA256:?Pin frozen execution lock}"
: "${PCB_GNN_E3_TASK_RECEIPT_SHA256:?Pin task zero receipt}"
cd "$PCB_GNN_DIAG_ROOT"
[[ "$(git rev-parse HEAD)" == "$PCB_GNN_DIAG_COMMIT" ]]
[[ -z "$(git status --short --untracked-files=no)" ]]
SITE_PACKAGES="$(/usr/bin/python3 -c 'import site; print(site.getusersitepackages())')"
EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"
/usr/bin/env -i PATH=/usr/bin:/bin PYTHONPATH="$SITE_PACKAGES" PYTHONNOUSERSITE=1 \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
  NUMEXPR_NUM_THREADS=8 BLIS_NUM_THREADS=8 PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  CUDA_VISIBLE_DEVICES= SLURM_JOB_ID="$SLURM_JOB_ID" SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
  PCB_GNN_EXECUTED_BATCH_SCRIPT="$EXECUTED_BATCH_SCRIPT" \
  /usr/bin/python3 -u code/experiments/proofs/diagnose_strict_e3_validation_replay_v1.py \
  --frozen-root "$PCB_GNN_E3_ROOT" --expected-diagnostic-commit "$PCB_GNN_DIAG_COMMIT" \
  --expected-protocol-sha256 "$PCB_GNN_E3_PROTOCOL_SHA256" \
  --expected-lock-sha256 "$PCB_GNN_E3_LOCK_SHA256" \
  --expected-task-receipt-sha256 "$PCB_GNN_E3_TASK_RECEIPT_SHA256" \
  --out "$PCB_GNN_DIAG_ROOT/results/corpus_v4/strict_e3_fem_v2/diagnostics/job_$SLURM_JOB_ID/result.json"
