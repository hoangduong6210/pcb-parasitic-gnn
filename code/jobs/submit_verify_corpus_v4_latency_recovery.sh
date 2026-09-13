#!/bin/bash
#SBATCH --job-name=pcb-v4-lat-replay
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

# Operational archive replay; the verifier authenticates both scientific roots.
: "${PCB_GNN_V4_EXECUTION_ROOT:?Set the absolute archive checkout}"
: "${PCB_GNN_V4_LATENCY_FINALIZER_JOB_ID:?Pin the successful finalizer job}"
[[ "$PCB_GNN_V4_LATENCY_FINALIZER_JOB_ID" =~ ^[0-9]+$ ]] || exit 2
cd "$PCB_GNN_V4_EXECUTION_ROOT"
export PCB_GNN_PYTHON=/usr/bin/python3
source "$PWD/code/jobs/slurm_job_env.sh"
export BLIS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONHASHSEED=0
export TZ=UTC LC_ALL=C.UTF-8 CUDA_VISIBLE_DEVICES=""

ANALYSIS_PATH="$PWD/results/corpus_v4/latency_fem_v2/final/job_${PCB_GNN_V4_LATENCY_FINALIZER_JOB_ID}/ANALYSIS_MANIFEST.json"
[[ -f "$ANALYSIS_PATH" && ! -L "$ANALYSIS_PATH" ]] || exit 2
ANALYSIS_SHA256=$(sha256sum "$ANALYSIS_PATH" | awk '{print $1}')
REPLAY_OPTIONS=()
case "${PCB_GNN_V4_ARCHIVE_ACTION:-create}" in
  create) ;;
  check) REPLAY_OPTIONS=(--check --require-git-tracked) ;;
  *) exit 2 ;;
esac

"$PCB_GNN_PYTHON" code/quality/verify_corpus_v4_latency_archive_v3.py \
  --protocol protocols/corpus_v4_latency_fem_v2_v1.json \
  --expected-protocol-sha256 6459fb716b79f0a95436691c9430e6505d5590d493f1e7e3ff191cbd602b4bf9 \
  --plan results/corpus_v4/latency_fem_v2/plan/v1/plan.json \
  --expected-plan-sha256 2ad12cdc11c356716e0cf0422f4e429a25bc1c094fe9a5ead4c7bc0ee0479cfb \
  --task-manifest results/corpus_v4/latency_fem_v2/plan/v1/task_manifest.jsonl \
  --expected-task-manifest-sha256 75ce9cebb34d4288077d38a33d418e5de391ebc94bd8aa3f10e03bee51631d04 \
  --execution-lock protocols/corpus_v4_latency_fem_v2_execution_lock_v1.json \
  --expected-execution-lock-sha256 b5ee0844267f261f7766bd1fb4265f8cf93da55f4194bcd67f81d38ada6061e5 \
  --expected-source-git-head 186ba2cbaf6a24bf62641eb2f2eba8ee3530dad6 \
  --finalizer-execution-lock protocols/corpus_v4_latency_fem_v2_finalizer_execution_lock_v1.json \
  --expected-finalizer-execution-lock-sha256 ecf8b64473a1e779072763e2ce12186abecd54483f4dc9d675fd7e2cb325457f \
  --expected-finalizer-source-git-head b2f2ac66ee61cbcd9149b80dfbf68269fcae3c08 \
  --accepted-set results/corpus_v4/latency_fem_v2/resume/round_00/accepted_artifact_set.json \
  --expected-accepted-set-sha256 90ba1f8d44a5db921a77fad50aec6b99171ef31b4e129fde59202a800ee6d221 \
  --analysis-manifest "$ANALYSIS_PATH" \
  --expected-analysis-manifest-sha256 "$ANALYSIS_SHA256" \
  --out "$PWD/results/corpus_v4/latency_fem_v2/ARCHIVE_MANIFEST.json" \
  "${REPLAY_OPTIONS[@]}"
