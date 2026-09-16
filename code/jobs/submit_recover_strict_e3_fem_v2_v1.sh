#!/bin/bash
#SBATCH --job-name=pcb-e3-recovery
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
: "${PCB_GNN_RECOVERY_ROOT:?Pin the recovery checkout}"
: "${PCB_GNN_RECOVERY_COMMIT:?Pin recovery source commit}"
: "${PCB_GNN_RECOVERY_PROTOCOL_SHA256:?Pin recovery protocol}"
: "${PCB_GNN_E3_ROOT:?Pin scientific execution or evidence checkout}"
: "${PCB_GNN_RECOVERY_STAGE:?Choose admit, finalize or verify}"
cd "$PCB_GNN_RECOVERY_ROOT"
[[ "$(git rev-parse HEAD)" == "$PCB_GNN_RECOVERY_COMMIT" ]]
[[ -z "$(git status --short --untracked-files=no)" ]]
ARGS=(--stage "$PCB_GNN_RECOVERY_STAGE" --frozen-root "$PCB_GNN_E3_ROOT"
  --expected-recovery-commit "$PCB_GNN_RECOVERY_COMMIT"
  --expected-recovery-protocol-sha256 "$PCB_GNN_RECOVERY_PROTOCOL_SHA256")
case "$PCB_GNN_RECOVERY_STAGE" in
  admit) ;;
  finalize|verify)
    : "${PCB_GNN_RECOVERY_ACCEPTED_SET:?Pin accepted-set path}"
    : "${PCB_GNN_RECOVERY_ACCEPTED_SHA256:?Pin accepted-set hash}"
    ARGS+=(--accepted-set "$PCB_GNN_RECOVERY_ACCEPTED_SET"
      --expected-accepted-set-sha256 "$PCB_GNN_RECOVERY_ACCEPTED_SHA256") ;;
  *) exit 2 ;;
esac
if [[ "$PCB_GNN_RECOVERY_STAGE" == verify ]]; then
  : "${PCB_GNN_RECOVERY_ANALYSIS_MANIFEST:?Pin analysis manifest path}"
  : "${PCB_GNN_RECOVERY_ANALYSIS_SHA256:?Pin analysis manifest hash}"
  ARGS+=(--analysis-manifest "$PCB_GNN_RECOVERY_ANALYSIS_MANIFEST"
    --expected-analysis-manifest-sha256 "$PCB_GNN_RECOVERY_ANALYSIS_SHA256")
  if [[ -n "${PCB_GNN_RECOVERY_ARCHIVE:-}" ]]; then
    ARGS+=(--archive "$PCB_GNN_RECOVERY_ARCHIVE" --check)
  fi
  if [[ "${PCB_GNN_RECOVERY_REQUIRE_GIT_TRACKED:-0}" == 1 ]]; then
    ARGS+=(--require-git-tracked)
  fi
fi
SITE_PACKAGES="$(/usr/bin/python3 -c 'import site; print(site.getusersitepackages())')"
EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}"
/usr/bin/env -i PATH=/usr/bin:/bin PYTHONPATH="$SITE_PACKAGES" PYTHONNOUSERSITE=1 \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
  NUMEXPR_NUM_THREADS=8 BLIS_NUM_THREADS=8 PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
  CUDA_VISIBLE_DEVICES= SLURM_JOB_ID="$SLURM_JOB_ID" SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
  PCB_GNN_EXECUTED_BATCH_SCRIPT="$EXECUTED_BATCH_SCRIPT" \
  /usr/bin/python3 -u code/experiments/proofs/recover_strict_e3_fem_v2_v1.py "${ARGS[@]}"
