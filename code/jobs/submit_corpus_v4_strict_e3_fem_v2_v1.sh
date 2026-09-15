#!/bin/bash
#SBATCH --job-name=pcb-v4-e3-femv2-v1
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --array=0-24%5
#SBATCH --no-requeue
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail

: "${PCB_GNN_E3_ROOT:?Pin the absolute clean execution checkout}"
: "${PCB_GNN_E3_PROTOCOL_SHA256:?Pin the strict-E3 protocol}"
: "${PCB_GNN_E3_LOCK_SHA256:?Pin the strict-E3 execution lock}"
: "${PCB_GNN_E3_SOURCE_COMMIT:?Pin the clean source commit}"
EXECUTION_ROOT="$(cd "$PCB_GNN_E3_ROOT" && pwd -P)"
cd "$EXECUTION_ROOT"
[[ "$(git rev-parse HEAD)" == "$PCB_GNN_E3_SOURCE_COMMIT" ]]
[[ -z "$(git status --short --untracked-files=no)" ]]
[[ -z "$(git status --short --untracked-files=all -- code protocols requirements-proof.txt)" ]]
[[ "$SLURM_ARRAY_TASK_ID" =~ ^[0-9]+$ && "$SLURM_ARRAY_TASK_ID" -le 24 ]]
SITE_PACKAGES="$(/usr/bin/python3 -c 'import site; print(site.getusersitepackages())')"
[[ -d "$SITE_PACKAGES" ]]
[[ "$(sha256sum /usr/bin/bwrap | cut -d' ' -f1)" == 9dba99a1fa3be3b0d3e5cb7d6d297742b56a3b1749465f520503c651b38d99aa ]]
EXECUTED_BATCH_SHA256="$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)"
[[ "$EXECUTED_BATCH_SHA256" == "$(sha256sum code/jobs/submit_corpus_v4_strict_e3_fem_v2_v1.sh | cut -d' ' -f1)" ]]

SPLIT_SEED=$((40 + SLURM_ARRAY_TASK_ID / 5))
TASK_PADDED="$(printf '%02d' "$SLURM_ARRAY_TASK_ID")"
PLAN_ROOT="$EXECUTION_ROOT/results/corpus_v4/accuracy_v3/plan/v1"
TASK_RELATIVE="results/corpus_v4/strict_e3_fem_v2/jobs/job_${SLURM_ARRAY_JOB_ID}/task_${TASK_PADDED}"
PROBE_ARGS=()
if [[ "${PCB_GNN_E3_PROBE_ONLY:-false}" == true ]]; then
  [[ "$SLURM_ARRAY_TASK_ID" == 0 && "$SLURM_ARRAY_TASK_COUNT" == 1 ]]
  TASK_RELATIVE="results/corpus_v4/strict_e3_fem_v2/probes/job_${SLURM_ARRAY_JOB_ID}/task_${TASK_PADDED}"
  PROBE_ARGS=(--probe-only)
fi
[[ ! -e "$EXECUTION_ROOT/$TASK_RELATIVE" && ! -L "$EXECUTION_ROOT/$TASK_RELATIVE" ]]
mkdir -p "$EXECUTION_ROOT/$TASK_RELATIVE"

/usr/bin/bwrap \
  --unshare-user --unshare-pid --unshare-ipc --unshare-uts --die-with-parent \
  --ro-bind /usr /usr \
  --symlink usr/bin /bin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --proc /proc --dev /dev --tmpfs /tmp \
  --dir /etc --ro-bind /etc/slurm /etc/slurm --ro-bind /etc/hosts /etc/hosts \
  --ro-bind /etc/passwd /etc/passwd --ro-bind /etc/group /etc/group \
  --ro-bind /etc/nsswitch.conf /etc/nsswitch.conf --ro-bind /etc/resolv.conf /etc/resolv.conf \
  --dir /run --ro-bind /run/munge /run/munge --ro-bind /run/slurm /run/slurm \
  --dir /var --dir /var/run --ro-bind /run/munge /var/run/munge \
  --dir /var/spool --dir /var/spool/slurmd \
  --ro-bind /var/spool/slurmd/conf-cache /var/spool/slurmd/conf-cache \
  --dir /opt --dir /opt/pcb-python \
  --ro-bind "$SITE_PACKAGES" /opt/pcb-python/site-packages \
  --dir /workspace \
  --ro-bind "$EXECUTION_ROOT/code" /workspace/code \
  --ro-bind "$EXECUTION_ROOT/protocols" /workspace/protocols \
  --ro-bind "$EXECUTION_ROOT/requirements-proof.txt" /workspace/requirements-proof.txt \
  --dir /workspace/results --dir /workspace/results/corpus_v4 \
  --dir /workspace/results/corpus_v4/accuracy_v3 \
  --dir /workspace/results/corpus_v4/accuracy_v3/plan \
  --dir /workspace/results/corpus_v4/accuracy_v3/plan/v1 \
  --ro-bind "$PLAN_ROOT/plan.json" /workspace/results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --ro-bind "$PLAN_ROOT/task_manifest.jsonl" /workspace/results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --ro-bind "$PLAN_ROOT/training_split_${SPLIT_SEED}.jsonl" "/workspace/results/corpus_v4/accuracy_v3/plan/v1/training_split_${SPLIT_SEED}.jsonl" \
  --dir /workspace/results/corpus_v4/strict_e3_fem_v2 \
  --dir "/workspace/$(dirname "$TASK_RELATIVE")" \
  --bind "$EXECUTION_ROOT/$TASK_RELATIVE" "/workspace/$TASK_RELATIVE" \
  --chdir /workspace -- /usr/bin/env -i \
  PATH=/usr/bin:/bin PYTHONPATH=/opt/pcb-python/site-packages PYTHONNOUSERSITE=1 \
  TMPDIR=/tmp OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 \
  NUMEXPR_NUM_THREADS=8 BLIS_NUM_THREADS=8 PYTHONHASHSEED=0 \
  TZ=UTC LC_ALL=C.UTF-8 CUDA_VISIBLE_DEVICES= \
  SLURM_ARRAY_JOB_ID="$SLURM_ARRAY_JOB_ID" SLURM_ARRAY_TASK_ID="$SLURM_ARRAY_TASK_ID" \
  SLURM_ARRAY_TASK_COUNT="$SLURM_ARRAY_TASK_COUNT" SLURM_ARRAY_TASK_MIN="$SLURM_ARRAY_TASK_MIN" \
  SLURM_ARRAY_TASK_MAX="$SLURM_ARRAY_TASK_MAX" SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
  SLURM_JOB_ID="$SLURM_JOB_ID" SLURM_JOB_PARTITION="$SLURM_JOB_PARTITION" \
  SLURM_MEM_PER_NODE="$SLURM_MEM_PER_NODE" \
  PCB_GNN_EXECUTED_BATCH_SCRIPT=/workspace/code/jobs/submit_corpus_v4_strict_e3_fem_v2_v1.sh \
  PCB_GNN_EXECUTED_BATCH_SHA256="$EXECUTED_BATCH_SHA256" \
  PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_COMMIT="$PCB_GNN_E3_SOURCE_COMMIT" \
  PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_CLEAN=true PCB_GNN_V4_ACCURACY_V3_SANDBOX_ACTIVE=true \
  /usr/bin/python3 -u code/experiments/proofs/corpus_v4_strict_e3_fem_v2_v1.py train \
  --protocol protocols/corpus_v4_strict_e3_fem_v2_v1.json \
  --expected-protocol-sha256 "$PCB_GNN_E3_PROTOCOL_SHA256" \
  --execution-lock protocols/corpus_v4_strict_e3_fem_v2_execution_lock_v1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_E3_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_E3_SOURCE_COMMIT" \
  --output-root "$TASK_RELATIVE" "${PROBE_ARGS[@]}"
