#!/bin/bash
# Submit the geometry-v3 evidence DAG with scheduler-enforced dependencies.
#
# Usage:
#   FASTHENRY_BIN=/absolute/path/to/fasthenry \
#     bash code/jobs/run_v3_pipeline.sh --account <slurm-account>
set -euo pipefail

ACCOUNT=""
while (($#)); do
    case "$1" in
        --account) ACCOUNT="${2:?missing account}"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
: "${ACCOUNT:?Pass --account <slurm-account>}"
: "${FASTHENRY_BIN:?Set FASTHENRY_BIN to an executable built from the external solver source}"
[[ -x "$FASTHENRY_BIN" ]] || { echo "FASTHENRY_BIN is not executable" >&2; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
[[ -z "$(git status --short --untracked-files=no)" ]] || {
    echo "Refusing pipeline submission from a dirty tracked worktree" >&2
    exit 2
}
mkdir -p logs

submit() {
    sbatch --parsable -A "$ACCOUNT" "$@"
}

audit_id="$(submit code/jobs/submit_legacy_v2_geometry_audit.sh)"
preflight_id="$(submit --export="ALL,FASTHENRY_BIN=$FASTHENRY_BIN" \
    code/jobs/submit_corpus_v3_preflight.sh)"
labels_id="$(submit --dependency="afterok:$preflight_id" \
    --export="ALL,FASTHENRY_BIN=$FASTHENRY_BIN" \
    code/jobs/submit_corpus_v3_field_labels.sh)"
corpus_final_id="$(submit --dependency="afterok:$labels_id" \
    --export="ALL,PCB_GNN_V3_SOURCE_ARRAY_JOB_ID=$labels_id" \
    code/jobs/submit_finalize_corpus_v3.sh)"
corpus_dir="$ROOT/results/corpus_v3/final/job_$corpus_final_id"
accuracy_id="$(submit --dependency="afterok:$corpus_final_id" \
    --export="ALL,PCB_GNN_V3_CORPUS_DIR=$corpus_dir" \
    code/jobs/submit_corpus_v3_accuracy.sh)"
strict_e3_id="$(submit --dependency="afterok:$corpus_final_id" \
    --export="ALL,PCB_GNN_V3_CORPUS_DIR=$corpus_dir" \
    code/jobs/submit_corpus_v3_strict_e3.sh)"
trees_id="$(submit --dependency="afterok:$corpus_final_id" \
    --export="ALL,PCB_GNN_V3_CORPUS_DIR=$corpus_dir" \
    code/jobs/submit_corpus_v3_trees.sh)"
lateral_id="$(submit --dependency="afterok:$corpus_final_id" \
    --export="ALL,FASTHENRY_BIN=$FASTHENRY_BIN" \
    code/jobs/submit_corpus_v3_lateral_labels.sh)"
accuracy_final_id="$(submit --dependency="afterok:$accuracy_id" \
    --export="ALL,PCB_GNN_V3_ACCURACY_ARRAY_JOB_ID=$accuracy_id" \
    code/jobs/submit_finalize_corpus_v3_accuracy.sh)"
strict_e3_final_id="$(submit --dependency="afterok:$strict_e3_id" \
    --export="ALL,PCB_GNN_V3_STRICT_E3_ARRAY_JOB_ID=$strict_e3_id" \
    code/jobs/submit_finalize_corpus_v3_strict_e3.sh)"
accuracy_final_path="$ROOT/results/corpus_v3/accuracy/final/job_$accuracy_final_id/results_corpus_v3_accuracy.json"
trees_final_id="$(submit --dependency="afterok:$trees_id:$accuracy_final_id" \
    --export="ALL,PCB_GNN_V3_TREES_ARRAY_JOB_ID=$trees_id,PCB_GNN_V3_ACCURACY_FINAL=$accuracy_final_path" \
    code/jobs/submit_finalize_corpus_v3_trees.sh)"
lateral_final_id="$(submit --dependency="afterok:$lateral_id" \
    --export="ALL,PCB_GNN_V3_LATERAL_ARRAY_JOB_ID=$lateral_id" \
    code/jobs/submit_finalize_corpus_v3_lateral.sh)"
bundle_dir="$ROOT/results/corpus_v3/accuracy/jobs/job_$accuracy_id/inference_bundle"
latency_id="$(submit --dependency="afterok:$accuracy_final_id" \
    --export="ALL,FASTHENRY_BIN=$FASTHENRY_BIN,PCB_GNN_V3_CORPUS_DIR=$corpus_dir,PCB_GNN_V3_BUNDLE_DIR=$bundle_dir" \
    code/jobs/submit_corpus_v3_latency.sh)"

printf '%s\n' \
    "legacy_audit=$audit_id" \
    "v3_preflight=$preflight_id" \
    "v3_labels=$labels_id" \
    "v3_corpus_final=$corpus_final_id" \
    "v3_accuracy=$accuracy_id" \
    "v3_accuracy_final=$accuracy_final_id" \
    "v3_strict_e3=$strict_e3_id" \
    "v3_strict_e3_final=$strict_e3_final_id" \
    "v3_trees=$trees_id" \
    "v3_trees_final=$trees_final_id" \
    "v3_lateral_labels=$lateral_id" \
    "v3_lateral_final=$lateral_final_id" \
    "v3_paired_latency=$latency_id"
