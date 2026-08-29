#!/bin/bash
#SBATCH --job-name=pcb-v4-accuracy-v3
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --array=0-24%5
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
# Explicit public-series identity retained for release contract: --series corpus_v4
: "${PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT:?Pin the absolute clean execution checkout}"
EXECUTION_ROOT="$(cd "$PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT" && pwd -P)"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$EXECUTION_ROOT/code/jobs/slurm_job_env.sh"
[[ "$PCB_GNN_ROOT" == "$EXECUTION_ROOT" ]] || {
  echo "Resolved job root differs from PCB_GNN_V4_ACCURACY_V3_EXECUTION_ROOT" >&2
  exit 2
}
cd "$PCB_GNN_ROOT"

: "${PCB_GNN_V4_ACCURACY_V3_PROTOCOL_SHA256:?Pin the protocol SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V3_PLAN_SHA256:?Pin the plan SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V3_TASK_MANIFEST_SHA256:?Pin the task-manifest SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V3_EXECUTION_LOCK_SHA256:?Pin the execution-lock SHA-256}"
: "${PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT:?Pin the exact clean Git commit}"

HOST_HEAD="$(git rev-parse HEAD)"
[[ "$HOST_HEAD" == "$PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT" ]] || {
  echo "Host execution commit differs from the external trust root" >&2
  exit 2
}
[[ -z "$(git status --short --untracked-files=no)" ]] || {
  echo "Host execution checkout has tracked modifications" >&2
  exit 2
}
[[ -z "$(git status --short --untracked-files=all -- code protocols requirements-proof.txt)" ]] || {
  echo "Host execution checkout has untracked source files" >&2
  exit 2
}

SITE_PACKAGES="$(/usr/bin/python3 -c 'import site; print(site.getusersitepackages())')"
[[ -d "$SITE_PACKAGES" ]] || {
  echo "Pinned Python site-packages directory is unavailable" >&2
  exit 2
}
[[ "$(sha256sum /usr/bin/bwrap | cut -d' ' -f1)" == \
  "9dba99a1fa3be3b0d3e5cb7d6d297742b56a3b1749465f520503c651b38d99aa" ]] || {
  echo "Bubblewrap executable differs from the frozen protocol" >&2
  exit 2
}

SPLIT_INDEX=$((SLURM_ARRAY_TASK_ID / 5))
SPLIT_SEEDS=(40 41 42 43 44)
SPLIT_SEED="${SPLIT_SEEDS[$SPLIT_INDEX]}"
PLAN_ROOT="$EXECUTION_ROOT/results/corpus_v4/accuracy_v3/plan/v1"
TRAINING_INPUT="$PLAN_ROOT/training_split_${SPLIT_SEED}.jsonl"
OUTPUT_ROOT="$EXECUTION_ROOT/results/corpus_v4/accuracy_v3/jobs"
mkdir -p "$OUTPUT_ROOT"
[[ -f "$TRAINING_INPUT" ]] || {
  echo "Split-scoped training input is unavailable" >&2
  exit 2
}

RETRY_ARGS=()
RETRY_MOUNTS=()
PROBE_ARGS=()
PROBE_MOUNTS=()
if [[ "${PCB_GNN_V4_ACCURACY_V3_SANDBOX_PROBE_ONLY:-false}" == "true" ]]; then
  [[ "$SLURM_ARRAY_TASK_ID" == "0" && "$SLURM_ARRAY_TASK_COUNT" == "1" ]] || {
    echo "Sandbox preflight must be submitted as the singleton array 0%5" >&2
    exit 2
  }
  PROBE_ROOT="$EXECUTION_ROOT/results/corpus_v4/accuracy_v3/sandbox_probes"
  mkdir -p "$PROBE_ROOT"
  PROBE_ARGS=(--sandbox-probe-only)
  PROBE_MOUNTS=(
    --dir /workspace/results/corpus_v4/accuracy_v3/sandbox_probes
    --bind "$PROBE_ROOT" /workspace/results/corpus_v4/accuracy_v3/sandbox_probes
  )
fi
if [[ -n "${PCB_GNN_V4_ACCURACY_V3_PENDING_SET:-}" || -n "${PCB_GNN_V4_ACCURACY_V3_PENDING_SET_SHA256:-}" ]]; then
  : "${PCB_GNN_V4_ACCURACY_V3_PENDING_SET:?Set the repository-relative pending-set path}"
  : "${PCB_GNN_V4_ACCURACY_V3_PENDING_SET_SHA256:?Pin the pending-set SHA-256}"
  RETRY_ARGS=(
    --pending-set "$PCB_GNN_V4_ACCURACY_V3_PENDING_SET"
    --expected-pending-set-sha256 "$PCB_GNN_V4_ACCURACY_V3_PENDING_SET_SHA256"
  )
  RETRY_ROOT="$EXECUTION_ROOT/results/corpus_v4/accuracy_v3/resume"
  [[ -d "$RETRY_ROOT" ]] || {
    echo "Retry resume root is unavailable" >&2
    exit 2
  }
  RETRY_MOUNTS=(
    --dir /workspace/results/corpus_v4/accuracy_v3/resume
    --ro-bind "$RETRY_ROOT" /workspace/results/corpus_v4/accuracy_v3/resume
  )
fi

/usr/bin/bwrap \
  --unshare-user \
  --unshare-pid \
  --unshare-ipc \
  --unshare-uts \
  --die-with-parent \
  --ro-bind /usr /usr \
  --symlink usr/bin /bin \
  --symlink usr/lib /lib \
  --symlink usr/lib64 /lib64 \
  --proc /proc \
  --dev /dev \
  --tmpfs /tmp \
  --dir /etc \
  --ro-bind /etc/slurm /etc/slurm \
  --ro-bind /etc/hosts /etc/hosts \
  --ro-bind /etc/nsswitch.conf /etc/nsswitch.conf \
  --ro-bind /etc/resolv.conf /etc/resolv.conf \
  --dir /run \
  --ro-bind /run/munge /run/munge \
  --dir /opt \
  --dir /opt/pcb-python \
  --ro-bind "$SITE_PACKAGES" /opt/pcb-python/site-packages \
  --dir /workspace \
  --ro-bind "$EXECUTION_ROOT/code" /workspace/code \
  --ro-bind "$EXECUTION_ROOT/protocols" /workspace/protocols \
  --ro-bind "$EXECUTION_ROOT/requirements-proof.txt" /workspace/requirements-proof.txt \
  --dir /workspace/results \
  --dir /workspace/results/corpus_v4 \
  --dir /workspace/results/corpus_v4/accuracy_v3 \
  --dir /workspace/results/corpus_v4/accuracy_v3/plan \
  --dir /workspace/results/corpus_v4/accuracy_v3/plan/v1 \
  --ro-bind "$PLAN_ROOT/plan.json" /workspace/results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --ro-bind "$PLAN_ROOT/task_manifest.jsonl" /workspace/results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --ro-bind "$TRAINING_INPUT" "/workspace/results/corpus_v4/accuracy_v3/plan/v1/training_split_${SPLIT_SEED}.jsonl" \
  --dir /workspace/results/corpus_v4/accuracy_v3/jobs \
  --bind "$OUTPUT_ROOT" /workspace/results/corpus_v4/accuracy_v3/jobs \
  "${RETRY_MOUNTS[@]}" \
  "${PROBE_MOUNTS[@]}" \
  --chdir /workspace \
  -- \
  /usr/bin/env -i \
  PATH=/usr/bin:/bin \
  PYTHONPATH=/opt/pcb-python/site-packages \
  PYTHONNOUSERSITE=1 \
  HOME=/nonexistent \
  TMPDIR=/tmp \
  OMP_NUM_THREADS=8 \
  MKL_NUM_THREADS=8 \
  OPENBLAS_NUM_THREADS=8 \
  NUMEXPR_NUM_THREADS=8 \
  PYTHONHASHSEED=0 \
  TZ=UTC \
  LC_ALL=C.UTF-8 \
  CUDA_VISIBLE_DEVICES= \
  SLURM_ARRAY_JOB_ID="$SLURM_ARRAY_JOB_ID" \
  SLURM_ARRAY_TASK_COUNT="$SLURM_ARRAY_TASK_COUNT" \
  SLURM_ARRAY_TASK_ID="$SLURM_ARRAY_TASK_ID" \
  SLURM_ARRAY_TASK_MAX="$SLURM_ARRAY_TASK_MAX" \
  SLURM_ARRAY_TASK_MIN="$SLURM_ARRAY_TASK_MIN" \
  SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
  SLURM_JOB_ID="$SLURM_JOB_ID" \
  SLURM_JOB_PARTITION="$SLURM_JOB_PARTITION" \
  SLURM_MEM_PER_NODE="$SLURM_MEM_PER_NODE" \
  PCB_GNN_EXECUTED_BATCH_SCRIPT=/workspace/code/jobs/submit_corpus_v4_accuracy_v3.sh \
  PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_COMMIT="$HOST_HEAD" \
  PCB_GNN_V4_ACCURACY_V3_HOST_SOURCE_CLEAN=true \
  PCB_GNN_V4_ACCURACY_V3_SANDBOX_ACTIVE=true \
  /usr/bin/python3 -u /workspace/code/experiments/proofs/run_corpus_v4_accuracy_task_v3.py \
  --protocol protocols/corpus_v4_accuracy_v3.json \
  --expected-protocol-sha256 "$PCB_GNN_V4_ACCURACY_V3_PROTOCOL_SHA256" \
  --plan results/corpus_v4/accuracy_v3/plan/v1/plan.json \
  --expected-plan-sha256 "$PCB_GNN_V4_ACCURACY_V3_PLAN_SHA256" \
  --task-manifest results/corpus_v4/accuracy_v3/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 "$PCB_GNN_V4_ACCURACY_V3_TASK_MANIFEST_SHA256" \
  --execution-lock protocols/corpus_v4_accuracy_execution_lock_v3r1.json \
  --expected-execution-lock-sha256 "$PCB_GNN_V4_ACCURACY_V3_EXECUTION_LOCK_SHA256" \
  --expected-source-git-head "$PCB_GNN_V4_ACCURACY_V3_SOURCE_COMMIT" \
  "${RETRY_ARGS[@]}" \
  "${PROBE_ARGS[@]}" \
  --output-root results/corpus_v4/accuracy_v3/jobs
