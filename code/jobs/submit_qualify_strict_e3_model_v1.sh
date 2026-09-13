#!/bin/bash
#SBATCH --job-name=pcb-e3-model-qual
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:10:00
#SBATCH --no-requeue
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
: "${PCB_E3_QUAL_ROOT:?Set the clean immutable qualification checkout}"
: "${PCB_E3_QUAL_COMMIT:?Pin its commit}"
: "${PCB_E3_QUAL_PROTOCOL_SHA256:?Pin the qualification protocol}"
cd "$PCB_E3_QUAL_ROOT"
SITE_PACKAGES="$(/usr/bin/python3 -I -c 'import site; print(site.getusersitepackages())')"
[[ -d "$SITE_PACKAGES" ]]
BATCH_SHA256="$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)"
/usr/bin/env -i PATH=/usr/bin:/bin PYTHONPATH="$SITE_PACKAGES" PYTHONNOUSERSITE=1 \
  OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  NUMEXPR_NUM_THREADS=2 BLIS_NUM_THREADS=2 PYTHONHASHSEED=0 \
  CUDA_VISIBLE_DEVICES= TZ=UTC LC_ALL=C.UTF-8 \
  SLURM_JOB_ID="$SLURM_JOB_ID" SLURM_ARRAY_JOB_ID="${SLURM_ARRAY_JOB_ID:-}" \
  PCB_E3_EXECUTED_BATCH_SHA256="$BATCH_SHA256" \
  /usr/bin/python3 -u code/experiments/proofs/qualify_strict_e3_model_v1.py \
  --expected-source-commit "$PCB_E3_QUAL_COMMIT" \
  --expected-protocol-sha256 "$PCB_E3_QUAL_PROTOCOL_SHA256"
